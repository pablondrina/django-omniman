Payment Integration
===================

Omniman provides a flexible payment integration system supporting multiple
payment gateways through a unified protocol.


Architecture Overview
---------------------

.. code-block:: text

   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
   │   Session   │────▶│   Commit    │────▶│    Order    │
   └─────────────┘     └──────┬──────┘     └──────┬──────┘
                              │                   │
                              ▼                   ▼
                       ┌─────────────┐     ┌─────────────┐
                       │ payment.hold│     │payment.confirm
                       │  Directive  │     │  Directive  │
                       └──────┬──────┘     └──────┬──────┘
                              │                   │
                              ▼                   ▼
                       ┌─────────────────────────────────┐
                       │        PaymentBackend           │
                       │  (Stripe, Efi/Pix, Mock, etc.)  │
                       └─────────────────────────────────┘


PaymentBackend Protocol
-----------------------

.. code-block:: python

   from typing import Protocol
   from dataclasses import dataclass

   @dataclass
   class PaymentResult:
       success: bool
       transaction_id: str | None
       status: str  # pending, authorized, captured, failed
       error_code: str | None = None
       error_message: str | None = None
       metadata: dict | None = None

   class PaymentBackend(Protocol):
       """Protocol for payment backends."""

       def authorize(
           self,
           amount_q: int,
           currency: str,
           order_ref: str,
           payment_method: dict,
           metadata: dict | None = None,
       ) -> PaymentResult:
           """Authorize payment (hold funds)."""
           ...

       def capture(
           self,
           transaction_id: str,
           amount_q: int | None = None,
       ) -> PaymentResult:
           """Capture previously authorized payment."""
           ...

       def charge(
           self,
           amount_q: int,
           currency: str,
           order_ref: str,
           payment_method: dict,
           metadata: dict | None = None,
       ) -> PaymentResult:
           """Authorize and capture in one step."""
           ...

       def refund(
           self,
           transaction_id: str,
           amount_q: int | None = None,
           reason: str | None = None,
       ) -> PaymentResult:
           """Refund a captured payment."""
           ...

       def get_status(
           self,
           transaction_id: str,
       ) -> PaymentResult:
           """Get current payment status."""
           ...


Stripe Integration
------------------

Configuration
~~~~~~~~~~~~~

.. code-block:: python

   # settings.py

   OMNIMAN = {
       "PAYMENT_BACKENDS": {
           "stripe": {
               "class": "omniman.contrib.payment.adapters.stripe.StripeBackend",
               "config": {
                   "api_key": env("STRIPE_SECRET_KEY"),
                   "webhook_secret": env("STRIPE_WEBHOOK_SECRET"),
                   "currency": "brl",
               },
           },
       },
       "DEFAULT_PAYMENT_BACKEND": "stripe",
   }

   # Channel config
   Channel.objects.create(
       code="ecommerce",
       config={
           "payment_backend": "stripe",
           "payment_flow": "authorize_capture",  # or "charge"
       },
   )

StripeBackend Implementation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # omniman/contrib/payment/adapters/stripe.py

   import stripe
   from omniman.contrib.payment.protocols import PaymentBackend, PaymentResult

   class StripeBackend:
       """Stripe payment backend."""

       def __init__(self, config: dict):
           self.api_key = config["api_key"]
           self.currency = config.get("currency", "usd")
           stripe.api_key = self.api_key

       def authorize(
           self,
           amount_q: int,
           currency: str,
           order_ref: str,
           payment_method: dict,
           metadata: dict | None = None,
       ) -> PaymentResult:
           try:
               intent = stripe.PaymentIntent.create(
                   amount=amount_q,
                   currency=currency or self.currency,
                   payment_method=payment_method.get("payment_method_id"),
                   confirm=True,
                   capture_method="manual",  # Authorize only
                   metadata={
                       "order_ref": order_ref,
                       **(metadata or {}),
                   },
               )
               return PaymentResult(
                   success=True,
                   transaction_id=intent.id,
                   status="authorized",
                   metadata={"intent": intent},
               )
           except stripe.error.CardError as e:
               return PaymentResult(
                   success=False,
                   transaction_id=None,
                   status="failed",
                   error_code=e.code,
                   error_message=str(e),
               )

       def capture(
           self,
           transaction_id: str,
           amount_q: int | None = None,
       ) -> PaymentResult:
           try:
               intent = stripe.PaymentIntent.capture(
                   transaction_id,
                   amount_to_capture=amount_q,
               )
               return PaymentResult(
                   success=True,
                   transaction_id=intent.id,
                   status="captured",
               )
           except stripe.error.StripeError as e:
               return PaymentResult(
                   success=False,
                   transaction_id=transaction_id,
                   status="failed",
                   error_message=str(e),
               )

       def refund(
           self,
           transaction_id: str,
           amount_q: int | None = None,
           reason: str | None = None,
       ) -> PaymentResult:
           refund = stripe.Refund.create(
               payment_intent=transaction_id,
               amount=amount_q,
               reason=reason or "requested_by_customer",
           )
           return PaymentResult(
               success=True,
               transaction_id=refund.id,
               status="refunded",
           )

Stripe Webhooks
~~~~~~~~~~~~~~~

.. code-block:: python

   # views.py

   import stripe
   from django.http import HttpResponse
   from django.views.decorators.csrf import csrf_exempt
   from omniman.models import Order, Directive

   @csrf_exempt
   def stripe_webhook(request):
       payload = request.body
       sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
       webhook_secret = settings.STRIPE_WEBHOOK_SECRET

       try:
           event = stripe.Webhook.construct_event(
               payload, sig_header, webhook_secret
           )
       except ValueError:
           return HttpResponse(status=400)
       except stripe.error.SignatureVerificationError:
           return HttpResponse(status=400)

       if event["type"] == "payment_intent.succeeded":
           intent = event["data"]["object"]
           order_ref = intent["metadata"]["order_ref"]

           order = Order.objects.get(ref=order_ref)
           order.data["payment"] = {
               "status": "captured",
               "transaction_id": intent["id"],
               "amount_q": intent["amount"],
           }
           order.save()

           # Trigger auto-transition
           flow = order.channel.config.get("order_flow", {})
           auto = flow.get("auto_transitions", {})
           if auto.get("on_payment_confirm"):
               order.transition_status(auto["on_payment_confirm"], actor="stripe-webhook")

       return HttpResponse(status=200)


Pix Integration (Efi/Gerencianet)
---------------------------------

Configuration
~~~~~~~~~~~~~

.. code-block:: python

   OMNIMAN = {
       "PAYMENT_BACKENDS": {
           "efi": {
               "class": "omniman.contrib.payment.adapters.efi.EfiBackend",
               "config": {
                   "client_id": env("EFI_CLIENT_ID"),
                   "client_secret": env("EFI_CLIENT_SECRET"),
                   "certificate": env("EFI_CERTIFICATE_PATH"),
                   "sandbox": env.bool("EFI_SANDBOX", True),
                   "pix_key": env("EFI_PIX_KEY"),
               },
           },
       },
   }

EfiBackend Implementation
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # omniman/contrib/payment/adapters/efi.py

   from efipay import EfiPay
   from omniman.contrib.payment.protocols import PaymentBackend, PaymentResult

   class EfiBackend:
       """Efi/Gerencianet Pix payment backend."""

       def __init__(self, config: dict):
           self.client_id = config["client_id"]
           self.client_secret = config["client_secret"]
           self.certificate = config["certificate"]
           self.sandbox = config.get("sandbox", True)
           self.pix_key = config["pix_key"]

           self.efi = EfiPay({
               "client_id": self.client_id,
               "client_secret": self.client_secret,
               "certificate": self.certificate,
               "sandbox": self.sandbox,
           })

       def charge(
           self,
           amount_q: int,
           currency: str,
           order_ref: str,
           payment_method: dict,
           metadata: dict | None = None,
       ) -> PaymentResult:
           """Create Pix charge."""

           # Create charge
           body = {
               "calendario": {"expiracao": 3600},  # 1 hour
               "valor": {"original": f"{amount_q / 100:.2f}"},
               "chave": self.pix_key,
               "infoAdicionais": [
                   {"nome": "order_ref", "valor": order_ref},
               ],
           }

           response = self.efi.pixCreateImmediateCharge(body=body)

           # Generate QR code
           qr_response = self.efi.pixGenerateQRCode(
               params={"id": response["loc"]["id"]}
           )

           return PaymentResult(
               success=True,
               transaction_id=response["txid"],
               status="pending",
               metadata={
                   "qr_code": qr_response["qrcode"],
                   "qr_image": qr_response["imagemQrcode"],
                   "copy_paste": response["pixCopiaECola"],
                   "expires_at": response["calendario"]["criacao"],
               },
           )

       def get_status(self, transaction_id: str) -> PaymentResult:
           """Check Pix payment status."""
           response = self.efi.pixDetailCharge(params={"txid": transaction_id})

           status_map = {
               "ATIVA": "pending",
               "CONCLUIDA": "captured",
               "REMOVIDA_PELO_USUARIO_RECEBEDOR": "cancelled",
               "REMOVIDA_PELO_PSP": "failed",
           }

           return PaymentResult(
               success=response["status"] == "CONCLUIDA",
               transaction_id=transaction_id,
               status=status_map.get(response["status"], "unknown"),
           )


Payment Handlers
----------------

PaymentHoldHandler
~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from omniman.registry import registry
   from omniman.contrib.payment import get_payment_backend

   @registry.register_handler("payment.hold")
   class PaymentHoldHandler:
       """Handler for payment authorization."""

       def handle(self, directive, ctx):
           payload = directive.payload
           order = directive.order

           backend = get_payment_backend(order.channel)

           result = backend.authorize(
               amount_q=payload["amount_q"],
               currency=payload.get("currency", "brl"),
               order_ref=order.ref,
               payment_method=payload["payment_method"],
           )

           if result.success:
               order.data["payment"] = {
                   "status": "authorized",
                   "transaction_id": result.transaction_id,
                   "amount_q": payload["amount_q"],
               }
               order.save()

               directive.status = "completed"
               directive.result = {"transaction_id": result.transaction_id}
           else:
               directive.status = "failed"
               directive.result = {
                   "error_code": result.error_code,
                   "error_message": result.error_message,
               }

           directive.save()
           return result

PaymentConfirmHandler
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   @registry.register_handler("payment.confirm")
   class PaymentConfirmHandler:
       """Handler for payment capture."""

       def handle(self, directive, ctx):
           order = directive.order
           payment = order.data.get("payment", {})

           if not payment.get("transaction_id"):
               directive.status = "failed"
               directive.result = {"error": "No transaction to capture"}
               directive.save()
               return

           backend = get_payment_backend(order.channel)

           result = backend.capture(
               transaction_id=payment["transaction_id"],
               amount_q=payment.get("amount_q"),
           )

           if result.success:
               order.data["payment"]["status"] = "captured"
               order.save()

               # Auto-transition
               flow = order.channel.config.get("order_flow", {})
               auto = flow.get("auto_transitions", {})
               if auto.get("on_payment_confirm"):
                   order.transition_status(
                       auto["on_payment_confirm"],
                       actor="payment.confirm",
                   )

           directive.status = "completed" if result.success else "failed"
           directive.result = {"status": result.status}
           directive.save()


Mock Backend for Testing
------------------------

.. code-block:: python

   # omniman/contrib/payment/adapters/mock.py

   class MockPaymentBackend:
       """Mock payment backend for testing."""

       def __init__(self, config: dict = None):
           self.config = config or {}
           self.transactions = {}

       def authorize(self, amount_q, currency, order_ref, payment_method, metadata=None):
           txn_id = f"mock_{order_ref}"
           self.transactions[txn_id] = {
               "status": "authorized",
               "amount_q": amount_q,
           }
           return PaymentResult(
               success=True,
               transaction_id=txn_id,
               status="authorized",
           )

       def capture(self, transaction_id, amount_q=None):
           if transaction_id in self.transactions:
               self.transactions[transaction_id]["status"] = "captured"
               return PaymentResult(
                   success=True,
                   transaction_id=transaction_id,
                   status="captured",
               )
           return PaymentResult(
               success=False,
               transaction_id=transaction_id,
               status="failed",
               error_message="Transaction not found",
           )

       def refund(self, transaction_id, amount_q=None, reason=None):
           return PaymentResult(
               success=True,
               transaction_id=f"refund_{transaction_id}",
               status="refunded",
           )


Testing Payments
----------------

.. code-block:: python

   import pytest
   from omniman.contrib.payment.adapters.mock import MockPaymentBackend

   @pytest.fixture
   def mock_payment(mocker):
       backend = MockPaymentBackend()
       mocker.patch(
           "omniman.contrib.payment.get_payment_backend",
           return_value=backend,
       )
       return backend

   def test_payment_authorize(mock_payment, order):
       result = mock_payment.authorize(
           amount_q=1000,
           currency="brl",
           order_ref=order.ref,
           payment_method={"type": "card"},
       )
       assert result.success
       assert result.status == "authorized"

   def test_payment_capture(mock_payment, order):
       auth = mock_payment.authorize(
           amount_q=1000,
           currency="brl",
           order_ref=order.ref,
           payment_method={"type": "card"},
       )
       capture = mock_payment.capture(auth.transaction_id)
       assert capture.success
       assert capture.status == "captured"


Best Practices
--------------

1. **Use Authorize + Capture**: For e-commerce, separate authorization and capture.

2. **Handle Webhooks**: Always implement webhook handlers for async payment updates.

3. **Idempotency**: Use idempotency keys for payment operations.

4. **Logging**: Log all payment operations for debugging.

5. **Test with Mock**: Use MockPaymentBackend for unit tests.


See Also
--------

- :doc:`../guides/orders` - Order lifecycle
- :doc:`custom` - Creating custom integrations
- :doc:`../deployment/production` - Production configuration
