"""
Omniman Payment Contrib — Processamento de pagamentos.

Uso:
    from omniman.contrib.payment.protocols import PaymentBackend
    from omniman.contrib.payment.handlers import PaymentCaptureHandler

Para desenvolvimento/testes:
    from omniman.contrib.payment.adapters.mock import MockPaymentBackend

Para Stripe:
    from omniman.contrib.payment.adapters.stripe import StripeBackend

Para Pix (Efi/antigo Gerencianet):
    from omniman.contrib.payment.adapters.efi import EfiPixBackend
"""

from .protocols import (
    PaymentBackend,
    PaymentIntent,
    CaptureResult,
    RefundResult,
    PaymentStatus,
)

__all__ = [
    "PaymentBackend",
    "PaymentIntent",
    "CaptureResult",
    "RefundResult",
    "PaymentStatus",
]
