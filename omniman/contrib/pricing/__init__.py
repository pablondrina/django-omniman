"""
Omniman Pricing Contrib — Precificação de itens.

Uso:
    from omniman.contrib.pricing.protocols import PricingBackend
    from omniman.contrib.pricing.modifiers import InternalPricingModifier

Para uso simples (Product.price_q):
    from omniman.contrib.pricing.adapters.simple import SimplePricingBackend
"""

from .protocols import PricingBackend

__all__ = ["PricingBackend"]








