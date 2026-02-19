Sessions
========

Sessions represent mutable pre-commit state in Omniman: baskets, tabs, draft orders, etc.
They hold items until committed to become an Order.


Session Lifecycle
-----------------

.. code-block:: text

   ┌─────────┐     ┌─────────┐     ┌───────────┐
   │  open   │────▶│ committed│────▶│   Order   │
   └─────────┘     └─────────┘     └───────────┘
        │
        ▼
   ┌─────────┐
   │abandoned│
   └─────────┘

States:

- **open**: Active session, can be modified
- **committed**: Session converted to Order
- **abandoned**: Session expired or cancelled


Creating Sessions
-----------------

Via ORM
~~~~~~~

.. code-block:: python

   from omniman.models import Channel, Session

   channel = Channel.objects.get(code="pos")

   session = Session.objects.create(
       session_key="SESS-001",  # Optional: auto-generated if not provided
       channel=channel,
       state="open",
       handle_type="table",      # table, customer, order, etc.
       handle_ref="5",           # Table number, customer ID, etc.
   )

Via API
~~~~~~~

.. code-block:: http

   POST /api/sessions/ HTTP/1.1
   Content-Type: application/json

   {
       "channel_code": "pos",
       "handle_type": "table",
       "handle_ref": "5"
   }


Session Keys
------------

Session keys are unique identifiers. You can:

1. **Auto-generate**: Leave ``session_key`` empty

   .. code-block:: python

      session = Session.objects.create(channel=channel, state="open")
      print(session.session_key)  # SESS-ABC123XYZ

2. **Custom key**: Provide your own

   .. code-block:: python

      session = Session.objects.create(
          session_key="TABLE-5-20251218",
          channel=channel,
          state="open",
      )


Modifying Sessions
------------------

Use the ``ModifyService`` for all item operations:

Add Item
~~~~~~~~

.. code-block:: python

   from omniman.services import ModifyService

   ModifyService.modify_session(
       session_key="SESS-001",
       channel_code="pos",
       ops=[
           {
               "op": "add_line",
               "sku": "ESPRESSO",
               "name": "Espresso",
               "qty": 2,
               "unit_price_q": 500,
               "meta": {"notes": "Extra hot"},
           },
       ],
   )

Update Quantity
~~~~~~~~~~~~~~~

.. code-block:: python

   # Get line_id from session.items
   session = Session.objects.get(session_key="SESS-001")
   line_id = session.items[0]["line_id"]

   ModifyService.modify_session(
       session_key="SESS-001",
       channel_code="pos",
       ops=[
           {
               "op": "set_qty",
               "line_id": line_id,
               "qty": 3,
           },
       ],
   )

Remove Item
~~~~~~~~~~~

.. code-block:: python

   ModifyService.modify_session(
       session_key="SESS-001",
       channel_code="pos",
       ops=[
           {
               "op": "remove_line",
               "line_id": line_id,
           },
       ],
   )

Batch Operations
~~~~~~~~~~~~~~~~

.. code-block:: python

   ModifyService.modify_session(
       session_key="SESS-001",
       channel_code="pos",
       ops=[
           {"op": "add_line", "sku": "COFFEE", "qty": 1, "unit_price_q": 500},
           {"op": "add_line", "sku": "CAKE", "qty": 1, "unit_price_q": 1500},
           {"op": "set_qty", "line_id": "L-xxx", "qty": 2},
       ],
   )


Session Items
-------------

Items are stored as a list of dictionaries:

.. code-block:: python

   session = Session.objects.get(session_key="SESS-001")

   for item in session.items:
       print(f"""
           Line ID: {item['line_id']}
           SKU: {item['sku']}
           Name: {item['name']}
           Qty: {item['qty']}
           Unit Price: R$ {item['unit_price_q'] / 100:.2f}
           Line Total: R$ {item['line_total_q'] / 100:.2f}
           Meta: {item.get('meta', {})}
       """)

Item Structure
~~~~~~~~~~~~~~

.. code-block:: python

   {
       "line_id": "L-abc123",      # Unique within session
       "sku": "PAINCHOC",          # Product SKU
       "name": "Pain au Chocolat", # Display name
       "qty": 2.0,                 # Quantity (float for fractional)
       "unit_price_q": 1300,       # Price in cents
       "line_total_q": 2600,       # qty * unit_price_q
       "meta": {                   # Flexible metadata
           "notes": "Extra sugar",
           "modifiers": ["large"],
       },
   }


Session Data
------------

The ``data`` field stores session-level metadata:

.. code-block:: python

   session = Session.objects.get(session_key="SESS-001")

   # Session data structure
   {
       "rev": 5,                   # Revision number (increments on modify)
       "checks": {                 # Validation results
           "stock": {
               "rev": 5,
               "status": "ok",
               "result": {"holds": [...]},
               "checked_at": "2025-12-18T10:00:00Z",
               "expires_at": "2025-12-18T10:15:00Z",
           },
       },
       "issues": [],               # Active validation issues
       "customer": {               # Optional customer info
           "name": "John Doe",
           "email": "john@example.com",
       },
   }

Revision Number
~~~~~~~~~~~~~~~

The ``rev`` field tracks modifications:

.. code-block:: python

   session = Session.objects.get(session_key="SESS-001")
   print(session.rev)  # Current revision

   # After modify
   ModifyService.modify_session(...)
   session.refresh_from_db()
   print(session.rev)  # Incremented


Session Checks
--------------

Checks validate session state (stock, payment, etc.):

.. code-block:: python

   # Access check data
   checks = session.data.get("checks", {})
   stock_check = checks.get("stock", {})

   if stock_check.get("status") == "ok":
       print("Stock validated")
   elif stock_check.get("status") == "issues":
       print("Stock issues found")


Session Issues
--------------

Issues are problems that need resolution:

.. code-block:: python

   issues = session.data.get("issues", [])

   for issue in issues:
       print(f"""
           Code: {issue['code']}
           SKU: {issue.get('sku')}
           Message: {issue['message']}
           Actions: {issue.get('actions', [])}
       """)

Issue Structure
~~~~~~~~~~~~~~~

.. code-block:: python

   {
       "code": "insufficient_stock",
       "sku": "PAINCHOC",
       "requested": 5,
       "available": 2,
       "message": "Only 2 units available",
       "actions": [
           {"action": "adjust_qty", "qty": 2},
           {"action": "remove_item"},
       ],
   }


Committing Sessions
-------------------

Convert a session to an Order:

.. code-block:: python

   from omniman.services import CommitService

   try:
       result = CommitService.commit(
           session_key="SESS-001",
           channel_code="pos",
           idempotency_key="COMMIT-001",  # Optional
       )
       print(f"Order: {result['order_ref']}")
       print(f"Total: R$ {result['total_q'] / 100:.2f}")

   except CommitError as e:
       print(f"Error: {e.message}")
       if e.code == "has_issues":
           print(f"Issues: {e.issues}")
       elif e.code == "stale_check":
           print("Run stock check and retry")


Idempotency
~~~~~~~~~~~

Use idempotency keys to prevent duplicate orders:

.. code-block:: python

   result = CommitService.commit(
       session_key="SESS-001",
       channel_code="pos",
       idempotency_key="COMMIT-ABC123",
   )

   # Same call returns same result (no duplicate order)
   result2 = CommitService.commit(
       session_key="SESS-001",
       channel_code="pos",
       idempotency_key="COMMIT-ABC123",
   )

   assert result["order_ref"] == result2["order_ref"]


Abandoning Sessions
-------------------

Mark sessions as abandoned:

.. code-block:: python

   session = Session.objects.get(session_key="SESS-001")
   session.state = "abandoned"
   session.save()

   # Or via service
   from omniman.services import SessionService
   SessionService.abandon(session_key="SESS-001", channel_code="pos")


Querying Sessions
-----------------

By State
~~~~~~~~

.. code-block:: python

   # Open sessions
   open_sessions = Session.objects.filter(state="open")

   # Today's sessions
   from django.utils.timezone import now
   today = now().date()
   todays_sessions = Session.objects.filter(created_at__date=today)

By Channel
~~~~~~~~~~

.. code-block:: python

   pos_sessions = Session.objects.filter(channel__code="pos")

By Owner
~~~~~~~~

.. code-block:: python

   # All sessions for table 5
   table_sessions = Session.objects.filter(
       handle_type="table",
       handle_ref="5",
   )


Best Practices
--------------

1. **Use ModifyService**: Always use the service for item operations to ensure proper validation.

2. **Check Session State**: Verify session is "open" before modifications.

3. **Use Idempotency Keys**: Prevent duplicate orders in production.

4. **Handle Issues**: Check for issues before committing.

5. **Clean Up**: Periodically abandon old open sessions.


See Also
--------

- :doc:`orders` - Order lifecycle after commit
- :doc:`issues-resolution` - Issue resolution system
- :doc:`../api/rest-api` - REST API reference
