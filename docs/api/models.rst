Models Reference
================

This page documents all Omniman Django models.


Channel
-------

.. py:class:: omniman.models.Channel

   Sales channel configuration.

   Channels represent different sales sources: POS, e-commerce, iFood, etc.
   Each channel can have its own configuration for pricing, workflows, and integrations.

   **Fields:**

   .. py:attribute:: code
      :type: CharField

      Unique identifier for the channel (max 64 chars).

   .. py:attribute:: name
      :type: CharField

      Display name (max 128 chars).

   .. py:attribute:: pricing_policy
      :type: CharField

      How prices are determined. Choices: ``internal``, ``external``.

   .. py:attribute:: edit_policy
      :type: CharField

      Session edit policy. Choices: ``open``, ``locked``.

   .. py:attribute:: display_order
      :type: PositiveIntegerField

      Order for admin display (default: 0).

   .. py:attribute:: config
      :type: JSONField

      JSON configuration for the channel.

   .. py:attribute:: is_active
      :type: BooleanField

      Whether channel is active (default: True).

   .. py:attribute:: created_at
      :type: DateTimeField

      Creation timestamp.

   **Example:**

   .. code-block:: python

      from omniman.models import Channel

      channel = Channel.objects.create(
          code="pos",
          name="Point of Sale",
          pricing_policy="internal",
          config={
              "order_flow": {
                  "initial_status": "new",
                  "transitions": {
                      "new": ["confirmed", "cancelled"],
                      "confirmed": ["completed"],
                  },
              },
          },
      )


Session
-------

.. py:class:: omniman.models.Session

   Pre-commit mutable unit (cart/draft).

   Sessions hold items until committed to become an Order.

   **Fields:**

   .. py:attribute:: session_key
      :type: CharField

      Unique session identifier (max 64 chars).

   .. py:attribute:: channel
      :type: ForeignKey

      Related Channel.

   .. py:attribute:: handle_type
      :type: CharField

      Type of owner (e.g., "table", "customer").

   .. py:attribute:: handle_ref
      :type: CharField

      Owner reference (e.g., table number, customer ID).

   .. py:attribute:: state
      :type: CharField

      Session state. Choices: ``open``, ``committed``, ``abandoned``.

   .. py:attribute:: pricing_policy
      :type: CharField

      Pricing policy (inherited from channel).

   .. py:attribute:: edit_policy
      :type: CharField

      Edit policy (inherited from channel).

   .. py:attribute:: rev
      :type: IntegerField

      Revision number, incremented on each modification.

   .. py:attribute:: data
      :type: JSONField

      Session metadata (checks, issues, customer data).

   .. py:attribute:: opened_at
      :type: DateTimeField

      When session was created.

   .. py:attribute:: committed_at
      :type: DateTimeField

      When session was committed (null if not committed).

   **Properties:**

   .. py:attribute:: items
      :type: list[dict]

      List of session items. Getter returns a copy, setter updates SessionItems.

   **Methods:**

   .. py:method:: invalidate_items_cache()

      Clear the cached items list.

   **Example:**

   .. code-block:: python

      from omniman.models import Session

      session = Session.objects.create(
          session_key="SESS-001",
          channel=channel,
          state="open",
          handle_type="table",
          handle_ref="5",
      )

      # Access items
      items = session.items

      # Set items
      session.items = [
          {"sku": "COFFEE", "qty": 2, "unit_price_q": 500}
      ]
      session.save()


SessionItem
-----------

.. py:class:: omniman.models.SessionItem

   Individual item in a session.

   .. note::

      This is an internal implementation detail. Use ``session.items``
      property instead of accessing SessionItem directly.

   **Fields:**

   .. py:attribute:: session
      :type: ForeignKey

      Related Session.

   .. py:attribute:: line_id
      :type: CharField

      Unique line identifier within session.

   .. py:attribute:: sku
      :type: CharField

      Product SKU.

   .. py:attribute:: name
      :type: CharField

      Product display name.

   .. py:attribute:: qty
      :type: DecimalField

      Quantity (12 digits, 3 decimal places).

   .. py:attribute:: unit_price_q
      :type: BigIntegerField

      Unit price in cents.

   .. py:attribute:: line_total_q
      :type: BigIntegerField

      Line total in cents (qty * unit_price_q).

   .. py:attribute:: meta
      :type: JSONField

      Additional metadata.

   **Methods:**

   .. py:method:: to_payload() -> dict

      Convert to dictionary format.


Order
-----

.. py:class:: omniman.models.Order

   Committed order (sealed, immutable).

   Orders are created when a Session is committed.

   **Status Constants:**

   - ``STATUS_NEW`` = "new"
   - ``STATUS_CONFIRMED`` = "confirmed"
   - ``STATUS_PROCESSING`` = "processing"
   - ``STATUS_READY`` = "ready"
   - ``STATUS_DISPATCHED`` = "dispatched"
   - ``STATUS_DELIVERED`` = "delivered"
   - ``STATUS_COMPLETED`` = "completed"
   - ``STATUS_CANCELLED`` = "cancelled"
   - ``STATUS_RETURNED`` = "returned"

   **Fields:**

   .. py:attribute:: ref
      :type: CharField

      Unique order reference (e.g., "ORD-20251218-ABC123").

   .. py:attribute:: channel
      :type: ForeignKey

      Related Channel.

   .. py:attribute:: session_key
      :type: CharField

      Original session key.

   .. py:attribute:: handle_type
      :type: CharField

      Owner type (copied from session).

   .. py:attribute:: handle_ref
      :type: CharField

      Owner reference (copied from session).

   .. py:attribute:: external_ref
      :type: CharField

      External reference (e.g., iFood order ID).

   .. py:attribute:: status
      :type: CharField

      Current order status.

   .. py:attribute:: snapshot
      :type: JSONField

      Session state at commit time.

   .. py:attribute:: currency
      :type: CharField

      Currency code (default: "BRL").

   .. py:attribute:: total_q
      :type: BigIntegerField

      Total amount in cents.

   .. py:attribute:: created_at
      :type: DateTimeField

      Creation timestamp.

   **Methods:**

   .. py:method:: get_transitions() -> dict[str, list[str]]

      Get status transition map from channel config or defaults.

   .. py:method:: get_terminal_statuses() -> list[str]

      Get list of terminal statuses.

   .. py:method:: get_allowed_transitions() -> list[str]

      Get valid next statuses from current status.

   .. py:method:: can_transition_to(new_status: str) -> bool

      Check if transition to new_status is allowed.

   .. py:method:: transition_status(new_status: str, actor: str = "system") -> None

      Transition to new status with validation.

      :param new_status: Target status
      :param actor: Who triggered the transition
      :raises InvalidTransition: If transition not allowed

   .. py:method:: emit_event(event_type: str, actor: str = "system", payload: dict = None) -> OrderEvent

      Create an audit event for this order.

   **Example:**

   .. code-block:: python

      from omniman.models import Order

      order = Order.objects.get(ref="ORD-20251218-ABC123")

      # Check valid transitions
      allowed = order.get_allowed_transitions()

      # Transition status
      order.transition_status("confirmed", actor="admin")

      # Emit event
      order.emit_event("note_added", actor="support", payload={"note": "Customer called"})


OrderItem
---------

.. py:class:: omniman.models.OrderItem

   Individual item in an order.

   **Fields:**

   .. py:attribute:: order
      :type: ForeignKey

      Related Order.

   .. py:attribute:: line_id
      :type: CharField

      Line identifier (from session).

   .. py:attribute:: sku
      :type: CharField

      Product SKU.

   .. py:attribute:: name
      :type: CharField

      Product display name.

   .. py:attribute:: qty
      :type: DecimalField

      Quantity.

   .. py:attribute:: unit_price_q
      :type: BigIntegerField

      Unit price in cents.

   .. py:attribute:: line_total_q
      :type: BigIntegerField

      Line total in cents.

   .. py:attribute:: meta
      :type: JSONField

      Additional metadata.


OrderEvent
----------

.. py:class:: omniman.models.OrderEvent

   Append-only audit log for orders.

   **Fields:**

   .. py:attribute:: order
      :type: ForeignKey

      Related Order.

   .. py:attribute:: type
      :type: CharField

      Event type (e.g., "status_changed", "note_added").

   .. py:attribute:: actor
      :type: CharField

      Who triggered the event.

   .. py:attribute:: payload
      :type: JSONField

      Event data.

   .. py:attribute:: created_at
      :type: DateTimeField

      Event timestamp.

   **Example:**

   .. code-block:: python

      from omniman.models import OrderEvent

      # List events for an order
      events = OrderEvent.objects.filter(order=order).order_by("created_at")

      for event in events:
          print(f"{event.type} by {event.actor} at {event.created_at}")


Directive
---------

.. py:class:: omniman.models.Directive

   Async task/command (at-least-once delivery).

   **Fields:**

   .. py:attribute:: topic
      :type: CharField

      Directive topic (e.g., "stock.commit", "payment.confirm").

   .. py:attribute:: status
      :type: CharField

      Execution status. Choices: ``queued``, ``running``, ``done``, ``failed``.

   .. py:attribute:: payload
      :type: JSONField

      Directive data.

   .. py:attribute:: attempts
      :type: IntegerField

      Number of execution attempts.

   .. py:attribute:: available_at
      :type: DateTimeField

      When directive becomes available for processing.

   .. py:attribute:: last_error
      :type: TextField

      Last error message (if failed).

   .. py:attribute:: created_at
      :type: DateTimeField

      Creation timestamp.

   **Example:**

   .. code-block:: python

      from omniman.models import Directive

      # Create directive
      Directive.objects.create(
          topic="notification.email",
          payload={
              "order_ref": "ORD-123",
              "template": "order_confirmation",
          },
      )

      # Query pending directives
      pending = Directive.objects.filter(status="queued")


IdempotencyKey
--------------

.. py:class:: omniman.models.IdempotencyKey

   Deduplication/replay guard for idempotent operations.

   **Fields:**

   .. py:attribute:: scope
      :type: CharField

      Operation scope (e.g., "commit:pos").

   .. py:attribute:: key
      :type: CharField

      Unique key within scope.

   .. py:attribute:: status
      :type: CharField

      Operation status. Choices: ``in_progress``, ``done``, ``failed``.

   .. py:attribute:: response_code
      :type: IntegerField

      HTTP response code (if applicable).

   .. py:attribute:: response_body
      :type: JSONField

      Cached response body.

   .. py:attribute:: expires_at
      :type: DateTimeField

      When key expires.

   .. py:attribute:: created_at
      :type: DateTimeField

      Creation timestamp.


See Also
--------

- :doc:`exceptions` - Exception classes
- :doc:`rest-api` - REST API reference
