# Invariants (I1-I14)

These invariants are **inviolable system contracts**. Any code that violates them is considered a bug.

---

## The 14 Invariants

| ID | Invariant | Description |
|----|-----------|-------------|
| **I1** | Idempotent Commit | Commit never creates two Orders for the same Session |
| **I2** | Validator/Modifier Separation | Validators don't mutate; Modifiers don't perform IO |
| **I3** | Edit Policy Respected | `edit_policy=locked` rejects mutable ops on items |
| **I4** | Pricing Policy Respected | `pricing_policy=external` prevents silent repricing |
| **I5** | Audited Price Override | Manual price override generates mandatory `OrderEvent` |
| **I6** | At-Least-Once Directives | Handlers must be idempotent |
| **I7** | Versioned Snapshot | `Order.snapshot` contains `_v` and validates on read |
| **I8** | Operational Timestamps | First transition wins; history in `OrderEvent` |
| **I9** | Blocked Compat Mode | Compat mode never runs in production without explicit override |
| **I10** | Fail-Fast DB Checks | DB checks fail early if vendor/capabilities mismatch |
| **I11** | Rev Increments | `Session.rev` increments on relevant modification |
| **I12** | Invalidated Checks | Any relevant change zeroes `checks` and `issues` |
| **I13** | Stale-Safe Check Write | Check write-back requires `expected_rev` |
| **I14** | Selective Freshness | Commit only requires freshness for checks in `required_checks_on_commit` |

---

## Critical Invariant Details

### I1 — Idempotent Commit

A commit never creates two Orders for the same `idempotency_key`.

```python
# First commit
result = CommitService.commit(
    session_key="SESS-123",
    channel_code="pos",
    idempotency_key="IDEM-ABC",
)
# Creates Order ORD-001

# Second commit with same key
result = CommitService.commit(
    session_key="SESS-123",
    channel_code="pos",
    idempotency_key="IDEM-ABC",
)
# Returns same Order ORD-001, doesn't create new one
```

### I2 — Validator/Modifier Separation

```python
# CORRECT: Deterministic Modifier, no IO
class LineTotalModifier:
    def apply(self, *, channel, session, ctx):
        items = session.items
        for item in items:
            item["line_total_q"] = int(item["qty"] * item["unit_price_q"])
        session.items = items  # Persist changes

# WRONG: Modifier performing IO
class BadModifier:
    def apply(self, *, channel, session, ctx):
        price = requests.get(f"/api/price/{sku}")  # IO forbidden!
```

### I4 — Pricing Policy Respected

```python
# CORRECT: Modifier respects pricing_policy
class LineTotalModifier:
    def apply(self, *, channel, session, ctx):
        if session.pricing_policy != "internal":
            return  # Don't reprice if external
        # ... recalculate line_total_q

# WRONG: Silent repricing
class BadModifier:
    def apply(self, *, channel, session, ctx):
        for item in session.items:
            item["line_total_q"] = ...  # Ignores pricing_policy!
```

### I11 — Rev Increments

Every relevant modification to Session increments `rev`:

```python
session = Session.objects.get(session_key="SESS-123")
print(session.rev)  # 1

ModifyService.modify_session(
    session_key="SESS-123",
    channel_code="pos",
    ops=[{"op": "add_line", "sku": "COFFEE", "qty": 1}],
)

session.refresh_from_db()
print(session.rev)  # 2
```

### I12 — Invalidated Checks

When Session changes, previous checks become stale:

```python
# Session has check at rev=3
session.data["checks"]["stock"]["rev"] = 3
session.rev = 3

# Modify session
ModifyService.modify_session(...)

# Now session.rev = 4, but check.rev = 3
# Check is stale—needs rerun before commit
```

### I13 — Stale-Safe Check Write

Check results can only be written if `expected_rev` matches:

```python
from omniman.services import SessionWriteService

# This will only write if session.rev == 5
SessionWriteService.write_check(
    session_key="SESS-123",
    channel_code="pos",
    check_code="stock",
    expected_rev=5,
    result={"holds": [...]},
)
```

---

## Why These Invariants Matter

| Invariant | Protects Against |
|-----------|------------------|
| I1 | Duplicate orders from retry/network issues |
| I2 | Unpredictable side effects, untestable code |
| I3-I4 | External channel data being silently overwritten |
| I5 | Unaudited price changes (fraud risk) |
| I6 | Lost or duplicated async work |
| I11-I13 | Race conditions in concurrent modifications |

---

## Violation Examples

### Violating I1 (Non-Idempotent Commit)

```python
# WRONG: No idempotency_key in production
result = CommitService.commit(
    session_key="SESS-123",
    channel_code="pos",
    # Missing idempotency_key!
)
# If user clicks twice, creates duplicate orders
```

### Violating I6 (Non-Idempotent Handler)

```python
# WRONG: Handler not idempotent
class BadStockHandler:
    def handle(self, directive, ctx):
        # This will decrement stock EVERY time handler runs
        Stock.objects.filter(sku=sku).update(qty=F('qty') - 1)

# CORRECT: Idempotent handler
class GoodStockHandler:
    def handle(self, directive, ctx):
        hold_id = directive.payload["hold_id"]
        # Check if already processed
        if Hold.objects.filter(id=hold_id, fulfilled=True).exists():
            return  # Already done
        # Process and mark as done
        hold = Hold.objects.get(id=hold_id)
        hold.fulfill()
```

---

## Testing Invariants

Write tests that specifically verify invariants:

```python
def test_i1_commit_idempotent(self):
    """I1: Commit with same key returns same order."""
    result1 = CommitService.commit(
        session_key="SESS-123",
        channel_code="pos",
        idempotency_key="TEST-KEY",
    )
    result2 = CommitService.commit(
        session_key="SESS-123",
        channel_code="pos",
        idempotency_key="TEST-KEY",
    )
    self.assertEqual(result1["order_ref"], result2["order_ref"])

def test_i11_rev_increments_on_modify(self):
    """I11: Rev increments on modification."""
    session = Session.objects.create(...)
    old_rev = session.rev

    ModifyService.modify_session(
        session_key=session.session_key,
        channel_code=session.channel.code,
        ops=[{"op": "add_line", "sku": "X", "qty": 1}],
    )

    session.refresh_from_db()
    self.assertEqual(session.rev, old_rev + 1)
```
