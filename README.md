# Django Omniman

[![PyPI version](https://badge.fury.io/py/django-omniman.svg)](https://badge.fury.io/py/django-omniman)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Django 5.0+](https://img.shields.io/badge/django-5.0+-green.svg)](https://www.djangoproject.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **Alpha Software**: API may change between versions. Use in production with care.

**A headless omnichannel order hub for Django.**

```
Session (mutable) → Order (immutable) → Directive (async)
```

## Philosophy (SIREL):

Every decision follows three core principles:

| Principle | Question |
|-----------|----------|
| **(SI)mple** | Can this be done simpler? |
| **(R)obust** | What if this runs twice? What if data is stale? |
| **(EL)egant** | Is the API intuitive? Does it follow Django patterns? |

### Practical Corollaries

From SIREL, two practical mandates emerge:

**Agnostic**: Omniman makes no assumptions about your stack.
- No opinions on your product catalog, customer model, or frontend
- Works with any payment provider, stock system, or notification service
- Channels abstract away origin differences (POS, e-commerce, marketplace)

**Flexible**: Extend, replace, or ignore any part.
- Protocol-based extensibility — implement the interface, plug it in
- Contrib modules are optional — use ours or bring your own
- No vendor lock-in — the kernel has zero external service dependencies

## What Omniman IS

- A **headless kernel** for order management
- A **protocol-based registry** for extensibility
- A **rev-based versioning system** for stale-safe writes
- An **audit-first** architecture with immutable orders

## What Omniman is NOT

- **Not a complete e-commerce solution** — no product catalog, no customer management
- **Not an opinionated UI** — the kernel is headless; you build the UI
- **Not a payment gateway** — use contrib/payment or bring your own
- **Not a stock manager** — use contrib/stock or bring your own

## Installation

```bash
pip install django-omniman
```

For enhanced admin UI (recommended):

```bash
pip install django-omniman[admin]
```

```python
# settings.py
INSTALLED_APPS = [
    # If using django-unfold for enhanced admin UI:
    # "unfold",
    # "unfold.contrib.filters",
    "rest_framework",
    "omniman",
]
```

```bash
python manage.py migrate
```

## Quick Start

```python
from omniman.models import Channel, Session
from omniman.services import ModifyService, CommitService

# 1. Create a channel
channel = Channel.objects.create(
    code="pos",
    name="Point of Sale",
    pricing_policy="internal",
    edit_policy="open",
)

# 2. Create a session
session = Session.objects.create(
    channel=channel,
    session_key="SESS-123",
)

# 3. Add items
ModifyService.modify_session(
    session_key="SESS-123",
    channel_code="pos",
    ops=[
        {"op": "add_line", "sku": "COFFEE", "qty": 2},
        {"op": "add_line", "sku": "CROISSANT", "qty": 1},
    ],
)

# 4. Commit (create order)
result = CommitService.commit(
    session_key="SESS-123",
    channel_code="pos",
    idempotency_key="CHECKOUT-123",
)

print(f"Order created: {result['order_ref']}")
```

## Core Concepts

### Channel

A logical origin for orders (POS, e-commerce, iFood, etc.). Each channel has:

- **pricing_policy**: `internal` (Omniman looks up prices) or `external` (you provide)
- **edit_policy**: `open` (editable) or `locked` (read-only)
- **status flow**: Custom order status transitions

### Session

Mutable pre-commit state (basket, tab, draft order, etc.).

- Rev-based versioning for stale-safe writes
- Checks and issues for validation
- Converts to Order on commit

### Order

Immutable snapshot created at commit. The source of truth.

- Cannot be modified after creation
- Full audit trail via OrderEvent
- Status transitions per channel config

### Directive

Async task for side effects (stock, payment, notifications).

- At-least-once semantics
- Handlers must be idempotent

## Contrib Modules

Optional modules for extended functionality. Only add to `INSTALLED_APPS` if you need them.

| Module | Purpose | Has Migrations |
|--------|---------|----------------|
| `omniman.contrib.pricing` | Price calculation | No |
| `omniman.contrib.stock` | Inventory management | No |
| `omniman.contrib.payment` | Payment processing | No |
| `omniman.contrib.refs` | External references/tagging | **Yes** |
| `omniman.contrib.notifications` | Multi-channel notifications | No |

**Note:** `omniman.contrib.refs` has its own database tables. Only add it to `INSTALLED_APPS` and run `migrate` if you need external reference/tagging functionality.

```python
# settings.py - with refs module
INSTALLED_APPS = [
    "unfold",
    "unfold.contrib.filters",
    "rest_framework",
    "omniman",
    "omniman.contrib.refs",  # Optional: only if you need refs
]
```

## API Endpoints

```
GET    /api/health                 Health check
GET    /api/channels/              List channels
GET    /api/sessions/              List sessions
POST   /api/sessions/              Create session
POST   /api/sessions/{key}/modify/ Modify session
POST   /api/sessions/{key}/resolve/ Resolve issue
POST   /api/sessions/{key}/commit/ Commit session
GET    /api/orders/                List orders
GET    /api/orders/{ref}/          Get order
GET    /api/orders/stream          SSE stream (real-time)
GET    /api/directives/            List directives
```

## Throttling Configuration

Configure API rate limiting in your settings:

```python
REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle'
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour',
        'omniman_commit': '60/minute',  # Specific limit for commits
    }
}
```

## Documentation

Full documentation: [django-omniman.readthedocs.io](https://django-omniman.readthedocs.io)

## Requirements

- Python 3.11+
- Django 5.0+
- Django REST Framework 3.15+
- django-unfold 0.49+ (optional, for enhanced admin UI)

## License

MIT License - see [LICENSE](LICENSE) for details.
