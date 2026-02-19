"""
Tests for contrib/stock/handlers module.

Covers:
- StockHoldHandler
- StockCommitHandler
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock

from django.test import TestCase
from django.utils import timezone

from omniman.contrib.stock.handlers import StockCommitHandler, StockHoldHandler
from omniman.contrib.stock.protocols import AvailabilityResult, HoldResult
from omniman.models import Channel, Directive, Session


class MockStockBackend:
    """Mock stock backend for testing."""

    def __init__(
        self,
        availability: dict[str, AvailabilityResult] | None = None,
        hold_result: HoldResult | None = None,
    ):
        self.availability = availability or {}
        self.hold_result = hold_result or HoldResult(
            success=True,
            hold_id="HOLD-001",
            expires_at=timezone.now() + timedelta(minutes=15),
        )
        self.released_references: list[str] = []
        self.created_holds: list[dict] = []
        self.fulfilled_holds: list[dict] = []

    def check_availability(self, sku: str, quantity: Decimal, target_date=None) -> AvailabilityResult:
        if sku in self.availability:
            return self.availability[sku]
        return AvailabilityResult(available=True, available_qty=quantity)

    def create_hold(self, sku: str, quantity: Decimal, expires_at=None, reference=None) -> HoldResult:
        self.created_holds.append({
            "sku": sku,
            "quantity": quantity,
            "expires_at": expires_at,
            "reference": reference,
        })
        return self.hold_result

    def release_hold(self, hold_id: str) -> None:
        pass

    def fulfill_hold(self, hold_id: str, reference: str | None = None) -> None:
        self.fulfilled_holds.append({"hold_id": hold_id, "reference": reference})

    def release_holds_for_reference(self, reference: str) -> int:
        self.released_references.append(reference)
        return 0


class StockHoldHandlerTests(TestCase):
    """Tests for StockHoldHandler."""

    def setUp(self) -> None:
        self.channel = Channel.objects.create(
            code="stock-handler-test",
            name="Stock Handler Test",
            config={},
        )
        self.session = Session.objects.create(
            session_key="STOCK-HOLD-SESSION",
            channel=self.channel,
            state="open",
            rev=1,
            items=[
                {"line_id": "L1", "sku": "PROD-A", "qty": 2, "unit_price_q": 1000},
                {"line_id": "L2", "sku": "PROD-B", "qty": 3, "unit_price_q": 500},
            ],
        )
        self.backend = MockStockBackend()
        self.handler = StockHoldHandler(backend=self.backend)

    def test_handler_has_correct_topic(self) -> None:
        """Should have topic='stock.hold'."""
        self.assertEqual(self.handler.topic, "stock.hold")

    def test_creates_holds_for_available_stock(self) -> None:
        """Should create holds for items with available stock."""
        directive = Directive.objects.create(
            topic="stock.hold",
            payload={
                "session_key": self.session.session_key,
                "channel_code": self.channel.code,
                "rev": 1,
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")
        self.assertEqual(len(self.backend.created_holds), 2)
        self.assertIn("holds", directive.payload)

    def test_releases_previous_holds_before_creating_new(self) -> None:
        """Should release holds for session before creating new ones (idempotency)."""
        directive = Directive.objects.create(
            topic="stock.hold",
            payload={
                "session_key": self.session.session_key,
                "channel_code": self.channel.code,
                "rev": 1,
            },
        )

        self.handler.handle(message=directive, ctx={})

        self.assertIn(self.session.session_key, self.backend.released_references)

    def test_aggregates_items_by_sku(self) -> None:
        """Should aggregate quantities for same SKU."""
        self.session.items = [
            {"line_id": "L1", "sku": "SAME-SKU", "qty": 2, "unit_price_q": 100},
            {"line_id": "L2", "sku": "SAME-SKU", "qty": 3, "unit_price_q": 100},
        ]
        self.session.save()

        directive = Directive.objects.create(
            topic="stock.hold",
            payload={
                "session_key": self.session.session_key,
                "channel_code": self.channel.code,
                "rev": 1,
            },
        )

        self.handler.handle(message=directive, ctx={})

        # Should create only 1 hold for aggregated qty=5
        self.assertEqual(len(self.backend.created_holds), 1)
        self.assertEqual(self.backend.created_holds[0]["quantity"], Decimal("5"))

    def test_creates_issues_for_insufficient_stock(self) -> None:
        """Should create issues when stock is insufficient."""
        self.backend.availability = {
            "PROD-A": AvailabilityResult(
                available=False,
                available_qty=Decimal("1"),
                message="Apenas 1 unidade disponível",
            ),
        }

        directive = Directive.objects.create(
            topic="stock.hold",
            payload={
                "session_key": self.session.session_key,
                "channel_code": self.channel.code,
                "rev": 1,
            },
        )

        self.handler.handle(message=directive, ctx={})

        self.session.refresh_from_db()
        issues = self.session.data.get("issues", [])
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["source"], "stock")
        self.assertEqual(issues[0]["code"], "stock.insufficient")
        self.assertTrue(issues[0]["blocking"])

    def test_issue_contains_actions(self) -> None:
        """Should include actions in issue context."""
        self.backend.availability = {
            "PROD-A": AvailabilityResult(
                available=False,
                available_qty=Decimal("1"),
            ),
        }

        directive = Directive.objects.create(
            topic="stock.hold",
            payload={
                "session_key": self.session.session_key,
                "channel_code": self.channel.code,
                "rev": 1,
            },
        )

        self.handler.handle(message=directive, ctx={})

        self.session.refresh_from_db()
        issue = self.session.data["issues"][0]
        actions = issue["context"]["actions"]

        # Should have 2 actions: adjust qty and remove
        self.assertEqual(len(actions), 2)
        self.assertIn("Ajustar", actions[0]["label"])
        self.assertEqual(actions[1]["label"], "Remover item")

    def test_skip_when_session_not_found(self) -> None:
        """Should mark as done when session doesn't exist."""
        directive = Directive.objects.create(
            topic="stock.hold",
            payload={
                "session_key": "NONEXISTENT",
                "channel_code": self.channel.code,
                "rev": 1,
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        # Session not found should be marked as failed (not silent success)
        self.assertEqual(directive.status, "failed")
        self.assertIn("not found", directive.last_error)
        self.assertEqual(len(self.backend.created_holds), 0)

    def test_skip_when_rev_mismatch(self) -> None:
        """Should mark as failed when rev doesn't match (stale directive)."""
        directive = Directive.objects.create(
            topic="stock.hold",
            payload={
                "session_key": self.session.session_key,
                "channel_code": self.channel.code,
                "rev": 999,  # Wrong rev
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        # Rev mismatch should be marked as failed (stale directive)
        self.assertEqual(directive.status, "failed")
        self.assertIn("Stale directive", directive.last_error)
        self.assertEqual(len(self.backend.created_holds), 0)

    def test_skip_when_session_not_open(self) -> None:
        """Should mark as done when session is not open."""
        self.session.state = "committed"
        self.session.save()

        directive = Directive.objects.create(
            topic="stock.hold",
            payload={
                "session_key": self.session.session_key,
                "channel_code": self.channel.code,
                "rev": 1,
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")
        self.assertEqual(len(self.backend.created_holds), 0)

    def test_creates_issue_when_hold_fails(self) -> None:
        """Should create issue when hold creation fails."""
        self.backend.hold_result = HoldResult(
            success=False,
            error_code="hold_failed",
            message="Falha ao reservar",
        )

        directive = Directive.objects.create(
            topic="stock.hold",
            payload={
                "session_key": self.session.session_key,
                "channel_code": self.channel.code,
                "rev": 1,
            },
        )

        self.handler.handle(message=directive, ctx={})

        self.session.refresh_from_db()
        issues = self.session.data.get("issues", [])
        self.assertEqual(len(issues), 2)  # One issue per item

    def test_stores_check_result_in_session(self) -> None:
        """Should store check result in session.data.checks.stock."""
        directive = Directive.objects.create(
            topic="stock.hold",
            payload={
                "session_key": self.session.session_key,
                "channel_code": self.channel.code,
                "rev": 1,
            },
        )

        self.handler.handle(message=directive, ctx={})

        self.session.refresh_from_db()
        check = self.session.data.get("checks", {}).get("stock", {})
        self.assertIn("result", check)
        self.assertIn("holds", check["result"])

    def test_only_remove_action_when_zero_available(self) -> None:
        """Should only include remove action when available_qty is 0."""
        self.backend.availability = {
            "PROD-A": AvailabilityResult(
                available=False,
                available_qty=Decimal("0"),
            ),
        }

        directive = Directive.objects.create(
            topic="stock.hold",
            payload={
                "session_key": self.session.session_key,
                "channel_code": self.channel.code,
                "rev": 1,
            },
        )

        self.handler.handle(message=directive, ctx={})

        self.session.refresh_from_db()
        issue = self.session.data["issues"][0]
        actions = issue["context"]["actions"]

        # Should have only 1 action: remove (no adjust since available_qty=0)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["label"], "Remover item")


class StockCommitHandlerTests(TestCase):
    """Tests for StockCommitHandler."""

    def setUp(self) -> None:
        self.channel = Channel.objects.create(
            code="stock-commit-test",
            name="Stock Commit Test",
            config={},
        )
        self.session = Session.objects.create(
            session_key="STOCK-COMMIT-SESSION",
            channel=self.channel,
            state="committed",
            data={
                "checks": {
                    "stock": {
                        "result": {
                            "holds": [
                                {"hold_id": "HOLD-001", "sku": "PROD-A", "qty": 2},
                                {"hold_id": "HOLD-002", "sku": "PROD-B", "qty": 3},
                            ],
                        },
                    },
                },
            },
        )
        self.backend = MockStockBackend()
        self.handler = StockCommitHandler(backend=self.backend)

    def test_handler_has_correct_topic(self) -> None:
        """Should have topic='stock.commit'."""
        self.assertEqual(self.handler.topic, "stock.commit")

    def test_fulfills_holds_from_payload(self) -> None:
        """Should fulfill holds passed in payload."""
        directive = Directive.objects.create(
            topic="stock.commit",
            payload={
                "holds": [
                    {"hold_id": "HOLD-001"},
                    {"hold_id": "HOLD-002"},
                ],
                "order_ref": "ORD-001",
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")
        self.assertEqual(len(self.backend.fulfilled_holds), 2)
        self.assertEqual(self.backend.fulfilled_holds[0]["hold_id"], "HOLD-001")
        self.assertEqual(self.backend.fulfilled_holds[0]["reference"], "ORD-001")

    def test_gets_holds_from_session_when_not_in_payload(self) -> None:
        """Should get holds from session.data if not in payload."""
        directive = Directive.objects.create(
            topic="stock.commit",
            payload={
                "session_key": self.session.session_key,
                "channel_code": self.channel.code,
                "order_ref": "ORD-002",
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")
        self.assertEqual(len(self.backend.fulfilled_holds), 2)

    def test_handles_empty_holds(self) -> None:
        """Should complete without errors when no holds."""
        directive = Directive.objects.create(
            topic="stock.commit",
            payload={"holds": []},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")
        self.assertEqual(len(self.backend.fulfilled_holds), 0)

    def test_handles_session_not_found(self) -> None:
        """Should complete without errors when session not found."""
        directive = Directive.objects.create(
            topic="stock.commit",
            payload={
                "session_key": "NONEXISTENT",
                "channel_code": self.channel.code,
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

    def test_skips_holds_without_id(self) -> None:
        """Should skip holds without hold_id."""
        directive = Directive.objects.create(
            topic="stock.commit",
            payload={
                "holds": [
                    {"hold_id": "HOLD-001"},
                    {"sku": "NO-HOLD-ID"},  # Missing hold_id
                ],
            },
        )

        self.handler.handle(message=directive, ctx={})

        # Should only fulfill the one with hold_id
        self.assertEqual(len(self.backend.fulfilled_holds), 1)


class StockAggregationTests(TestCase):
    """Tests for item aggregation logic."""

    def setUp(self) -> None:
        self.backend = MockStockBackend()
        self.handler = StockHoldHandler(backend=self.backend)

    def test_aggregate_single_item(self) -> None:
        """Should handle single item."""
        items = [{"line_id": "L1", "sku": "A", "qty": 5}]
        result = self.handler._aggregate_items_by_sku(items)

        self.assertEqual(len(result), 1)
        self.assertEqual(result["A"]["qty"], Decimal("5"))
        self.assertEqual(result["A"]["line_ids"], ["L1"])

    def test_aggregate_multiple_skus(self) -> None:
        """Should aggregate multiple different SKUs."""
        items = [
            {"line_id": "L1", "sku": "A", "qty": 2},
            {"line_id": "L2", "sku": "B", "qty": 3},
        ]
        result = self.handler._aggregate_items_by_sku(items)

        self.assertEqual(len(result), 2)
        self.assertEqual(result["A"]["qty"], Decimal("2"))
        self.assertEqual(result["B"]["qty"], Decimal("3"))

    def test_aggregate_same_sku_multiple_lines(self) -> None:
        """Should sum quantities for same SKU from multiple lines."""
        items = [
            {"line_id": "L1", "sku": "A", "qty": 2},
            {"line_id": "L2", "sku": "A", "qty": 3},
            {"line_id": "L3", "sku": "A", "qty": 1},
        ]
        result = self.handler._aggregate_items_by_sku(items)

        self.assertEqual(len(result), 1)
        self.assertEqual(result["A"]["qty"], Decimal("6"))
        self.assertEqual(result["A"]["line_ids"], ["L1", "L2", "L3"])

    def test_aggregate_mixed_skus(self) -> None:
        """Should correctly aggregate mixed SKUs."""
        items = [
            {"line_id": "L1", "sku": "A", "qty": 2},
            {"line_id": "L2", "sku": "B", "qty": 3},
            {"line_id": "L3", "sku": "A", "qty": 1},
            {"line_id": "L4", "sku": "B", "qty": 2},
        ]
        result = self.handler._aggregate_items_by_sku(items)

        self.assertEqual(result["A"]["qty"], Decimal("3"))
        self.assertEqual(result["B"]["qty"], Decimal("5"))
        self.assertEqual(result["A"]["line_ids"], ["L1", "L3"])
        self.assertEqual(result["B"]["line_ids"], ["L2", "L4"])
