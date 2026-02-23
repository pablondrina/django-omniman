# Omniman Contracts

This document defines the public API surface, invariants, and integration points
of `django-omniman`. If your code violates any contract listed here, it is a bug.

---

## Public API

### ModifyService

```python
ModifyService.modify_session(
    session_key: str,
    channel_code: str,
    ops: list[dict],
    ctx: dict | None = None,
) -> Session
```

Modifies an open Session by applying operations atomically.

Pipeline:
1. Lock session (`select_for_update`)
2. Validate session is open and editable
3. Apply ops (`add_line`, `remove_line`, `set_qty`, `replace_sku`, `set_data`, `merge_lines`)
4. Run registered Modifiers (sorted by `order`)
5. Run registered Validators (`stage="draft"`)
6. Increment `rev`
7. Clear `checks` and `issues` (stale after modification)
8. Save session
9. Enqueue directives for required checks (per channel config)

Raises `SessionError` if the session is not found, already committed, abandoned, or locked.
Raises `ValidationError` if any op or validator fails.

### CommitService

```python
CommitService.commit(
    session_key: str,
    channel_code: str,
    idempotency_key: str,
    ctx: dict | None = None,
) -> dict
```

Closes a Session and creates an immutable Order.

Pipeline:
1. Acquire idempotency lock (return cached response if key already succeeded)
2. Lock session
3. Validate session is open and has items
4. Verify required checks are fresh (`check.rev == session.rev`) and holds not expired
5. Verify no blocking issues
6. Run registered Validators (`stage="commit"`)
7. Create Order + OrderItems from session snapshot
8. Mark session as committed
9. Enqueue post-commit directives (per channel config)
10. Cache response in IdempotencyKey

Returns `{"order_ref", "order_id", "status", "total_q", "items_count"}`.
Raises `CommitError` or `SessionError` on failure.

### ResolveService

```python
ResolveService.resolve(
    session_key: str,
    channel_code: str,
    issue_id: str,
    action_id: str,
    ctx: dict | None = None,
) -> Session
```

Resolves a blocking issue on a Session by delegating to the registered
`IssueResolver` for that issue's `source`.

Raises `IssueResolveError` if the issue, resolver, or action is not found.

### SessionWriteService

```python
SessionWriteService.apply_check_result(
    session_key: str,
    channel_code: str,
    expected_rev: int,
    check_code: str,
    check_payload: dict,
    issues: list[dict],
) -> bool
```

Writes a check result back to a Session. Returns `True` if applied,
`False` if the session's `rev` no longer matches `expected_rev` (stale).

---

## Core Invariants

### I1: Session.rev increments on every modification

Every call to `ModifyService.modify_session()` increments `rev` by 1.
This is the optimistic concurrency token. Checks and directive payloads
carry `rev` so stale writes are detected and rejected.

### I2: Session is mutable; Order is immutable

A Session can be modified any number of times while `state == "open"`.
Once committed, the Session moves to `state == "committed"` and an Order is
created. Orders cannot be modified after creation -- status transitions are
the only mutation, enforced by the state machine in `Order.save()`.

### I3: Modifiers are pure transforms

Modifiers implement the `Modifier` protocol. They mutate the session in-place
(items, pricing, pricing_trace) but must **never perform IO** (no database
queries, no HTTP calls, no file access). They are deterministic and
idempotent: running the same modifier twice on the same input produces the
same output.

### I4: Validators are pure checks

Validators implement the `Validator` protocol. They inspect session state and
raise `ValidationError` if something is wrong. They must **never mutate state
and never perform IO**. Validators run at two stages: `"draft"` (during modify)
and `"commit"` (during commit).

### I5: Directives handle all side effects

Stock reservations, payment captures, notifications, and any other IO-bound
operation must be modeled as a Directive. Directives are never executed inline
during modify or commit. They are enqueued as database rows and processed
asynchronously by handlers.

### I6: Directive handlers must be idempotent (at-least-once)

A handler may execute more than once for the same directive (worker crash,
manual re-execution, retry after failure). Handlers must check whether the
work has already been done before acting. The `StockCommitHandler`, for
example, skips holds that are already fulfilled.

### I7: IdempotencyKey prevents duplicate commits

Every commit requires an `idempotency_key`. If the same key is submitted
again and the previous commit succeeded, the cached response is returned
without creating a second Order. If the previous attempt failed, a retry is
allowed.

### I8: Checks are rev-stamped for tamper detection

A check result carries the `rev` at which it was computed. At commit time,
`CommitService` verifies that `check.rev == session.rev`. If the session was
modified after the check ran, the check is stale and the commit is rejected.
This prevents committing with outdated stock availability or other validations.

### I9: Monetary values are in quantum (smallest indivisible unit)

All prices and totals use integer fields with the `_q` suffix (e.g.,
`unit_price_q`, `total_q`, `line_total_q`). Values are in centavos (or the
smallest currency unit). Quantities use `Decimal` for fractional precision.
`monetary_mult(qty, price_q)` handles the multiplication with correct rounding.

---

## Idempotency

**Commit idempotency**: Calling `CommitService.commit()` with the same
`idempotency_key` is safe. The first successful call creates the Order and
caches the response. Subsequent calls return the cached response with
HTTP 200 instead of 201. Failed attempts are marked in the IdempotencyKey
so they can be retried.

**Directive handler idempotency**: Handlers must be safe to re-execute.
Patterns:
- Check if the work is already done before acting (e.g., hold already fulfilled)
- Use `release_holds_for_reference()` before creating new holds to avoid accumulation
- Record side effects in typed models (OrderEvent, Hold) for reliable detection

---

## Integration Points

### Pricing Adapter (`PricingBackend` protocol)

```python
def get_price(self, sku: str, channel: Any) -> int | None
```

Used by `ItemPricingModifier` to look up `unit_price_q` for items that don't
have one. Only active when `session.pricing_policy == "internal"`.

Adapters: `SimplePricingBackend`, `ChannelPricingBackend`, `NoopPricingModifier`,
or any Offerman-backed implementation.

### Stock Adapter (`StockBackend` protocol)

```python
def check_availability(sku, quantity, target_date) -> AvailabilityResult
def create_hold(sku, quantity, expires_at, reference) -> HoldResult
def release_hold(hold_id) -> None
def fulfill_hold(hold_id, reference) -> None
def get_alternatives(sku, quantity) -> list[Alternative]
def release_holds_for_reference(reference) -> int
```

Used by `StockHoldHandler` (pre-commit check) and `StockCommitHandler`
(post-commit fulfillment). Adapters: `StockmanBackend`, `NoopStockBackend`.

### Customer Adapter (`CustomerBackend` protocol)

```python
def get_customer(code) -> CustomerInfo | None
def validate_customer(code) -> CustomerValidationResult
def get_price_list_code(customer_code) -> str | None
def get_customer_context(code) -> CustomerContext | None
def record_order(customer_code, order_data) -> bool
```

Used by application code to enrich sessions with customer data.
Adapters: `GuestmanBackend`, `NoopCustomerBackend`.

### Payment Handler (`PaymentBackend` protocol)

`PaymentCaptureHandler` and `PaymentRefundHandler` process `payment.capture`
and `payment.refund` directives. They delegate to a `PaymentBackend`
implementation (MockPaymentBackend, StripeBackend, EfiPixBackend).

### Refs (`omniman.contrib.refs`)

External locators (table numbers, pickup tickets, order references) attached
to Sessions or Orders via the `Ref` model. Refs have scoped uniqueness and
lifecycle management. Requires `omniman.contrib.refs` in `INSTALLED_APPS`.

---

## What is NOT Omniman's Job

| Concern | Owner | Omniman's role |
|---------|-------|----------------|
| Product catalog | Offerman (or your own) | Receives SKU + price via adapter |
| Inventory management | Stockman (or your own) | Calls `StockBackend` via directives |
| Customer identity | Guestman (or your own) | Calls `CustomerBackend` via adapter |
| Authentication | Doorman (or your own) | DRF permission classes on API views |
| UI / frontend | Your application | Omniman is headless; provides REST API |

Omniman is the **orchestrator**. It does not own domain data -- it delegates
to adapters and receives results through protocols.

---

## Pipeline Summary

```
                         The Omniman Pipeline
                         ====================

1. CREATE SESSION
   Channel + session_key --> Session(state="open", rev=0)

2. MODIFY (repeatable)
   ops --> apply ops --> modifiers --> validators(draft) --> rev++ --> save
           |                                                  |
           |                                                  +-> checks = {}, issues = []
           +-> enqueue check directives (e.g., stock.hold)

3. CHECK RESULTS (async, via directive handlers)
   stock.hold handler --> check availability --> create holds
                      --> SessionWriteService.apply_check_result(expected_rev)

4. COMMIT
   verify idempotency_key
   --> verify checks fresh (check.rev == session.rev)
   --> verify no blocking issues
   --> validators(commit)
   --> create Order + OrderItems (immutable snapshot)
   --> session.state = "committed"
   --> enqueue post-commit directives (stock.commit, payment.capture)

5. POST-COMMIT (async, via directive handlers)
   stock.commit  --> fulfill holds (decrement inventory)
   payment.capture --> capture authorized payment

6. ORDER LIFECYCLE
   Order.status transitions per channel config state machine:
   new -> confirmed -> processing -> ready -> dispatched -> delivered -> completed
                                                                     -> cancelled
```
