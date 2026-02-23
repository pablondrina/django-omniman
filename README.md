# Django Omniman

[![PyPI version](https://badge.fury.io/py/django-omniman.svg)](https://badge.fury.io/py/django-omniman)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Django 5.2+](https://img.shields.io/badge/django-5.2+-green.svg)](https://www.djangoproject.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **Alpha Software**: API may change between versions. Use in production with care.

**Headless omnichannel order management hub for Django.** Omniman turns any Django
project into an order orchestrator -- POS, e-commerce, iFood, Rappi, or any channel
that produces orders.

## Key Concepts

- **Session** -- mutable pre-commit state (cart, tab, draft). Rev-versioned for
  optimistic concurrency. Modified through `ModifyService`.
- **Order** -- immutable snapshot sealed at commit time. The canonical source of truth.
  Status transitions enforced by a per-channel state machine.
- **Directive** -- async side-effect task (stock reservation, payment capture,
  notification). At-least-once semantics; handlers must be idempotent.
- **Channel** -- logical origin of orders. Each channel defines pricing policy,
  edit policy, required checks, and status flow.

## Quick Start (5 minutes)

### 1. Install

```bash
pip install django-omniman
```

### 2. Add to INSTALLED_APPS

```python
# settings.py
INSTALLED_APPS = [
    # ...
    "rest_framework",
    "omniman",
]
```

### 3. Run migrations

```bash
python manage.py migrate
```

### 4. Create a channel, add items, and commit

Open a Django shell (`python manage.py shell`) and run:

```python
from omniman.models import Channel, Session, Order
from omniman.services import ModifyService, CommitService

# Create a channel
channel = Channel.objects.create(
    code="pos",
    name="Point of Sale",
    pricing_policy="internal",
    edit_policy="open",
)

# Open a session
session = Session.objects.create(
    channel=channel,
    session_key="DEMO-001",
)

# Add items via ModifyService
session = ModifyService.modify_session(
    session_key="DEMO-001",
    channel_code="pos",
    ops=[
        {"op": "add_line", "sku": "COFFEE", "qty": 2, "unit_price_q": 550},
        {"op": "add_line", "sku": "CROISSANT", "qty": 1, "unit_price_q": 850},
    ],
)

# Check session state
print(f"Rev: {session.rev}")          # Rev: 1
print(f"Items: {len(session.items)}") # Items: 2

# Commit -- creates an immutable Order
result = CommitService.commit(
    session_key="DEMO-001",
    channel_code="pos",
    idempotency_key="DEMO-CHECKOUT-001",
)

print(f"Order ref: {result['order_ref']}")   # ORD-20260223-XXXXXXXX
print(f"Total (q): {result['total_q']}")     # 1950

# Verify the Order
order = Order.objects.get(ref=result["order_ref"])
print(f"Status: {order.status}")             # new
print(f"Items: {order.items.count()}")       # 2
```

Calling `CommitService.commit()` again with the same `idempotency_key` returns
the cached result without creating a duplicate Order.

## Architecture Overview

```
                     The Omniman Pipeline
                     ====================

  Client          Omniman Kernel              Adapters / Handlers
  ------          --------------              -------------------

  POST /modify -->  ModifyService
                      apply ops
                      run Modifiers  -------> PricingBackend.get_price()
                      run Validators
                      rev++, save
                      enqueue directives ---> [stock.hold directive]

  (async)           StockHoldHandler -------> StockBackend.check_availability()
                      write check result       StockBackend.create_hold()

  POST /commit -->  CommitService
                      verify checks & rev
                      verify no blocking issues
                      run Validators
                      create Order (immutable)
                      enqueue directives ---> [stock.commit, payment.capture]

  (async)           StockCommitHandler -----> StockBackend.fulfill_hold()
                    PaymentCaptureHandler --> PaymentBackend.capture()
```

Sessions are mutable. Orders are immutable. Side effects are Directives.

## Configuration

Omniman settings live under the `OMNIMAN` dict in `settings.py`:

```python
OMNIMAN = {
    # DRF permission classes for public API endpoints
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    # DRF permission classes for admin-only endpoints (directives)
    "ADMIN_PERMISSION_CLASSES": ["rest_framework.permissions.IsAdminUser"],
}
```

Per-channel behavior is configured via `Channel.config`:

```python
channel = Channel.objects.create(
    code="ecommerce",
    name="E-commerce",
    config={
        "required_checks_on_commit": ["stock"],
        "checks": {
            "stock": {"directive_topic": "stock.hold"}
        },
        "post_commit_directives": ["stock.commit", "payment.capture"],
        "order_flow": {
            "transitions": {
                "new": ["confirmed", "cancelled"],
                "confirmed": ["processing", "cancelled"],
                "processing": ["ready"],
                "ready": ["dispatched", "completed"],
                "dispatched": ["delivered"],
                "delivered": ["completed", "returned"],
            }
        },
    },
)
```

## API Endpoints

```
GET    /api/health                    Health check
GET    /api/channels                  List channels
GET    /api/sessions                  List sessions
POST   /api/sessions                  Create session
GET    /api/sessions/{key}            Get session (requires channel_code param)
POST   /api/sessions/{key}/modify     Modify session
POST   /api/sessions/{key}/resolve    Resolve issue
POST   /api/sessions/{key}/commit     Commit session -> Order
GET    /api/orders                    List orders
GET    /api/orders/{ref}              Get order
GET    /api/orders/stream             Polling endpoint for new orders
GET    /api/directives                List directives (admin only)
```

Include in your `urls.py`:

```python
from django.urls import include, path

urlpatterns = [
    path("api/", include("omniman.api.urls")),
]
```

## Contrib Modules

Optional modules for extended functionality:

| Module | Purpose | Needs `INSTALLED_APPS` |
|--------|---------|------------------------|
| `omniman.contrib.pricing` | Price calculation modifiers | No |
| `omniman.contrib.stock` | Inventory check/hold/fulfill | No |
| `omniman.contrib.payment` | Payment capture/refund | No |
| `omniman.contrib.customer` | Customer lookup/validation | No |
| `omniman.contrib.refs` | External locators (tables, tickets) | **Yes** (has migrations) |
| `omniman.contrib.notifications` | Multi-channel notifications | No |

Each contrib module ships noop adapters for standalone development and testing:

```python
from omniman.contrib.pricing.adapters.noop import NoopPricingModifier
from omniman.contrib.stock.adapters.noop import NoopStockBackend
from omniman.contrib.customer.adapters.noop import NoopCustomerBackend
```

## Integration with the Shopman Suite

Omniman is the order management hub of the
[Shopman suite](https://github.com/pablondrina). It integrates with sibling
packages through adapter protocols:

| Package | Role | Omniman adapter |
|---------|------|-----------------|
| [django-stockman](https://github.com/pablondrina/django-stockman) | Inventory management | `StockmanBackend` in `contrib/stock` |
| [django-offerman](https://github.com/pablondrina/django-offerman) | Product catalog & pricing | `OffermanPricingBackend` in `contrib/pricing` |
| [django-guestman](https://github.com/pablondrina/django-guestman) | Customer identity & insights | `GuestmanBackend` in `contrib/customer` |
| [django-doorman](https://github.com/pablondrina/django-doorman) | Authentication & permissions | DRF permission classes on API views |

Install suite integrations as extras:

```bash
pip install django-omniman[stockman,offerman,guestman]
```

Shared admin utilities are available via
[django-shopman-commons](https://github.com/pablondrina/django-shopman-commons).

## Further Reading

- [CONTRACTS.md](CONTRACTS.md) -- public API surface, invariants, and integration points
- [docs/concepts/pipeline.md](docs/concepts/pipeline.md) -- the full modify/commit/directive pipeline
- [docs/concepts/directives.md](docs/concepts/directives.md) -- directive model and handler patterns
- [docs/concepts/sessions.md](docs/concepts/sessions.md) -- session lifecycle
- [docs/concepts/orders.md](docs/concepts/orders.md) -- order model and status flow
- [docs/concepts/channels.md](docs/concepts/channels.md) -- channel configuration

## Requirements

- Python 3.11+
- Django 5.2+
- Django REST Framework 3.15+
- django-unfold 0.80+ (optional, for enhanced admin UI)

## License

MIT License -- see [LICENSE](LICENSE) for details.
