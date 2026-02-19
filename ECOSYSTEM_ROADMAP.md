# Ecossistema Django Micro-* — Roadmap

> **Visão**: Conjunto de micro-bibliotecas Django que seguem a filosofia SIREL (Simples, Robusto, Elegante), cada uma resolvendo um domínio específico de negócio.

---

## VISÃO DO ECOSSISTEMA

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DJANGO MICRO-* ECOSYSTEM                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌───────────────┐    ┌───────────────┐    ┌───────────────┐              │
│  │   GOODSMAN    │    │  MERCHANTMAN  │    │   OMNIMAN     │              │
│  │  Micro-PIM    │───▶│   Micro-CRM   │───▶│  Order Hub    │              │
│  │   Catálogo    │    │   Clientes    │    │    Pedidos    │              │
│  └───────────────┘    └───────────────┘    └───────┬───────┘              │
│         │                    │                      │                       │
│         │                    │                      │                       │
│         ▼                    ▼                      ▼                       │
│  ┌───────────────┐    ┌───────────────┐    ┌───────────────┐              │
│  │   STOCKMAN    │◀───│   CRAFTSMAN   │◀───│   PRICEMAN    │              │
│  │Micro-Inventory│    │   Micro-MRP   │    │ Micro-Pricing │              │
│  │    Estoque    │    │   Produção    │    │    Preços     │              │
│  └───────────────┘    └───────────────┘    └───────────────┘              │
│                                                                             │
│  ──────────────────────────────────────────────────────────────────────── │
│                            FUNDAÇÃO COMUM                                   │
│  ┌───────────────┐    ┌───────────────┐    ┌───────────────┐              │
│  │   BRIDGEMAN   │    │   HOOKMAN     │    │   WATCHMAN    │              │
│  │  Integrações  │    │    Eventos    │    │  Observability│              │
│  └───────────────┘    └───────────────┘    └───────────────┘              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## PROJETOS EXISTENTES

### 1. Django Omniman ✅
**Status**: Alpha (0.1.0a1)
**Repo**: `django-omniman`
**Domínio**: Hub de pedidos omnichannel

| Funcionalidade | Status |
|----------------|--------|
| Session → Order → Directive | ✅ |
| Multi-channel | ✅ |
| Rev-based concurrency | ✅ |
| Idempotency | ✅ |
| Registry extensível | ✅ |
| Contrib: Payment | ✅ |
| Contrib: Stock | ✅ |
| Contrib: Pricing | ✅ |
| Contrib: Notifications | ✅ |
| Contrib: Refs | ✅ |

### 2. Django Stockman ✅
**Status**: [INFORMAR STATUS]
**Repo**: `django-stockman`
**Domínio**: Micro-inventário

**Funcionalidades esperadas**:
- [ ] Locations (almoxarifados, prateleiras)
- [ ] Stock movements (entrada, saída, transferência, ajuste)
- [ ] Reservations (holds temporários)
- [ ] Lot tracking (lotes, validade)
- [ ] Multi-unit (un, kg, L)
- [ ] Stock alerts
- [ ] Reconciliation

**Perguntas para Pablo**:
1. Qual o estado atual do Stockman?
2. Já implementa `StockBackend` protocol do Omniman?
3. Suporta multi-location?
4. Tem controle de lotes?

### 3. Django Craftsman ✅
**Status**: [INFORMAR STATUS]
**Repo**: `django-craftsman`
**Domínio**: Micro-MRP (Manufacturing Resource Planning)

**Funcionalidades esperadas**:
- [ ] BOM (Bill of Materials) - receitas
- [ ] Production orders
- [ ] Resource scheduling
- [ ] Cost calculation
- [ ] Yield tracking
- [ ] Quality control checkpoints

**Perguntas para Pablo**:
1. Qual o estado atual do Craftsman?
2. Como se integra com Stockman?
3. Suporta multi-step production?
4. Tem custeio de produção?

---

## PROJETOS A DESENVOLVER

### 4. Django Goodsman 📋
**Status**: A desenvolver
**Repo**: `django-goodsman`
**Domínio**: Micro-PIM (Product Information Management)

**Escopo**:
```python
# Core models
class ProductCategory(models.Model):
    """Hierarquia de categorias."""
    name: str
    slug: str
    parent: FK(self)
    attributes_schema: JSONField  # Atributos permitidos

class Product(models.Model):
    """Produto base."""
    sku: str
    name: str
    description: str
    category: FK(ProductCategory)
    product_type: str  # simple, configurable, bundle, virtual
    attributes: JSONField
    is_active: bool

class ProductVariant(models.Model):
    """Variante de produto (ex: tamanho, cor)."""
    product: FK(Product)
    sku: str
    attributes: JSONField  # {size: "M", color: "blue"}

class ProductMedia(models.Model):
    """Imagens e vídeos."""
    product: FK(Product)
    media_type: str  # image, video
    url: str
    position: int

class ProductAttribute(models.Model):
    """Definição de atributo."""
    code: str
    name: str
    attribute_type: str  # text, number, select, boolean
    options: JSONField  # Para selects
```

**Funcionalidades**:
- [ ] Catálogo de produtos com hierarquia
- [ ] Sistema de atributos flexível
- [ ] Variantes de produto
- [ ] Gestão de mídia
- [ ] Import/export CSV/Excel
- [ ] API REST completa
- [ ] Integração com e-commerce platforms

### 5. Django Merchantman 📋
**Status**: A desenvolver
**Repo**: `django-merchantman`
**Domínio**: Micro-CRM (Customer Relationship Management)

**Escopo**:
```python
# Core models
class Customer(models.Model):
    """Cliente."""
    external_id: str  # Para integração
    email: str
    phone: str
    name: str
    document: str  # CPF/CNPJ
    customer_type: str  # individual, company
    tags: JSONField
    metadata: JSONField

class CustomerAddress(models.Model):
    """Endereço do cliente."""
    customer: FK(Customer)
    label: str  # casa, trabalho
    street: str
    number: str
    complement: str
    neighborhood: str
    city: str
    state: str
    zipcode: str
    is_default: bool

class CustomerInteraction(models.Model):
    """Histórico de interações."""
    customer: FK(Customer)
    interaction_type: str  # order, support, campaign
    channel: str
    summary: str
    metadata: JSONField
    created_at: datetime

class LoyaltyProgram(models.Model):
    """Programa de fidelidade."""
    name: str
    points_per_currency: int  # Ex: 1 ponto a cada R$1
    rules: JSONField

class LoyaltyBalance(models.Model):
    """Saldo de pontos."""
    customer: FK(Customer)
    program: FK(LoyaltyProgram)
    balance: int
    lifetime_earned: int
    lifetime_redeemed: int

class LoyaltyTransaction(models.Model):
    """Movimentação de pontos."""
    balance: FK(LoyaltyBalance)
    transaction_type: str  # earn, redeem, expire, adjust
    points: int
    reference: str  # order_ref, campaign_id
    created_at: datetime
```

**Funcionalidades**:
- [ ] Cadastro unificado de clientes
- [ ] Múltiplos endereços
- [ ] Histórico de interações
- [ ] Programa de fidelidade
- [ ] Segmentação por tags
- [ ] Merge de cadastros duplicados
- [ ] LGPD compliance (anonimização)

### 6. Django Priceman 📋 (Opcional)
**Status**: A avaliar
**Repo**: `django-priceman`
**Domínio**: Micro-Pricing

**Escopo**:
- Tabelas de preço por canal
- Regras de desconto
- Promoções temporais
- Preço dinâmico
- Histórico de preços

**Nota**: Pode ser parte do Goodsman ou módulo separado dependendo da complexidade.

---

## PROJETOS DE SUPORTE

### 7. Django Bridgeman 📋
**Status**: A avaliar
**Domínio**: Integrações externas padronizadas

**Escopo**:
- Bridges para marketplaces (iFood, Rappi, Mercado Livre)
- Bridges para e-commerce (Shopify, WooCommerce)
- Bridges para ERPs
- Webhook standardization
- Retry/circuit breaker

### 8. Django Hookman 📋
**Status**: A avaliar
**Domínio**: Sistema de eventos

**Escopo**:
- Event bus interno
- Webhooks de saída
- Event sourcing patterns
- Audit logging

### 9. Django Watchman 📋
**Status**: A avaliar
**Domínio**: Observability

**Escopo**:
- Métricas Prometheus
- Tracing OpenTelemetry
- Health checks padronizados
- Alerting

---

## MATRIZ DE INTEGRAÇÃO

| Projeto | Omniman | Stockman | Craftsman | Goodsman | Merchantman |
|---------|---------|----------|-----------|----------|-------------|
| **Omniman** | - | StockBackend | - | Catalog | Customer |
| **Stockman** | Holds | - | Materials | SKUs | - |
| **Craftsman** | Orders | Inventory | - | Recipes | - |
| **Goodsman** | Products | SKUs | BOMs | - | - |
| **Merchantman** | Orders | - | - | Favorites | - |

---

## ROADMAP DE DESENVOLVIMENTO

### Fase 1: Fundação (Atual)
```
Q1 2025
├── ✅ Omniman estável
├── 📋 Avaliar estado do Stockman
├── 📋 Avaliar estado do Craftsman
└── 📋 Especificar Goodsman
```

### Fase 2: Catálogo e CRM
```
Q2 2025
├── 🚀 Goodsman v0.1
├── 🚀 Merchantman v0.1
└── 🔗 Integração Omniman ↔ Goodsman
```

### Fase 3: Demo Completa
```
Q3 2025
├── 🚀 django-omniman-demo
├── 🔗 Todas integrações funcionando
└── 📚 Documentação completa
```

### Fase 4: Produção
```
Q4 2025
├── 📦 Todos projetos em v1.0
├── 🧪 Battle-tested em produção
└── 🌐 Comunidade ativa
```

---

## CHECKLIST PARA PABLO

### Informações Necessárias

**Stockman**:
- [ ] Link do repositório
- [ ] Estado atual (alpha/beta/stable)
- [ ] Funcionalidades implementadas
- [ ] Pendências conhecidas

**Craftsman**:
- [ ] Link do repositório
- [ ] Estado atual
- [ ] Funcionalidades implementadas
- [ ] Pendências conhecidas

**Decisões de Design**:
- [ ] Goodsman deve ter pricing embutido ou separado?
- [ ] Merchantman deve ter campaigns/marketing ou só CRM básico?
- [ ] Bridgeman como projeto separado ou contrib do Omniman?

---

## CONVENÇÕES DO ECOSSISTEMA

### Nomenclatura
- Todos projetos terminam em `man` (Omniman, Stockman, etc.)
- Repos: `django-{nome}`
- Packages: `{nome}` (sem django prefix)

### Padrões Técnicos
- Python 3.11+
- Django 5.0+
- Type hints obrigatórios
- Protocols para extensibilidade
- pytest para testes
- Ruff para linting

### Filosofia SIREL
Cada projeto deve responder:
1. **Simples**: Pode ser mais simples?
2. **Robusto**: E se rodar 2x? E se dados estiverem stale?
3. **Elegante**: A API é intuitiva? Segue padrões Django?

### Versionamento
- SemVer (MAJOR.MINOR.PATCH)
- Alpha: 0.1.0a1
- Beta: 0.1.0b1
- Release: 1.0.0

---

## PRÓXIMOS PASSOS IMEDIATOS

1. **Pablo traz info sobre Stockman e Craftsman**
2. **Claude especifica Goodsman detalhadamente**
3. **Decisão sobre Merchantman scope**
4. **Início do django-omniman-demo**

---

> Este documento é vivo e será atualizado conforme o ecossistema evolui.
