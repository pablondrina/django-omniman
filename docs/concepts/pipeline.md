# The Omniman Pipeline

This document is the definitive reference for the Session lifecycle and the
modify/commit/directive processing pipelines.

---

## Session Lifecycle

A Session moves through four states:

```
  create         modify (N times)       commit           (time passes)
    |                 |                    |                   |
    v                 v                    v                   v
 ┌──────┐  ops  ┌──────┐  commit  ┌───────────┐       ┌───────────┐
 │ open │──────>│ open │────────>│ committed │       │ abandoned │
 └──────┘       └──────┘         └───────────┘       └───────────┘
  rev=0          rev=N                                  (cleanup)
```

| State | Meaning | Transitions |
|-------|---------|-------------|
| `open` | Mutable. Items can be added/removed. Checks can be written. | `committed`, `abandoned` |
| `committed` | Sealed. An Order exists. No further modifications. | (terminal) |
| `abandoned` | Discarded. No Order was created. | (terminal) |

**Key rule**: Once a Session leaves `open`, it never goes back.

---

## The Modify Pipeline

`ModifyService.modify_session()` is the only sanctioned way to change a
Session. Calling it triggers a strict 8-step pipeline inside a single
database transaction.

### Steps

```
  Client sends ops
       │
       ▼
  ┌─────────────────────────────┐
  │ 1. LOCK SESSION             │  select_for_update()
  │    Acquire row-level lock   │
  └─────────────┬───────────────┘
                │
                ▼
  ┌─────────────────────────────┐
  │ 2. VALIDATE STATE           │  state == "open"?
  │    Not committed?           │  edit_policy != "locked"?
  │    Not abandoned?           │
  │    Not locked?              │
  └─────────────┬───────────────┘
                │
                ▼
  ┌─────────────────────────────┐
  │ 3. APPLY OPS                │  add_line, remove_line,
  │    Modify items and data    │  set_qty, replace_sku,
  │    in memory                │  set_data, merge_lines
  └─────────────┬───────────────┘
                │
                ▼
  ┌─────────────────────────────┐
  │ 4. RUN MODIFIERS            │  Sorted by .order
  │    Pure transforms, no IO   │  e.g., ItemPricingModifier
  │    Mutate session in-place  │       SessionTotalModifier
  └─────────────┬───────────────┘
                │
                ▼
  ┌─────────────────────────────┐
  │ 5. RUN VALIDATORS (draft)   │  Pure checks, no IO
  │    Raise ValidationError    │  No mutations allowed
  │    if invalid               │
  └─────────────┬───────────────┘
                │
                ▼
  ┌─────────────────────────────┐
  │ 6. INCREMENT REV            │  session.rev += 1
  └─────────────┬───────────────┘
                │
                ▼
  ┌─────────────────────────────┐
  │ 7. CLEAR CHECKS & ISSUES   │  data["checks"] = {}
  │    Previous check results   │  data["issues"] = []
  │    are now stale            │
  └─────────────┬───────────────┘
                │
                ▼
  ┌─────────────────────────────┐
  │ 8. SAVE + ENQUEUE           │  session.save()
  │    Persist to database      │  Create Directives for
  │    Enqueue check directives │  required_checks_on_commit
  └─────────────────────────────┘
```

### Why checks are cleared

After any modification, the items may have changed. A stock check computed at
`rev=3` is meaningless if the session is now at `rev=4`. Clearing checks
forces the system to re-run them before commit.

### Supported operations

| Op | Required fields | Effect |
|----|----------------|--------|
| `add_line` | `sku`, `qty` | Appends a new item with a generated `line_id` |
| `remove_line` | `line_id` | Removes the item matching `line_id` |
| `set_qty` | `line_id`, `qty` | Updates quantity on an existing item |
| `replace_sku` | `line_id`, `sku` | Swaps the SKU on an existing item |
| `set_data` | `path`, `value` | Sets a value at a dot-separated path in `session.data` |
| `merge_lines` | `from_line_id`, `into_line_id` | Merges two lines with same SKU (sums quantities) |

---

## The Commit Pipeline

`CommitService.commit()` seals a Session into an immutable Order. The pipeline
has two phases: an idempotency check (outside the main transaction) and the
actual commit (inside an atomic transaction).

### Steps

```
  Client sends commit request
       │
       ▼
  ┌─────────────────────────────┐
  │ 1. ACQUIRE IDEMPOTENCY LOCK │  Outside main transaction
  │                             │
  │    Key exists + done?       │──► Return cached response
  │    Key exists + in_progress?│──► Raise CommitError
  │    Key exists + failed?     │──► Allow retry
  │    Key not found?           │──► Create with status="in_progress"
  └─────────────┬───────────────┘
                │
  ══════════════╪══════════════════  BEGIN ATOMIC TRANSACTION
                │
                ▼
  ┌─────────────────────────────┐
  │ 2. LOCK SESSION             │  select_for_update()
  │    Validate state == "open" │
  └─────────────┬───────────────┘
                │
                ▼
  ┌─────────────────────────────┐
  │ 3. VERIFY REQUIRED CHECKS   │  For each required check:
  │    Are checks fresh?        │    check.rev == session.rev?
  │    Are holds not expired?   │    hold.expires_at > now?
  └─────────────┬───────────────┘
                │
                ▼
  ┌─────────────────────────────┐
  │ 4. VERIFY NO BLOCKING       │  Any issue with
  │    ISSUES                   │  blocking == True?
  │                             │  If yes, reject commit.
  └─────────────┬───────────────┘
                │
                ▼
  ┌─────────────────────────────┐
  │ 5. RUN VALIDATORS (commit)  │  Pure checks, no IO
  │    Final gate before seal   │
  └─────────────┬───────────────┘
                │
                ▼
  ┌─────────────────────────────┐
  │ 6. VALIDATE SESSION HAS     │  session.items must
  │    ITEMS                    │  not be empty
  └─────────────┬───────────────┘
                │
                ▼
  ┌─────────────────────────────┐
  │ 7. CREATE ORDER             │  Order(ref, channel,
  │    + ORDER ITEMS            │    snapshot, total_q)
  │    + ORDER EVENT            │  OrderItem per line
  │                             │  OrderEvent(type="created")
  └─────────────┬───────────────┘
                │
                ▼
  ┌─────────────────────────────┐
  │ 8. MARK SESSION COMMITTED   │  state = "committed"
  │                             │  committed_at = now
  │                             │  commit_token = idempotency_key
  └─────────────┬───────────────┘
                │
                ▼
  ┌─────────────────────────────┐
  │ 9. ENQUEUE POST-COMMIT      │  stock.commit
  │    DIRECTIVES               │  payment.capture
  │    (per channel config)     │  (any custom topics)
  └─────────────────────────────┘
                │
  ══════════════╪══════════════════  END ATOMIC TRANSACTION
                │
                ▼
  ┌─────────────────────────────┐
  │ 10. CACHE IN IDEMPOTENCY    │  idem.status = "done"
  │     KEY                     │  idem.response_body = result
  └─────────────────────────────┘
```

### The Order snapshot

The Order stores a JSON snapshot of the Session at commit time:

```python
snapshot = {
    "items": session.items,     # Full item list with prices
    "data": session.data,       # checks, issues, customer data, etc.
    "pricing": session.pricing, # Pricing summary
    "rev": session.rev,         # Rev at commit time
}
```

This allows full reconstruction of the session state for auditing or dispute
resolution, even after the Session row is archived or deleted.

### Idempotency semantics

| Scenario | Behavior |
|----------|----------|
| First call, success | Creates Order, caches response, returns 201 |
| Same key, previous success | Returns cached response, 200 |
| Same key, previous failure | Allows retry (resets to `in_progress`) |
| Same key, currently in progress | Rejects with `CommitError(code="in_progress")` |
| Orphaned key (expired `in_progress`) | Allows retry |

---

## Directive Processing

Directives are async tasks created by the modify and commit pipelines.
They follow at-least-once delivery semantics.

### Lifecycle

```
  ┌──────────────────────────────────────┐
  │                                      │
  ▼                                      │
queued ──► running ──► done              │
               │                          │
               └──► failed ──(retry)──────┘
```

| Status | Meaning |
|--------|---------|
| `queued` | Created, waiting to be picked up |
| `running` | Handler is executing (`started_at` is set) |
| `done` | Completed successfully |
| `failed` | Handler raised an exception. Can be retried. |

### Handler registration

Handlers are registered in the global Registry, typically in `AppConfig.ready()`:

```python
class MyAppConfig(AppConfig):
    def ready(self):
        from omniman import registry
        from omniman.contrib.stock.handlers import StockHoldHandler, StockCommitHandler
        from omniman.contrib.stock.adapters.stockman import StockmanBackend
        from myapp.models import Product

        backend = StockmanBackend(product_resolver=lambda sku: Product.objects.get(sku=sku))
        registry.register_directive_handler(StockHoldHandler(backend=backend))
        registry.register_directive_handler(StockCommitHandler(backend=backend))
```

Each topic can have exactly one handler. Registering a second handler for the
same topic raises `ValueError`.

### Processing directives

Directives are processed via the management command:

```bash
# Single pass (for cron)
python manage.py process_directives

# Continuous worker (for supervisor/systemd)
python manage.py process_directives --watch --interval 2

# Filter by topic
python manage.py process_directives --topic stock.hold --topic stock.commit

# Limit batch size
python manage.py process_directives --limit 100
```

The processing loop:

```
  ┌──────────────────────────────────────┐
  │  SELECT directives                   │
  │  WHERE status = "queued"             │
  │    AND available_at <= now()          │
  │    AND topic IN (registered handlers)│
  │  ORDER BY created_at ASC             │
  │  LIMIT N                             │
  │  FOR UPDATE SKIP LOCKED              │
  └─────────────┬────────────────────────┘
                │
                ▼  (for each directive)
  ┌─────────────────────────────────────┐
  │  Mark status = "running"            │
  │  Set started_at = now()             │
  │  Increment attempts                 │
  └─────────────┬───────────────────────┘
                │
                ▼
  ┌─────────────────────────────────────┐
  │  Call handler.handle(               │
  │      message=directive,             │
  │      ctx={...}                      │
  │  )                                  │
  └─────────────┬───────────────────────┘
                │
           success?
           /     \
          yes     no
          │       │
          ▼       ▼
       [done]  [failed]
               last_error = str(exc)
```

### Exponential backoff (deferred execution)

When a handler fails, the directive can be rescheduled with a future
`available_at` to implement exponential backoff:

```python
directive.available_at = timezone.now() + timedelta(minutes=2 ** directive.attempts)
directive.status = "queued"  # or "failed" depending on strategy
directive.save()
```

The processing loop skips directives whose `available_at` is in the future.

### Stuck directive reaping

A directive stuck in `running` status (e.g., worker crashed mid-execution)
can be detected by checking `started_at`:

```python
stuck = Directive.objects.filter(
    status="running",
    started_at__lte=timezone.now() - timedelta(minutes=5),
)
for d in stuck:
    d.status = "queued"  # Re-queue for another attempt
    d.save(update_fields=["status", "updated_at"])
```

Production setups should run a periodic job (cron or management command) to
reap stuck directives.

### Existing topics

| Topic | When created | What the handler does |
|-------|-------------|----------------------|
| `stock.hold` | After `modify_session()` (if `required_checks_on_commit` includes `"stock"`) | Checks availability, creates holds, writes check result back to session |
| `stock.commit` | After `commit()` (if `post_commit_directives` includes `"stock.commit"`) | Fulfills holds (confirms + decrements inventory) |
| `payment.capture` | After `commit()` (if `post_commit_directives` includes `"payment.capture"`) | Captures previously authorized payment |
| `payment.refund` | Created programmatically | Refunds a captured payment |

---

## Fulfillment Model

Orders can be fulfilled in parts. The `Fulfillment` model tracks shipments:

```
  Order
    │
    ├── Fulfillment #1 (status: shipped)
    │     ├── FulfillmentItem: SKU-A x 2
    │     └── FulfillmentItem: SKU-B x 1
    │
    └── Fulfillment #2 (status: pending)
          └── FulfillmentItem: SKU-C x 3
```

### Fulfillment lifecycle

```
  pending ──► in_progress ──► shipped ──► delivered
                  │
                  └──► cancelled
```

### Partial fulfillment

A single Order can have multiple Fulfillments. Each Fulfillment contains a
subset of the Order's items via `FulfillmentItem`, which references an
`OrderItem` and carries its own `qty`:

```python
# Order with 3 items
order = Order.objects.get(ref="ORD-20260223-ABC123")

# Ship 2 items now
f1 = Fulfillment.objects.create(order=order, status="pending")
FulfillmentItem.objects.create(fulfillment=f1, order_item=item_a, qty=2)
FulfillmentItem.objects.create(fulfillment=f1, order_item=item_b, qty=1)

# Ship remaining item later
f2 = Fulfillment.objects.create(order=order, status="pending")
FulfillmentItem.objects.create(fulfillment=f2, order_item=item_c, qty=3)
```

### Use cases

| Scenario | Fulfillments |
|----------|-------------|
| Single shipment | 1 Fulfillment with all items |
| Split shipping | N Fulfillments, each with a subset of items |
| Partial availability | Ship available items now, backorder rest |
| Multi-warehouse | 1 Fulfillment per source location |

The Order's overall status is driven by the channel's state machine and is
independent of fulfillment status. Application code can transition the Order
status based on fulfillment progress (e.g., all fulfillments delivered implies
order completed).

---

## Full Pipeline Diagram

```
  ┌─────────┐
  │  Client  │
  └────┬─────┘
       │
       │  POST /sessions              ┌──────────────────────┐
       ├──────────────────────────────►│  Create Session      │
       │                               │  state=open, rev=0   │
       │                               └──────────┬───────────┘
       │                                          │
       │  POST /sessions/{key}/modify             │
       ├──────────────────────────────►┌───────────▼──────────┐
       │                               │  ModifyService       │
       │                               │  apply ops           │
       │                               │  run modifiers       │◄─── PricingBackend
       │                               │  run validators      │
       │                               │  rev++               │
       │                               │  clear checks        │
       │                               │  save                │
       │                               │  enqueue directives  │───► Directive(stock.hold)
       │                               └───────────┬──────────┘          │
       │                                           │                     │
       │                               ┌───────────▼──────────┐         │
       │                               │  (repeat modify)     │         │
       │                               └───────────┬──────────┘         │
       │                                           │                     ▼
       │                                           │         ┌───────────────────┐
       │                                           │         │ StockHoldHandler   │
       │                                           │         │ check availability │
       │                                           │         │ create holds       │
       │                                           │         │ write check result │
       │                                           │         │ (rev-stamped)      │
       │                                           │         └───────────────────┘
       │                                           │
       │  POST /sessions/{key}/commit              │
       ├──────────────────────────────►┌───────────▼──────────┐
       │                               │  CommitService       │
       │                               │  verify idempotency  │
       │                               │  verify checks fresh │
       │                               │  verify no blockers  │
       │                               │  run validators      │
       │                               │  create Order        │
       │                               │  mark committed      │
       │                               │  enqueue directives  │───► Directive(stock.commit)
       │                               └───────────┬──────────┘───► Directive(payment.capture)
       │                                           │                     │
       │                                           │                     ▼
       │                                           │         ┌────────────────────┐
       │                                           │         │ StockCommitHandler  │
       │                                           │         │ fulfill holds       │
       │                                           │         ├────────────────────┤
       │                                           │         │ PaymentCapture     │
       │                                           │         │ Handler            │
       │                                           │         │ capture payment    │
       │                                           │         └────────────────────┘
       │                                           │
       │  GET /orders/{ref}                        ▼
       ├──────────────────────────────►┌──────────────────────┐
       │                               │  Order (immutable)   │
       │                               │  status transitions  │
       │                               │  via state machine   │
       │                               └──────────────────────┘
       │
  ┌────▼─────┐
  │  Client  │
  └──────────┘
```
