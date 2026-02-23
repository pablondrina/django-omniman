"""
Omniman Simple Pricing Adapter — Adapter para precificação simples.

Busca preço diretamente do model Product.price_q.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from django.core.exceptions import ObjectDoesNotExist

logger = logging.getLogger(__name__)


class SimplePricingBackend:
    """
    Adapter para precificação simples via Product.price_q.

    Uso:
        from omniman.contrib.pricing.adapters.simple import SimplePricingBackend
        from catalog.models import Product

        def get_product(sku: str):
            return Product.objects.get(sku=sku)

        backend = SimplePricingBackend(product_resolver=get_product)
    """

    def __init__(self, product_resolver: Callable[[str], Any]):
        """
        Inicializa o adapter.

        Args:
            product_resolver: Função que recebe SKU e retorna objeto produto
                             (deve ter atributo price_q)
        """
        self.get_product = product_resolver

    def get_price(self, sku: str, channel: Any) -> int | None:
        """
        Retorna preço do produto.

        Args:
            sku: Código do produto
            channel: Canal de venda (não usado nesta implementação)

        Returns:
            Preço em q (centavos) ou None se não encontrado
        """
        try:
            product = self.get_product(sku)
            return product.price_q
        except ObjectDoesNotExist:
            return None
        except Exception:
            logger.exception("Unexpected error in SimplePricingBackend.get_price for sku=%s", sku)
            return None


class ChannelPricingBackend:
    """
    Adapter para precificação por canal.

    Busca preço em ChannelListing primeiro, fallback para Product.price_q.

    Uso:
        from omniman.contrib.pricing.adapters.simple import ChannelPricingBackend
        from catalog.models import Product, ChannelListing

        def get_product(sku: str):
            return Product.objects.get(sku=sku)

        def get_listing(sku: str, channel_code: str):
            return ChannelListing.objects.get(product__sku=sku, channel__code=channel_code)

        backend = ChannelPricingBackend(
            product_resolver=get_product,
            listing_resolver=get_listing,
        )
    """

    def __init__(
        self,
        product_resolver: Callable[[str], Any],
        listing_resolver: Callable[[str, str], Any] | None = None,
    ):
        """
        Inicializa o adapter.

        Args:
            product_resolver: Função que recebe SKU e retorna produto
            listing_resolver: Função que recebe (SKU, channel_code) e retorna listing
        """
        self.get_product = product_resolver
        self.get_listing = listing_resolver

    def get_price(self, sku: str, channel: Any) -> int | None:
        """
        Retorna preço do produto para o canal.

        Prioridade:
        1. ChannelListing.price_q (se listing_resolver fornecido)
        2. Product.price_q (fallback)

        Args:
            sku: Código do produto
            channel: Canal de venda

        Returns:
            Preço em q (centavos) ou None se não encontrado
        """
        # Tenta listing primeiro
        if self.get_listing:
            try:
                listing = self.get_listing(sku, channel.code)
                if hasattr(listing, "price_q") and listing.price_q is not None:
                    return listing.price_q
            except ObjectDoesNotExist:
                pass
            except Exception:
                logger.exception("Unexpected error in ChannelPricingBackend.get_price listing lookup for sku=%s", sku)
                pass  # Fall through to product fallback

        # Fallback para product
        try:
            product = self.get_product(sku)
            return product.price_q
        except ObjectDoesNotExist:
            return None
        except Exception:
            logger.exception("Unexpected error in ChannelPricingBackend.get_price product fallback for sku=%s", sku)
            return None








