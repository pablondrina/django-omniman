"""
Omniman Noop Pricing Adapter -- No-op modifier for development and testing.

Use this when you don't have a product catalog (Offerman) or any pricing
backend configured. Items keep whatever ``unit_price_q`` was supplied in the
``add_line`` op; no lookup is performed.

Usage::

    from omniman.contrib.pricing.adapters.noop import NoopPricingModifier
    from omniman import registry

    registry.register_modifier(NoopPricingModifier())
"""

from __future__ import annotations

from typing import Any


class NoopPricingModifier:
    """
    Modifier that leaves item prices unchanged.

    When ``pricing_policy == "internal"``, a real pricing modifier would look up
    ``unit_price_q`` from a catalog backend. This no-op variant skips that step
    entirely, which is useful for:

    - Development without a product catalog
    - Tests that set prices explicitly in ``add_line`` ops
    - Channels where ``pricing_policy == "external"`` (prices come from the caller)

    Implements the ``Modifier`` protocol (``code``, ``order``, ``apply``).
    """

    code = "pricing.noop"
    order = 10

    def apply(self, *, channel: Any, session: Any, ctx: dict) -> None:
        """No-op: items retain their current prices without modification."""
        pass
