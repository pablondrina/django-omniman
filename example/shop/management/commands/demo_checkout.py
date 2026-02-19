"""
Demo checkout command - simulates a complete order flow.

Usage:
    python manage.py demo_checkout
    python manage.py demo_checkout --user alice
    python manage.py demo_checkout --complete
"""

from django.core.management.base import BaseCommand

from example.shop.basket_service import BasketService
from example.shop.models import Product
from omniman.models import Order


class Command(BaseCommand):
    help = "Demonstrate a complete checkout flow"

    def add_arguments(self, parser):
        parser.add_argument(
            "--user",
            type=str,
            default="demo",
            help="User identifier for the basket (default: demo)",
        )
        parser.add_argument(
            "--complete",
            action="store_true",
            help="Complete the order through all status transitions",
        )

    def handle(self, *args, **options):
        user = options["user"]
        complete = options["complete"]

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== Omniman Demo Checkout ===\n"))

        # Step 1: Create basket
        self.stdout.write("1. Creating basket...")
        session = BasketService.get_or_create_basket(user)
        self.stdout.write(f"   Basket: {session.session_key}")

        # Step 2: Add items
        self.stdout.write("\n2. Adding items...")
        products = list(Product.objects.filter(is_active=True)[:3])

        if not products:
            self.stdout.write(
                self.style.WARNING("   No products found. Run 'seed_example' first.")
            )
            return

        for product in products:
            BasketService.add_item(
                session,
                sku=product.sku,
                qty=1,
                unit_price_q=product.price_q,
            )
            self.stdout.write(f"   + {product.name} ({product.sku}) - {product.price_display}")

        session.refresh_from_db()
        self.stdout.write(f"\n   Total: {BasketService.get_subtotal_display(session)}")

        # Step 3: Commit
        self.stdout.write("\n3. Committing basket...")
        import uuid
        idempotency_key = f"DEMO-{uuid.uuid4().hex[:8].upper()}"

        result = BasketService.commit(session, idempotency_key=idempotency_key)
        order_ref = result["order_ref"]
        self.stdout.write(self.style.SUCCESS(f"   Order created: {order_ref}"))

        # Step 4: View order
        order = Order.objects.get(ref=order_ref)
        self.stdout.write(f"\n4. Order details:")
        self.stdout.write(f"   Reference: {order.ref}")
        self.stdout.write(f"   Status: {order.status}")
        self.stdout.write(f"   Items: {order.items.count()}")
        self.stdout.write(f"   Total: R$ {order.total_q / 100:.2f}")

        # Step 5: Complete flow (optional)
        if complete:
            self.stdout.write("\n5. Processing order...")

            transitions = [
                ("confirmed", "cashier"),
                ("processing", "kitchen"),
                ("ready", "kitchen"),
                ("completed", "cashier"),
            ]

            for status, actor in transitions:
                order.transition_status(status, actor=actor)
                self.stdout.write(f"   → {status} (by {actor})")

            self.stdout.write(self.style.SUCCESS(f"\n   Order {order.ref} completed!"))

            # Show audit trail
            self.stdout.write("\n6. Audit trail:")
            for event in order.events.all().order_by("created_at"):
                if event.type == "status_changed":
                    old = event.payload.get("old_status", "?")
                    new = event.payload.get("new_status", "?")
                    self.stdout.write(f"   {old} → {new} (by {event.actor})")

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== Demo Complete ===\n"))
