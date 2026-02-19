Tutorial: Complete Order Flow
=============================

This tutorial walks you through a complete Omniman flow using the example shop.
By the end, you'll understand how Sessions, Orders, and Directives work together.


What You'll Learn
-----------------

- How to set up and seed the example project
- The complete basket → order → fulfillment flow
- How stock validation works with modifiers
- How to extend Omniman for your use case


Prerequisites
-------------

- Python 3.11+
- Basic Django knowledge
- 15-30 minutes


Step 1: Setup the Project
-------------------------

Clone and configure the example project:

.. code-block:: bash

   # Clone the repository
   git clone https://github.com/your-repo/django-omniman.git
   cd django-omniman

   # Create virtual environment
   python -m venv venv
   source venv/bin/activate  # or `venv\Scripts\activate` on Windows

   # Install dependencies
   pip install -e ".[dev]"

   # Setup database
   cd example
   python manage.py migrate


Step 2: Seed Example Data
-------------------------

Create sample products and demo orders:

.. code-block:: bash

   # Create products and demo orders
   python manage.py seed_example --demo

This creates:

- **6 products**: Espresso, Cappuccino, Latte, Croissant, Pain au Chocolat, Carrot Cake
- **6 demo orders**: In various states (new, confirmed, processing, ready, completed, cancelled)


Step 3: Explore via Admin
-------------------------

Create a superuser and explore the data:

.. code-block:: bash

   python manage.py createsuperuser
   python manage.py runserver

Visit http://localhost:8000/admin/ and explore:

- **Channels**: The "shop" channel with its configuration
- **Sessions**: Open and committed sessions
- **Orders**: Demo orders in different states
- **Products**: The product catalog


Step 4: Interactive Shell Flow
------------------------------

Open the Django shell for hands-on experimentation:

.. code-block:: bash

   python manage.py shell

Now let's walk through a complete order flow:

Create a Basket
~~~~~~~~~~~~~~~

.. code-block:: python

   from example.shop.basket_service import BasketService

   # Create a new basket for user "tutorial"
   session = BasketService.get_or_create_basket("tutorial")
   print(f"Basket created: {session.session_key}")
   # Output: Basket created: BASKET-tutorial

Add Items
~~~~~~~~~

.. code-block:: python

   # Add items to the basket
   BasketService.add_item(session, sku="ESPRESSO", qty=2, unit_price_q=500)
   BasketService.add_item(session, sku="CROISSANT", qty=1, unit_price_q=650)

   # View basket contents
   session.refresh_from_db()
   for item in session.items:
       print(f"  {item['qty']}x {item['sku']} @ R$ {item['unit_price_q']/100:.2f}")

   # Output:
   #   2x ESPRESSO @ R$ 5.00
   #   1x CROISSANT @ R$ 6.50

   # Check totals
   print(f"Total items: {BasketService.get_total_items(session)}")
   print(f"Subtotal: {BasketService.get_subtotal_display(session)}")
   # Output:
   #   Total items: 3
   #   Subtotal: R$ 16.50

Modify the Basket
~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Update quantity
   espresso_line = session.items[0]
   BasketService.update_item(session, espresso_line["line_id"], qty=3)

   # Remove an item
   croissant_line = session.items[1]
   BasketService.remove_item(session, croissant_line["line_id"])

   # Check updated basket
   session.refresh_from_db()
   print(f"Items: {len(session.items)}, Total: {BasketService.get_subtotal_display(session)}")
   # Output: Items: 1, Total: R$ 15.00

Commit (Create Order)
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Commit the basket to create an order
   result = BasketService.commit(session, idempotency_key="TUTORIAL-001")
   print(f"Order created: {result['order_ref']}")
   # Output: Order created: ORD-20260119-XXXXXX

   # Verify session state changed
   session.refresh_from_db()
   print(f"Session state: {session.state}")
   # Output: Session state: committed

View the Order
~~~~~~~~~~~~~~

.. code-block:: python

   from omniman.models import Order

   order = Order.objects.get(ref=result["order_ref"])
   print(f"Order: {order.ref}")
   print(f"Status: {order.status}")
   print(f"Items: {order.items.count()}")
   print(f"Total: R$ {order.total_q/100:.2f}")

Process the Order
~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Transition through the order lifecycle
   order.transition_status("confirmed", actor="cashier")
   print(f"Status: {order.status}")  # confirmed

   order.transition_status("processing", actor="kitchen")
   print(f"Status: {order.status}")  # processing

   order.transition_status("ready", actor="kitchen")
   print(f"Status: {order.status}")  # ready

   order.transition_status("completed", actor="cashier")
   print(f"Status: {order.status}")  # completed

   # View audit trail
   for event in order.events.all():
       print(f"  {event.type}: {event.payload}")


Step 5: Test Idempotency
------------------------

Omniman prevents duplicate orders via idempotency keys:

.. code-block:: python

   # Try to commit the same session again
   result2 = BasketService.commit(session, idempotency_key="TUTORIAL-001")
   print(f"Same order: {result2['order_ref'] == result['order_ref']}")
   # Output: Same order: True

   # Verify no duplicate was created
   print(f"Total orders: {Order.objects.count()}")


Step 6: Run the Tests
---------------------

Validate everything works with the test suite:

.. code-block:: bash

   # Run example shop tests
   python manage.py test example.shop

   # Expected output:
   # test_create_basket ... ok
   # test_add_item_to_basket ... ok
   # test_commit_basket_creates_order ... ok
   # ... (13 tests)
   # OK


Step 7: Understand the Architecture
-----------------------------------

Now that you've seen it in action, let's understand what happened:

.. code-block:: text

   ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
   │     Session     │ ──► │      Order      │ ──► │    Directive    │
   │    (mutable)    │     │   (immutable)   │     │     (async)     │
   └─────────────────┘     └─────────────────┘     └─────────────────┘
         │                        │                        │
         │                        │                        │
   BasketService           CommitService            Handlers
   - add_item()            - commit()               - stock.hold
   - update_item()         - idempotency            - stock.commit
   - remove_item()         - snapshot               - payment.capture

**Session**: Mutable pre-commit state. Can be modified freely until committed.

**Order**: Immutable snapshot. Created at commit time. The source of truth.

**Directive**: Async tasks for side effects (stock, payment, notifications).


Step 8: Extend for Your Use Case
--------------------------------

The example shop demonstrates a minimal integration. For production, you might add:

Custom Pricing Modifier
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # example/shop/modifiers.py

   from omniman.registry import registry

   @registry.register_modifier("pricing")
   class ProductPricingModifier:
       """Look up prices from the Product catalog."""

       def modify(self, session, ops, ctx):
           from example.shop.models import Product

           for op in ops:
               if op.get("op") == "add_line" and "unit_price_q" not in op:
                   try:
                       product = Product.objects.get(sku=op["sku"])
                       op["unit_price_q"] = product.price_q
                       op["name"] = product.name
                   except Product.DoesNotExist:
                       pass

           return ops

Stock Validation Handler
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # example/shop/handlers.py

   from omniman.registry import registry

   @registry.register_handler("stock.check")
   class StockCheckHandler:
       """Validate stock availability."""

       def handle(self, directive, ctx):
           from example.shop.models import Product

           issues = []
           for item in directive.session.items:
               try:
                   product = Product.objects.get(sku=item["sku"])
                   # Add stock field to Product model for real implementation
                   # if product.stock < item["qty"]:
                   #     issues.append({...})
               except Product.DoesNotExist:
                   issues.append({
                       "code": "product_not_found",
                       "sku": item["sku"],
                       "message": f"Product {item['sku']} not found",
                   })

           return {"issues": issues, "ok": len(issues) == 0}


What's Next?
------------

- :doc:`../guides/sessions` - Deep dive into Sessions
- :doc:`../guides/orders` - Order lifecycle and events
- :doc:`../guides/pricing` - Pricing strategies
- :doc:`../api/rest-api` - REST API reference
