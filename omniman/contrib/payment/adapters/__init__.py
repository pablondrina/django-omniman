"""
Payment Adapters — Implementações de PaymentBackend.

Backends disponíveis:
- MockPaymentBackend: Para desenvolvimento e testes
- StripeBackend: Cartões via Stripe
- EfiPixBackend: Pix via Efi (antigo Gerencianet)
"""

from .mock import MockPaymentBackend

# Lazy imports para não exigir dependências opcionais
def get_stripe_backend():
    from .stripe import StripeBackend
    return StripeBackend

def get_efi_backend():
    from .efi import EfiPixBackend
    return EfiPixBackend

# Alias for backwards compatibility
get_pix_backend = get_efi_backend

__all__ = [
    "MockPaymentBackend",
    "get_stripe_backend",
    "get_efi_backend",
    "get_pix_backend",  # Deprecated alias
]
