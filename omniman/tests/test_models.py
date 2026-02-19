from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from omniman.exceptions import InvalidTransition
from omniman.models import Channel, Order, OrderEvent, Session, SessionItem


class SessionItemTests(TestCase):
    def setUp(self) -> None:
        self.channel = Channel.objects.create(code="shop", name="Shop")

    def test_session_create_persists_items(self) -> None:
        session = Session.objects.create(
            session_key="S-1",
            channel=self.channel,
            pricing_policy="internal",
            edit_policy="open",
            items=[
                {"line_id": "L-1", "sku": "SKU", "qty": 2, "unit_price_q": 1000},
                {"sku": "SKU2", "qty": 1, "unit_price_q": 500},
            ],
        )

        self.assertEqual(session.session_items.count(), 2)
        item = session.session_items.get(line_id="L-1")
        self.assertEqual(item.sku, "SKU")
        self.assertEqual(item.qty, Decimal("2"))

    def test_session_items_property_updates_session_items(self) -> None:
        session = Session.objects.create(
            session_key="S-2",
            channel=self.channel,
            pricing_policy="internal",
            edit_policy="open",
            items=[
                {"line_id": "L-1", "sku": "SKU", "qty": 2, "unit_price_q": 1000},
            ],
        )

        updated = session.items
        updated[0]["qty"] = 3
        updated.append({"sku": "SKU2", "qty": 1, "unit_price_q": 500})

        session.items = updated
        session.save()

        self.assertEqual(session.session_items.count(), 2)
        self.assertEqual(session.session_items.get(line_id="L-1").qty, Decimal("3"))

    def test_session_item_save_invalidates_cache(self) -> None:
        session = Session.objects.create(
            session_key="S-3",
            channel=self.channel,
            pricing_policy="internal",
            edit_policy="open",
            items=[{"line_id": "L-1", "sku": "SKU", "qty": 2, "unit_price_q": 1000}],
        )

        list(session.items)  # prime cache
        item = session.session_items.get(line_id="L-1")
        item.qty = Decimal("4")
        item.save()

        # qty should be native Decimal (or numeric) in the items dict
        self.assertEqual(session.items[0]["qty"], Decimal("4"))


class OrderTransitionTests(TestCase):
    def setUp(self) -> None:
        self.channel = Channel.objects.create(code="shop", name="Shop")
        self.order = Order.objects.create(
            ref="ORD-20250101-ABC123",
            channel=self.channel,
            status=Order.STATUS_NEW,
            total_q=10000,
        )

    def test_transition_to_allowed_status_succeeds(self) -> None:
        """Testa transição válida de status."""
        self.order.transition_status(Order.STATUS_CONFIRMED, actor="test_user")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.STATUS_CONFIRMED)

    def test_transition_emits_event(self) -> None:
        """Testa que transição cria evento de auditoria."""
        self.order.transition_status(Order.STATUS_CONFIRMED, actor="test_user")
        event = OrderEvent.objects.get(order=self.order, type="status_changed")
        self.assertEqual(event.actor, "test_user")
        self.assertEqual(event.payload["old_status"], Order.STATUS_NEW)
        self.assertEqual(event.payload["new_status"], Order.STATUS_CONFIRMED)

    def test_transition_to_invalid_status_raises_error(self) -> None:
        """Testa que transição inválida lança exceção."""
        with self.assertRaises(InvalidTransition) as cm:
            self.order.transition_status(Order.STATUS_DELIVERED, actor="test_user")
        self.assertEqual(cm.exception.code, "invalid_transition")
        self.assertIn("allowed_transitions", cm.exception.context)

    def test_transition_from_terminal_status_raises_error(self) -> None:
        """Testa que não é possível transicionar de status terminal."""
        self.order.status = Order.STATUS_COMPLETED
        self.order.save()
        with self.assertRaises(InvalidTransition) as cm:
            self.order.transition_status(Order.STATUS_PROCESSING, actor="test_user")
        self.assertEqual(cm.exception.code, "terminal_status")

    def test_can_transition_to_returns_correct_value(self) -> None:
        """Testa verificação de transição permitida."""
        self.assertTrue(self.order.can_transition_to(Order.STATUS_CONFIRMED))
        self.assertTrue(self.order.can_transition_to(Order.STATUS_CANCELLED))
        self.assertFalse(self.order.can_transition_to(Order.STATUS_PROCESSING))
        self.assertFalse(self.order.can_transition_to(Order.STATUS_DELIVERED))

    def test_custom_channel_transitions(self) -> None:
        """Testa transições customizadas por canal."""
        custom_channel = Channel.objects.create(
            code="custom",
            name="Custom",
            config={
                "order_flow": {
                    "transitions": {
                        "new": ["processing"],  # Skip confirmed
                        "processing": ["completed"],
                    },
                    "terminal_statuses": ["completed"],
                }
            },
        )
        order = Order.objects.create(
            ref="ORD-20250101-XYZ999",
            channel=custom_channel,
            status=Order.STATUS_NEW,
            total_q=5000,
        )

        # Pode ir direto para processing
        self.assertTrue(order.can_transition_to(Order.STATUS_PROCESSING))
        # Não pode ir para confirmed (não está nas transições customizadas)
        self.assertFalse(order.can_transition_to(Order.STATUS_CONFIRMED))
