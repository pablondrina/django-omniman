# Directives

**Directives** are async commands for side effects like stock management, payments, and notifications. They follow **at-least-once** semantics.

---

## What is a Directive?

A Directive is a task that:

1. Is created after some action (commit, status change, etc.)
2. Is processed asynchronously by a handler
3. May run multiple times (handlers must be idempotent)

```
Session ──commit──► Order ──enqueues──► Directive ──handler──► Side Effect
                                        (stock.commit)        (Stock decremented)
```

---

## Directive Model

```python
from omniman.models import Directive

directive = Directive.objects.create(
    topic="stock.commit",
    status="pending",
    payload={
        "order_ref": "ORD-123",
        "session_key": "SESS-456",
        "items": [...],
    },
)
```

### Fields

| Field | Description |
|-------|-------------|
| `topic` | Directive type (e.g., `stock.commit`, `payment.capture`) |
| `status` | `pending`, `completed`, `failed` |
| `payload` | JSONField with directive-specific data |
| `result` | JSONField with handler result |
| `created_at` | When created |
| `completed_at` | When processed |

---

## Common Topics

| Topic | Purpose | Created When |
|-------|---------|--------------|
| `stock.hold` | Reserve stock | Session modified |
| `stock.commit` | Finalize stock | Order committed |
| `stock.release` | Release hold | Session abandoned |
| `payment.capture` | Capture payment | Order confirmed |
| `payment.refund` | Refund payment | Order cancelled |
| `notification.send` | Send notification | Various events |

---

## How Directives are Created

### Via Channel Config

Channels define `post_commit_directives`:

```python
Channel.objects.create(
    code="ecommerce",
    config={
        "post_commit_directives": ["stock.commit", "notification.order_received"],
    },
)
```

When a session is committed, these directives are automatically enqueued.

### Programmatically

```python
Directive.objects.create(
    topic="custom.sync_erp",
    payload={"order_ref": order.ref},
)
```

---

## Directive Handlers

Handlers process directives. **They must be idempotent.**

### Creating a Handler

```python
from omniman.registry import DirectiveHandler

class StockCommitHandler(DirectiveHandler):
    """Commits stock holds when order is finalized."""

    topic = "stock.commit"

    def handle(self, directive, ctx):
        payload = directive.payload
        order_ref = payload["order_ref"]
        holds = payload.get("holds", [])

        for hold in holds:
            # Check if already processed (idempotency)
            if self.is_hold_fulfilled(hold["hold_id"]):
                continue

            # Process the hold
            self.fulfill_hold(hold)

        return {"processed": len(holds)}

    def is_hold_fulfilled(self, hold_id):
        # Check if this hold was already processed
        ...

    def fulfill_hold(self, hold):
        # Actually decrement stock
        ...
```

### Registering a Handler

```python
# apps.py
from django.apps import AppConfig

class MyAppConfig(AppConfig):
    def ready(self):
        from omniman import registry
        from .handlers import StockCommitHandler

        registry.register_directive_handler(StockCommitHandler())
```

---

## At-Least-Once Semantics

**Invariant I6**: Handlers must be idempotent because directives may run multiple times.

### Why Multiple Runs?

- Worker crashed after processing but before marking complete
- Network timeout caused retry
- Manual "execute now" clicked twice

### Idempotency Pattern

```python
class PaymentCaptureHandler(DirectiveHandler):
    topic = "payment.capture"

    def handle(self, directive, ctx):
        payment_intent_id = directive.payload["payment_intent_id"]

        # Check if already captured
        existing = PaymentCapture.objects.filter(
            intent_id=payment_intent_id,
            status="captured",
        ).first()

        if existing:
            # Already done—return cached result
            return {"capture_id": existing.capture_id}

        # Perform capture
        result = stripe.PaymentIntent.capture(payment_intent_id)

        # Record for idempotency
        PaymentCapture.objects.create(
            intent_id=payment_intent_id,
            capture_id=result.id,
            status="captured",
        )

        return {"capture_id": result.id}
```

---

## Processing Directives

### In Development (Manual)

Use Django Admin to execute directives:

1. Go to Directives list
2. Select pending directives
3. Click "Execute Now"

### In Production (Worker)

Use Celery or similar task queue:

```python
# tasks.py
from celery import shared_task
from omniman.models import Directive
from omniman import registry

@shared_task
def process_directive(directive_id):
    directive = Directive.objects.get(id=directive_id)

    if directive.status != "pending":
        return

    handler = registry.get_directive_handler(directive.topic)
    if not handler:
        directive.status = "failed"
        directive.result = {"error": f"No handler for {directive.topic}"}
        directive.save()
        return

    try:
        result = handler.handle(directive, ctx={"actor": "celery"})
        directive.status = "completed"
        directive.result = result
        directive.completed_at = timezone.now()
    except Exception as e:
        directive.status = "failed"
        directive.result = {"error": str(e)}

    directive.save()
```

### Polling Worker

Alternative to Celery for simpler setups:

```python
# management/commands/process_directives.py
from django.core.management.base import BaseCommand
from omniman.models import Directive
from omniman import registry
import time

class Command(BaseCommand):
    def handle(self, *args, **options):
        while True:
            pending = Directive.objects.filter(status="pending").first()

            if pending:
                self.process(pending)
            else:
                time.sleep(5)  # Poll interval

    def process(self, directive):
        handler = registry.get_directive_handler(directive.topic)
        if handler:
            try:
                result = handler.handle(directive, ctx={})
                directive.status = "completed"
                directive.result = result
            except Exception as e:
                directive.status = "failed"
                directive.result = {"error": str(e)}
            directive.save()
```

---

## Handling Failures

### Retry Logic

```python
class RetryableHandler(DirectiveHandler):
    topic = "notification.send"
    max_retries = 3

    def handle(self, directive, ctx):
        retries = directive.payload.get("_retries", 0)

        try:
            self.send_notification(directive.payload)
            return {"sent": True}
        except TemporaryError as e:
            if retries < self.max_retries:
                # Re-enqueue with incremented retry count
                Directive.objects.create(
                    topic=self.topic,
                    payload={**directive.payload, "_retries": retries + 1},
                )
                return {"retrying": True, "attempt": retries + 1}
            raise
```

### Dead Letter Queue

Track failed directives for investigation:

```python
failed = Directive.objects.filter(
    status="failed",
    created_at__gte=timezone.now() - timedelta(days=1),
)

for d in failed:
    print(f"{d.topic}: {d.result.get('error')}")
```

---

## Best Practices

1. **Always be idempotent**: Check if work was already done
2. **Store idempotency markers**: Use a separate table or payload field
3. **Keep handlers focused**: One handler, one responsibility
4. **Log extensively**: Track what happened for debugging
5. **Handle partial failures**: If 3 of 5 items fail, record which ones
6. **Use transactions wisely**: Don't hold long transactions
