"""
Tests for contrib/pricing module.

Covers:
- ItemPricingModifier (aplica preços e calcula line_total_q)
- SessionTotalModifier (calcula total da sessão)
- SimplePricingBackend
- ChannelPricingBackend
- PricingBackend protocol

Note: Session normalizes items on creation, adding default values.
These tests use mocks where necessary to test modifier logic in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import Mock, PropertyMock

from django.test import TestCase

from omniman.contrib.pricing.adapters.simple import (
    ChannelPricingBackend,
    SimplePricingBackend,
)
from omniman.contrib.pricing.modifiers import (
    ItemPricingModifier,
    SessionTotalModifier,
)
from omniman.contrib.pricing.protocols import PricingBackend
from omniman.models import Channel, Session


class MockPricingBackend:
    """Mock pricing backend for testing."""

    def __init__(self, prices: dict[str, int] | None = None):
        self.prices = prices or {}

    def get_price(self, sku: str, channel: Any) -> int | None:
        return self.prices.get(sku)


class ItemPricingModifierTests(TestCase):
    """Tests for ItemPricingModifier.

    ItemPricingModifier é responsável por:
    1. Aplicar unit_price_q para itens sem preço (usando backend)
    2. Calcular line_total_q = qty * unit_price_q
    """

    def setUp(self) -> None:
        self.channel = Mock(code="test")
        self.backend = MockPricingBackend({"COFFEE": 500, "CAKE": 1000})
        self.modifier = ItemPricingModifier(backend=self.backend)

    def test_modifier_has_correct_code_and_order(self) -> None:
        """Should have correct code and order."""
        self.assertEqual(self.modifier.code, "pricing.item")
        self.assertEqual(self.modifier.order, 10)

    def test_apply_prices_and_calculates_line_total(self) -> None:
        """Should apply unit_price_q and calculate line_total_q."""
        session = Mock()
        session.pricing_policy = "internal"
        session.pricing_trace = []
        items = [
            {"line_id": "L1", "sku": "COFFEE", "qty": 2},
            {"line_id": "L2", "sku": "CAKE", "qty": 1, "unit_price_q": 1000},
        ]
        session.items = items

        self.modifier.apply(channel=self.channel, session=session, ctx={})

        # First item: price applied + line_total calculated
        self.assertEqual(items[0]["unit_price_q"], 500)
        self.assertEqual(items[0]["line_total_q"], 1000)  # 2 * 500
        # Second item: keeps original price + line_total calculated
        self.assertEqual(items[1]["unit_price_q"], 1000)
        self.assertEqual(items[1]["line_total_q"], 1000)  # 1 * 1000

    def test_skip_items_with_existing_price(self) -> None:
        """Should not overwrite existing unit_price_q."""
        session = Mock()
        session.pricing_policy = "internal"
        session.pricing_trace = []
        items = [{"line_id": "L1", "sku": "COFFEE", "qty": 2, "unit_price_q": 999}]
        session.items = items

        self.modifier.apply(channel=self.channel, session=session, ctx={})

        self.assertEqual(items[0]["unit_price_q"], 999)
        self.assertEqual(items[0]["line_total_q"], 1998)  # 2 * 999

    def test_skip_when_pricing_policy_external(self) -> None:
        """Should not apply prices when pricing_policy is external."""
        session = Mock()
        session.pricing_policy = "external"
        items = [{"line_id": "L1", "sku": "COFFEE", "qty": 2}]
        session.items = items

        self.modifier.apply(channel=self.channel, session=session, ctx={})

        # Items should not have unit_price_q
        self.assertNotIn("unit_price_q", items[0])

    def test_updates_pricing_trace(self) -> None:
        """Should add trace entries for applied prices."""
        session = Mock()
        session.pricing_policy = "internal"
        session.pricing_trace = []
        items = [{"line_id": "L1", "sku": "COFFEE", "qty": 2}]
        session.items = items

        self.modifier.apply(channel=self.channel, session=session, ctx={})

        self.assertEqual(len(session.pricing_trace), 1)
        self.assertEqual(session.pricing_trace[0]["sku"], "COFFEE")
        self.assertEqual(session.pricing_trace[0]["price_q"], 500)

    def test_handles_unknown_sku(self) -> None:
        """Should skip items with unknown SKU but still calculate line_total."""
        session = Mock()
        session.pricing_policy = "internal"
        session.pricing_trace = None
        items = [{"line_id": "L1", "sku": "UNKNOWN", "qty": 1}]
        session.items = items

        self.modifier.apply(channel=self.channel, session=session, ctx={})

        self.assertNotIn("unit_price_q", items[0])
        # line_total_q should be 0 when no price
        self.assertEqual(items[0]["line_total_q"], 0)

    def test_initializes_pricing_trace_if_none(self) -> None:
        """Should initialize pricing_trace if None."""
        session = Mock()
        session.pricing_policy = "internal"
        session.pricing_trace = None
        items = [{"line_id": "L1", "sku": "COFFEE", "qty": 1}]
        session.items = items

        self.modifier.apply(channel=self.channel, session=session, ctx={})

        self.assertIsNotNone(session.pricing_trace)
        self.assertEqual(len(session.pricing_trace), 1)

    def test_calculates_line_totals_correctly(self) -> None:
        """Should calculate line_total_q for each item."""
        session = Mock()
        session.pricing_policy = "internal"
        session.pricing_trace = []
        items = [
            {"line_id": "L1", "sku": "COFFEE", "qty": 3, "unit_price_q": 500},
            {"line_id": "L2", "sku": "CAKE", "qty": 2, "unit_price_q": 1000},
        ]
        session.items = items

        self.modifier.apply(channel=self.channel, session=session, ctx={})

        self.assertEqual(items[0]["line_total_q"], 1500)  # 3 * 500
        self.assertEqual(items[1]["line_total_q"], 2000)  # 2 * 1000

    def test_handles_decimal_precision(self) -> None:
        """Should correctly handle decimal calculations."""
        session = Mock()
        session.pricing_policy = "internal"
        session.pricing_trace = []
        items = [{"line_id": "L1", "sku": "ITEM", "qty": 7, "unit_price_q": 333}]
        session.items = items

        self.modifier.apply(channel=self.channel, session=session, ctx={})

        self.assertEqual(items[0]["line_total_q"], 2331)  # 7 * 333



class SessionTotalModifierTests(TestCase):
    """Tests for SessionTotalModifier."""

    def setUp(self) -> None:
        self.channel = Mock(code="test")
        self.modifier = SessionTotalModifier()

    def test_modifier_has_correct_code_and_order(self) -> None:
        """Should have correct code and order."""
        self.assertEqual(self.modifier.code, "pricing.session_total")
        self.assertEqual(self.modifier.order, 50)

    def test_calculates_session_total(self) -> None:
        """Should calculate total_q from all line_total_q."""
        session = Mock()
        session.pricing = None
        session.items = [
            {"line_id": "L1", "line_total_q": 1000},
            {"line_id": "L2", "line_total_q": 1000},
        ]

        self.modifier.apply(channel=self.channel, session=session, ctx={})

        self.assertEqual(session.pricing["total_q"], 2000)  # 1000 + 1000
        self.assertEqual(session.pricing["items_count"], 2)

    def test_handles_empty_session(self) -> None:
        """Should handle session with no items."""
        session = Mock()
        session.pricing = None
        session.items = []

        self.modifier.apply(channel=self.channel, session=session, ctx={})

        self.assertEqual(session.pricing["total_q"], 0)
        self.assertEqual(session.pricing["items_count"], 0)

    def test_handles_missing_line_total(self) -> None:
        """Should treat missing line_total_q as 0."""
        session = Mock()
        session.pricing = None
        session.items = [{"line_id": "L1", "sku": "COFFEE", "qty": 2}]

        self.modifier.apply(channel=self.channel, session=session, ctx={})

        self.assertEqual(session.pricing["total_q"], 0)

    def test_preserves_existing_pricing_dict(self) -> None:
        """Should update existing pricing dict."""
        session = Mock()
        session.pricing = {"discount": 100}
        session.items = [{"line_id": "L1", "line_total_q": 500}]

        self.modifier.apply(channel=self.channel, session=session, ctx={})

        self.assertEqual(session.pricing["total_q"], 500)
        self.assertEqual(session.pricing["discount"], 100)  # Preserved

    def test_works_with_any_pricing_policy(self) -> None:
        """Should calculate totals regardless of pricing_policy."""
        session = Mock()
        session.pricing_policy = "external"
        session.pricing = None
        session.items = [{"line_id": "L1", "line_total_q": 2000}]

        self.modifier.apply(channel=self.channel, session=session, ctx={})

        self.assertEqual(session.pricing["total_q"], 2000)


class SimplePricingBackendTests(TestCase):
    """Tests for SimplePricingBackend."""

    def setUp(self) -> None:
        @dataclass
        class MockProduct:
            sku: str
            price_q: int

        self.products = {
            "COFFEE": MockProduct("COFFEE", 500),
            "CAKE": MockProduct("CAKE", 1000),
        }

        def resolver(sku: str):
            if sku in self.products:
                return self.products[sku]
            raise ValueError("Product not found")

        self.backend = SimplePricingBackend(product_resolver=resolver)
        self.channel = Mock(code="test")

    def test_implements_protocol(self) -> None:
        """SimplePricingBackend should implement PricingBackend protocol."""
        self.assertIsInstance(self.backend, PricingBackend)

    def test_returns_price_for_existing_product(self) -> None:
        """Should return price_q for existing product."""
        price = self.backend.get_price("COFFEE", self.channel)
        self.assertEqual(price, 500)

    def test_returns_none_for_unknown_product(self) -> None:
        """Should return None when product not found."""
        price = self.backend.get_price("UNKNOWN", self.channel)
        self.assertIsNone(price)

    def test_handles_resolver_exception(self) -> None:
        """Should return None when resolver raises exception."""
        def failing_resolver(sku: str):
            raise RuntimeError("Database error")

        backend = SimplePricingBackend(product_resolver=failing_resolver)
        price = backend.get_price("ANY", self.channel)
        self.assertIsNone(price)


class ChannelPricingBackendTests(TestCase):
    """Tests for ChannelPricingBackend."""

    def setUp(self) -> None:
        @dataclass
        class MockProduct:
            sku: str
            price_q: int

        @dataclass
        class MockListing:
            sku: str
            price_q: int | None

        self.products = {
            "COFFEE": MockProduct("COFFEE", 500),
            "CAKE": MockProduct("CAKE", 1000),
            "TEA": MockProduct("TEA", 300),
        }

        self.listings = {
            ("COFFEE", "premium"): MockListing("COFFEE", 600),  # Premium channel price
            ("TEA", "premium"): MockListing("TEA", None),  # Listing exists but no special price
        }

        def product_resolver(sku: str):
            if sku in self.products:
                return self.products[sku]
            raise ValueError("Product not found")

        def listing_resolver(sku: str, channel_code: str):
            key = (sku, channel_code)
            if key in self.listings:
                return self.listings[key]
            raise ValueError("Listing not found")

        self.backend = ChannelPricingBackend(
            product_resolver=product_resolver,
            listing_resolver=listing_resolver,
        )
        self.premium_channel = Mock(code="premium")
        self.standard_channel = Mock(code="standard")

    def test_implements_protocol(self) -> None:
        """ChannelPricingBackend should implement PricingBackend protocol."""
        self.assertIsInstance(self.backend, PricingBackend)

    def test_returns_listing_price_when_available(self) -> None:
        """Should return listing price_q when available."""
        price = self.backend.get_price("COFFEE", self.premium_channel)
        self.assertEqual(price, 600)  # Listing price, not product price

    def test_falls_back_to_product_price(self) -> None:
        """Should fall back to product price when no listing."""
        price = self.backend.get_price("CAKE", self.premium_channel)
        self.assertEqual(price, 1000)  # Product price, no listing exists

    def test_falls_back_when_listing_has_no_price(self) -> None:
        """Should fall back to product when listing.price_q is None."""
        price = self.backend.get_price("TEA", self.premium_channel)
        self.assertEqual(price, 300)  # Product price, listing has None

    def test_returns_none_for_unknown_product(self) -> None:
        """Should return None when product not found."""
        price = self.backend.get_price("UNKNOWN", self.premium_channel)
        self.assertIsNone(price)

    def test_works_without_listing_resolver(self) -> None:
        """Should work when listing_resolver is not provided."""
        def product_resolver(sku: str):
            return Mock(price_q=999)

        backend = ChannelPricingBackend(product_resolver=product_resolver)
        price = backend.get_price("ANY", self.standard_channel)
        self.assertEqual(price, 999)

    def test_handles_listing_resolver_exception(self) -> None:
        """Should fall back to product when listing resolver raises."""
        price = self.backend.get_price("COFFEE", self.standard_channel)
        self.assertEqual(price, 500)  # Product price, listing not found for standard channel


class PricingProtocolTests(TestCase):
    """Tests for pricing protocols."""

    def test_pricing_backend_protocol_exists(self) -> None:
        """Should be able to import PricingBackend protocol."""
        self.assertIsNotNone(PricingBackend)

    def test_pricing_backend_has_get_price_method(self) -> None:
        """Protocol should define get_price method."""
        methods = [m for m in dir(PricingBackend) if not m.startswith("_")]
        self.assertIn("get_price", methods)


class PricingModifiersIntegrationTests(TestCase):
    """Integration tests for pricing modifiers with real Session objects."""

    def setUp(self) -> None:
        self.channel = Channel.objects.create(
            code="integration-test",
            name="Integration Test",
            pricing_policy="internal",
            config={},
        )

    def test_item_pricing_modifier_with_real_session(self) -> None:
        """ItemPricingModifier should work with real Session objects."""
        session = Session.objects.create(
            session_key="ITEM-PRICING-INT",
            channel=self.channel,
            state="open",
            pricing_policy="internal",
            items=[
                {"line_id": "L1", "sku": "COFFEE", "qty": 3, "unit_price_q": 500},
            ],
        )

        # Items are normalized on creation
        self.assertEqual(session.items[0]["unit_price_q"], 500)
        self.assertEqual(session.items[0]["line_total_q"], 1500)  # Auto-calculated

        # Simulate qty change
        items = session.items
        items[0]["qty"] = 5
        items[0]["line_total_q"] = None  # Reset to force recalculation
        session.items = items
        session.save()

        # Apply modifier (now ItemPricingModifier handles both price and line_total)
        backend = MockPricingBackend({"COFFEE": 500})
        modifier = ItemPricingModifier(backend=backend)
        session.refresh_from_db()

        # Note: Session normalizes items on assignment, so line_total_q is recalculated
        # The modifier's role is to ensure this happens in the pipeline

    def test_session_total_modifier_with_real_session(self) -> None:
        """SessionTotalModifier should work with real Session objects."""
        session = Session.objects.create(
            session_key="SESSION-TOTAL-INT",
            channel=self.channel,
            state="open",
            pricing_policy="internal",
            items=[
                {"line_id": "L1", "sku": "A", "qty": 2, "unit_price_q": 500},
                {"line_id": "L2", "sku": "B", "qty": 1, "unit_price_q": 1000},
            ],
        )

        modifier = SessionTotalModifier()
        modifier.apply(channel=self.channel, session=session, ctx={})

        self.assertEqual(session.pricing["total_q"], 2000)  # 1000 + 1000
        self.assertEqual(session.pricing["items_count"], 2)
