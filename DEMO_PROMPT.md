# Django Omniman Demo - Prompt de Geração

> **Objetivo**: Criar uma demo completa e funcional do ecossistema Django Micro-* com foco em operações de varejo/food service.

---

## VISÃO GERAL DO PROJETO

Crie o repositório `django-omniman-demo` - uma aplicação Django completa demonstrando integração entre:

- **Django Omniman** - Hub de pedidos omnichannel
- **Django Stockman** - Micro-inventário
- **Django Craftsman** - Micro-MRP (produção)
- **Django Goodsman** - Micro-PIM (catálogo de produtos) *(a desenvolver)*
- **Django Merchantman** - Micro-CRM (clientes e fidelidade) *(a desenvolver)*

### Cenário de Negócio: Cafeteria Artesanal

Uma cafeteria que:
1. Vende pelo balcão (PDV)
2. Tem e-commerce para delivery
3. Recebe pedidos do iFood
4. Aceita Cartão (Stripe) e Pix (Efi)
5. Produz alguns itens internamente (pães, bolos)
6. Gerencia estoque de insumos e produtos acabados

---

## ESTRUTURA DO PROJETO

```
django-omniman-demo/
├── demo/
│   ├── settings/
│   │   ├── base.py
│   │   ├── development.py
│   │   └── production.py
│   ├── urls.py
│   └── wsgi.py
│
├── apps/
│   ├── core/                    # Configurações compartilhadas
│   │   ├── models.py           # Tenant, Settings
│   │   └── middleware.py       # Multi-tenant (futuro)
│   │
│   ├── catalog/                 # Catálogo de Produtos (usa Goodsman)
│   │   ├── models.py           # Product, Category, Variant
│   │   ├── admin.py
│   │   └── api/
│   │
│   ├── inventory/               # Estoque (usa Stockman)
│   │   ├── adapters.py         # StockmanAdapter implements StockBackend
│   │   └── handlers.py         # Directive handlers
│   │
│   ├── production/              # Produção (usa Craftsman)
│   │   ├── adapters.py         # CraftsmanAdapter
│   │   └── signals.py          # Auto-produção quando estoque baixo
│   │
│   ├── customers/               # Clientes (usa Merchantman)
│   │   ├── models.py           # Customer, LoyaltyPoints
│   │   └── api/
│   │
│   ├── pos/                     # Ponto de Venda Web
│   │   ├── views.py            # SPA views
│   │   ├── templates/
│   │   │   └── pos/
│   │   │       ├── terminal.html
│   │   │       └── components/
│   │   └── static/
│   │       └── pos/
│   │           ├── js/
│   │           └── css/
│   │
│   ├── shop/                    # E-commerce
│   │   ├── views.py
│   │   ├── templates/
│   │   │   └── shop/
│   │   │       ├── home.html
│   │   │       ├── product.html
│   │   │       ├── cart.html
│   │   │       └── checkout.html
│   │   └── static/
│   │
│   ├── bridges/                 # Integrações Externas
│   │   ├── ifood/
│   │   │   ├── client.py       # API client
│   │   │   ├── webhooks.py     # Webhook handlers
│   │   │   ├── bridge.py       # ChannelBridge
│   │   │   └── mappers.py      # iFood → Omniman
│   │   └── __init__.py
│   │
│   └── payments/                # Pagamentos
│       ├── adapters/
│       │   ├── stripe_adapter.py
│       │   └── efi_adapter.py
│       ├── handlers.py         # Directive handlers
│       ├── webhooks.py         # Stripe/Efi webhooks
│       └── api/
│
├── templates/
│   ├── base.html
│   ├── admin/
│   └── components/
│
├── static/
│   ├── css/
│   ├── js/
│   └── images/
│
├── docker/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── docker-compose.prod.yml
│
├── scripts/
│   ├── seed_demo_data.py
│   └── simulate_orders.py
│
├── tests/
│   ├── conftest.py
│   ├── test_pos_flow.py
│   ├── test_shop_flow.py
│   ├── test_ifood_bridge.py
│   └── test_payments.py
│
├── docs/
│   ├── architecture.md
│   ├── setup.md
│   └── api.md
│
├── pyproject.toml
├── requirements/
│   ├── base.txt
│   ├── dev.txt
│   └── prod.txt
├── README.md
└── Makefile
```

---

## REQUISITOS FUNCIONAIS

### 1. PDV Web (`apps/pos/`)

Interface de ponto de venda moderna:

```
┌─────────────────────────────────────────────────────────────────┐
│  ☕ Café Demo                                    Mesa: ___  │ ≡ │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │ ☕       │ │ 🥐       │ │ 🍰       │ │ 🥤       │          │
│  │ Cafés    │ │ Pães     │ │ Doces    │ │ Bebidas  │          │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘          │
│                                                                 │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐  │
│  │Espresso │ │Cappucc. │ │ Latte   │ │ Mocha   │ │Americano│  │
│  │ R$6,00  │ │ R$9,00  │ │ R$10,00 │ │ R$12,00 │ │ R$7,00  │  │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘  │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  COMANDA #123                                                   │
│  ─────────────────────────────────────────────────────────────  │
│  2x Espresso                              R$ 12,00    [-] [+]  │
│  1x Croissant                              R$ 8,00    [-] [+]  │
│  ─────────────────────────────────────────────────────────────  │
│  Subtotal:                                          R$ 20,00   │
│  ─────────────────────────────────────────────────────────────  │
│  [💳 Cartão]  [📱 Pix]  [💵 Dinheiro]     [FECHAR COMANDA]    │
└─────────────────────────────────────────────────────────────────┘
```

**Funcionalidades**:
- Grid de produtos por categoria
- Busca rápida por nome/SKU
- Identificador de comanda/mesa
- Modificadores de item (ex: "sem açúcar", "leite de aveia")
- Split de pagamento
- Impressão de comanda/cupom
- Modo offline com sync posterior

**Tecnologias sugeridas**:
- HTMX para interatividade
- Alpine.js para estado local
- Tailwind CSS para UI
- Service Worker para offline

### 2. E-commerce (`apps/shop/`)

Loja virtual responsiva:

**Páginas**:
- Home com produtos em destaque
- Listagem por categoria
- Página de produto com variantes
- Carrinho persistente
- Checkout com endereço de entrega
- Tracking de pedido
- Área do cliente (histórico, endereços)

**Funcionalidades**:
- Carrinho persistente (Session → localStorage)
- Cálculo de frete por CEP
- Cupons de desconto
- Checkout como guest ou logado
- Pagamento via Stripe (cartão) ou Efi (Pix)
- Confirmação por email
- Tracking de status em tempo real (SSE)

### 3. Bridge iFood (`apps/bridges/ifood/`)

Integração completa com iFood:

**Fluxo de entrada**:
```
iFood Webhook → bridge.py → Session (locked) → Order
```

**Implementar**:
- OAuth2 para autenticação
- Webhook receiver para novos pedidos
- Mapper iFood → Omniman (produtos, modificadores, cliente)
- Status sync bidirecional
- Cancelamento e ajustes
- Métricas de tempo de preparo

**Eventos iFood → Omniman**:
```python
IFOOD_STATUS_MAP = {
    "PLACED": Order.Status.NEW,
    "CONFIRMED": Order.Status.CONFIRMED,
    "PREPARATION_STARTED": Order.Status.PROCESSING,
    "READY_TO_PICKUP": Order.Status.READY,
    "DISPATCHED": Order.Status.DISPATCHED,
    "DELIVERED": Order.Status.DELIVERED,
    "CANCELLED": Order.Status.CANCELLED,
}
```

### 4. Pagamentos (`apps/payments/`)

#### Stripe (Cartões)

```python
class StripePaymentAdapter:
    """Adapter para Stripe seguindo omniman.contrib.payment.protocols.PaymentBackend."""

    def create_intent(self, amount_q: int, currency: str, **kwargs) -> PaymentIntent:
        """Cria PaymentIntent no Stripe."""

    def capture(self, intent_id: str, amount_q: int | None = None) -> CaptureResult:
        """Captura pagamento autorizado."""

    def refund(self, intent_id: str, amount_q: int | None = None) -> RefundResult:
        """Processa reembolso."""
```

**Fluxo**:
1. Checkout cria PaymentIntent
2. Frontend usa Stripe Elements
3. Webhook confirma pagamento
4. Directive `payment.capture` processa

#### Efi (Pix)

```python
class EfiPaymentAdapter:
    """Adapter para Efi (Pix) com confirmação automatizada."""

    def create_pix(self, amount_q: int, **kwargs) -> PixCharge:
        """Cria cobrança Pix com QR Code."""

    def check_status(self, txid: str) -> PixStatus:
        """Verifica status do pagamento."""
```

**Fluxo**:
1. Checkout gera QR Code Pix
2. Cliente paga pelo app do banco
3. Webhook Efi confirma (ou polling como fallback)
4. Order transiciona para CONFIRMED

**Tela de Pix**:
```
┌─────────────────────────────────────┐
│                                     │
│         [QR CODE PIX]               │
│                                     │
│  Valor: R$ 35,00                    │
│  Chave: cafe-demo@pix.com           │
│                                     │
│  [📋 Copiar código]                 │
│                                     │
│  ⏱️ Aguardando pagamento...         │
│  Expira em: 14:59                   │
│                                     │
└─────────────────────────────────────┘
```

### 5. Estoque/Produção (`apps/inventory/`, `apps/production/`)

#### Integração Stockman

```python
class StockmanAdapter:
    """Adapter conectando Omniman ao Stockman."""

    def check_availability(self, sku: str, quantity: Decimal) -> Availability:
        """Consulta disponibilidade no Stockman."""

    def create_hold(self, sku: str, quantity: Decimal, **kwargs) -> HoldResult:
        """Cria reserva de estoque."""

    def fulfill_hold(self, hold_id: str, **kwargs) -> FulfillResult:
        """Converte reserva em baixa definitiva."""
```

#### Integração Craftsman (MRP)

```python
class CraftsmanAdapter:
    """Conecta pedidos à produção."""

    def request_production(self, sku: str, quantity: Decimal) -> ProductionOrder:
        """Solicita produção quando estoque baixo."""

    def check_can_produce(self, sku: str, quantity: Decimal) -> bool:
        """Verifica se há insumos para produzir."""
```

**Fluxo automático**:
1. Estoque de Croissant baixo (< 10 unidades)
2. Signal dispara `request_production`
3. Craftsman verifica insumos (farinha, manteiga...)
4. Cria ordem de produção
5. Ao finalizar, Stockman recebe entrada

### 6. Admin Unificado

Dashboard administrativo com Django Unfold:

```
┌─────────────────────────────────────────────────────────────────┐
│  📊 Dashboard                                      Admin ▼      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌───────────┐ │
│  │ 📦 47       │ │ 💰 R$2.340  │ │ ⏱️ 12min    │ │ ⚠️ 3      │ │
│  │ Pedidos Hoje│ │ Faturamento │ │ Tempo Médio │ │ Alertas   │ │
│  └─────────────┘ └─────────────┘ └─────────────┘ └───────────┘ │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Pedidos Recentes                              [+ Novo] │   │
│  │  ───────────────────────────────────────────────────── │   │
│  │  #1234  Mesa 5      ⏳ Em preparo    R$ 45,00   [Ver]  │   │
│  │  #1233  iFood       ✅ Pronto        R$ 67,00   [Ver]  │   │
│  │  #1232  E-commerce  🚚 Despachado    R$ 89,00   [Ver]  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────┐  ┌─────────────────────────────────┐  │
│  │ Estoque Baixo       │  │ Produção Pendente              │  │
│  │ ─────────────────── │  │ ───────────────────────────── │  │
│  │ Croissant: 8 un     │  │ Pão de Queijo: 50 un (10:00)  │  │
│  │ Leite: 2 L          │  │ Bolo Cenoura: 2 un (11:00)    │  │
│  └─────────────────────┘  └─────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## CONFIGURAÇÃO DE CANAIS

```python
# apps/core/fixtures/channels.json

CHANNELS = [
    {
        "code": "pos",
        "name": "Balcão",
        "pricing_policy": "internal",
        "edit_policy": "open",
        "config": {
            "icon": "point_of_sale",
            "terminology": {
                "session": "Comanda",
                "order": "Venda",
            },
            "required_checks_on_commit": ["stock"],
            "post_commit_directives": ["stock.commit", "receipt.print"],
            "order_flow": {
                "transitions": {
                    "new": ["confirmed", "cancelled"],
                    "confirmed": ["completed", "cancelled"],
                    "completed": [],
                    "cancelled": [],
                },
                "terminal_statuses": ["completed", "cancelled"],
            },
        },
    },
    {
        "code": "shop",
        "name": "E-commerce",
        "pricing_policy": "internal",
        "edit_policy": "open",
        "config": {
            "icon": "shopping_cart",
            "required_checks_on_commit": ["stock"],
            "post_commit_directives": [
                "stock.commit",
                "payment.authorize",
                "notification.send",
            ],
            "order_flow": {
                "transitions": {
                    "new": ["confirmed", "cancelled"],
                    "confirmed": ["processing", "cancelled"],
                    "processing": ["ready", "cancelled"],
                    "ready": ["dispatched", "cancelled"],
                    "dispatched": ["delivered"],
                    "delivered": ["completed"],
                    "completed": [],
                    "cancelled": [],
                },
            },
        },
    },
    {
        "code": "ifood",
        "name": "iFood",
        "pricing_policy": "external",
        "edit_policy": "locked",
        "config": {
            "icon": "delivery_dining",
            "bridge": "apps.bridges.ifood.bridge.IFoodBridge",
            "required_checks_on_commit": [],  # iFood já validou
            "post_commit_directives": ["stock.commit"],
            "auto_transitions": {
                "on_create": "confirmed",  # Pedido já vem pago
            },
        },
    },
]
```

---

## SEED DATA

Script para popular demo com dados realistas:

```python
# scripts/seed_demo_data.py

CATEGORIES = ["Cafés", "Pães", "Doces", "Bebidas", "Combos"]

PRODUCTS = [
    {"sku": "ESP", "name": "Espresso", "category": "Cafés", "price": 600},
    {"sku": "CAP", "name": "Cappuccino", "category": "Cafés", "price": 900},
    {"sku": "LAT", "name": "Latte", "category": "Cafés", "price": 1000},
    {"sku": "CRO", "name": "Croissant", "category": "Pães", "price": 800},
    {"sku": "PDQ", "name": "Pão de Queijo", "category": "Pães", "price": 500},
    {"sku": "BOL", "name": "Bolo do Dia", "category": "Doces", "price": 1200},
    {"sku": "SUC", "name": "Suco Natural", "category": "Bebidas", "price": 1000},
    {"sku": "CMB01", "name": "Combo Café + Pão", "category": "Combos", "price": 1200},
]

CUSTOMERS = [
    {"name": "João Silva", "email": "joao@example.com", "phone": "11999990001"},
    {"name": "Maria Santos", "email": "maria@example.com", "phone": "11999990002"},
]
```

---

## DOCKER COMPOSE

```yaml
# docker/docker-compose.yml

version: "3.8"

services:
  web:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DEBUG=1
      - DATABASE_URL=postgres://demo:demo@db:5432/demo
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - db
      - redis
    volumes:
      - .:/app

  db:
    image: postgres:15
    environment:
      - POSTGRES_USER=demo
      - POSTGRES_PASSWORD=demo
      - POSTGRES_DB=demo
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7

  worker:
    build: .
    command: python manage.py process_directives --continuous
    depends_on:
      - db
      - redis

  stripe-cli:
    image: stripe/stripe-cli
    command: listen --forward-to web:8000/webhooks/stripe/
    environment:
      - STRIPE_API_KEY=${STRIPE_SECRET_KEY}

volumes:
  postgres_data:
```

---

## MAKEFILE

```makefile
.PHONY: setup dev test seed simulate

setup:
	pip install -e ".[dev]"
	python manage.py migrate
	python manage.py createsuperuser --noinput || true

dev:
	docker-compose up -d db redis
	python manage.py runserver

seed:
	python scripts/seed_demo_data.py

simulate:
	python scripts/simulate_orders.py --count=50 --interval=5

test:
	pytest tests/ -v

lint:
	ruff check .
	mypy apps/
```

---

## CRITÉRIOS DE ACEITE

### Funcionalidade
- [ ] PDV funcional com todas operações básicas
- [ ] E-commerce completo com checkout
- [ ] Bridge iFood recebendo e processando pedidos
- [ ] Pagamento Stripe funcionando end-to-end
- [ ] Pagamento Pix com confirmação automática
- [ ] Estoque atualizado em tempo real
- [ ] Admin com dashboard operacional

### Qualidade
- [ ] Cobertura de testes > 80%
- [ ] Documentação completa
- [ ] Docker compose funcional
- [ ] Scripts de seed e simulação
- [ ] Código type-hinted

### UX
- [ ] PDV responsivo e rápido
- [ ] E-commerce mobile-first
- [ ] Feedback visual em todas operações
- [ ] Tratamento de erros amigável

---

## NOTAS DE IMPLEMENTAÇÃO

1. **Comece pelo PDV** - É o fluxo mais simples e permite testar Omniman isoladamente

2. **Depois E-commerce** - Adiciona complexidade de pagamento e delivery

3. **Por último iFood** - Requer mock da API para desenvolvimento

4. **Pagamentos em paralelo** - Stripe e Efi podem ser desenvolvidos independentemente

5. **Use feature flags** - Para habilitar/desabilitar integrações em diferentes ambientes

---

## PROMPT DE CONTINUAÇÃO

Quando os micro-serviços estiverem prontos, use este prompt para integração:

```
Integre o Django Omniman Demo com:
- Django Stockman em [URL_STOCKMAN]
- Django Craftsman em [URL_CRAFTSMAN]
- Django Goodsman em [URL_GOODSMAN]
- Django Merchantman em [URL_MERCHANTMAN]

Atualize os adapters para usar as APIs reais ao invés dos mocks.
Configure service discovery e health checks.
Adicione circuit breakers para resiliência.
```
