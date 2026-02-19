"""
Example pricing modifier that looks up prices from the Product catalog.

This demonstrates how to implement a Modifier that integrates with
your product catalog to fill in prices during session modification.
"""

from typing import Any


class SimplePricingModifier:
    """
    Modifier that fills in unit_price_q from the Product catalog.

    This is triggered after every ModifyService.modify_session() call.
    It looks up products by SKU and fills in missing prices.

    For channels with pricing_policy="internal", this ensures all items
    have their prices set from the catalog.

    Usage:
        from omniman import registry
        from example.shop.pricing import SimplePricingModifier

        registry.register_modifier(SimplePricingModifier())
    """

    code = "shop.pricing"
    order = 10  # Run early in the modifier chain

    def apply(self, *, channel: Any, session: Any, ctx: dict) -> None:
        """
        Apply pricing to session items.

        Only runs for channels with pricing_policy="internal".
        Items with existing unit_price_q are not modified.
        """
        # Skip if channel uses external pricing
        if session.pricing_policy == "external":
            return

        # Lazy import to avoid circular imports
        from .models import Product

        items = session.items
        modified = False

        # Collect SKUs that need pricing
        skus_to_price = [
            item["sku"]
            for item in items
            if not item.get("unit_price_q")
        ]

        if not skus_to_price:
            return

        # Batch lookup products
        products = {
            p.sku: p
            for p in Product.objects.filter(sku__in=skus_to_price, is_active=True)
        }

        # Apply prices
        for item in items:
            if not item.get("unit_price_q"):
                product = products.get(item["sku"])
                if product:
                    item["unit_price_q"] = product.price_q
                    item["name"] = product.name
                    modified = True

        if modified:
            session.items = items
