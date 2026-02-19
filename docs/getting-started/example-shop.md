# Example: Shop Integration

This guide shows how to integrate Omniman with a simple shop application. The `example/shop` app demonstrates the essential patterns.

---

## Project Structure

```
example/
├── project/
│   ├── settings.py    # Django settings
│   ├── urls.py        # URL configuration
│   └── wsgi.py        # WSGI entry point
└── shop/
    ├── models.py      # Product model
    ├── pricing.py     # Pricing modifier
    ├── admin.py       # Admin configuration
    └── apps.py        # App registration
```

---

## The Product Model

The shop needs products. Omniman doesn't provide a product catalog—you bring your own.

```python
# example/shop/models.py
from django.db import models

class Product(models.Model):
    sku = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    price_q = models.BigIntegerField(default=0)  # Price in cents
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return f"{self.sku} - {self.name}"
```

### Price Convention: Centavos (`_q` suffix)

**All monetary values are stored in cents (smallest unit).**

```python
# Correct: cents (integers)
unit_price_q = 1290   # $12.90
line_total_q = 2580   # $25.80
total_q = 15000       # $150.00

# Avoid: decimals (precision problems)
unit_price = Decimal("12.90")  # Requires special care
```

**Why cents?**

1. **Precision**: Integers are exact, no rounding errors
2. **Simplicity**: `10 + 20 = 30` (not `0.1 + 0.2 = 0.30000000000000004`)
3. **Compatibility**: Stripe, PayPal, banks use the same convention
4. **JSON**: Serializes naturally without precision loss

---

## Creating a Pricing Modifier

Omniman doesn't know your products. You tell it how to price items.

```python
# example/shop/pricing.py
from omniman.contrib.pricing.modifiers import InternalPricingModifier
from example.shop.models import Product

class SimplePricingModifier(InternalPricingModifier):
    """Fetch prices from Product model."""

    code = "shop.pricing"
    order = 10  # Runs early in the modifier chain

    def get_price_for_sku(self, sku: str) -> int | None:
        """Return price in cents for the given SKU."""
        try:
            product = Product.objects.get(sku=sku, is_active=True)
            return product.price_q
        except Product.DoesNotExist:
            return None

    def get_name_for_sku(self, sku: str) -> str | None:
        """Return product name for the given SKU."""
        try:
            product = Product.objects.get(sku=sku, is_active=True)
            return product.name
        except Product.DoesNotExist:
            return None
```

---

## Registering the Modifier

Register your modifier when Django starts.

```python
# example/shop/apps.py
from django.apps import AppConfig

class ShopConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "example.shop"

    def ready(self):
        from omniman import registry
        from example.shop.pricing import SimplePricingModifier

        registry.register_modifier(SimplePricingModifier())
```

---

## Creating Channels

Channels represent different sales sources. Each has its own configuration.

```python
from omniman.models import Channel

# Point of Sale channel
pos_channel = Channel.objects.create(
    code="pos",
    name="Point of Sale",
    pricing_policy="internal",  # Omniman looks up prices
    edit_policy="open",         # Items can be modified
    config={
        "icon": "point_of_sale",
        "required_checks_on_commit": [],
        "post_commit_directives": [],
    }
)

# E-commerce channel
ecommerce_channel = Channel.objects.create(
    code="ecommerce",
    name="E-commerce",
    pricing_policy="internal",
    edit_policy="open",
    config={
        "icon": "shopping_cart",
        "required_checks_on_commit": ["stock"],
        "post_commit_directives": ["stock.commit"],
    }
)

# External channel (prices come from outside)
ifood_channel = Channel.objects.create(
    code="ifood",
    name="iFood",
    pricing_policy="external",  # Don't reprice
    edit_policy="locked",       # Don't allow modifications
    config={
        "icon": "delivery_dining",
        "required_checks_on_commit": [],
        "post_commit_directives": [],
    }
)
```

### Pricing Policy

| Value | Behavior |
|-------|----------|
| `internal` | Omniman calculates prices (looks up from catalog) |
| `external` | Channel provides `unit_price_q` mandatorily |

### Edit Policy

| Value | Behavior |
|-------|----------|
| `open` | Session can be freely edited |
| `locked` | Session locked after creation |

---

## Working with Sessions

### Creating a Session (Basket)

```python
from omniman.models import Session

session = Session.objects.create(
    channel=pos_channel,
    session_key="BASKET-USER-123",
    state="open",
)
```

### Adding Items

```python
from omniman.services import ModifyService

ModifyService.modify_session(
    session_key="BASKET-USER-123",
    channel_code="pos",
    ops=[
        {"op": "add_line", "sku": "COFFEE", "qty": 2},
        {"op": "add_line", "sku": "CROISSANT", "qty": 1},
    ],
)
```

Since `pricing_policy="internal"`, Omniman will:
1. Call your `SimplePricingModifier.get_price_for_sku("COFFEE")`
2. Set `unit_price_q` automatically
3. Calculate `line_total_q`

### Viewing Items

```python
session.refresh_from_db()
for item in session.items:
    print(f"{item['sku']}: {item['qty']} x {item['unit_price_q']} = {item['line_total_q']}")
```

### Modifying Quantities

```python
ModifyService.modify_session(
    session_key="BASKET-USER-123",
    channel_code="pos",
    ops=[
        {"op": "set_qty", "line_id": "L-ABC123", "qty": 5},
    ],
)
```

### Removing Items

```python
ModifyService.modify_session(
    session_key="BASKET-USER-123",
    channel_code="pos",
    ops=[
        {"op": "remove_line", "line_id": "L-ABC123"},
    ],
)
```

---

## Committing (Creating Order)

```python
from omniman.services import CommitService

result = CommitService.commit(
    session_key="BASKET-USER-123",
    channel_code="pos",
    idempotency_key="COMMIT-USER-123-001",
)

print(result["order_ref"])  # ORD-20260119-ABC123
```

The commit:
1. Validates the session (runs all validators)
2. Creates an immutable `Order` with snapshot
3. Changes session state to `committed`
4. Enqueues any `post_commit_directives`

---

## Managing Order Status

```python
from omniman.models import Order

order = Order.objects.get(ref=result["order_ref"])

# Transition through states
order.transition_status("confirmed", actor="payment_webhook")
order.transition_status("processing", actor="kitchen")
order.transition_status("ready", actor="kitchen")
order.transition_status("completed", actor="cashier")

# View history
for event in order.events.all():
    print(f"{event.created_at}: {event.type} by {event.actor}")
```

---

## Complete Flow Example

```python
from omniman.models import Channel, Session
from omniman.services import ModifyService, CommitService

# 1. Get channel
channel = Channel.objects.get(code="pos")

# 2. Create or get session
session, created = Session.objects.get_or_create(
    channel=channel,
    handle_type="table",
    handle_ref="5",
    state="open",
    defaults={"session_key": f"TABLE-5-{uuid4().hex[:8]}"},
)

# 3. Add items
ModifyService.modify_session(
    session_key=session.session_key,
    channel_code="pos",
    ops=[
        {"op": "add_line", "sku": "COFFEE", "qty": 2},
        {"op": "add_line", "sku": "CROISSANT", "qty": 1},
    ],
)

# 4. View total
session.refresh_from_db()
total = sum(item["line_total_q"] for item in session.items)
print(f"Total: ${total / 100:.2f}")

# 5. Commit
result = CommitService.commit(
    session_key=session.session_key,
    channel_code="pos",
    idempotency_key=f"COMMIT-{session.session_key}",
)

print(f"Order created: {result['order_ref']}")
```

---

## Seed Example Data

Use the management command to seed test data:

```bash
# Seed products and channels
python manage.py seed_example

# Clear and reseed
python manage.py seed_example --reset
```

This creates:
- 3 channels: pos, ecommerce, ifood
- 10 products: Coffee, Espresso, Cappuccino, Croissant, etc.
