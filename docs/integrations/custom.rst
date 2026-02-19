Custom Integrations
===================

This guide covers creating custom integrations with Omniman using the
extensible handler and protocol system.


Integration Architecture
------------------------

Omniman uses a registry-based architecture for extensibility:

.. code-block:: text

   ┌─────────────────────────────────────────────────────────┐
   │                      Registry                           │
   │  ┌───────────┐  ┌───────────┐  ┌───────────┐           │
   │  │ Handlers  │  │ Backends  │  │  Hooks    │           │
   │  └───────────┘  └───────────┘  └───────────┘           │
   └─────────────────────────────────────────────────────────┘
              │              │              │
              ▼              ▼              ▼
   ┌───────────────┐ ┌───────────────┐ ┌───────────────┐
   │   Directive   │ │  External     │ │    Event      │
   │   Processing  │ │  Services     │ │   Callbacks   │
   └───────────────┘ └───────────────┘ └───────────────┘


Creating Handlers
-----------------

Directive Handlers
~~~~~~~~~~~~~~~~~~

Handlers process directives (async commands):

.. code-block:: python

   # myapp/handlers.py

   from omniman.registry import registry

   @registry.register_handler("notification.email")
   class EmailNotificationHandler:
       """Handler for sending email notifications."""

       def handle(self, directive, ctx):
           """
           Process the directive.

           Args:
               directive: Directive model instance
               ctx: Context dict with actor, timestamp, etc.

           Returns:
               dict with result data
           """
           payload = directive.payload
           order = directive.order

           # Send email
           send_email(
               to=payload["to"],
               subject=payload["subject"],
               template="order_notification.html",
               context={
                   "order": order,
                   "message": payload.get("message"),
               },
           )

           return {"sent": True, "to": payload["to"]}

Handler with Dependencies
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   @registry.register_handler("inventory.sync")
   class InventorySyncHandler:
       """Handler for syncing inventory with external system."""

       def __init__(self):
           self.erp_client = ERPClient()

       def handle(self, directive, ctx):
           payload = directive.payload
           items = payload.get("items", [])

           results = []
           for item in items:
               result = self.erp_client.update_stock(
                   sku=item["sku"],
                   quantity=-item["qty"],
                   reference=payload["order_ref"],
               )
               results.append(result)

           return {"synced": len(results), "results": results}


Creating Backends
-----------------

Backend Protocol
~~~~~~~~~~~~~~~~

Define a protocol for your backend type:

.. code-block:: python

   # myapp/protocols.py

   from typing import Protocol
   from dataclasses import dataclass

   @dataclass
   class ShippingQuote:
       carrier: str
       service: str
       price_q: int
       delivery_days: int
       tracking_code: str | None = None

   class ShippingBackend(Protocol):
       """Protocol for shipping backends."""

       def get_quotes(
           self,
           origin_zip: str,
           destination_zip: str,
           items: list[dict],
       ) -> list[ShippingQuote]:
           """Get shipping quotes."""
           ...

       def create_shipment(
           self,
           order_ref: str,
           carrier: str,
           service: str,
           destination: dict,
           items: list[dict],
       ) -> ShippingQuote:
           """Create shipment and get tracking."""
           ...

       def get_tracking(
           self,
           tracking_code: str,
       ) -> dict:
           """Get tracking information."""
           ...

Implementing Backend
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # myapp/backends/correios.py

   from myapp.protocols import ShippingBackend, ShippingQuote

   class CorreiosBackend:
       """Correios (Brazilian Post) shipping backend."""

       def __init__(self, config: dict):
           self.username = config["username"]
           self.password = config["password"]
           self.contract = config.get("contract")

       def get_quotes(
           self,
           origin_zip: str,
           destination_zip: str,
           items: list[dict],
       ) -> list[ShippingQuote]:
           # Calculate package dimensions
           weight = sum(i.get("weight", 0.5) for i in items)

           # Call Correios API
           response = self._call_api("CalcPrecoPrazo", {
               "nCdServico": "04014,04510",  # SEDEX, PAC
               "sCepOrigem": origin_zip,
               "sCepDestino": destination_zip,
               "nVlPeso": weight,
           })

           quotes = []
           for service in response["servicos"]:
               quotes.append(ShippingQuote(
                   carrier="correios",
                   service=service["codigo"],
                   price_q=int(float(service["valor"]) * 100),
                   delivery_days=int(service["prazoEntrega"]),
               ))

           return quotes

       def create_shipment(
           self,
           order_ref: str,
           carrier: str,
           service: str,
           destination: dict,
           items: list[dict],
       ) -> ShippingQuote:
           # Create shipment in Correios
           response = self._call_api("GerarEtiqueta", {...})

           return ShippingQuote(
               carrier="correios",
               service=service,
               price_q=response["valor"],
               delivery_days=response["prazo"],
               tracking_code=response["etiqueta"],
           )

Registering Backend
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # myapp/apps.py

   from django.apps import AppConfig

   class MyAppConfig(AppConfig):
       name = "myapp"

       def ready(self):
           from omniman.registry import registry
           from myapp.backends.correios import CorreiosBackend

           registry.register_backend(
               "shipping",
               "correios",
               CorreiosBackend(settings.CORREIOS_CONFIG),
           )


Creating Hooks
--------------

Event Hooks
~~~~~~~~~~~

Hooks are called when events occur:

.. code-block:: python

   from omniman.registry import registry

   @registry.register_hook("order.created")
   def on_order_created(order, ctx):
       """Called when order is created."""
       # Send notification
       notify_new_order(order)

       # Update analytics
       track_event("order_created", {
           "order_ref": order.ref,
           "channel": order.channel.code,
           "total": order.total_q,
       })


   @registry.register_hook("order.status_changed")
   def on_status_changed(order, old_status, new_status, actor):
       """Called when order status changes."""
       if new_status == "shipped":
           send_tracking_email(order)

       elif new_status == "delivered":
           request_review(order)

       elif new_status == "cancelled":
           process_refund(order)


   @registry.register_hook("session.modified")
   def on_session_modified(session, ops, ctx):
       """Called when session is modified."""
       # Real-time cart analytics
       track_cart_change(session, ops)

Available Hooks
~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1

   * - Hook
     - Arguments
     - Description
   * - ``order.created``
     - order, ctx
     - After order creation
   * - ``order.status_changed``
     - order, old_status, new_status, actor
     - After status transition
   * - ``session.created``
     - session, ctx
     - After session creation
   * - ``session.modified``
     - session, ops, ctx
     - After session modification
   * - ``session.committed``
     - session, order, ctx
     - After session commit
   * - ``directive.completed``
     - directive, result, ctx
     - After directive processing
   * - ``directive.failed``
     - directive, error, ctx
     - When directive fails


Creating Resolvers
------------------

Issue Resolvers
~~~~~~~~~~~~~~~

Resolvers check for issues and provide resolution actions:

.. code-block:: python

   from omniman.registry import registry

   @registry.register_resolver("delivery")
   class DeliveryResolver:
       """Resolver for delivery-related issues."""

       def get_issues(self, session, context=None):
           issues = []
           delivery = session.data.get("delivery", {})

           # Check delivery address
           if not delivery.get("address"):
               issues.append({
                   "code": "missing_address",
                   "message": "Delivery address is required",
                   "actions": [
                       {"action": "add_address", "label": "Add address"},
                   ],
               })

           # Check delivery area
           if delivery.get("zip"):
               if not self._is_deliverable(delivery["zip"]):
                   issues.append({
                       "code": "outside_delivery_area",
                       "message": "Address is outside delivery area",
                       "actions": [
                           {"action": "change_address", "label": "Change address"},
                           {"action": "pickup", "label": "Pickup instead"},
                       ],
                   })

           return issues

       def _is_deliverable(self, zip_code: str) -> bool:
           # Check if zip is in delivery area
           return zip_code.startswith(("01", "02", "03", "04", "05"))


Creating Modifiers
------------------

Item Modifiers
~~~~~~~~~~~~~~

Modifiers transform items during operations:

.. code-block:: python

   from omniman.registry import registry

   @registry.register_modifier("pricing")
   class PromotionModifier:
       """Apply promotions to items."""

       def modify(self, item: dict, session, ctx) -> dict:
           """
           Modify item before adding to session.

           Args:
               item: Item dict to modify
               session: Current session
               ctx: Operation context

           Returns:
               Modified item dict
           """
           promo = self._get_applicable_promo(item["sku"], session)

           if promo:
               original_price = item["unit_price_q"]
               discount = int(original_price * promo.discount_pct / 100)
               item["unit_price_q"] = original_price - discount
               item["meta"]["promotion"] = {
                   "code": promo.code,
                   "discount_pct": promo.discount_pct,
                   "original_price": original_price,
               }

           return item


   @registry.register_modifier("validation")
   class QuantityLimitModifier:
       """Enforce quantity limits."""

       def modify(self, item: dict, session, ctx) -> dict:
           max_qty = self._get_max_qty(item["sku"])

           if item["qty"] > max_qty:
               item["qty"] = max_qty
               item["meta"]["qty_limited"] = True
               item["meta"]["max_qty"] = max_qty

           return item


Complete Integration Example
----------------------------

WhatsApp Order Notifications
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # integrations/whatsapp/__init__.py

   from omniman.registry import registry
   from django.conf import settings
   import requests

   class WhatsAppClient:
       """WhatsApp Business API client."""

       def __init__(self):
           self.api_url = settings.WHATSAPP_API_URL
           self.token = settings.WHATSAPP_TOKEN

       def send_message(self, phone: str, template: str, params: list):
           response = requests.post(
               f"{self.api_url}/messages",
               headers={"Authorization": f"Bearer {self.token}"},
               json={
                   "messaging_product": "whatsapp",
                   "to": phone,
                   "type": "template",
                   "template": {
                       "name": template,
                       "language": {"code": "pt_BR"},
                       "components": [
                           {
                               "type": "body",
                               "parameters": [
                                   {"type": "text", "text": p} for p in params
                               ],
                           }
                       ],
                   },
               },
           )
           return response.json()


   @registry.register_handler("notification.whatsapp")
   class WhatsAppHandler:
       """Handler for WhatsApp notifications."""

       def __init__(self):
           self.client = WhatsAppClient()

       def handle(self, directive, ctx):
           payload = directive.payload
           order = directive.order

           customer_phone = order.data.get("customer", {}).get("phone")
           if not customer_phone:
               return {"sent": False, "reason": "No phone number"}

           template_map = {
               "order_confirmed": ("order_confirmation", [
                   order.ref,
                   f"R$ {order.total_q / 100:.2f}",
               ]),
               "order_ready": ("order_ready", [order.ref]),
               "order_shipped": ("order_shipped", [
                   order.ref,
                   order.data.get("tracking_code", ""),
               ]),
           }

           notification_type = payload.get("type", "order_confirmed")
           template, params = template_map.get(
               notification_type,
               ("generic", [order.ref]),
           )

           result = self.client.send_message(customer_phone, template, params)

           return {
               "sent": True,
               "message_id": result.get("messages", [{}])[0].get("id"),
           }


   @registry.register_hook("order.status_changed")
   def send_whatsapp_on_status_change(order, old_status, new_status, actor):
       """Send WhatsApp notification on status change."""
       from omniman.models import Directive

       notification_statuses = {
           "confirmed": "order_confirmed",
           "ready": "order_ready",
           "dispatched": "order_shipped",
       }

       if new_status in notification_statuses:
           Directive.objects.create(
               order=order,
               topic="notification.whatsapp",
               payload={"type": notification_statuses[new_status]},
           )


Testing Integrations
--------------------

.. code-block:: python

   import pytest
   from omniman.registry import registry
   from omniman.models import Directive

   @pytest.fixture
   def mock_whatsapp(mocker):
       mock = mocker.patch(
           "integrations.whatsapp.WhatsAppClient.send_message"
       )
       mock.return_value = {"messages": [{"id": "msg-123"}]}
       return mock

   def test_whatsapp_handler(order, mock_whatsapp):
       order.data["customer"] = {"phone": "+5511999999999"}
       order.save()

       directive = Directive.objects.create(
           order=order,
           topic="notification.whatsapp",
           payload={"type": "order_confirmed"},
       )

       handler = registry.get_handler("notification.whatsapp")
       result = handler.handle(directive, {})

       assert result["sent"]
       mock_whatsapp.assert_called_once()


Best Practices
--------------

1. **Use Protocols**: Define clear protocols for backends.

2. **Idempotent Handlers**: Make handlers idempotent for retry safety.

3. **Error Handling**: Handle external service failures gracefully.

4. **Logging**: Log all integration operations.

5. **Testing**: Mock external services in tests.

6. **Configuration**: Use settings for credentials and configuration.


See Also
--------

- :doc:`payments` - Payment integration example
- :doc:`ifood` - iFood integration example
- :doc:`../api/rest-api` - REST API reference
