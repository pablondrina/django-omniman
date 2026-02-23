"""
Omniman Noop Customer Adapter -- No-op backend for development and testing.

Use this when you don't have a customer identity system (Guestman) connected.
Customer lookups return minimal placeholder data, validations always pass,
and order recording is a no-op.

Usage::

    from omniman.contrib.customer.adapters.noop import NoopCustomerBackend

    backend = NoopCustomerBackend()
    info = backend.get_customer("CUST-001")
    # CustomerInfo(code="CUST-001", name="Guest CUST-001", ...)
"""

from __future__ import annotations

import logging

from omniman.contrib.customer.protocols import (
    CustomerContext,
    CustomerInfo,
    CustomerValidationResult,
)

logger = logging.getLogger(__name__)


class NoopCustomerBackend:
    """
    Customer backend that returns minimal placeholder data.

    All operations succeed with sensible defaults:

    - ``get_customer`` returns a ``CustomerInfo`` with the code as the name
    - ``validate_customer`` always returns valid
    - ``get_price_list_code`` returns ``None`` (no customer-specific pricing)
    - ``get_customer_context`` returns a minimal context
    - ``record_order`` is a no-op that returns ``True``

    This backend implements the ``CustomerBackend`` protocol and is suitable
    for development and testing without Guestman.
    """

    def get_customer(self, code: str) -> CustomerInfo | None:
        """Returns a minimal CustomerInfo with the code as the display name."""
        logger.debug("NoopCustomerBackend.get_customer: code=%s (returning placeholder)", code)
        return CustomerInfo(
            code=code,
            name=f"Guest {code}",
            customer_type="individual",
        )

    def validate_customer(self, code: str) -> CustomerValidationResult:
        """Always returns valid."""
        logger.debug("NoopCustomerBackend.validate_customer: code=%s (always valid)", code)
        return CustomerValidationResult(
            valid=True,
            code=code,
            info=self.get_customer(code),
        )

    def get_price_list_code(self, customer_code: str) -> str | None:
        """Returns None. No customer-specific pricing in noop mode."""
        return None

    def get_customer_context(self, code: str) -> CustomerContext | None:
        """Returns a minimal customer context with empty preferences and history."""
        info = self.get_customer(code)
        if info is None:
            return None

        logger.debug("NoopCustomerBackend.get_customer_context: code=%s (returning minimal context)", code)
        return CustomerContext(
            info=info,
            preferences={},
            recent_orders=[],
        )

    def record_order(self, customer_code: str, order_data: dict) -> bool:
        """No-op: always returns True."""
        logger.debug("NoopCustomerBackend.record_order: customer_code=%s (no-op)", customer_code)
        return True
