Quickstart
==========

This guide walks you through creating your first session and order using Omniman.


Prerequisites
-------------

Make sure you have completed the :doc:`installation` guide.


Step 1: Create a Channel
------------------------

Channels represent sales sources (POS, e-commerce, iFood, etc.). Each channel can have
its own configuration for pricing, workflows, and integrations.

.. code-block:: python

   from omniman.models import Channel

   channel = Channel.objects.create(
       code="quickstart",
       name="Quickstart Channel",
       config={
           "pricing_policy": "internal",  # Use prices from ops
           "order_flow": {
               "initial_status": "created",
               "transitions": {
                   "created": ["confirmed", "cancelled"],
                   "confirmed": ["completed"],
               },
           },
       },
   )


Step 2: Create a Session
------------------------

Sessions represent mutable pre-commit state (baskets, tabs, draft orders, etc.).
They hold items until committed to become an Order.

.. code-block:: python

   from omniman.models import Session

   session = Session.objects.create(
       session_key="SESS-001",
       channel=channel,
       state="open",
       handle_type="customer",
       handle_ref="cust-123",
   )


Step 3: Add Items
-----------------

Use the ``ModifyService`` to add, update, or remove items from a session:

.. code-block:: python

   from omniman.services import ModifyService

   # Add items
   result = ModifyService.modify_session(
       session_key="SESS-001",
       channel_code="quickstart",
       ops=[
           {
               "op": "add_line",
               "sku": "COFFEE-001",
               "name": "Espresso",
               "qty": 2,
               "unit_price_q": 500,  # R$ 5.00 in cents
           },
           {
               "op": "add_line",
               "sku": "CAKE-001",
               "name": "Chocolate Cake",
               "qty": 1,
               "unit_price_q": 1500,  # R$ 15.00 in cents
           },
       ],
   )

   # Check items
   session.refresh_from_db()
   for item in session.items:
       print(f"{item['qty']}x {item['name']} = R$ {item['line_total_q']/100:.2f}")

Output::

   2x Espresso = R$ 10.00
   1x Chocolate Cake = R$ 15.00


Step 4: Update an Item
----------------------

Modify existing items by their ``line_id``:

.. code-block:: python

   # Get the line_id of the first item
   espresso_line_id = session.items[0]["line_id"]

   # Update quantity
   ModifyService.modify_session(
       session_key="SESS-001",
       channel_code="quickstart",
       ops=[
           {
               "op": "set_qty",
               "line_id": espresso_line_id,
               "qty": 3,
           },
       ],
   )


Step 5: Commit the Session
--------------------------

When the customer is ready to checkout, commit the session to create an Order:

.. code-block:: python

   from omniman.services import CommitService

   result = CommitService.commit(
       session_key="SESS-001",
       channel_code="quickstart",
   )

   print(f"Order created: {result['order_ref']}")
   print(f"Total: R$ {result['total_q']/100:.2f}")

Output::

   Order created: ORD-20251218-ABC123
   Total: R$ 30.00


Step 6: View the Order
----------------------

.. code-block:: python

   from omniman.models import Order

   order = Order.objects.get(ref=result["order_ref"])
   print(f"Order: {order.ref}")
   print(f"Status: {order.status}")
   print(f"Channel: {order.channel.code}")
   print(f"Items: {len(order.items)}")


Step 7: Transition Order Status
-------------------------------

.. code-block:: python

   # Confirm the order
   order.transition_status("confirmed", actor="admin")
   print(f"New status: {order.status}")

   # Complete the order
   order.transition_status("completed", actor="admin")
   print(f"Final status: {order.status}")


Using the REST API
------------------

All operations are also available via the REST API:

Create Session
~~~~~~~~~~~~~~

.. code-block:: http

   POST /api/sessions/ HTTP/1.1
   Content-Type: application/json

   {
       "channel_code": "quickstart",
       "handle_type": "customer",
       "handle_ref": "cust-123"
   }

Response:

.. code-block:: json

   {
       "session_key": "SESS-ABC123",
       "state": "open",
       "items": [],
       "total_q": 0
   }

Modify Session
~~~~~~~~~~~~~~

.. code-block:: http

   POST /api/sessions/SESS-ABC123/modify/ HTTP/1.1
   Content-Type: application/json

   {
       "channel_code": "quickstart",
       "ops": [
           {"op": "add_line", "sku": "COFFEE-001", "qty": 2, "unit_price_q": 500}
       ]
   }

Commit Session
~~~~~~~~~~~~~~

.. code-block:: http

   POST /api/sessions/SESS-ABC123/commit/ HTTP/1.1
   Content-Type: application/json

   {
       "channel_code": "quickstart"
   }


What's Next?
------------

- :doc:`tutorial` - Complete order flow tutorial
- :doc:`../guides/channels` - Configure channels for different use cases
- :doc:`../guides/sessions` - Advanced session management
- :doc:`../api/rest-api` - Full REST API reference
