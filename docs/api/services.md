# Services API

Omniman provides services as the primary interface for modifying state. **Always use services instead of direct model manipulation.**

---

## ModifyService

Modifies session items and data.

### modify_session

```python
from omniman.services import ModifyService

result = ModifyService.modify_session(
    session_key="SESS-123",
    channel_code="pos",
    ops=[
        {"op": "add_line", "sku": "COFFEE", "qty": 2},
        {"op": "set_data", "path": "customer.name", "value": "John"},
    ],
)
```

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `session_key` | str | Yes | Session identifier |
| `channel_code` | str | Yes | Channel code |
| `ops` | list[dict] | Yes | List of operations |

**Returns:** `dict` with updated session data

**Raises:**

| Exception | When |
|-----------|------|
| `SessionNotFound` | Session doesn't exist |
| `SessionNotOpen` | Session not in `open` state |
| `EditPolicyViolation` | Channel has `edit_policy=locked` |
| `InvalidOperation` | Unknown op or invalid parameters |

### Operations

#### add_line

Add an item to the session.

```python
{"op": "add_line", "sku": "COFFEE", "qty": 2}

# With price (required for external pricing)
{"op": "add_line", "sku": "COFFEE", "qty": 2, "unit_price_q": 500}

# With metadata
{"op": "add_line", "sku": "COFFEE", "qty": 2, "meta": {"note": "No sugar"}}
```

#### remove_line

Remove an item by line_id.

```python
{"op": "remove_line", "line_id": "L-abc123"}
```

#### set_qty

Update quantity of an item.

```python
{"op": "set_qty", "line_id": "L-abc123", "qty": 5}
```

#### replace_sku

Replace an item's SKU (swap product).

```python
{"op": "replace_sku", "line_id": "L-abc123", "sku": "ESPRESSO"}
```

#### set_data

Set arbitrary data in session.data.

```python
{"op": "set_data", "path": "customer.name", "value": "John Doe"}
{"op": "set_data", "path": "notes", "value": "Ring doorbell"}
```

#### merge_lines

Merge two items with same SKU.

```python
{"op": "merge_lines", "from_line_id": "L-123", "into_line_id": "L-456"}
```

---

## CommitService

Commits a session to create an order.

### commit

```python
from omniman.services import CommitService

result = CommitService.commit(
    session_key="SESS-123",
    channel_code="pos",
    idempotency_key="CHECKOUT-ABC",
)

print(result["order_ref"])  # ORD-20260119-XYZ
```

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `session_key` | str | Yes | Session identifier |
| `channel_code` | str | Yes | Channel code |
| `idempotency_key` | str | No | Prevents duplicate commits |

**Returns:**

```python
{
    "order_ref": "ORD-20260119-XYZ",
    "status": "committed",
    "idempotent": False,  # True if replayed
}
```

**Raises:**

| Exception | When |
|-----------|------|
| `SessionNotFound` | Session doesn't exist |
| `SessionNotOpen` | Session not in `open` state |
| `BlockingIssues` | Session has unresolved blocking issues |
| `StaleCheck` | Required check has stale rev |
| `CommitError` | Generic commit failure |

### Idempotency

If `idempotency_key` is provided and was used before, returns the same result:

```python
# First call
result1 = CommitService.commit(..., idempotency_key="KEY-123")
# result1["order_ref"] = "ORD-001"

# Retry (network issue, etc.)
result2 = CommitService.commit(..., idempotency_key="KEY-123")
# result2["order_ref"] = "ORD-001" (same order)
# result2["idempotent"] = True
```

---

## SessionWriteService

Writes check results with stale-safety.

### write_check

```python
from omniman.services import SessionWriteService

success = SessionWriteService.write_check(
    session_key="SESS-123",
    channel_code="pos",
    check_code="stock",
    expected_rev=5,
    result={"holds": [{"hold_id": "H-1", "sku": "COFFEE", "qty": 2}]},
    status="ok",
)
```

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `session_key` | str | Yes | Session identifier |
| `channel_code` | str | Yes | Channel code |
| `check_code` | str | Yes | Check identifier (e.g., "stock") |
| `expected_rev` | int | Yes | Session rev when check started |
| `result` | dict | Yes | Check result data |
| `status` | str | No | "ok" or "issues" |
| `issues` | list | No | List of issues if any |

**Returns:** `bool` - True if write succeeded, False if session changed

**Why expected_rev?**

Prevents race conditions:

```python
# Process A starts stock check at rev=5
# Process B modifies session, rev becomes 6
# Process A tries to write check result

# Without expected_rev: Stale check is written
# With expected_rev=5: Write rejected, returns False
```

### write_issues

Write issues to session.

```python
SessionWriteService.write_issues(
    session_key="SESS-123",
    channel_code="pos",
    issues=[
        {
            "id": "ISS-001",
            "code": "insufficient_stock",
            "message": "Not enough COFFEE in stock",
            "severity": "blocking",
            "actions": [
                {
                    "id": "ACT-001",
                    "label": "Reduce quantity to 1",
                    "ops": [{"op": "set_qty", "line_id": "L-123", "qty": 1}],
                }
            ],
        }
    ],
)
```

---

## ResolveService

Resolves issues by applying suggested actions.

### resolve

```python
from omniman.services import ResolveService

result = ResolveService.resolve(
    session_key="SESS-123",
    channel_code="pos",
    issue_id="ISS-001",
    action_id="ACT-001",
)
```

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `session_key` | str | Yes | Session identifier |
| `channel_code` | str | Yes | Channel code |
| `issue_id` | str | Yes | Issue to resolve |
| `action_id` | str | Yes | Action to apply |

**Returns:** Updated session data

**Raises:**

| Exception | When |
|-----------|------|
| `IssueNotFound` | Issue doesn't exist |
| `ActionNotFound` | Action doesn't exist |
| `ResolveError` | Action failed to apply |

### How Resolution Works

1. Find issue by `issue_id` in `session.data["issues"]`
2. Find action by `action_id` in issue's `actions`
3. Apply action's `ops` via `ModifyService`
4. Remove resolved issue from list

---

## Error Handling

### Exception Hierarchy

```
OmnimanError
├── SessionNotFound
├── SessionNotOpen
├── EditPolicyViolation
├── InvalidOperation
├── CommitError
│   ├── BlockingIssues
│   └── StaleCheck
├── IssueNotFound
├── ActionNotFound
└── ResolveError
```

### Example Error Handling

```python
from omniman.services import CommitService
from omniman.exceptions import (
    BlockingIssues,
    StaleCheck,
    CommitError,
)

try:
    result = CommitService.commit(
        session_key="SESS-123",
        channel_code="pos",
    )
except BlockingIssues as e:
    print(f"Cannot commit: {len(e.issues)} blocking issues")
    for issue in e.issues:
        print(f"  - {issue['message']}")
except StaleCheck as e:
    print(f"Check '{e.check_code}' is stale, please re-run")
except CommitError as e:
    print(f"Commit failed: {e.message}")
```

---

## Transaction Safety

Services use database transactions appropriately:

```python
# ModifyService uses select_for_update
# to prevent concurrent modification

from django.db import transaction

with transaction.atomic():
    # Session is locked during modification
    ModifyService.modify_session(...)
```

**Important:** If you need multiple operations to be atomic, wrap them yourself:

```python
from django.db import transaction

with transaction.atomic():
    ModifyService.modify_session(
        session_key="SESS-123",
        channel_code="pos",
        ops=[{"op": "add_line", "sku": "COFFEE", "qty": 1}],
    )
    # If this fails, the add_line is rolled back
    CommitService.commit(
        session_key="SESS-123",
        channel_code="pos",
    )
```
