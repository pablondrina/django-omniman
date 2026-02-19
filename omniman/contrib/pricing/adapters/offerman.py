"""
Omniman Offerman Pricing Adapter — Adapter para precificação via Offerman.

Este adapter conecta o contrib/pricing ao Offerman, usando a API pública:
- CatalogService.get(sku)
- CatalogService.price(sku, qty, channel)
- CatalogService.validate(sku)
- CatalogService.expand(sku, qty)
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)


def _offerman_available() -> bool:
    """Check if Offerman is installed."""
    try:
        from offerman import CatalogService
        return True
    except ImportError:
        return False


class OffermanPricingBackend:
    """
    Adapter que conecta contrib/pricing ao Offerman.

    Usa CatalogService.price() para obter preços.
    A convenção Channel.code == PriceList.slug determina
    qual lista de preços aplicar automaticamente.
    """

    def get_price(self, sku: str, channel: Any) -> int | None:
        """
        Retorna preço do produto para o canal.

        Args:
            sku: Código do produto
            channel: Canal de venda (com atributo .code)

        Returns:
            Preço em q (centavos) ou None se não encontrado/inválido
        """
        if not _offerman_available():
            logger.warning("get_price: Offerman not installed")
            return None

        from offerman import CatalogService

        try:
            channel_code = getattr(channel, "code", None) if channel else None
            price_q = CatalogService.price(sku, Decimal("1"), channel=channel_code)
            return price_q
        except Exception as e:
            logger.warning("get_price: Failed for SKU %s: %s", sku, e)
            return None


class OffermanCatalogBackend:
    """
    Adapter completo para catálogo via Offerman.

    Usa CatalogService para todas as operações de catálogo.
    """

    def get_product(self, sku: str):
        """
        Retorna produto.

        Returns:
            Product do Offerman ou None se não encontrado
        """
        if not _offerman_available():
            logger.warning("get_product: Offerman not installed")
            return None

        from offerman import CatalogService

        try:
            return CatalogService.get(sku)
        except Exception as e:
            logger.debug("get_product: Failed for SKU %s: %s", sku, e)
            return None

    def get_price(
        self,
        sku: str,
        qty: Decimal = Decimal("1"),
        channel: str | None = None,
    ) -> int:
        """
        Retorna preço do produto em centavos.

        Returns:
            Preço total em centavos
        """
        if not _offerman_available():
            raise ImportError("Offerman is not installed")

        from offerman import CatalogService

        return CatalogService.price(sku, qty, channel=channel)

    def validate_sku(self, sku: str):
        """
        Valida se SKU existe e está ativo.

        Returns:
            SkuValidation do Offerman
        """
        if not _offerman_available():
            raise ImportError("Offerman is not installed")

        from offerman import CatalogService

        return CatalogService.validate(sku)

    def expand_bundle(self, sku: str, qty: Decimal = Decimal("1")):
        """
        Expande bundle em componentes.

        Returns:
            list[dict] com componentes
        """
        if not _offerman_available():
            return []

        from offerman import CatalogService

        try:
            return CatalogService.expand(sku, qty)
        except Exception:
            return []

    def is_bundle(self, sku: str) -> bool:
        """Verifica se SKU é um bundle."""
        if not _offerman_available():
            return False

        from offerman import CatalogService

        try:
            product = CatalogService.get(sku)
            return product.is_bundle if product else False
        except Exception:
            return False

    def search_products(
        self,
        query: str | None = None,
        category: str | None = None,
        collection: str | None = None,
        limit: int = 20,
    ):
        """
        Busca produtos.

        Returns:
            list[Product] do Offerman
        """
        if not _offerman_available():
            return []

        from offerman import CatalogService

        try:
            return CatalogService.search(
                query=query,
                category=category,
                collection=collection,
                limit=limit,
            )
        except Exception as e:
            logger.warning("search_products: Failed: %s", e)
            return []
