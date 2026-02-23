# Diretivas

**Diretivas** representam tarefas assíncronas com semântica **at-least-once**.
Efeitos colaterais como reserva de estoque, captura de pagamento e notificações
são modelados como diretivas — nunca executados inline dentro do commit.

---

## O que é uma Diretiva?

Uma Diretiva é uma linha no banco que representa uma unidade de trabalho:

1. É **criada** após uma ação (modify, commit, mudança de status)
2. É **processada** por um handler registrado no Registry
3. Pode ser executada **mais de uma vez** — handlers devem ser idempotentes

```
Session ──modify──► Directive (stock.hold)    ──handler──► Holds criados
Session ──commit──► Order ──► Directive (stock.commit)  ──handler──► Estoque decrementado
                            ► Directive (payment.capture) ──handler──► Pagamento capturado
```

---

## Model

```python
class Directive(models.Model):
    topic        = models.CharField(max_length=64, db_index=True)
    status       = models.CharField(default="queued", db_index=True)  # ver ciclo abaixo
    payload      = models.JSONField(default=dict, blank=True)

    attempts     = models.IntegerField(default=0)
    available_at = models.DateTimeField(default=timezone.now, db_index=True)
    last_error   = models.TextField(blank=True, default="")

    created_at   = models.DateTimeField(auto_now_add=True)
    started_at   = models.DateTimeField(null=True, blank=True)
    updated_at   = models.DateTimeField(auto_now=True)
```

### Campos — razão de cada um

| Campo | Por que existe |
|-------|----------------|
| `topic` | Chave de roteamento para o handler (`"stock.hold"`, `"payment.capture"`) |
| `status` | Ciclo de vida: `queued → running → done \| failed` |
| `payload` | Dados específicos do handler (JSON). A Directive inteira é a *message*; `payload` é o conteúdo que ela carrega |
| `attempts` | Quantas vezes foi tentada. Útil para monitoramento |
| `available_at` | Permite agendar execução futura (*deferred execution*) |
| `last_error` | Texto do último erro. Visível no admin para diagnóstico |
| `created_at` | Quando foi criada (auto) |
| `started_at` | Quando começou a executar. Permite calcular duração: `updated_at - started_at` |
| `updated_at` | Última modificação (auto). Quando `status == done`, equivale a `completed_at` |

### Decisões de design

**Por que `queued/running/done/failed` e não `pending/completed`?**
`queued` é mais preciso — diz que está *numa fila*, não apenas "pendente" (que poderia
significar aprovação humana). `done` é mais curto e direto que `completed`.

**Por que não existe campo `result`?**
Handlers produzem side-effects em models especializados (holds, order events, etc.),
não retornam um JSON genérico. Cada resultado tem tipagem e rastreabilidade própria.

**Por que não existe FK para Session/Order?**
O `payload` JSON com `session_key`/`order_ref` é mais flexível e desacoplado.
Diretivas futuras podem referenciar qualquer entidade sem alterar o schema.

### Ciclo de vida

```
    ┌──────────────────────────────────────┐
    │                                      │
    ▼                                      │
 queued ──► running ──► done               │
               │                           │
               └──► failed ──(re-executar)─┘
```

- `queued`: criada, aguardando processamento
- `running`: handler em execução (`started_at` é populado neste momento)
- `done`: concluída com sucesso
- `failed`: erro. Pode ser re-executada via admin (volta para `running`)

---

## Tópicos existentes

| Topic | Propósito | Criado quando |
|-------|-----------|---------------|
| `stock.hold` | Reservar estoque temporariamente | Session modificada (`required_checks_on_commit`) |
| `stock.commit` | Confirmar holds (decrementar estoque) | Order commitada (`post_commit_directives`) |
| `payment.capture` | Capturar pagamento autorizado | Order commitada (`post_commit_directives`) |
| `payment.refund` | Processar reembolso | Programaticamente |

---

## Como Diretivas são criadas

### Via Channel Config (automático)

O `Channel.config` define quais diretivas são enfileiradas automaticamente:

```json
{
  "required_checks_on_commit": ["stock"],
  "checks": {
    "stock": {
      "directive_topic": "stock.hold",
      "label": "Verificar Estoque"
    }
  },
  "post_commit_directives": ["stock.commit", "payment.capture"]
}
```

- **`required_checks_on_commit`**: diretivas criadas ao modificar a session (pré-commit)
- **`post_commit_directives`**: diretivas criadas após o commit gerar a Order

### Programaticamente

```python
from omniman.models import Directive

Directive.objects.create(
    topic="custom.sync_erp",
    payload={"order_ref": order.ref},
)
```

---

## Handlers

Handlers processam diretivas. Seguem o protocolo `DirectiveHandler`:

```python
# omniman/registry.py

class DirectiveHandler(Protocol):
    topic: str

    def handle(self, *, message: Any, ctx: dict) -> None:
        """Processa a diretiva. Pode fazer IO."""
        ...
```

> **Atenção**: `message` e `ctx` são **keyword-only** (`*`).
> O parâmetro `message` é a instância `Directive` inteira (não apenas o payload).

### Criando um handler

```python
class StockCommitHandler:
    topic = "stock.commit"

    def handle(self, *, message, ctx):
        payload = message.payload
        order_ref = payload["order_ref"]
        holds = payload.get("holds", [])

        for hold in holds:
            # Idempotência: verifica se já foi processado
            if self._is_fulfilled(hold["hold_id"]):
                continue
            self._fulfill(hold)

        # Marca como done
        message.status = "done"
        message.last_error = ""
        message.save(update_fields=["status", "last_error", "updated_at"])
```

### Registrando no `apps.py`

```python
class MyAppConfig(AppConfig):
    def ready(self):
        from omniman import registry
        from .handlers import StockCommitHandler

        registry.register_directive_handler(StockCommitHandler())
```

> Um topic só pode ter **um** handler. Registrar duplicado levanta `ValueError`.

---

## Semântica At-Least-Once

**Invariante I6**: Handlers devem ser idempotentes — podem executar múltiplas vezes.

### Por que múltiplas execuções?

- Worker caiu após processar, antes de marcar `done`
- Operador clicou "Executar agora" duas vezes
- Re-execução manual de diretiva `failed`

### Padrão de idempotência

```python
class PaymentCaptureHandler:
    topic = "payment.capture"

    def handle(self, *, message, ctx):
        intent_id = message.payload["payment_intent_id"]

        # Já capturado? Sai sem erro.
        if OrderEvent.objects.filter(
            order__ref=message.payload["order_ref"],
            type="payment.captured",
        ).exists():
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        # Captura via gateway
        result = gateway.capture(intent_id)

        # Registra evento (rastreável, tipado)
        OrderEvent.objects.create(
            order_id=...,
            type="payment.captured",
            data={"capture_id": result.id},
        )

        message.status = "done"
        message.save(update_fields=["status", "last_error", "updated_at"])
```

---

## Processamento

### a) Via Admin (manual / operador)

O admin oferece 3 formas de executar diretivas:

| Local | Ação | Quando usar |
|-------|------|-------------|
| Detalhe da diretiva | Botão **"Executar agora"** | Executar uma diretiva específica |
| Listagem de diretivas | Action em bulk **"Executar agora"** | Executar várias de uma vez |
| Detalhe da session | Botão **"Confirmar"** | Executa diretivas pós-commit inline automaticamente |

Diretivas com status `queued` ou `failed` podem ser executadas.
A execução inline no commit usa `select_for_update(skip_locked=True)` para evitar
race condition com workers de background.

### b) Via Management Command (automático / background)

```bash
# Execução única — ideal para cron
python manage.py process_directives

# Worker contínuo — ideal para supervisor/systemd
python manage.py process_directives --watch --interval 2

# Filtrar por tópico
python manage.py process_directives --topic stock.hold --topic stock.commit

# Limitar quantidade por ciclo
python manage.py process_directives --limit 100
```

**Opções:**

| Flag | Default | Descrição |
|------|---------|-----------|
| `--topic` | todos registrados | Filtrar por tópico (pode repetir) |
| `--limit` | 50 | Máximo de diretivas por ciclo |
| `--watch` | off | Loop contínuo (worker) |
| `--interval` | 2.0s | Intervalo entre ciclos no modo `--watch` |

### Setup de produção recomendado

```ini
# Worker contínuo (supervisor / systemd)
[program:omniman-directives]
command=python manage.py process_directives --watch --interval 2
autostart=true
autorestart=true
```

```cron
# Rede de segurança — se o worker cair, o cron garante processamento
*/5 * * * *  python manage.py process_directives --limit 100

# Manutenção diária
0 3 * * *  python manage.py cleanup_idempotency_keys
0 3 * * *  python manage.py release_expired_holds
```

A combinação worker + cron garante que **nenhuma diretiva fica órfã**.

---

## Tratamento de falhas

Quando um handler lança exceção:

1. `status` é marcado como `failed`
2. `last_error` recebe a mensagem do erro
3. `attempts` já foi incrementado

Diretivas `failed` ficam visíveis no admin e podem ser re-executadas manualmente.

### Monitoramento

```python
from datetime import timedelta
from django.utils import timezone
from omniman.models import Directive

# Diretivas falhadas nas últimas 24h
failed = Directive.objects.filter(
    status="failed",
    updated_at__gte=timezone.now() - timedelta(days=1),
)

for d in failed:
    print(f"#{d.pk} {d.topic}: {d.last_error}")

# Diretivas travadas (running há mais de 5 min) — possível worker crash
stuck = Directive.objects.filter(
    status="running",
    started_at__lte=timezone.now() - timedelta(minutes=5),
)
```

---

## Boas práticas

1. **Sempre idempotente**: verifique se o trabalho já foi feito antes de executar
2. **Side-effects em models tipados**: use `OrderEvent`, `Hold`, etc. — não um campo `result` genérico
3. **Um handler, uma responsabilidade**: cada topic faz uma coisa
4. **Handler marca `done`**: se o handler não marcar status, o caller faz fallback para `done`
5. **Transações curtas**: não segure locks longos dentro do handler
6. **Log**: registre o que aconteceu para diagnóstico (`logging.getLogger(__name__)`)
