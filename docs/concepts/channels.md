# Channels

A **Channel** represents a logical origin for orders. Each channel can have its own pricing policy, edit policy, and status flow.

---

## What is a Channel?

Think of a channel as "where the order comes from":

| Channel Code | Example Use Case |
|--------------|------------------|
| `pos` | Physical point of sale |
| `ecommerce` | Website/mobile app |
| `ifood` | iFood delivery platform |
| `rappi` | Rappi delivery platform |
| `whatsapp` | WhatsApp orders |

---

## Channel Model

```python
from omniman.models import Channel

channel = Channel.objects.create(
    code="pos",                     # Unique identifier
    name="Point of Sale",           # Human-readable name
    pricing_policy="internal",      # internal or external
    edit_policy="open",             # open or locked
    config={
        "icon": "point_of_sale",
        "required_checks_on_commit": ["stock"],
        "post_commit_directives": ["stock.commit"],
        "order_flow": {
            "initial_status": "new",
            "transitions": {
                "new": ["confirmed", "cancelled"],
                "confirmed": ["processing", "cancelled"],
                "processing": ["ready", "cancelled"],
                "ready": ["dispatched", "completed"],
            },
            "terminal_statuses": ["completed", "cancelled"],
        },
        "terminology": {
            "order": "Pedido",
            "order_plural": "Pedidos",
        },
    },
)
```

---

## Pricing Policy

Controls how item prices are determined.

### `internal` (Default)

Omniman calculates prices by calling registered Modifiers.

```python
channel = Channel.objects.create(
    code="pos",
    pricing_policy="internal",
    # ...
)

# When adding item, price is looked up:
ModifyService.modify_session(
    session_key="SESS-123",
    channel_code="pos",
    ops=[{"op": "add_line", "sku": "COFFEE", "qty": 1}],
    # unit_price_q not required—will be fetched
)
```

### `external`

Prices come from outside (e.g., iFood sends prices). Omniman does NOT reprice.

```python
channel = Channel.objects.create(
    code="ifood",
    pricing_policy="external",
    # ...
)

# Must provide price:
ModifyService.modify_session(
    session_key="SESS-456",
    channel_code="ifood",
    ops=[{
        "op": "add_line",
        "sku": "COFFEE",
        "qty": 1,
        "unit_price_q": 500,  # Required!
        "line_total_q": 500,  # Required!
    }],
)
```

**Invariant I4**: `pricing_policy=external` prevents silent repricing. If you try to reprice an external-policy session, it's a bug.

---

## Edit Policy

Controls whether sessions can be modified after creation.

### `open` (Default)

Items can be added, removed, or modified.

```python
channel = Channel.objects.create(
    code="pos",
    edit_policy="open",
)
```

### `locked`

Session is read-only after creation. Useful for external orders (iFood, Rappi).

```python
channel = Channel.objects.create(
    code="ifood",
    edit_policy="locked",
)
```

**Invariant I3**: `edit_policy=locked` rejects mutable ops on items.

---

## Channel Config

The `config` JSONField holds channel-specific settings.

### Common Config Keys

```python
config = {
    # UI
    "icon": "point_of_sale",  # Material icon name

    # Commit behavior
    "required_checks_on_commit": ["stock"],
    "post_commit_directives": ["stock.commit", "notification.send"],

    # Status flow
    "order_flow": {
        "initial_status": "new",
        "transitions": {...},
        "terminal_statuses": ["completed", "cancelled"],
    },

    # Terminology
    "terminology": {
        "order": "Pedido",
        "draft": "Carrinho",
    },
}
```

### Required Checks on Commit

List of check codes that must be fresh (same rev) before commit:

```python
"required_checks_on_commit": ["stock"]
```

If `session.data["checks"]["stock"]["rev"] != session.rev`, commit fails.

### Post-Commit Directives

List of directive topics to enqueue after commit:

```python
"post_commit_directives": ["stock.commit", "payment.capture"]
```

Creates `Directive` records that handlers will process.

---

## Order Status Flow

Each channel can define its own status transitions.

### E-commerce Flow

```
created → confirmed → processing → dispatched → delivered → completed
```

### Restaurant Flow

```
created → confirmed → processing → ready → dispatched → delivered → completed
```

### POS Flow (Instant)

```
created → confirmed → completed
```

### Configuration

```python
"order_flow": {
    "initial_status": "new",
    "transitions": {
        "new": ["confirmed", "cancelled"],
        "confirmed": ["processing", "ready", "cancelled"],
        "processing": ["ready", "cancelled"],
        "ready": ["dispatched", "completed"],
        "dispatched": ["delivered"],
        "delivered": ["completed"],
    },
    "terminal_statuses": ["completed", "cancelled", "returned"],
}
```

---

## Examples by Business Type

### Coffee Shop (POS)

```python
Channel.objects.create(
    code="pos",
    name="Balcão",
    pricing_policy="internal",
    edit_policy="open",
    config={
        "icon": "point_of_sale",
        "required_checks_on_commit": [],
        "post_commit_directives": [],
        "order_flow": {
            "initial_status": "new",
            "transitions": {
                "new": ["confirmed"],
                "confirmed": ["completed"],
            },
            "terminal_statuses": ["completed"],
        },
    },
)
```

### E-commerce with Stock

```python
Channel.objects.create(
    code="ecommerce",
    name="Loja Online",
    pricing_policy="internal",
    edit_policy="open",
    config={
        "icon": "shopping_cart",
        "required_checks_on_commit": ["stock"],
        "post_commit_directives": ["stock.commit", "notification.order_received"],
        "order_flow": {
            "initial_status": "new",
            "transitions": {
                "new": ["confirmed", "cancelled"],
                "confirmed": ["processing", "cancelled"],
                "processing": ["dispatched"],
                "dispatched": ["delivered"],
                "delivered": ["completed"],
            },
            "terminal_statuses": ["completed", "cancelled"],
        },
    },
)
```

### iFood Integration

```python
Channel.objects.create(
    code="ifood",
    name="iFood",
    pricing_policy="external",  # iFood sends prices
    edit_policy="locked",       # Can't modify iFood orders
    config={
        "icon": "delivery_dining",
        "required_checks_on_commit": [],
        "post_commit_directives": [],
        "order_flow": {
            "initial_status": "new",
            "transitions": {
                "new": ["confirmed", "cancelled"],
                "confirmed": ["processing"],
                "processing": ["ready"],
                "ready": ["dispatched"],
                "dispatched": ["delivered"],
                "delivered": ["completed"],
            },
            "terminal_statuses": ["completed", "cancelled"],
        },
    },
)
```

---

## Best Practices

1. **Use meaningful codes**: `pos`, `ecommerce`, `ifood`—not `channel1`, `channel2`
2. **Keep config minimal**: Only add what you need
3. **Document transitions**: Make status flow explicit
4. **Test policies**: Verify pricing and edit policies work as expected
