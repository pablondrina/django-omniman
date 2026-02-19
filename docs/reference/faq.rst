Frequently Asked Questions
==========================


General
-------

What is Omniman?
~~~~~~~~~~~~~~~~

Omniman is a Django-based omnichannel hub for managing orders across multiple
sales channels. It provides a unified API for session management, order processing,
and integrations with external services like payment gateways and delivery platforms.

What are the main use cases?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **Point of Sale (POS)**: In-store order management
- **E-commerce**: Basket and checkout
- **Delivery Apps**: iFood, Rappi integration
- **Multi-channel Retail**: Unified order management

What are the requirements?
~~~~~~~~~~~~~~~~~~~~~~~~~~

- Python 3.11+
- Django 5.0+
- Django REST Framework 3.15+
- PostgreSQL (recommended) or SQLite


Sessions
--------

What is a Session?
~~~~~~~~~~~~~~~~~~

A Session represents mutable pre-commit state (basket, tab, draft order, etc.).
It holds items until committed to become an Order. Sessions are mutable and
can be modified using the ModifyService.

What is the difference between Session and Order?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **Session**: Mutable pre-commit state (cart/draft)
- **Order**: Immutable committed transaction

Sessions can be modified, abandoned, or committed. Orders are sealed and
only their status can change.

Can I have multiple open sessions per customer?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

By default, Omniman enforces one open session per owner (customer/table).
You can customize this via the session constraints or use different
handle_type values.

What happens when a session is abandoned?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When a session is marked as abandoned:

1. Stock holds are released
2. Session state changes to "abandoned"
3. Session data is preserved for analytics

How long do sessions last?
~~~~~~~~~~~~~~~~~~~~~~~~~~

Sessions don't have a built-in TTL. You can implement session cleanup using
a scheduled task:

.. code-block:: python

   from datetime import timedelta
   from django.utils import timezone

   # Abandon old sessions
   old_sessions = Session.objects.filter(
       state="open",
       created_at__lt=timezone.now() - timedelta(hours=24),
   )
   old_sessions.update(state="abandoned")


Orders
------

How are order references generated?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Order references follow the format: ``ORD-{date}-{random}``

Example: ``ORD-20251218-ABC123``

You can customize this in settings:

.. code-block:: python

   OMNIMAN = {
       "ORDER_REF_PREFIX": "PED-",
       "ORDER_REF_DATE_FORMAT": "%Y%m%d",
   }

Can I modify an order after it's created?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Orders are immutable by design. You can:

1. Change the order status (following the channel's flow)
2. Add events to the audit log
3. Create directives for external actions

For order modifications, cancel the original and create a new one.

What are terminal statuses?
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Terminal statuses are final states that cannot be changed. By default:

- ``completed``: Order fulfilled
- ``cancelled``: Order cancelled

Configure per channel:

.. code-block:: python

   {
       "order_flow": {
           "terminal_statuses": ["completed", "cancelled", "refunded"],
       }
   }


Stock
-----

How does stock reservation work?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. When a session is modified, a ``stock.hold`` directive is created
2. The handler reserves stock with a TTL (default: 15 minutes)
3. When the session is committed, ``stock.commit`` converts holds to permanent
4. If the session is abandoned, holds expire automatically

What happens if stock hold expires?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If a hold expires before commit:

1. CommitService raises ``CommitError(code="hold_expired")``
2. The admin re-runs the stock check automatically
3. If stock is available, new holds are created
4. If stock is insufficient, issues are generated

How do I implement custom stock validation?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Create a StockBackend implementation:

.. code-block:: python

   class MyStockBackend:
       def check_availability(self, items, session_key):
           # Your logic here
           pass

       def create_holds(self, items, session_key, ttl_minutes):
           # Your logic here
           pass

Register it in settings or registry.


Pricing
-------

What pricing policies are available?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **internal**: Prices provided in operation payload
- **external**: Prices fetched from PricingBackend
- **mixed**: Try external, fallback to internal

When should I use external pricing?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Use external pricing when:

- Prices are managed in an external system (ERP, PIM)
- You need dynamic pricing (promotions, customer tiers)
- Prices need to be consistent across channels

How do I handle promotions?
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Implement a PricingBackend that considers promotions:

.. code-block:: python

   class PromoPricingBackend:
       def get_price(self, sku, channel_code, qty, context):
           base_price = get_base_price(sku)
           promo_code = context.get("promo_code")

           if promo_code:
               discount = get_promo_discount(promo_code, sku)
               return int(base_price * (1 - discount))

           return base_price


Integrations
------------

How do I integrate with iFood?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. Create an iFood channel with status mapping
2. Implement webhook receiver for order events
3. Register handlers for status sync
4. Configure OAuth credentials

See :doc:`../integrations/ifood` for details.

How do I add a new payment gateway?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Implement the PaymentBackend protocol:

.. code-block:: python

   class MyPaymentBackend:
       def authorize(self, amount_q, currency, order_ref, payment_method):
           # Authorize payment
           pass

       def capture(self, transaction_id, amount_q):
           # Capture authorized payment
           pass

       def refund(self, transaction_id, amount_q, reason):
           # Process refund
           pass

Register in settings and configure channel.


Performance
-----------

How do I improve performance?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **Database**: Use PostgreSQL with connection pooling
2. **Caching**: Cache channels, prices, and session data
3. **Async**: Process directives asynchronously (Celery)
4. **Pagination**: Use cursor pagination for large lists

See :doc:`../deployment/performance` for details.

How do I handle high traffic?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **Horizontal scaling**: Run multiple Gunicorn workers
2. **Load balancing**: Use Nginx or cloud load balancer
3. **Database**: Use read replicas for queries
4. **Cache**: Use Redis for caching and sessions


Troubleshooting
---------------

Why is my commit failing?
~~~~~~~~~~~~~~~~~~~~~~~~~

Common causes:

1. **blocking_issues**: Session has unresolved issues
2. **stale_check**: Check needs to be re-run
3. **hold_expired**: Stock reservation expired
4. **missing_check**: Required check not found

Check the error code and context for details.

Why are items not being added?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Check:

1. Session state is "open"
2. Session edit_policy is not "locked"
3. Required fields (sku, qty) are provided
4. For external pricing, unit_price_q is required

Why is stock validation failing?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Check:

1. Stock backend is properly configured
2. Products exist in the catalog
3. Stock quantities are sufficient
4. No expired holds blocking stock


See Also
--------

- :doc:`../getting-started/quickstart` - Quick start guide
- :doc:`../guides/sessions` - Session management
- :doc:`../api/exceptions` - Exception reference
