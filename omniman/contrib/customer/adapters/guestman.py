"""
Omniman Guestman Adapter — Adapter para integração com Guestman.

Este adapter conecta o contrib/customer ao Guestman, usando a API pública:
- CustomerService.get(code)
- CustomerService.validate(code)
- CustomerService.price_list(code)
- PreferenceService (contrib/preferences)
- InsightService (contrib/insights)
- OrderHistoryBackend (protocol)
"""

from __future__ import annotations

import logging
import threading

from omniman.contrib.customer.protocols import (
    AddressInfo,
    CustomerBackend,
    CustomerContext,
    CustomerInfo,
    CustomerValidationResult,
)

logger = logging.getLogger(__name__)


def _guestman_available() -> bool:
    """Check if Guestman is installed."""
    try:
        from guestman.services import customer as CustomerService  # noqa: F811
        return True
    except ImportError:
        return False


class GuestmanBackend:
    """
    Adapter que conecta contrib/customer ao Guestman.

    Usa a API pública do Guestman:
    - CustomerService.get(), validate(), price_list()
    - PreferenceService.get_preferences_dict() (contrib)
    - InsightService.get_insight() (contrib)
    - OrderHistoryBackend (protocol) para histórico
    """

    def get_customer(self, code: str) -> CustomerInfo | None:
        """Get customer information by code."""
        if not _guestman_available():
            logger.warning("get_customer: Guestman not installed")
            return None

        from guestman.services import customer as CustomerService

        cust = CustomerService.get(code)
        if not cust:
            return None

        # Build default address
        default_addr = None
        if cust.default_address:
            addr = cust.default_address
            default_addr = AddressInfo(
                label=addr.display_label,
                formatted_address=addr.formatted_address,
                short_address=addr.short_address,
                complement=addr.complement,
                delivery_instructions=getattr(addr, "delivery_instructions", None),
                latitude=float(addr.latitude) if addr.latitude else None,
                longitude=float(addr.longitude) if addr.longitude else None,
            )

        # Get insights if contrib/insights is available
        total_orders = 0
        is_vip = False
        is_at_risk = False
        favorite_products = []

        try:
            from guestman.contrib.insights.service import InsightService
            insight = InsightService.get_insight(code)
            if insight:
                total_orders = insight.total_orders
                is_vip = insight.is_vip
                is_at_risk = insight.is_at_risk
                if insight.favorite_products:
                    favorite_products = [p.get("sku") for p in insight.favorite_products[:5] if p.get("sku")]
        except ImportError:
            pass  # contrib/insights not installed

        return CustomerInfo(
            code=cust.code,
            name=cust.name,
            customer_type=cust.customer_type,
            group_code=cust.group.code if cust.group else None,
            price_list_code=cust.price_list_code,
            phone=cust.phone,
            email=cust.email,
            default_address=default_addr,
            total_orders=total_orders,
            is_vip=is_vip,
            is_at_risk=is_at_risk,
            favorite_products=favorite_products,
        )

    def validate_customer(self, code: str) -> CustomerValidationResult:
        """Validate if customer can operate."""
        if not _guestman_available():
            return CustomerValidationResult(
                valid=False,
                code=code,
                error_code="GUESTMAN_NOT_INSTALLED",
                message="Guestman is not installed",
            )

        from guestman.services import customer as CustomerService

        validation = CustomerService.validate(code)

        if not validation.valid:
            return CustomerValidationResult(
                valid=False,
                code=code,
                error_code=validation.error_code,
                message=validation.message,
            )

        # Get full customer info
        cust_info = self.get_customer(code)

        return CustomerValidationResult(
            valid=True,
            code=code,
            info=cust_info,
        )

    def get_price_list_code(self, customer_code: str) -> str | None:
        """Return applicable PriceList code for customer."""
        if not _guestman_available():
            return None

        from guestman.services import customer as CustomerService
        return CustomerService.price_list(customer_code)

    def get_customer_context(self, code: str) -> CustomerContext | None:
        """Return complete customer context for personalization."""
        if not _guestman_available():
            return None

        cust_info = self.get_customer(code)
        if not cust_info:
            return None

        # Preferences (contrib/preferences)
        prefs = {}
        try:
            from guestman.contrib.preferences.service import PreferenceService
            prefs = PreferenceService.get_preferences_dict(code)
        except ImportError:
            pass

        # Recent orders via OrderHistoryBackend
        recent_orders = []
        rfm_segment = None
        days_since = None

        try:
            from guestman.contrib.insights.service import InsightService
            insight = InsightService.get_insight(code)
            if insight:
                rfm_segment = insight.rfm_segment
                days_since = insight.days_since_last_order

            # Get recent orders from OrderHistoryBackend
            from django.conf import settings
            from django.utils.module_loading import import_string

            guestman_settings = getattr(settings, "GUESTMAN", {})
            backend_path = guestman_settings.get("ORDER_HISTORY_BACKEND")
            if backend_path:
                backend_class = import_string(backend_path)
                backend = backend_class()
                orders = backend.get_customer_orders(code, limit=5)
                for o in orders:
                    recent_orders.append({
                        "order_ref": o.order_ref,
                        "ordered_at": o.ordered_at.isoformat(),
                        "total_q": o.total_q,
                        "channel_code": o.channel_code,
                        "items_count": o.items_count,
                    })
        except ImportError:
            pass

        # Recommendations (simple: favorite products)
        recommended = cust_info.favorite_products[:3] if cust_info.favorite_products else []

        return CustomerContext(
            info=cust_info,
            preferences=prefs,
            recent_orders=recent_orders,
            rfm_segment=rfm_segment,
            days_since_last_order=days_since,
            recommended_products=recommended,
        )

    def record_order(self, customer_code: str, order_data: dict) -> bool:
        """
        Record order in customer history.

        This triggers insight recalculation if contrib/insights is installed.
        """
        if not _guestman_available():
            logger.warning("record_order: Guestman not installed")
            return False

        try:
            from guestman.contrib.insights.service import InsightService
            InsightService.recalculate(customer_code)
            return True
        except ImportError:
            # Insights not installed, nothing to recalculate
            return True
        except Exception as e:
            logger.warning("record_order: Failed for customer %s: %s", customer_code, e)
            return False


# Singleton factory
_lock = threading.Lock()
_backend_instance: GuestmanBackend | None = None


def get_customer_backend() -> GuestmanBackend:
    """Return singleton instance of GuestmanBackend."""
    global _backend_instance
    if _backend_instance is None:
        with _lock:
            if _backend_instance is None:  # double-checked
                _backend_instance = GuestmanBackend()
    return _backend_instance


def reset_customer_backend() -> None:
    """Reset singleton (for tests)."""
    global _backend_instance
    _backend_instance = None
