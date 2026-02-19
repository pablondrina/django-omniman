Status Flow
===========

Omniman uses a configurable state machine for order status transitions.
Each channel can define its own status flow to match business requirements.


Canonical Statuses
------------------

Omniman defines semantic statuses that represent real order states:

.. list-table:: Canonical Statuses
   :header-rows: 1
   :widths: 15 45 25 15

   * - Status
     - Description
     - Typical Next
     - Timestamp
   * - ``new``
     - Order received, awaiting processing
     - confirmed, cancelled
     - ``created_at``
   * - ``confirmed``
     - Confirmed (availability OK, payment may be pending or received)
     - processing, ready, cancelled
     - ``confirmed_at``
   * - ``processing``
     - In preparation/production
     - ready, cancelled
     - ``processing_at``
   * - ``ready``
     - Ready for pickup/dispatch
     - dispatched, completed
     - ``ready_at``
   * - ``dispatched``
     - In transit (delivery only)
     - delivered, returned
     - ``dispatched_at``
   * - ``delivered``
     - Received by customer
     - completed, returned
     - ``delivered_at``
   * - ``completed``
     - Finalized successfully (terminal)
     - —
     - ``completed_at``
   * - ``cancelled``
     - Cancelled for any reason (terminal)
     - —
     - ``cancelled_at``
   * - ``returned``
     - Returned after delivery
     - completed
     - —


Flows by Channel Type
---------------------

Different channel types have different typical flows:

External Channels (iFood, Rappi)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Orders arrive pre-paid and pre-confirmed from the external platform.
The Bridge translates external events to Order transitions.

.. code-block:: text

   Order received → NEW → CONFIRMED (auto, already paid)
        → PROCESSING → READY → DISPATCHED → COMPLETED

   Key points:
   - Orders arrive already paid
   - Auto-confirm possible (Channel.config["auto_transitions"]["on_create"])
   - Bridge translates events → actions, not status → status

E-commerce (Shop)
~~~~~~~~~~~~~~~~~

Orders start as purchase intentions, require validation and payment.

.. code-block:: text

   Intention → NEW → (validate availability) → CONFIRMED → (payment)
        → PROCESSING → READY → [DISPATCHED] → COMPLETED

   Key points:
   - NEW = intention to purchase
   - Validation before CONFIRMED
   - DISPATCHED only for delivery orders
   - Payment may happen at various stages

PDV (Point of Sale)
~~~~~~~~~~~~~~~~~~~

Simplified flow for in-person sales, often synchronous.

.. code-block:: text

   Sale → NEW → CONFIRMED → COMPLETED (almost immediate)

   Key points:
   - Simplified, near-synchronous flow
   - Payment usually immediate
   - May skip some intermediate statuses


Lifecycle Timestamps
--------------------

Each status transition automatically records a timestamp for B.I. and auditing:

.. code-block:: python

   order = Order.objects.get(ref="ORD-123")

   # Check how long preparation took
   if order.ready_at and order.processing_at:
       prep_time = order.ready_at - order.processing_at
       print(f"Preparation took: {prep_time}")

   # Check delivery time
   if order.delivered_at and order.dispatched_at:
       delivery_time = order.delivered_at - order.dispatched_at
       print(f"Delivery took: {delivery_time}")

The timestamps are set automatically by ``transition_status()``:

.. code-block:: python

   order.transition_status("confirmed", actor="admin")
   # order.confirmed_at is now set

   order.transition_status("processing", actor="kitchen")
   # order.processing_at is now set

.. note::

   Timestamps are only set once (on first transition to that status).
   Subsequent transitions to the same status won't overwrite.


Future Extension: REVIEW Status
-------------------------------

If validation of alternatives becomes necessary when products are unavailable,
a ``review`` status can be added between NEW and CONFIRMED:

.. code-block:: text

   NEW → REVIEW (alternatives suggested) → CONFIRMED (user approves)

This is not currently implemented. Availability validation is done before commit.
The idea is documented for future reference if the need arises


Configuring Status Flow
-----------------------

In Channel Config
~~~~~~~~~~~~~~~~~

.. code-block:: python

   Channel.objects.create(
       code="ecommerce",
       config={
           "order_flow": {
               "initial_status": "pending_payment",
               "transitions": {
                   "pending_payment": ["confirmed", "cancelled", "expired"],
                   "confirmed": ["processing", "cancelled"],
                   "processing": ["shipped"],
                   "shipped": ["delivered", "returned"],
                   "delivered": ["completed", "returned"],
                   "returned": ["refunded"],
                   "refunded": ["completed"],
                   "completed": [],
                   "cancelled": [],
                   "expired": [],
               },
               "terminal_statuses": ["completed", "cancelled", "expired"],
               "auto_transitions": {
                   "on_payment_confirm": "confirmed",
                   "on_stock_commit": null,  # Don't auto-transition
               },
           },
       },
   )

Flow Visualization
~~~~~~~~~~~~~~~~~~

.. code-block:: text

   E-commerce Flow:

   pending_payment ──┬──▶ confirmed ───▶ processing ───▶ shipped
                     │         │                           │
                     │         │                           ▼
                     │         │                       delivered
                     │         │                           │
                     │         ▼                           ▼
                     └──▶ cancelled                    completed
                               │                           │
                               │                           ▼
                               └──────────────────────▶ returned ───▶ refunded


Transitions API
---------------

Using transition_status
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from omniman.models import Order
   from omniman.exceptions import InvalidTransition

   order = Order.objects.get(ref="ORD-123")

   # Valid transition
   order.transition_status("confirmed", actor="payment-webhook")

   # Invalid transition raises exception
   try:
       order.transition_status("completed")  # Can't skip steps
   except InvalidTransition as e:
       print(f"Error: {e}")  # "Transition confirmed → completed not allowed"

Checking Valid Transitions
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   def get_valid_transitions(order):
       """Get list of valid next statuses."""
       flow = order.channel.config.get("order_flow", {})
       transitions = flow.get("transitions", {})
       return transitions.get(order.status, [])

   # Usage
   valid = get_valid_transitions(order)
   print(f"Can transition to: {valid}")


Auto-Transitions
----------------

Configure automatic transitions based on events:

.. code-block:: python

   {
       "order_flow": {
           "auto_transitions": {
               # When stock.commit completes
               "on_stock_commit": "confirmed",

               # When payment.confirm completes
               "on_payment_confirm": "confirmed",

               # When all items ready
               "on_items_ready": "ready",

               # When delivery confirmed
               "on_delivery_confirm": "delivered",
           },
       },
   }

Handler Implementation
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # handlers.py

   from omniman.registry import registry
   from omniman.models import Order

   @registry.register_handler("stock.commit")
   class StockCommitHandler:
       def handle(self, directive, ctx):
           # ... process stock

           # Check for auto-transition
           order = Order.objects.get(ref=directive.payload["order_ref"])
           flow = order.channel.config.get("order_flow", {})
           auto = flow.get("auto_transitions", {})

           if auto.get("on_stock_commit"):
               order.transition_status(
                   auto["on_stock_commit"],
                   actor="stock.commit",
               )


Terminal Statuses
-----------------

Terminal statuses cannot be changed:

.. code-block:: python

   {
       "order_flow": {
           "terminal_statuses": ["completed", "cancelled", "expired"],
       },
   }

Checking Terminal
~~~~~~~~~~~~~~~~~

.. code-block:: python

   def is_terminal(order):
       """Check if order is in terminal status."""
       flow = order.channel.config.get("order_flow", {})
       terminal = flow.get("terminal_statuses", ["completed", "cancelled"])
       return order.status in terminal


Status Events
-------------

Events are emitted on status changes:

.. code-block:: python

   from omniman.models import OrderEvent

   # After transition
   order.transition_status("confirmed", actor="admin")

   # Event created automatically
   event = OrderEvent.objects.filter(
       order=order,
       event_type="status_changed",
   ).latest("created_at")

   print(event.data)
   # {
   #     "old_status": "created",
   #     "new_status": "confirmed",
   #     "actor": "admin",
   # }


Custom Hooks
------------

Register hooks for status changes:

.. code-block:: python

   # hooks.py

   from omniman.registry import registry

   @registry.register_hook("order.status_changed")
   def on_status_changed(order, old_status, new_status, actor):
       """Handle order status change."""

       if new_status == "confirmed":
           # Send confirmation email
           send_order_confirmation(order)

       elif new_status == "shipped":
           # Send tracking info
           send_tracking_notification(order)

       elif new_status == "cancelled":
           # Process refund
           create_refund_directive(order)


Business-Specific Flows
-----------------------

Restaurant
~~~~~~~~~~

.. code-block:: python

   {
       "order_flow": {
           "initial_status": "received",
           "transitions": {
               "received": ["accepted", "rejected"],
               "accepted": ["preparing"],
               "preparing": ["ready"],
               "ready": ["picked_up", "delivered"],
               "picked_up": ["completed"],
               "delivered": ["completed"],
               "rejected": [],
               "completed": [],
           },
           "terminal_statuses": ["rejected", "completed"],
       },
       "terminology": {
           "received": "Pedido Recebido",
           "accepted": "Aceito",
           "preparing": "Em Preparo",
           "ready": "Pronto",
           "picked_up": "Retirado",
           "delivered": "Entregue",
       },
   }

Subscription Service
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   {
       "order_flow": {
           "initial_status": "pending",
           "transitions": {
               "pending": ["active", "cancelled"],
               "active": ["paused", "cancelled", "expired"],
               "paused": ["active", "cancelled"],
               "expired": ["renewed"],
               "renewed": ["active"],
               "cancelled": [],
           },
           "terminal_statuses": ["cancelled"],
       },
   }

Service/Appointment
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   {
       "order_flow": {
           "initial_status": "scheduled",
           "transitions": {
               "scheduled": ["confirmed", "cancelled", "rescheduled"],
               "confirmed": ["in_progress", "no_show", "cancelled"],
               "rescheduled": ["confirmed", "cancelled"],
               "in_progress": ["completed"],
               "no_show": [],
               "completed": [],
               "cancelled": [],
           },
           "terminal_statuses": ["completed", "no_show", "cancelled"],
       },
   }


Status Display
--------------

Terminology Mapping
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   def get_status_display(order):
       """Get localized status name."""
       terminology = order.channel.config.get("terminology", {})
       return terminology.get(order.status, order.status.title())

Admin Display
~~~~~~~~~~~~~

.. code-block:: python

   from django.contrib import admin
   from django.utils.html import format_html

   @admin.register(Order)
   class OrderAdmin(admin.ModelAdmin):

       @admin.display(description="Status")
       def status_badge(self, obj):
           colors = {
               "created": "#3498db",
               "confirmed": "#27ae60",
               "processing": "#f39c12",
               "completed": "#2ecc71",
               "cancelled": "#e74c3c",
           }
           color = colors.get(obj.status, "#95a5a6")
           return format_html(
               '<span style="background: {}; color: white; '
               'padding: 2px 8px; border-radius: 4px;">{}</span>',
               color,
               obj.status.upper(),
           )


Testing Status Flow
-------------------

.. code-block:: python

   import pytest
   from omniman.models import Order, Channel
   from omniman.exceptions import InvalidTransition

   @pytest.fixture
   def channel():
       return Channel.objects.create(
           code="test",
           config={
               "order_flow": {
                   "initial_status": "created",
                   "transitions": {
                       "created": ["confirmed", "cancelled"],
                       "confirmed": ["completed"],
                       "completed": [],
                       "cancelled": [],
                   },
                   "terminal_statuses": ["completed", "cancelled"],
               },
           },
       )

   def test_valid_transition(channel, order):
       order.transition_status("confirmed", actor="test")
       assert order.status == "confirmed"

   def test_invalid_transition(channel, order):
       with pytest.raises(InvalidTransition):
           order.transition_status("completed")  # Skip confirmed

   def test_terminal_status(channel, order):
       order.transition_status("cancelled", actor="test")
       with pytest.raises(InvalidTransition):
           order.transition_status("created")


Best Practices
--------------

1. **Plan Before Implementing**: Design your status flow on paper before coding.

2. **Keep It Simple**: Avoid too many statuses; combine related states.

3. **Use Terminal Statuses**: Clearly define which statuses are final.

4. **Add Events**: Use events for status changes to enable integrations.

5. **Test Edge Cases**: Test invalid transitions and terminal status behavior.


See Also
--------

- :doc:`orders` - Order model and operations
- :doc:`channels` - Channel configuration
- :doc:`../reference/settings` - Configuration reference
