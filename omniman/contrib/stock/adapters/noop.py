"""
Omniman Noop Stock Adapter -- No-op backend for development and testing.

Use this when you don't have an inventory system (Stockman) connected.
Every SKU is reported as available, holds are accepted silently, and
fulfillment is a no-op.

Usage::

    from omniman.contrib.stock.adapters.noop import NoopStockBackend
    from omniman.contrib.stock.handlers import StockHoldHandler, StockCommitHandler
    from omniman import registry

    backend = NoopStockBackend()
    registry.register_directive_handler(StockHoldHandler(backend=backend))
    registry.register_directive_handler(StockCommitHandler(backend=backend))
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from django.utils import timezone

from omniman.contrib.stock.protocols import (
    Alternative,
    AvailabilityResult,
    HoldResult,
)

logger = logging.getLogger(__name__)


class NoopStockBackend:
    """
    Stock backend that always reports items as available.

    All operations succeed silently:

    - ``check_availability`` returns available with unlimited quantity
    - ``create_hold`` returns a synthetic hold ID without reserving anything
    - ``release_hold`` and ``fulfill_hold`` are no-ops
    - ``get_alternatives`` returns an empty list
    - ``release_holds_for_reference`` returns 0

    This backend implements the ``StockBackend`` protocol and is safe to use
    with ``StockHoldHandler`` and ``StockCommitHandler``.
    """

    # Counter for generating unique synthetic hold IDs
    _hold_counter: int = 0

    def check_availability(
        self,
        sku: str,
        quantity: Decimal,
        target_date: date | None = None,
    ) -> AvailabilityResult:
        """Always returns available with a large available quantity."""
        logger.debug("NoopStockBackend.check_availability: sku=%s qty=%s (always available)", sku, quantity)
        return AvailabilityResult(
            available=True,
            available_qty=Decimal("999999"),
        )

    def create_hold(
        self,
        sku: str,
        quantity: Decimal,
        expires_at: datetime | None = None,
        reference: str | None = None,
    ) -> HoldResult:
        """Returns a successful hold with a synthetic ID. Nothing is actually reserved."""
        NoopStockBackend._hold_counter += 1
        hold_id = f"noop-hold:{NoopStockBackend._hold_counter}"
        hold_expires = expires_at or (timezone.now() + timedelta(minutes=15))

        logger.debug(
            "NoopStockBackend.create_hold: sku=%s qty=%s hold_id=%s (no-op)",
            sku, quantity, hold_id,
        )

        return HoldResult(
            success=True,
            hold_id=hold_id,
            expires_at=hold_expires,
        )

    def release_hold(self, hold_id: str) -> None:
        """No-op: nothing to release."""
        logger.debug("NoopStockBackend.release_hold: hold_id=%s (no-op)", hold_id)

    def fulfill_hold(self, hold_id: str, reference: str | None = None) -> None:
        """No-op: nothing to fulfill."""
        logger.debug("NoopStockBackend.fulfill_hold: hold_id=%s reference=%s (no-op)", hold_id, reference)

    def get_alternatives(self, sku: str, quantity: Decimal) -> list[Alternative]:
        """Returns an empty list. No alternatives in noop mode."""
        return []

    def release_holds_for_reference(self, reference: str) -> int:
        """No-op: returns 0 released holds."""
        logger.debug("NoopStockBackend.release_holds_for_reference: reference=%s (no-op)", reference)
        return 0
