# Sessions

A **Session** is the mutable pre-commit state. It's a generic concept that works for any channel—whether it's a shopping basket, a restaurant table tab, or an import from an external platform.

---

## Session Lifecycle

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│    OPEN     │ ──► │  COMMITTED  │     │  ABANDONED  │
│  (mutable)  │     │ (immutable) │     │  (discarded)│
└─────────────┘     └─────────────┘     └─────────────┘
```

| State | Meaning |
|-------|---------|
| `open` | Session is active and can be modified |
| `committed` | Session was converted to Order |
| `abandoned` | Session was discarded |

---

## Creating a Session

```python
from omniman.models import Channel, Session

channel = Channel.objects.get(code="pos")

session = Session.objects.create(
    channel=channel,
    session_key="SESS-USER-123",  # Unique identifier
    state="open",
)
```

### Session Key

The `session_key` is a unique identifier. You can:

1. **Generate it**: `session_key=f"SESS-{uuid4().hex}"`
2. **Use a business key**: `session_key=f"TABLE-5-{date.today()}"` or `f"BASKET-{user_id}"`

### Handle: Get-or-Open Pattern

Use `handle_type` and `handle_ref` for idempotent session retrieval:

```python
# First call: creates session
session = Session.objects.get_or_create(
    channel=channel,
    handle_type="table",
    handle_ref="5",
    state="open",
    defaults={"session_key": f"TABLE-5-{uuid4().hex[:8]}"},
)[0]

# Second call with same handle: returns existing session
session = Session.objects.get_or_create(
    channel=channel,
    handle_type="table",
    handle_ref="5",
    state="open",
    defaults={"session_key": f"TABLE-5-{uuid4().hex[:8]}"},
)[0]
```

---

## Session Items

Items are stored as a list of dictionaries.

### Item Structure

```python
{
    "line_id": "L-abc123",      # Unique within session
    "sku": "COFFEE",
    "name": "Coffee",
    "qty": 2.0,
    "unit_price_q": 500,        # Price in cents
    "line_total_q": 1000,       # qty * unit_price_q
    "meta": {...},              # Flexible (promotions, notes, etc)
}
```

### Reading Items

```python
session = Session.objects.get(session_key="SESS-123")

for item in session.items:
    print(f"{item['sku']}: {item['qty']} x ${item['unit_price_q']/100:.2f}")
```

### Writing Items

**Always use `ModifyService`**, not direct assignment:

```python
from omniman.services import ModifyService

# CORRECT: Use ModifyService
ModifyService.modify_session(
    session_key="SESS-123",
    channel_code="pos",
    ops=[{"op": "add_line", "sku": "COFFEE", "qty": 1}],
)

# WRONG: Direct assignment (doesn't update rev, doesn't run modifiers)
session.items.append({"sku": "COFFEE", "qty": 1})  # Don't do this!
```

---

## Rev-Based Versioning

Every session has a `rev` (revision number) that increments on modification.

### Why Rev?

Rev enables **stale-safe writes**—detecting when two processes tried to modify the same session.

```python
session = Session.objects.get(session_key="SESS-123")
print(session.rev)  # 1

ModifyService.modify_session(...)
session.refresh_from_db()
print(session.rev)  # 2
```

### Stale Check Detection

Checks store the `rev` when they ran:

```python
session.data = {
    "checks": {
        "stock": {
            "rev": 2,          # Check ran at rev 2
            "status": "ok",
            "result": {...},
        }
    }
}
```

If `session.rev > check.rev`, the check is stale and must be rerun.

---

## Session Data

The `data` JSONField stores checks, issues, and custom data.

### Structure

```python
session.data = {
    "checks": {
        "stock": {
            "rev": 3,
            "status": "ok",
            "result": {"holds": [...]},
            "checked_at": "2026-01-19T10:30:00Z",
        },
    },
    "issues": [
        {
            "id": "ISS-001",
            "code": "insufficient_stock",
            "message": "Not enough stock for COFFEE",
            "severity": "blocking",
            "actions": [
                {
                    "id": "ACT-001",
                    "label": "Reduce quantity",
                    "ops": [{"op": "set_qty", "line_id": "L-123", "qty": 1}],
                }
            ],
        }
    ],
    "customer": {
        "name": "John Doe",
        "phone": "555-1234",
    },
}
```

### Checks

Results from async checks (stock verification, payment pre-auth, etc.):

```python
checks = session.data.get("checks", {})
stock_check = checks.get("stock", {})

if stock_check.get("status") == "ok":
    print("Stock verified")
```

### Issues

Problems detected during checks, with suggested actions:

```python
issues = session.data.get("issues", [])

for issue in issues:
    if issue["severity"] == "blocking":
        print(f"Blocking issue: {issue['message']}")
        for action in issue["actions"]:
            print(f"  → {action['label']}")
```

---

## ModifyService Operations

### add_line

```python
{"op": "add_line", "sku": "COFFEE", "qty": 2}
{"op": "add_line", "sku": "COFFEE", "qty": 2, "unit_price_q": 500}  # External pricing
{"op": "add_line", "sku": "COFFEE", "qty": 2, "meta": {"note": "No sugar"}}
```

### remove_line

```python
{"op": "remove_line", "line_id": "L-abc123"}
```

### set_qty

```python
{"op": "set_qty", "line_id": "L-abc123", "qty": 5}
```

### replace_sku

```python
{"op": "replace_sku", "line_id": "L-abc123", "sku": "ESPRESSO"}
```

### set_data

```python
{"op": "set_data", "path": "customer.name", "value": "John Doe"}
{"op": "set_data", "path": "notes", "value": "Deliver to back door"}
```

---

## Pricing Behavior

### Internal Pricing (`pricing_policy="internal"`)

Omniman looks up prices via registered Modifiers:

```python
# Price will be fetched from your pricing modifier
ModifyService.modify_session(
    session_key="SESS-123",
    channel_code="pos",
    ops=[{"op": "add_line", "sku": "COFFEE", "qty": 1}],
)
```

### External Pricing (`pricing_policy="external"`)

You must provide prices:

```python
ModifyService.modify_session(
    session_key="SESS-456",
    channel_code="ifood",
    ops=[{
        "op": "add_line",
        "sku": "COFFEE",
        "qty": 1,
        "unit_price_q": 500,
        "line_total_q": 500,
    }],
)
```

---

## Best Practices

1. **Always use `ModifyService`**: Never modify `session.items` directly
2. **Use handles for idempotency**: `handle_type` + `handle_ref` for get-or-open
3. **Check for stale data**: Verify `check.rev == session.rev` before commit
4. **Store customer data in `data`**: Use `set_data` op for custom fields
5. **Don't rely on `SessionItem` model**: Use `session.items` (the public API)
