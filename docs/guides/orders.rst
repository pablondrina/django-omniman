Orders
======

Orders are the final result of a committed Session. They represent confirmed
transactions that can be processed, shipped, and completed.


Order Lifecycle
---------------

.. code-block:: text

   Session (committed)
         │
         ▼
   ┌─────────────┐
   │   created   │◀─────────────────────┐
   └──────┬──────┘                      │
          │                             │
          ▼                             │
   ┌─────────────┐                      │
   │  confirmed  │                      │
   └──────┬──────┘                      │
          │                             │
          ▼                             │
   ┌─────────────┐                      │
   │ processing  │                      │
   └──────┬──────┘                      │
          │                             │
          ▼                             │
   ┌─────────────┐     ┌─────────────┐  │
   │   ready     │────▶│ dispatched  │  │
   └──────┬──────┘     └──────┬──────┘  │
          │                   │         │
          │                   ▼         │
          │            ┌─────────────┐  │
          │            │  delivered  │  │
          │            └──────┬──────┘  │
          │                   │         │
          ▼                   ▼         │
   ┌─────────────┐     ┌─────────────┐  │
   │  completed  │     │  returned   │──┘
   └─────────────┘     └─────────────┘

          │
          ▼
   ┌─────────────┐
   │  cancelled  │
   └─────────────┘


Order Structure
---------------

.. code-block:: python

   from omniman.models import Order

   order = Order.objects.get(ref="ORD-20251218-ABC123")

   print(f"""
       Ref: {order.ref}
       Channel: {order.channel.code}
       Status: {order.status}
       Total: R$ {order.total_q / 100:.2f}
       Items: {len(order.items)}
       Created: {order.created_at}
   """)

Order Fields
~~~~~~~~~~~~

- **ref**: Unique reference (e.g., ORD-20251218-ABC123)
- **channel**: Associated Channel
- **status**: Current status
- **items**: List of order items (snapshot from session)
- **total_q**: Total amount in cents
- **data**: Metadata (customer info, notes, etc.)
- **session_key**: Original session key
- **external_ref**: External reference (e.g., iFood order ID)

Lifecycle Timestamps
~~~~~~~~~~~~~~~~~~~~

Each order tracks when status transitions occurred:

- **created_at**: When the order was created
- **confirmed_at**: When the order was confirmed
- **processing_at**: When preparation started
- **ready_at**: When the order became ready
- **dispatched_at**: When the order was dispatched
- **delivered_at**: When delivery was confirmed
- **completed_at**: When the order was completed
- **cancelled_at**: When the order was cancelled

These timestamps are automatically set by ``transition_status()`` and are useful
for B.I. and performance analysis:

.. code-block:: python

   # Calculate average preparation time
   from django.db.models import F, Avg, ExpressionWrapper, DurationField

   avg_prep = Order.objects.filter(
       status="completed",
       processing_at__isnull=False,
       ready_at__isnull=False,
   ).annotate(
       prep_duration=ExpressionWrapper(
           F("ready_at") - F("processing_at"),
           output_field=DurationField(),
       )
   ).aggregate(avg=Avg("prep_duration"))

   print(f"Average preparation time: {avg_prep['avg']}")


Order Items
-----------

Items are copied from the session at commit time:

.. code-block:: python

   for item in order.items:
       print(f"""
           SKU: {item['sku']}
           Name: {item['name']}
           Qty: {item['qty']}
           Unit Price: R$ {item['unit_price_q'] / 100:.2f}
           Line Total: R$ {item['line_total_q'] / 100:.2f}
       """)


Status Transitions
------------------

Using transition_status
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from omniman.models import Order
   from omniman.exceptions import InvalidTransition

   order = Order.objects.get(ref="ORD-123")

   try:
       order.transition_status("confirmed", actor="admin")
       print(f"New status: {order.status}")

   except InvalidTransition as e:
       print(f"Invalid transition: {e}")

Actor Parameter
~~~~~~~~~~~~~~~

The ``actor`` parameter tracks who/what triggered the transition:

.. code-block:: python

   # Human operator
   order.transition_status("confirmed", actor="john@example.com")

   # Automated system
   order.transition_status("confirmed", actor="stock.commit")

   # API integration
   order.transition_status("confirmed", actor="ifood-webhook")

Valid Transitions
~~~~~~~~~~~~~~~~~

Check what transitions are valid:

.. code-block:: python

   flow = order.channel.config.get("order_flow", {})
   transitions = flow.get("transitions", {})
   allowed = transitions.get(order.status, [])

   print(f"Current status: {order.status}")
   print(f"Allowed transitions: {allowed}")


Order Events
------------

Events track all order changes:

.. code-block:: python

   from omniman.models import OrderEvent

   events = OrderEvent.objects.filter(order=order).order_by("created_at")

   for event in events:
       print(f"""
           Type: {event.event_type}
           Actor: {event.actor}
           Data: {event.data}
           Created: {event.created_at}
       """)

Event Types
~~~~~~~~~~~

- **status_changed**: Status transition
- **item_added**: Item added (for open orders)
- **item_removed**: Item removed
- **payment_received**: Payment confirmed
- **note_added**: Note or comment added

Creating Events
~~~~~~~~~~~~~~~

.. code-block:: python

   order.emit_event(
       event_type="note_added",
       data={
           "note": "Customer requested express delivery",
           "author": "support@example.com",
       },
       actor="support@example.com",
   )


Querying Orders
---------------

By Status
~~~~~~~~~

.. code-block:: python

   # Pending orders
   pending = Order.objects.filter(status="created")

   # Active orders (not terminal)
   flow = channel.config.get("order_flow", {})
   terminal = flow.get("terminal_statuses", ["completed", "cancelled"])
   active = Order.objects.exclude(status__in=terminal)

By Date
~~~~~~~

.. code-block:: python

   from django.utils.timezone import now
   from datetime import timedelta

   # Today's orders
   today = now().date()
   todays_orders = Order.objects.filter(created_at__date=today)

   # Last 7 days
   week_ago = now() - timedelta(days=7)
   recent = Order.objects.filter(created_at__gte=week_ago)

By Channel
~~~~~~~~~~

.. code-block:: python

   pos_orders = Order.objects.filter(channel__code="pos")

Complex Queries
~~~~~~~~~~~~~~~

.. code-block:: python

   from django.db.models import Sum, Count

   # Daily totals
   daily_totals = Order.objects.filter(
       status="completed",
       created_at__date=today,
   ).aggregate(
       total_revenue=Sum("total_q"),
       order_count=Count("id"),
   )

   # Orders by status
   status_counts = Order.objects.values("status").annotate(
       count=Count("id")
   )


Order Operations
----------------

Cancel Order
~~~~~~~~~~~~

.. code-block:: python

   order = Order.objects.get(ref="ORD-123")

   if "cancelled" in order.channel.config["order_flow"]["transitions"][order.status]:
       order.transition_status("cancelled", actor="admin")

       # Emit cancellation event
       order.emit_event(
           "cancelled",
           {"reason": "Customer request"},
           actor="admin",
       )

       # Release stock holds (via directive)
       from omniman.models import Directive
       Directive.objects.create(
           order=order,
           topic="stock.release",
           payload={"order_ref": order.ref},
       )

Refund Order
~~~~~~~~~~~~

.. code-block:: python

   # Create refund directive
   Directive.objects.create(
       order=order,
       topic="payment.refund",
       payload={
           "order_ref": order.ref,
           "amount_q": order.total_q,
           "reason": "Customer request",
       },
   )


Directives
----------

Directives are async commands for external integrations:

.. code-block:: python

   from omniman.models import Directive

   # List pending directives
   pending = Directive.objects.filter(
       order=order,
       status="pending",
   )

   for directive in pending:
       print(f"""
           Topic: {directive.topic}
           Status: {directive.status}
           Payload: {directive.payload}
       """)

Common Directive Topics
~~~~~~~~~~~~~~~~~~~~~~~

- **stock.commit**: Finalize stock reservation
- **stock.release**: Release stock holds
- **payment.capture**: Capture authorized payment
- **payment.refund**: Process refund
- **notification.send**: Send notification (email, SMS, etc.)
- **delivery.dispatch**: Notify delivery service


Order Data
----------

Store additional metadata:

.. code-block:: python

   order.data.update({
       "customer": {
           "name": "John Doe",
           "email": "john@example.com",
           "phone": "+55 11 99999-9999",
       },
       "delivery": {
           "address": "123 Main St",
           "instructions": "Leave at door",
       },
       "notes": "Birthday cake - add candles",
   })
   order.save()


Admin Actions
-------------

You can add admin actions:

.. code-block:: python

   # In admin.py

   @admin.register(Order)
   class OrderAdmin(ModelAdmin):
       actions = ["action_confirm", "action_process", "action_complete"]

       @action(description="Confirm selected orders")
       def action_confirm(self, request, queryset):
           for order in queryset:
               try:
                   order.transition_status("confirmed", actor=request.user.username)
               except InvalidTransition:
                   messages.warning(request, f"Cannot confirm {order.ref}")


Best Practices
--------------

1. **Use transition_status**: Always use the method for status changes to ensure validation.

2. **Track Actors**: Always provide meaningful actor values for audit trails.

3. **Use Events**: Emit events for significant order changes.

4. **Handle Failures**: Implement retry logic for directive failures.

5. **Clean Terminal Orders**: Archive or delete old terminal orders periodically.


See Also
--------

- :doc:`status-flow` - Detailed status configuration
- :doc:`../api/models` - Order model reference
- :doc:`../integrations/payments` - Payment integration
