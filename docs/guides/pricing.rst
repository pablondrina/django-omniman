Pricing
=======

Omniman supports flexible pricing policies per channel, allowing different
pricing sources for different sales channels.


Pricing Policies
----------------

Internal Pricing
~~~~~~~~~~~~~~~~

Prices are provided in the operation payload:

.. code-block:: python

   Channel.objects.create(
       code="pos",
       config={
           "pricing_policy": "internal",
       },
   )

   # Usage
   ModifyService.modify_session(
       session_key="SESS-001",
       channel_code="pos",
       ops=[
           {
               "op": "add_line",
               "sku": "COFFEE",
               "qty": 1,
               "unit_price_q": 500,  # Required
           },
       ],
   )

**Use cases**:
- POS systems with local price lookup
- Manual price entry
- Quick prototyping

External Pricing
~~~~~~~~~~~~~~~~

Prices are fetched from a PricingBackend:

.. code-block:: python

   Channel.objects.create(
       code="ecommerce",
       config={
           "pricing_policy": "external",
           "pricing_backend": "myapp.pricing.CatalogPricingBackend",
       },
   )

   # Usage - no price needed
   ModifyService.modify_session(
       session_key="SESS-001",
       channel_code="ecommerce",
       ops=[
           {
               "op": "add_line",
               "sku": "COFFEE",
               "qty": 1,
               # unit_price_q fetched from backend
           },
       ],
   )

**Use cases**:
- E-commerce with catalog prices
- Integration with ERP/pricing systems
- Dynamic pricing

Mixed Pricing
~~~~~~~~~~~~~

Try external first, fallback to internal:

.. code-block:: python

   Channel.objects.create(
       code="marketplace",
       config={
           "pricing_policy": "mixed",
           "pricing_backend": "myapp.pricing.CatalogPricingBackend",
       },
   )


Creating a PricingBackend
-------------------------

Protocol Definition
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from typing import Protocol

   class PricingBackend(Protocol):
       """Protocol for pricing backends."""

       def get_price(
           self,
           sku: str,
           channel_code: str,
           qty: float = 1.0,
           context: dict | None = None,
       ) -> int | None:
           """
           Get price for SKU.

           Args:
               sku: Product SKU
               channel_code: Channel code
               qty: Quantity (for volume discounts)
               context: Additional context (customer, promotions, etc.)

           Returns:
               Price in cents or None if not found
           """
           ...

       def get_prices(
           self,
           skus: list[str],
           channel_code: str,
           context: dict | None = None,
       ) -> dict[str, int]:
           """
           Get prices for multiple SKUs.

           Returns:
               Dict mapping SKU to price in cents
           """
           ...

Simple Implementation
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # myapp/pricing.py

   from catalog.models import Product

   class CatalogPricingBackend:
       """Pricing backend using Product model."""

       def get_price(
           self,
           sku: str,
           channel_code: str,
           qty: float = 1.0,
           context: dict | None = None,
       ) -> int | None:
           try:
               product = Product.objects.get(sku=sku, active=True)
               return product.price_q
           except Product.DoesNotExist:
               return None

       def get_prices(
           self,
           skus: list[str],
           channel_code: str,
           context: dict | None = None,
       ) -> dict[str, int]:
           products = Product.objects.filter(sku__in=skus, active=True)
           return {p.sku: p.price_q for p in products}

Advanced Implementation
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   class AdvancedPricingBackend:
       """Pricing backend with promotions and customer pricing."""

       def get_price(
           self,
           sku: str,
           channel_code: str,
           qty: float = 1.0,
           context: dict | None = None,
       ) -> int | None:
           context = context or {}
           customer_id = context.get("customer_id")
           promo_code = context.get("promo_code")

           # Get base price
           product = Product.objects.get(sku=sku)
           price = product.price_q

           # Apply customer tier discount
           if customer_id:
               customer = Customer.objects.get(id=customer_id)
               if customer.tier == "gold":
                   price = int(price * 0.9)  # 10% discount

           # Apply volume discount
           if qty >= 10:
               price = int(price * 0.95)  # 5% volume discount

           # Apply promo code
           if promo_code:
               promo = Promotion.objects.get(code=promo_code)
               if promo.is_valid and sku in promo.applicable_skus:
                   price = int(price * (1 - promo.discount_pct / 100))

           return price


Registering Backend
-------------------

Via Settings
~~~~~~~~~~~~

.. code-block:: python

   # settings.py

   OMNIMAN = {
       "PRICING_BACKENDS": {
           "catalog": "myapp.pricing.CatalogPricingBackend",
           "external_api": "myapp.pricing.ExternalAPIPricingBackend",
       },
       "DEFAULT_PRICING_BACKEND": "catalog",
   }

Via Registry
~~~~~~~~~~~~

.. code-block:: python

   # myapp/apps.py

   from django.apps import AppConfig

   class MyAppConfig(AppConfig):
       name = "myapp"

       def ready(self):
           from omniman.registry import registry
           from myapp.pricing import CatalogPricingBackend

           registry.register_pricing_backend("catalog", CatalogPricingBackend())


Price in Operations
-------------------

When using internal/mixed pricing:

.. code-block:: python

   ops = [
       # With explicit price
       {
           "op": "add_line",
           "sku": "COFFEE",
           "qty": 2,
           "unit_price_q": 500,
       },

       # With price override
       {
           "op": "add_line",
           "sku": "CAKE",
           "qty": 1,
           "unit_price_q": 1200,  # Override catalog price
           "meta": {"price_override_reason": "Manager discount"},
       },

       # Free item
       {
           "op": "add_line",
           "sku": "NAPKIN",
           "qty": 10,
           "unit_price_q": 0,
       },
   ]


Price Calculation
-----------------

Line Total
~~~~~~~~~~

.. code-block:: python

   # Calculated automatically
   line_total_q = qty * unit_price_q

Session Total
~~~~~~~~~~~~~

.. code-block:: python

   session = Session.objects.get(session_key="SESS-001")
   total = sum(item["line_total_q"] for item in session.items)

Order Total
~~~~~~~~~~~

.. code-block:: python

   order = Order.objects.get(ref="ORD-123")
   # Stored at commit time
   print(f"Total: R$ {order.total_q / 100:.2f}")


Price Updates
-------------

Recalculate Session
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from omniman.services import ModifyService

   # Force price recalculation
   ModifyService.recalculate_prices(
       session_key="SESS-001",
       channel_code="ecommerce",
   )

Price at Commit
~~~~~~~~~~~~~~~

For external pricing, prices can be re-fetched at commit time:

.. code-block:: python

   Channel.objects.create(
       code="ecommerce",
       config={
           "pricing_policy": "external",
           "refresh_prices_on_commit": True,  # Re-fetch before commit
       },
   )


Currency Handling
-----------------

All prices are stored in cents (integer) to avoid floating-point issues:

.. code-block:: python

   # Price: R$ 15.99
   unit_price_q = 1599

   # Display
   def format_price(cents: int) -> str:
       return f"R$ {cents / 100:.2f}"

   # Parse
   def parse_price(display: str) -> int:
       return int(float(display.replace("R$", "").strip()) * 100)


Testing Pricing
---------------

.. code-block:: python

   # tests/test_pricing.py

   import pytest
   from omniman.services import ModifyService

   @pytest.fixture
   def pricing_backend(mocker):
       backend = mocker.Mock()
       backend.get_price.return_value = 1000
       return backend

   def test_external_pricing(session, pricing_backend, mocker):
       mocker.patch(
           "omniman.registry.registry.get_pricing_backend",
           return_value=pricing_backend,
       )

       ModifyService.modify_session(
           session_key=session.session_key,
           channel_code=session.channel.code,
           ops=[{"op": "add_line", "sku": "TEST", "qty": 1}],
       )

       session.refresh_from_db()
       assert session.items[0]["unit_price_q"] == 1000


Best Practices
--------------

1. **Use Cents**: Always store prices as integers in cents.

2. **External for Production**: Use external pricing for production e-commerce.

3. **Cache Prices**: Cache external prices to reduce API calls.

4. **Audit Price Changes**: Log when prices change between session creation and commit.

5. **Handle Missing Prices**: Gracefully handle products without prices.


See Also
--------

- :doc:`channels` - Channel configuration
- :doc:`sessions` - Session management
- :doc:`../contrib/pricing` - Pricing contrib module
