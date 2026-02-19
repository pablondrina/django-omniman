# Orders

An **Order** is the immutable snapshot created when a Session is committed. It's the source of truth for what was sold.

---

## Order Lifecycle

```
Session ──commit──► Order ──transitions──► Terminal Status
(mutable)          (immutable)            (completed/cancelled)
```

Once created, an Order's items and snapshot cannot be modified. Only status can change.

---

## Creating Orders (Commit)

Orders are created via `CommitService.commit()`:

```python
from omniman.services import CommitService

result = CommitService.commit(
    session_key="SESS-123",
    channel_code="pos",
    idempotency_key="COMMIT-123",
)

order_ref = result["order_ref"]  # ORD-20260119-ABC123
```

### What Happens on Commit

1. **Validation**: All registered validators run
2. **Check freshness**: Required checks must match session rev
3. **Snapshot creation**: Session state is frozen into Order
4. **State transition**: Session moves to `committed`
5. **Directives enqueued**: Post-commit directives are created

### Idempotency

**Invariant I1**: Commit with the same `idempotency_key` returns the same Order.

```python
# First commit
result1 = CommitService.commit(..., idempotency_key="KEY-123")

# Second commit with same key (retry, network issue, etc.)
result2 = CommitService.commit(..., idempotency_key="KEY-123")

assert result1["order_ref"] == result2["order_ref"]  # Same order!
```

---

## Order Model

```python
from omniman.models import Order

order = Order.objects.get(ref="ORD-20260119-ABC123")

print(order.ref)           # ORD-20260119-ABC123
print(order.channel.code)  # pos
print(order.status)        # new
print(order.total_q)       # 1500 (cents)
print(order.snapshot)      # Full session state at commit time
```

### Key Fields

| Field | Description |
|-------|-------------|
| `ref` | Unique order reference |
| `channel` | FK to Channel |
| `session_key` | Original session key |
| `status` | Current status |
| `total_q` | Total in cents |
| `snapshot` | JSONField with full state |
| `created_at` | When committed |

### Snapshot

The snapshot contains everything at commit time:

```python
order.snapshot = {
    "_v": "0.5.9",  # Schema version
    "items": [...],
    "data": {...},
    "channel_code": "pos",
    "pricing_policy": "internal",
}
```

**Invariant I7**: Snapshot contains `_v` and validates on read.

---

## Order Items

Items are normalized in `OrderItem` model:

```python
for item in order.items.all():
    print(f"{item.sku}: {item.qty} x {item.unit_price_q} = {item.line_total_q}")
```

### OrderItem Fields

| Field | Description |
|-------|-------------|
| `line_id` | Unique line identifier |
| `sku` | Product SKU |
| `name` | Product name at commit time |
| `qty` | Quantity |
| `unit_price_q` | Unit price in cents |
| `line_total_q` | Line total in cents |
| `meta` | JSONField with custom data |

---

## Status Transitions

### Built-in Statuses

| Status | Meaning |
|--------|---------|
| `new` | Just created, awaiting processing |
| `confirmed` | Stock/payment confirmed |
| `processing` | Being prepared |
| `ready` | Ready for pickup/dispatch |
| `dispatched` | Sent out |
| `delivered` | Received by customer |
| `completed` | Finished |
| `cancelled` | Cancelled |
| `returned` | Returned |

### Transitioning Status

```python
order = Order.objects.get(ref="ORD-123")

# Transition with actor tracking
order.transition_status("confirmed", actor="payment_webhook")
order.transition_status("processing", actor="kitchen@restaurant.com")
order.transition_status("ready", actor="kitchen@restaurant.com")
order.transition_status("completed", actor="cashier@restaurant.com")
```

### Invalid Transitions

Transitions are validated against channel config:

```python
order.status  # "new"

# Valid: new → confirmed
order.transition_status("confirmed", actor="system")

# Invalid: confirmed → new (not allowed)
order.transition_status("new", actor="system")  # Raises InvalidTransition
```

---

## Order Events (Audit Log)

Every significant action creates an `OrderEvent`:

```python
for event in order.events.all().order_by("created_at"):
    print(f"{event.created_at}: {event.type} by {event.actor}")
    print(f"  Payload: {event.payload}")
```

### Event Types

| Type | When |
|------|------|
| `status_changed` | Status transition |
| `payment.captured` | Payment captured |
| `payment.refunded` | Payment refunded |
| `stock.committed` | Stock committed |
| `custom.* ` | Your custom events |

### Creating Events

```python
order.emit_event(
    event_type="custom.note_added",
    payload={"note": "Customer requested extra napkins"},
    actor="staff@restaurant.com",
)
```

**Invariant I5**: Manual price overrides generate mandatory `OrderEvent`.

---

## Directives

After commit, directives are enqueued for async processing:

```python
from omniman.models import Directive

# Directives created by commit
directives = Directive.objects.filter(
    payload__order_ref=order.ref
)

for d in directives:
    print(f"{d.topic}: {d.status}")
```

### Common Directive Topics

| Topic | Purpose |
|-------|---------|
| `stock.commit` | Finalize stock reservation |
| `payment.capture` | Capture payment |
| `notification.send` | Send confirmation |

---

## Querying Orders

### By Channel

```python
Order.objects.filter(channel__code="pos")
```

### By Status

```python
Order.objects.filter(status="processing")
```

### By Date Range

```python
from django.utils import timezone
from datetime import timedelta

today = timezone.now().date()
Order.objects.filter(created_at__date=today)
```

### With Events

```python
Order.objects.prefetch_related("events").filter(status="completed")
```

---

## Best Practices

1. **Never modify Order items directly**: They're immutable by design
2. **Always provide idempotency_key**: Prevents duplicate orders
3. **Track actors**: Every transition should have an actor for audit
4. **Use events for audit trail**: Emit events for significant actions
5. **Query via channel**: Filter by channel for multi-channel systems
