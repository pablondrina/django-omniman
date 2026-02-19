from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from omniman.exceptions import CommitError
from omniman.ids import generate_idempotency_key
from omniman.models import Channel, Directive, Session
from omniman.services import CommitService


class CommitServiceTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.channel = Channel.objects.create(
            code="pos",
            name="POS",
            config={
                "required_checks_on_commit": ["stock"],
                "checks": {"stock": {"directive_topic": "stock.hold"}},
                "post_commit_directives": ["stock.commit"],
            },
            is_active=True,
        )

    def _base_session_data(self) -> dict:
        return {
            "checks": {},
            "issues": [],
        }

    def test_commit_rejects_expired_hold(self) -> None:
        expired_at = (timezone.now() - timedelta(minutes=5)).isoformat()
        session = Session.objects.create(
            session_key="S-HOLD-EXPIRED",
            channel=self.channel,
            state="open",
            pricing_policy=self.channel.pricing_policy,
            edit_policy=self.channel.edit_policy,
            rev=0,
            items=[{"line_id": "L1", "sku": "SKU", "qty": 1, "unit_price_q": 1000, "meta": {}}],
            data={
                "checks": {
                    "stock": {
                        "rev": 0,
                        "result": {
                            "holds": [
                                {"hold_id": "HOLD-1", "expires_at": expired_at},
                            ]
                        },
                    }
                },
                "issues": [],
            },
        )

        with self.assertRaises(CommitError) as ctx:
            CommitService.commit(
                session_key=session.session_key,
                channel_code=self.channel.code,
                idempotency_key=generate_idempotency_key(),
            )

        self.assertEqual(ctx.exception.code, "hold_expired")

    def test_commit_enqueues_stock_commit_with_holds(self) -> None:
        future = (timezone.now() + timedelta(minutes=10)).isoformat()
        session = Session.objects.create(
            session_key="S-HOLD-OK",
            channel=self.channel,
            state="open",
            pricing_policy=self.channel.pricing_policy,
            edit_policy=self.channel.edit_policy,
            rev=0,
            items=[{"line_id": "L1", "sku": "SKU", "qty": 1, "unit_price_q": 1500, "meta": {}}],
            data={
                "checks": {
                    "stock": {
                        "rev": 0,
                        "result": {
                            "holds": [
                                {"hold_id": "HOLD-123", "expires_at": future},
                            ]
                        },
                    }
                },
                "issues": [],
            },
        )

        result = CommitService.commit(
            session_key=session.session_key,
            channel_code=self.channel.code,
            idempotency_key=generate_idempotency_key(),
        )

        self.assertEqual(result["status"], "committed")
        directive = Directive.objects.filter(topic="stock.commit").order_by("-id").first()
        self.assertIsNotNone(directive)
        self.assertEqual(directive.payload["order_ref"], result["order_ref"])
        self.assertEqual(directive.payload["session_key"], session.session_key)
        self.assertEqual(directive.payload["holds"][0]["hold_id"], "HOLD-123")
