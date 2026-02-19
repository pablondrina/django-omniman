"""
Tests for the BasketService demonstrating Omniman integration.

These tests show the complete flow from basket creation to order completion.
"""

from django.test import TestCase

from omniman.models import Order

from example.shop.basket_service import BasketService
from example.shop.models import Product


class BasketServiceTests(TestCase):
    """Tests for BasketService demonstrating Omniman Session/Order flow."""

    def setUp(self):
        """Create test products."""
        self.coffee = Product.objects.create(
            sku="COFFEE",
            name="Coffee",
            price_q=500,  # R$ 5.00
        )
        self.croissant = Product.objects.create(
            sku="CROISSANT",
            name="Croissant",
            price_q=750,  # R$ 7.50
        )
        self.latte = Product.objects.create(
            sku="LATTE",
            name="Latte",
            price_q=800,  # R$ 8.00
        )

    def test_create_basket(self):
        """Test creating a basket (Session)."""
        session = BasketService.get_or_create_basket("USER-001")

        self.assertEqual(session.state, "open")
        self.assertEqual(len(session.items), 0)
        self.assertIn("BASKET-USER-001", session.session_key)

    def test_add_item_to_basket(self):
        """Test adding items to basket."""
        session = BasketService.get_or_create_basket("USER-002")

        # Add coffee
        result = BasketService.add_item(session, sku="COFFEE", qty=2)

        self.assertTrue(result["success"])
        self.assertEqual(result["total_items"], 2)

        # Verify item in session
        session.refresh_from_db()
        self.assertEqual(len(session.items), 1)
        self.assertEqual(session.items[0]["sku"], "COFFEE")
        self.assertEqual(session.items[0]["qty"], 2)

    def test_add_same_item_increases_quantity(self):
        """Test that adding same SKU increases quantity."""
        session = BasketService.get_or_create_basket("USER-003")

        # Add 2 coffees
        BasketService.add_item(session, sku="COFFEE", qty=2)

        # Add 3 more coffees
        result = BasketService.add_item(session, sku="COFFEE", qty=3)

        self.assertEqual(result["total_items"], 5)

        session.refresh_from_db()
        self.assertEqual(len(session.items), 1)  # Still one line
        self.assertEqual(session.items[0]["qty"], 5)

    def test_add_multiple_items(self):
        """Test adding different items to basket."""
        session = BasketService.get_or_create_basket("USER-004")

        BasketService.add_item(session, sku="COFFEE", qty=2)
        BasketService.add_item(session, sku="CROISSANT", qty=1)
        result = BasketService.add_item(session, sku="LATTE", qty=1)

        self.assertEqual(result["total_items"], 4)

        session.refresh_from_db()
        self.assertEqual(len(session.items), 3)

    def test_update_item_quantity(self):
        """Test updating item quantity."""
        session = BasketService.get_or_create_basket("USER-005")
        BasketService.add_item(session, sku="COFFEE", qty=2)

        session.refresh_from_db()
        line_id = session.items[0]["line_id"]

        # Update to 5
        result = BasketService.update_item(session, line_id=line_id, qty=5)

        self.assertEqual(result["total_items"], 5)

        session.refresh_from_db()
        self.assertEqual(session.items[0]["qty"], 5)

    def test_remove_item(self):
        """Test removing item from basket."""
        session = BasketService.get_or_create_basket("USER-006")
        BasketService.add_item(session, sku="COFFEE", qty=2)
        BasketService.add_item(session, sku="CROISSANT", qty=1)

        session.refresh_from_db()
        coffee_line_id = None
        for item in session.items:
            if item["sku"] == "COFFEE":
                coffee_line_id = item["line_id"]
                break

        # Remove coffee
        result = BasketService.remove_item(session, line_id=coffee_line_id)

        self.assertEqual(result["total_items"], 1)

        session.refresh_from_db()
        self.assertEqual(len(session.items), 1)
        self.assertEqual(session.items[0]["sku"], "CROISSANT")

    def test_clear_basket(self):
        """Test clearing all items from basket."""
        session = BasketService.get_or_create_basket("USER-007")
        BasketService.add_item(session, sku="COFFEE", qty=2)
        BasketService.add_item(session, sku="CROISSANT", qty=1)

        BasketService.clear(session)

        session.refresh_from_db()
        self.assertEqual(len(session.items), 0)

    def test_commit_basket_creates_order(self):
        """Test that committing basket creates an Order."""
        session = BasketService.get_or_create_basket("USER-008")
        BasketService.add_item(session, sku="COFFEE", qty=2, unit_price_q=500)
        BasketService.add_item(session, sku="CROISSANT", qty=1, unit_price_q=750)

        # Commit
        result = BasketService.commit(session, idempotency_key="CHECKOUT-008")

        self.assertTrue(result["success"])
        self.assertIn("order_ref", result)

        # Verify order was created
        order = Order.objects.get(ref=result["order_ref"])
        self.assertEqual(order.status, "new")
        self.assertEqual(order.items.count(), 2)

        # Verify session is committed
        session.refresh_from_db()
        self.assertEqual(session.state, "committed")

    def test_commit_idempotency(self):
        """Test that commit with same key returns same order."""
        session = BasketService.get_or_create_basket("USER-009")
        BasketService.add_item(session, sku="COFFEE", qty=1, unit_price_q=500)

        # First commit
        result1 = BasketService.commit(session, idempotency_key="CHECKOUT-009")

        # Second commit with same key
        result2 = BasketService.commit(session, idempotency_key="CHECKOUT-009")

        # Should return same order
        self.assertEqual(result1["order_ref"], result2["order_ref"])

        # Only one order created
        self.assertEqual(Order.objects.count(), 1)

    def test_order_status_transitions(self):
        """Test order status transitions after commit."""
        session = BasketService.get_or_create_basket("USER-010")
        BasketService.add_item(session, sku="COFFEE", qty=1, unit_price_q=500)

        result = BasketService.commit(session, idempotency_key="CHECKOUT-010")
        order = Order.objects.get(ref=result["order_ref"])

        # Initial status
        self.assertEqual(order.status, "new")

        # Transition through states
        order.transition_status("confirmed", actor="payment_webhook")
        self.assertEqual(order.status, "confirmed")

        order.transition_status("processing", actor="kitchen")
        self.assertEqual(order.status, "processing")

        order.transition_status("ready", actor="kitchen")
        self.assertEqual(order.status, "ready")

        order.transition_status("completed", actor="cashier")
        self.assertEqual(order.status, "completed")

        # Verify audit trail
        events = order.events.filter(type="status_changed")
        self.assertEqual(events.count(), 4)

    def test_cannot_commit_empty_basket(self):
        """Test that empty basket cannot be committed."""
        session = BasketService.get_or_create_basket("USER-011")

        with self.assertRaises(ValueError) as ctx:
            BasketService.commit(session, idempotency_key="CHECKOUT-011")

        self.assertIn("empty basket", str(ctx.exception))

    def test_get_basket_items_with_product_info(self):
        """Test getting basket items with product information."""
        session = BasketService.get_or_create_basket("USER-012")
        BasketService.add_item(session, sku="COFFEE", qty=2)

        items = BasketService.get_items(session)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["sku"], "COFFEE")
        self.assertEqual(items[0]["qty"], 2)
        self.assertIsNotNone(items[0]["product"])
        self.assertEqual(items[0]["product"].name, "Coffee")


class EndToEndFlowTests(TestCase):
    """
    End-to-end tests demonstrating complete Omniman flow.

    These tests show:
    1. Session creation (basket)
    2. Item modifications
    3. Commit (Order creation)
    4. Status transitions
    5. Audit trail (OrderEvents)
    """

    def setUp(self):
        """Create test products."""
        Product.objects.create(sku="ESPRESSO", name="Espresso", price_q=450)
        Product.objects.create(sku="CAPPUCCINO", name="Cappuccino", price_q=750)
        Product.objects.create(sku="MUFFIN", name="Blueberry Muffin", price_q=550)

    def test_complete_order_flow(self):
        """
        Test complete flow from basket to completed order.

        This demonstrates Omniman's core functionality:
        - Session as mutable cart
        - Order as immutable snapshot
        - Status transitions with audit
        """
        # 1. Create basket
        session = BasketService.get_or_create_basket("CUSTOMER-001")
        self.assertEqual(session.state, "open")
        self.assertEqual(session.rev, 0)

        # 2. Add items
        BasketService.add_item(session, sku="ESPRESSO", qty=2, unit_price_q=450)
        session.refresh_from_db()
        self.assertEqual(session.rev, 1)  # Rev incremented

        BasketService.add_item(session, sku="MUFFIN", qty=1, unit_price_q=550)
        session.refresh_from_db()
        self.assertEqual(session.rev, 2)

        # 3. Modify quantity
        espresso_line = next(i for i in session.items if i["sku"] == "ESPRESSO")
        BasketService.update_item(session, line_id=espresso_line["line_id"], qty=3)
        session.refresh_from_db()
        self.assertEqual(session.rev, 3)

        # 4. Commit (creates Order)
        result = BasketService.commit(session, idempotency_key="ORDER-001")
        order = Order.objects.get(ref=result["order_ref"])

        # Verify immutable snapshot
        self.assertEqual(order.snapshot["rev"], 3)
        self.assertIn("items", order.snapshot)

        # Verify order items
        self.assertEqual(order.items.count(), 2)
        espresso_item = order.items.get(sku="ESPRESSO")
        self.assertEqual(espresso_item.qty, 3)

        # 5. Status transitions with audit
        order.transition_status("confirmed", actor="system")
        order.transition_status("processing", actor="barista@shop.com")
        order.transition_status("ready", actor="barista@shop.com")
        order.transition_status("completed", actor="cashier@shop.com")

        # 6. Verify audit trail
        events = list(order.events.filter(type="status_changed").order_by("created_at"))
        self.assertEqual(len(events), 4)

        # Check first and last transition
        self.assertEqual(events[0].payload["old_status"], "new")
        self.assertEqual(events[0].payload["new_status"], "confirmed")

        self.assertEqual(events[-1].payload["old_status"], "ready")
        self.assertEqual(events[-1].payload["new_status"], "completed")
        self.assertEqual(events[-1].actor, "cashier@shop.com")

        # 7. Order is terminal - no more transitions allowed
        self.assertEqual(order.status, "completed")
