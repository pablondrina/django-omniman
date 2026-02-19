Pricing Module
==============

The Pricing contrib module provides flexible pricing strategies
for different channels.


Overview
--------

Omniman supports multiple pricing policies:

- **Internal**: Prices provided in operation payload
- **External**: Prices fetched from a PricingBackend
- **Mixed**: Try external, fallback to internal


Configuration
-------------

Channel Pricing Policy
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Internal pricing
   Channel.objects.create(
       code="pos",
       pricing_policy="internal",
   )

   # External pricing
   Channel.objects.create(
       code="ecommerce",
       pricing_policy="external",
       config={
           "pricing_backend": "catalog.pricing.CatalogPricingBackend",
       },
   )

Settings
~~~~~~~~

.. code-block:: python

   # settings.py

   OMNIMAN_PRICING = {
       "DEFAULT_BACKEND": "catalog.pricing.CatalogPricingBackend",
       "CACHE_TTL": 300,  # Cache prices for 5 minutes
   }


Pricing Protocol
----------------

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
           Get price for a single SKU.

           Args:
               sku: Product SKU
               channel_code: Channel code
               qty: Quantity (for volume pricing)
               context: Additional context (customer, promotions)

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


Implementation Examples
-----------------------

Catalog Pricing
~~~~~~~~~~~~~~~

.. code-block:: python

   # catalog/pricing.py

   from catalog.models import Product

   class CatalogPricingBackend:
       """Pricing backend using Product model."""

       def get_price(self, sku, channel_code, qty=1.0, context=None):
           try:
               product = Product.objects.get(sku=sku, active=True)
               return product.price_q
           except Product.DoesNotExist:
               return None

       def get_prices(self, skus, channel_code, context=None):
           products = Product.objects.filter(sku__in=skus, active=True)
           return {p.sku: p.price_q for p in products}

Channel-Specific Pricing
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   class ChannelPricingBackend:
       """Pricing backend with channel-specific prices."""

       def get_price(self, sku, channel_code, qty=1.0, context=None):
           # Try channel-specific price first
           try:
               channel_price = ChannelPrice.objects.get(
                   sku=sku,
                   channel_code=channel_code,
               )
               return channel_price.price_q
           except ChannelPrice.DoesNotExist:
               pass

           # Fall back to default price
           try:
               product = Product.objects.get(sku=sku)
               return product.price_q
           except Product.DoesNotExist:
               return None

Volume Pricing
~~~~~~~~~~~~~~

.. code-block:: python

   class VolumePricingBackend:
       """Pricing backend with volume discounts."""

       def get_price(self, sku, channel_code, qty=1.0, context=None):
           product = Product.objects.get(sku=sku)
           base_price = product.price_q

           # Volume discounts
           volume_discounts = VolumeDiscount.objects.filter(
               sku=sku,
               min_qty__lte=qty,
           ).order_by("-min_qty").first()

           if volume_discounts:
               discount_pct = volume_discounts.discount_pct
               return int(base_price * (1 - discount_pct / 100))

           return base_price

Customer Pricing
~~~~~~~~~~~~~~~~

.. code-block:: python

   class CustomerPricingBackend:
       """Pricing backend with customer-specific prices."""

       def get_price(self, sku, channel_code, qty=1.0, context=None):
           context = context or {}
           customer_id = context.get("customer_id")

           product = Product.objects.get(sku=sku)
           base_price = product.price_q

           if customer_id:
               try:
                   customer = Customer.objects.get(id=customer_id)

                   # Customer-specific price
                   customer_price = CustomerPrice.objects.filter(
                       customer=customer,
                       sku=sku,
                   ).first()
                   if customer_price:
                       return customer_price.price_q

                   # Tier discount
                   if customer.tier == "gold":
                       return int(base_price * 0.9)
                   elif customer.tier == "silver":
                       return int(base_price * 0.95)

               except Customer.DoesNotExist:
                   pass

           return base_price


Pricing Modifier
----------------

The pricing modifier applies prices during session modification.

.. warning::

   **Invariante I4**: ``pricing_policy=external`` impede reprecificação silenciosa.

   Modifiers que manipulam preços **devem** verificar ``session.pricing_policy``
   antes de alterar ``unit_price_q`` ou ``line_total_q``. Sistemas externos
   (iFood, ERPs, APIs de pricing dinâmico) podem enviar valores especiais
   que não devem ser sobrescritos.

.. note::

   **Padrão Obrigatório**: ``session.items`` retorna ``deepcopy`` para proteção
   de dados. Modifiers que modificam items **devem** atribuir de volta via
   ``session.items = items`` para persistir alterações.

Built-in Modifiers (v0.5.10+)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

O módulo ``omniman.contrib.pricing.modifiers`` fornece:

- **InternalPricingModifier** (order=10): Busca preços via ``PricingBackend``
  quando ``pricing_policy="internal"`` e ``unit_price_q`` não está definido.

- **LineTotalModifier** (order=50): Recalcula ``line_total_q = qty * unit_price_q``
  quando ``pricing_policy="internal"``. Preserva ``line_total_q`` se ``external``.

- **SessionTotalModifier** (order=60): Calcula ``session.pricing["total_q"]``
  como soma de todos ``line_total_q``.

Example Custom Modifier
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from omniman.registry import registry

   @registry.register_modifier("pricing")
   class PricingModifier:
       """Modifier that applies prices to items."""

       def apply(self, channel, session, ctx):
           # CRÍTICO: Respeitar pricing_policy (Invariante I4)
           if session.pricing_policy == "internal":
               return  # Prices already in ops

           backend = get_pricing_backend(channel)
           items = session.items  # ← deepcopy!
           modified = False

           for item in items:
               if item.get("unit_price_q") is None:
                   price = backend.get_price(
                       sku=item["sku"],
                       channel_code=channel.code,
                       qty=item["qty"],
                       context=ctx,
                   )
                   if price is not None:
                       item["unit_price_q"] = price
                       item["line_total_q"] = int(item["qty"] * price)
                       modified = True

           # CRÍTICO: Persistir alterações
           if modified:
               session.items = items  # ← Obrigatório!


Caching
-------

Price Caching
~~~~~~~~~~~~~

.. code-block:: python

   from django.core.cache import cache

   class CachedPricingBackend:
       """Pricing backend with caching."""

       def __init__(self, backend, cache_ttl=300):
           self.backend = backend
           self.cache_ttl = cache_ttl

       def get_price(self, sku, channel_code, qty=1.0, context=None):
           cache_key = f"price:{channel_code}:{sku}"
           price = cache.get(cache_key)

           if price is None:
               price = self.backend.get_price(sku, channel_code, qty, context)
               if price is not None:
                   cache.set(cache_key, price, self.cache_ttl)

           return price

       def invalidate(self, sku, channel_code=None):
           if channel_code:
               cache.delete(f"price:{channel_code}:{sku}")
           else:
               # Invalidate all channels
               for channel in Channel.objects.all():
                   cache.delete(f"price:{channel.code}:{sku}")


Promotions
----------

Promotion Backend
~~~~~~~~~~~~~~~~~

.. code-block:: python

   class PromotionPricingBackend:
       """Pricing backend with promotion support."""

       def __init__(self, base_backend):
           self.base_backend = base_backend

       def get_price(self, sku, channel_code, qty=1.0, context=None):
           base_price = self.base_backend.get_price(sku, channel_code, qty)
           if base_price is None:
               return None

           context = context or {}
           promo_code = context.get("promo_code")

           if promo_code:
               promo = Promotion.objects.filter(
                   code=promo_code,
                   active=True,
                   start_date__lte=timezone.now(),
                   end_date__gte=timezone.now(),
               ).first()

               if promo and sku in promo.applicable_skus:
                   if promo.discount_type == "percentage":
                       return int(base_price * (1 - promo.discount_value / 100))
                   elif promo.discount_type == "fixed":
                       return max(0, base_price - promo.discount_value)

           return base_price

Applying Promotions
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # In ModifyService

   ModifyService.modify_session(
       session_key="SESS-001",
       channel_code="ecommerce",
       ops=[
           {
               "op": "set_data",
               "path": "promo_code",
               "value": "SUMMER20",
           },
       ],
   )

   # Pricing modifier uses promo_code from session data


Price Recalculation
-------------------

.. code-block:: python

   from omniman.services import ModifyService

   def recalculate_session_prices(session):
       """Force recalculation of all item prices."""
       backend = get_pricing_backend(session.channel)

       for item in session.items:
           price = backend.get_price(
               sku=item["sku"],
               channel_code=session.channel.code,
               qty=item["qty"],
           )
           if price:
               item["unit_price_q"] = price
               item["line_total_q"] = int(item["qty"] * price)

       session.save()


Testing
-------

.. code-block:: python

   import pytest
   from catalog.pricing import CatalogPricingBackend

   @pytest.fixture
   def pricing_backend():
       return CatalogPricingBackend()

   def test_get_price(pricing_backend, product):
       product.price_q = 1500
       product.save()

       price = pricing_backend.get_price(
           sku=product.sku,
           channel_code="pos",
       )

       assert price == 1500

   def test_price_not_found(pricing_backend):
       price = pricing_backend.get_price(
           sku="NONEXISTENT",
           channel_code="pos",
       )

       assert price is None


See Also
--------

- :doc:`../guides/pricing` - Pricing guide
- :doc:`stock` - Stock module
