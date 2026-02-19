iFood Integration
=================

This guide covers integrating Omniman with iFood, Brazil's largest food
delivery platform.


Architecture
------------

.. code-block:: text

   ┌─────────────┐                     ┌─────────────┐
   │    iFood    │◀───── Webhooks ─────│   Omniman   │
   │   Platform  │                     │   Server    │
   └──────┬──────┘                     └──────┬──────┘
          │                                   │
          │  New Order                        │
          │  Status Update                    │
          ▼                                   ▼
   ┌─────────────┐                     ┌─────────────┐
   │  iFood API  │────── Sync ────────▶│  Order DB   │
   └─────────────┘                     └─────────────┘


Prerequisites
-------------

1. **iFood Partner Account**: Register at https://portal.ifood.com.br
2. **API Credentials**: Client ID and Secret from iFood portal
3. **Webhook URL**: Public HTTPS endpoint for receiving webhooks


Configuration
-------------

Channel Setup
~~~~~~~~~~~~~

.. code-block:: python

   Channel.objects.create(
       code="ifood",
       name="iFood",
       config={
           "pricing_policy": "external",
           "external_sync": True,
           "order_flow": {
               "initial_status": "received",
               "transitions": {
                   "received": ["confirmed", "cancelled"],
                   "confirmed": ["preparing"],
                   "preparing": ["ready"],
                   "ready": ["dispatched"],
                   "dispatched": ["delivered"],
                   "delivered": ["completed"],
                   "cancelled": [],
                   "completed": [],
               },
               "terminal_statuses": ["completed", "cancelled"],
           },
           "ifood": {
               "merchant_id": "your-merchant-id",
               "auto_confirm": False,  # Manual confirmation
               "sync_status": True,    # Sync status changes to iFood
           },
           "status_mapping": {
               # iFood status → Omniman status
               "PLACED": "received",
               "CONFIRMED": "confirmed",
               "PREPARATION_STARTED": "preparing",
               "READY_TO_PICKUP": "ready",
               "DISPATCHED": "dispatched",
               "CONCLUDED": "completed",
               "CANCELLED": "cancelled",
           },
           "reverse_status_mapping": {
               # Omniman status → iFood status
               "confirmed": "confirm",
               "preparing": "startPreparation",
               "ready": "readyToPickup",
               "dispatched": "dispatch",
           },
       },
   )

Settings
~~~~~~~~

.. code-block:: python

   # settings.py

   OMNIMAN_IFOOD = {
       "CLIENT_ID": env("IFOOD_CLIENT_ID"),
       "CLIENT_SECRET": env("IFOOD_CLIENT_SECRET"),
       "MERCHANT_ID": env("IFOOD_MERCHANT_ID"),
       "SANDBOX": env.bool("IFOOD_SANDBOX", True),
       "WEBHOOK_SECRET": env("IFOOD_WEBHOOK_SECRET"),
   }


iFood Client
------------

.. code-block:: python

   # integrations/ifood/client.py

   import requests
   from django.conf import settings
   from django.core.cache import cache

   class IFoodClient:
       """iFood API client."""

       BASE_URL = "https://merchant-api.ifood.com.br"
       SANDBOX_URL = "https://merchant-api.ifood.com.br/sandbox"

       def __init__(self):
           config = settings.OMNIMAN_IFOOD
           self.client_id = config["CLIENT_ID"]
           self.client_secret = config["CLIENT_SECRET"]
           self.merchant_id = config["MERCHANT_ID"]
           self.sandbox = config.get("SANDBOX", True)
           self.base_url = self.SANDBOX_URL if self.sandbox else self.BASE_URL

       def _get_token(self) -> str:
           """Get or refresh OAuth token."""
           cache_key = "ifood_access_token"
           token = cache.get(cache_key)

           if not token:
               response = requests.post(
                   f"{self.base_url}/authentication/v1.0/oauth/token",
                   data={
                       "grantType": "client_credentials",
                       "clientId": self.client_id,
                       "clientSecret": self.client_secret,
                   },
               )
               response.raise_for_status()
               data = response.json()
               token = data["accessToken"]
               # Cache for 50 minutes (token expires in 60)
               cache.set(cache_key, token, 50 * 60)

           return token

       def _request(self, method: str, endpoint: str, **kwargs) -> dict:
           """Make authenticated request."""
           headers = {
               "Authorization": f"Bearer {self._get_token()}",
               "Content-Type": "application/json",
           }
           response = requests.request(
               method,
               f"{self.base_url}{endpoint}",
               headers=headers,
               **kwargs,
           )
           response.raise_for_status()
           return response.json() if response.content else {}

       # Order Management

       def get_order(self, order_id: str) -> dict:
           """Get order details from iFood."""
           return self._request("GET", f"/order/v1.0/orders/{order_id}")

       def confirm_order(self, order_id: str) -> dict:
           """Confirm order on iFood."""
           return self._request("POST", f"/order/v1.0/orders/{order_id}/confirm")

       def start_preparation(self, order_id: str) -> dict:
           """Mark order as preparing on iFood."""
           return self._request(
               "POST",
               f"/order/v1.0/orders/{order_id}/startPreparation",
           )

       def ready_to_pickup(self, order_id: str) -> dict:
           """Mark order as ready on iFood."""
           return self._request(
               "POST",
               f"/order/v1.0/orders/{order_id}/readyToPickup",
           )

       def dispatch_order(self, order_id: str) -> dict:
           """Dispatch order on iFood."""
           return self._request("POST", f"/order/v1.0/orders/{order_id}/dispatch")

       # Catalog Management

       def pause_item(self, item_id: str) -> None:
           """Pause an item (unavailable for sale)."""
           self._request(
               "POST",
               f"/catalog/v2.0/merchants/{self.merchant_id}/items/{item_id}/pause",
           )

       def unpause_item(self, item_id: str) -> None:
           """Unpause an item (available for sale)."""
           self._request(
               "POST",
               f"/catalog/v2.0/merchants/{self.merchant_id}/items/{item_id}/unpause",
           )

       def cancel_order(
           self,
           order_id: str,
           reason: str,
           cancellation_code: str,
       ) -> dict:
           """Cancel order on iFood."""
           return self._request(
               "POST",
               f"/order/v1.0/orders/{order_id}/requestCancellation",
               json={
                   "reason": reason,
                   "cancellationCode": cancellation_code,
               },
           )


Webhook Handler
---------------

.. code-block:: python

   # integrations/ifood/webhooks.py

   import hmac
   import hashlib
   import json
   from django.http import JsonResponse
   from django.views.decorators.csrf import csrf_exempt
   from django.views.decorators.http import require_POST
   from django.conf import settings
   from omniman.models import Channel, Session, Order
   from omniman.services import ModifyService, CommitService

   @csrf_exempt
   @require_POST
   def ifood_webhook(request):
       """Handle iFood webhooks."""

       # Verify signature
       signature = request.headers.get("X-Ifood-Signature")
       secret = settings.OMNIMAN_IFOOD["WEBHOOK_SECRET"]

       expected = hmac.new(
           secret.encode(),
           request.body,
           hashlib.sha256,
       ).hexdigest()

       if not hmac.compare_digest(signature, expected):
           return JsonResponse({"error": "Invalid signature"}, status=401)

       payload = json.loads(request.body)
       event_type = payload.get("code")

       handlers = {
           "PLACED": handle_order_placed,
           "CONFIRMED": handle_status_update,
           "CANCELLED": handle_order_cancelled,
           "PREPARATION_STARTED": handle_status_update,
           "READY_TO_PICKUP": handle_status_update,
           "DISPATCHED": handle_status_update,
           "CONCLUDED": handle_status_update,
       }

       handler = handlers.get(event_type)
       if handler:
           handler(payload)

       return JsonResponse({"status": "ok"})


   def handle_order_placed(payload: dict):
       """Handle new order from iFood."""
       channel = Channel.objects.get(code="ifood")
       order_data = payload["data"]

       # Create session
       session = Session.objects.create(
           session_key=f"IFOOD-{order_data['id']}",
           channel=channel,
           state="open",
           handle_type="ifood_order",
           handle_ref=order_data["id"],
           data={
               "ifood_order_id": order_data["id"],
               "customer": {
                   "name": order_data["customer"]["name"],
                   "phone": order_data["customer"]["phone"],
               },
               "delivery": order_data.get("delivery", {}),
           },
       )

       # Add items
       ops = []
       for item in order_data["items"]:
           ops.append({
               "op": "add_line",
               "sku": item["externalCode"] or item["id"],
               "name": item["name"],
               "qty": item["quantity"],
               "unit_price_q": int(item["unitPrice"] * 100),
               "meta": {
                   "ifood_item_id": item["id"],
                   "options": item.get("options", []),
               },
           })

       ModifyService.modify_session(
           session_key=session.session_key,
           channel_code="ifood",
           ops=ops,
       )

       # Commit to create order
       result = CommitService.commit(
           session_key=session.session_key,
           channel_code="ifood",
       )

       # Update order with iFood reference
       order = Order.objects.get(ref=result["order_ref"])
       order.data["ifood_order_id"] = order_data["id"]
       order.save()


   def handle_status_update(payload: dict):
       """Handle status update from iFood."""
       ifood_order_id = payload["data"]["id"]
       ifood_status = payload["code"]

       try:
           order = Order.objects.get(data__ifood_order_id=ifood_order_id)
       except Order.DoesNotExist:
           return

       channel = order.channel
       status_mapping = channel.config.get("status_mapping", {})
       new_status = status_mapping.get(ifood_status)

       if new_status and new_status != order.status:
           order.transition_status(new_status, actor="ifood-webhook")


   def handle_order_cancelled(payload: dict):
       """Handle order cancellation from iFood."""
       ifood_order_id = payload["data"]["id"]

       try:
           order = Order.objects.get(data__ifood_order_id=ifood_order_id)
       except Order.DoesNotExist:
           return

       if order.status != "cancelled":
           order.transition_status("cancelled", actor="ifood-webhook")
           order.data["cancellation"] = {
               "source": "ifood",
               "reason": payload["data"].get("cancellationReason"),
           }
           order.save()


Sync Omniman → iFood
--------------------

.. code-block:: python

   # integrations/ifood/sync.py

   from omniman.registry import registry
   from omniman.models import Order
   from integrations.ifood.client import IFoodClient

   @registry.register_hook("order.status_changed")
   def sync_status_to_ifood(order: Order, old_status: str, new_status: str, actor: str):
       """Sync status changes to iFood."""

       # Don't sync if change came from iFood
       if actor == "ifood-webhook":
           return

       # Check if this is an iFood order
       ifood_order_id = order.data.get("ifood_order_id")
       if not ifood_order_id:
           return

       # Check if sync is enabled
       ifood_config = order.channel.config.get("ifood", {})
       if not ifood_config.get("sync_status"):
           return

       # Map status to iFood action
       reverse_mapping = order.channel.config.get("reverse_status_mapping", {})
       action = reverse_mapping.get(new_status)

       if not action:
           return

       client = IFoodClient()

       action_methods = {
           "confirm": client.confirm_order,
           "startPreparation": client.start_preparation,
           "readyToPickup": client.ready_to_pickup,
           "dispatch": client.dispatch_order,
       }

       method = action_methods.get(action)
       if method:
           try:
               method(ifood_order_id)
           except Exception as e:
               # Log error but don't fail
               import logging
               logger = logging.getLogger(__name__)
               logger.error(f"Failed to sync to iFood: {e}")


URL Configuration
-----------------

.. code-block:: python

   # urls.py

   from django.urls import path
   from integrations.ifood.webhooks import ifood_webhook

   urlpatterns = [
       path("webhooks/ifood/", ifood_webhook, name="ifood-webhook"),
   ]


Testing with Sandbox
--------------------

Local Development
~~~~~~~~~~~~~~~~~

Use ngrok to expose local webhook endpoint:

.. code-block:: bash

   # Terminal 1: Run Django
   python manage.py runserver

   # Terminal 2: Run ngrok
   ngrok http 8000

Configure webhook URL in iFood portal: ``https://xxxx.ngrok.io/webhooks/ifood/``

Test Fixtures
~~~~~~~~~~~~~

.. code-block:: python

   # tests/fixtures/ifood_order.json

   {
       "code": "PLACED",
       "data": {
           "id": "ifood-order-123",
           "merchant": {
               "id": "merchant-123",
               "name": "Test Restaurant"
           },
           "customer": {
               "name": "John Doe",
               "phone": "+5511999999999"
           },
           "items": [
               {
                   "id": "item-1",
                   "name": "Hamburger",
                   "externalCode": "BURGER-001",
                   "quantity": 2,
                   "unitPrice": 25.00,
                   "totalPrice": 50.00,
                   "options": []
               }
           ],
           "totalPrice": 50.00,
           "delivery": {
               "address": {
                   "streetName": "Rua Teste",
                   "streetNumber": "123"
               }
           }
       }
   }

Unit Tests
~~~~~~~~~~

.. code-block:: python

   import pytest
   from django.test import Client
   from omniman.models import Channel, Order

   @pytest.fixture
   def ifood_channel():
       return Channel.objects.create(
           code="ifood",
           config={
               "order_flow": {
                   "initial_status": "received",
                   "transitions": {"received": ["confirmed"]},
               },
               "status_mapping": {"PLACED": "received"},
           },
       )

   def test_ifood_order_creation(ifood_channel, mocker):
       mocker.patch(
           "integrations.ifood.webhooks.verify_signature",
           return_value=True,
       )

       client = Client()
       response = client.post(
           "/webhooks/ifood/",
           data={"code": "PLACED", "data": {...}},
           content_type="application/json",
       )

       assert response.status_code == 200
       assert Order.objects.filter(channel=ifood_channel).exists()


Admin Integration
-----------------

.. code-block:: python

   # admin.py

   from django.contrib import admin
   from django.utils.html import format_html
   from omniman.models import Order

   @admin.register(Order)
   class OrderAdmin(admin.ModelAdmin):

       @admin.display(description="iFood ID")
       def ifood_id(self, obj):
           ifood_order_id = obj.data.get("ifood_order_id")
           if ifood_order_id:
               return format_html(
                   '<a href="https://portal.ifood.com.br/orders/{}" target="_blank">{}</a>',
                   ifood_order_id,
                   ifood_order_id[:8] + "...",
               )
           return "-"

       actions = ["action_sync_to_ifood"]

       @admin.action(description="Sync status to iFood")
       def action_sync_to_ifood(self, request, queryset):
           for order in queryset:
               if order.data.get("ifood_order_id"):
                   # Trigger sync
                   sync_status_to_ifood(order, None, order.status, "admin")


Catalog Sync (Availability)
---------------------------

Sync product availability to iFood using Listings.

Listing Model
~~~~~~~~~~~~~

The Listing model bridges Products and Channels:

.. code-block:: python

   # catalog/models.py

   class Listing(models.Model):
       """Product offering in a Sales Channel."""

       product = models.ForeignKey(Product, on_delete=models.CASCADE)
       channel = models.ForeignKey("omniman.Channel", on_delete=models.CASCADE)

       is_active = models.BooleanField(default=True)  # Strategic offer decision
       stock_threshold = models.PositiveIntegerField(default=0)  # Safety margin
       external_id = models.CharField(max_length=128, blank=True)  # iFood item ID
       last_synced_at = models.DateTimeField(null=True, blank=True)

       @property
       def is_available(self) -> bool:
           """Real availability = Offer AND Stock."""
           if not self.is_active:
               return False
           return self.check_stock_availability()["available"]

Syncing Availability
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # integrations/ifood/sync.py

   from catalog.models import Listing
   from integrations.ifood.client import IFoodClient

   def sync_listing_to_ifood(listing: Listing) -> bool:
       """Sync a Listing's availability to iFood."""
       if not listing.external_id:
           return True  # No iFood item linked

       client = IFoodClient()

       if listing.is_available:
           client.unpause_item(listing.external_id)
       else:
           client.pause_item(listing.external_id)

       listing.last_synced_at = timezone.now()
       listing.save(update_fields=["last_synced_at"])
       return True

   def sync_all_listings():
       """Sync all iFood listings."""
       channel = Channel.objects.get(code="ifood")
       listings = Listing.objects.filter(
           channel=channel,
           external_id__isnull=False,
       ).exclude(external_id="")

       for listing in listings:
           try:
               sync_listing_to_ifood(listing)
           except Exception as e:
               logger.error(f"Failed to sync {listing}: {e}")

Availability vs Offer
~~~~~~~~~~~~~~~~~~~~~

Important distinction:

- **is_active**: Strategic decision to offer the product (can be paused for promotions, seasonality, etc.)
- **Stock availability**: Operational reality (current inventory level)
- **Real availability**: is_active AND stock > threshold

.. code-block:: python

   # Cascade deactivation: Category → Products → Listings
   # When a category is deactivated, all products and listings follow

   @receiver(pre_save, sender=Category)
   def cascade_deactivate_products(sender, instance, **kwargs):
       if not instance.pk:
           return
       old = Category.objects.get(pk=instance.pk)
       if old.is_active and not instance.is_active:
           Product.objects.filter(category=instance, is_active=True).update(is_active=False)

Polling Recommendation
~~~~~~~~~~~~~~~~~~~~~~

iFood recommends polling every 30 seconds for merchants with < 500 items:

.. code-block:: python

   # management/commands/sync_ifood_catalog.py

   from django.core.management.base import BaseCommand
   from integrations.ifood.sync import sync_all_listings

   class Command(BaseCommand):
       help = "Sync catalog availability to iFood"

       def handle(self, *args, **options):
           sync_all_listings()
           self.stdout.write(self.style.SUCCESS("Catalog synced"))

   # Run via cron or scheduler every 30s


Best Practices
--------------

1. **Webhook Verification**: Always verify webhook signatures.

2. **Idempotent Processing**: Handle duplicate webhooks gracefully.

3. **Error Handling**: Log errors but don't fail on sync issues.

4. **Rate Limiting**: Respect iFood API rate limits.

5. **Testing**: Use sandbox mode for development.

6. **Catalog Sync**: Poll every 30s for real-time availability updates.

7. **Threshold Hierarchy**: Listing → Product → Channel.config["default_stock_threshold"]


See Also
--------

- :doc:`payments` - Payment integration
- :doc:`custom` - Creating custom integrations
- :doc:`../guides/status-flow` - Status transitions
