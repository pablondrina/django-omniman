"""
Management command to seed example data for testing and demonstration.

Usage:
    python manage.py seed_example
    python manage.py seed_example --reset  # Clear and reseed
    python manage.py seed_example --demo   # Include demo orders
"""

from django.core.management.base import BaseCommand

from omniman.models import Channel, Session, Order
from example.shop.models import Product


class Command(BaseCommand):
    help = "Seed example data for the shop"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Clear existing data before seeding",
        )
        parser.add_argument(
            "--demo",
            action="store_true",
            help="Create demo orders to show the flow",
        )

    def handle(self, *args, **options):
        if options["reset"]:
            self.stdout.write("Clearing existing data...")
            Order.objects.all().delete()
            Session.objects.all().delete()
            Product.objects.all().delete()
            Channel.objects.all().delete()

        self.seed_channels()
        self.seed_products()

        if options["demo"]:
            self.create_demo_orders()

        self.stdout.write(self.style.SUCCESS("\nExample data seeded successfully!"))
        self.stdout.write("\nNext steps:")
        self.stdout.write("  1. Run: python manage.py runserver")
        self.stdout.write("  2. Visit: http://localhost:8000/admin/")
        self.stdout.write("  3. Or run tests: python manage.py test example.shop")

    def seed_channels(self):
        """Create example channels demonstrating different policies."""
        self.stdout.write("\nCreating channels...")

        channels = [
            {
                "code": "pos",
                "name": "Point of Sale",
                "pricing_policy": "internal",
                "edit_policy": "open",
                "config": {
                    "icon": "point_of_sale",
                    "required_checks_on_commit": [],
                    "post_commit_directives": [],
                    "order_flow": {
                        "initial_status": "new",
                        "transitions": {
                            "new": ["confirmed", "cancelled"],
                            "confirmed": ["completed"],
                            "completed": [],
                            "cancelled": [],
                        },
                        "terminal_statuses": ["completed", "cancelled"],
                    },
                },
            },
            {
                "code": "shop",
                "name": "Online Shop",
                "pricing_policy": "internal",
                "edit_policy": "open",
                "config": {
                    "icon": "storefront",
                    "required_checks_on_commit": [],
                    "post_commit_directives": [],
                    "order_flow": {
                        "initial_status": "new",
                        "transitions": {
                            "new": ["confirmed", "cancelled"],
                            "confirmed": ["processing", "cancelled"],
                            "processing": ["ready", "cancelled"],
                            "ready": ["completed"],
                            "completed": [],
                            "cancelled": [],
                        },
                        "terminal_statuses": ["completed", "cancelled"],
                    },
                },
            },
            {
                "code": "ifood",
                "name": "iFood",
                "pricing_policy": "external",  # Prices come from iFood
                "edit_policy": "locked",       # Can't modify iFood orders
                "config": {
                    "icon": "delivery_dining",
                    "required_checks_on_commit": [],
                    "post_commit_directives": [],
                    "order_flow": {
                        "initial_status": "new",
                        "transitions": {
                            "new": ["confirmed", "cancelled"],
                            "confirmed": ["processing"],
                            "processing": ["ready"],
                            "ready": ["dispatched"],
                            "dispatched": ["delivered"],
                            "delivered": ["completed"],
                            "completed": [],
                            "cancelled": [],
                        },
                        "terminal_statuses": ["completed", "cancelled"],
                    },
                },
            },
        ]

        for data in channels:
            channel, created = Channel.objects.get_or_create(
                code=data["code"],
                defaults=data,
            )
            status = "created" if created else "exists"
            policy_info = f"(pricing={data['pricing_policy']}, edit={data['edit_policy']})"
            self.stdout.write(f"  Channel {channel.code}: {status} {policy_info}")

    def seed_products(self):
        """Create example products."""
        self.stdout.write("\nCreating products...")

        products = [
            # Beverages
            {"sku": "COFFEE", "name": "Coffee", "price_q": 500, "description": "Fresh brewed coffee"},
            {"sku": "ESPRESSO", "name": "Espresso", "price_q": 450, "description": "Double shot espresso"},
            {"sku": "CAPPUCCINO", "name": "Cappuccino", "price_q": 750, "description": "Espresso with steamed milk"},
            {"sku": "LATTE", "name": "Latte", "price_q": 800, "description": "Espresso with lots of steamed milk"},
            {"sku": "MOCHA", "name": "Mocha", "price_q": 900, "description": "Espresso with chocolate and milk"},
            # Bakery
            {"sku": "CROISSANT", "name": "Croissant", "price_q": 650, "description": "Buttery French pastry"},
            {"sku": "PAINCHOC", "name": "Pain au Chocolat", "price_q": 750, "description": "Croissant with chocolate"},
            {"sku": "MUFFIN", "name": "Blueberry Muffin", "price_q": 550, "description": "Fresh baked muffin"},
            {"sku": "COOKIE", "name": "Chocolate Chip Cookie", "price_q": 400, "description": "Warm cookie"},
            {"sku": "BROWNIE", "name": "Brownie", "price_q": 600, "description": "Rich chocolate brownie"},
            # Food
            {"sku": "SANDWICH", "name": "Ham & Cheese Sandwich", "price_q": 1200, "description": "Classic sandwich"},
            {"sku": "SALAD", "name": "Garden Salad", "price_q": 950, "description": "Fresh mixed greens"},
            {"sku": "QUICHE", "name": "Quiche Lorraine", "price_q": 1100, "description": "French savory pie"},
        ]

        for data in products:
            product, created = Product.objects.get_or_create(
                sku=data["sku"],
                defaults=data,
            )
            status = "created" if created else "exists"
            price_display = f"R$ {data['price_q']/100:.2f}"
            self.stdout.write(f"  {product.sku}: {product.name} ({price_display}) - {status}")

    def create_demo_orders(self):
        """Create demo orders showing different states."""
        from example.shop.basket_service import BasketService

        self.stdout.write("\nCreating demo orders...")

        # Order 1: New order (just created)
        session1 = BasketService.get_or_create_basket("demo-new")
        BasketService.add_item(session1, sku="COFFEE", qty=2, unit_price_q=500)
        BasketService.add_item(session1, sku="CROISSANT", qty=1, unit_price_q=650)
        result1 = BasketService.commit(session1, idempotency_key="DEMO-001")
        self.stdout.write(f"  Order {result1['order_ref']}: NEW (just committed)")

        # Order 2: Confirmed order
        session2 = BasketService.get_or_create_basket("demo-confirmed")
        BasketService.add_item(session2, sku="CAPPUCCINO", qty=1, unit_price_q=750)
        BasketService.add_item(session2, sku="MUFFIN", qty=2, unit_price_q=550)
        result2 = BasketService.commit(session2, idempotency_key="DEMO-002")
        order2 = Order.objects.get(ref=result2["order_ref"])
        order2.transition_status("confirmed", actor="demo")
        self.stdout.write(f"  Order {result2['order_ref']}: CONFIRMED")

        # Order 3: Processing order
        session3 = BasketService.get_or_create_basket("demo-processing")
        BasketService.add_item(session3, sku="LATTE", qty=1, unit_price_q=800)
        BasketService.add_item(session3, sku="SANDWICH", qty=1, unit_price_q=1200)
        result3 = BasketService.commit(session3, idempotency_key="DEMO-003")
        order3 = Order.objects.get(ref=result3["order_ref"])
        order3.transition_status("confirmed", actor="demo")
        order3.transition_status("processing", actor="kitchen")
        self.stdout.write(f"  Order {result3['order_ref']}: PROCESSING")

        # Order 4: Ready order
        session4 = BasketService.get_or_create_basket("demo-ready")
        BasketService.add_item(session4, sku="ESPRESSO", qty=2, unit_price_q=450)
        result4 = BasketService.commit(session4, idempotency_key="DEMO-004")
        order4 = Order.objects.get(ref=result4["order_ref"])
        order4.transition_status("confirmed", actor="demo")
        order4.transition_status("processing", actor="kitchen")
        order4.transition_status("ready", actor="kitchen")
        self.stdout.write(f"  Order {result4['order_ref']}: READY")

        # Order 5: Completed order
        session5 = BasketService.get_or_create_basket("demo-completed")
        BasketService.add_item(session5, sku="MOCHA", qty=1, unit_price_q=900)
        BasketService.add_item(session5, sku="BROWNIE", qty=1, unit_price_q=600)
        result5 = BasketService.commit(session5, idempotency_key="DEMO-005")
        order5 = Order.objects.get(ref=result5["order_ref"])
        order5.transition_status("confirmed", actor="demo")
        order5.transition_status("processing", actor="kitchen")
        order5.transition_status("ready", actor="kitchen")
        order5.transition_status("completed", actor="cashier")
        self.stdout.write(f"  Order {result5['order_ref']}: COMPLETED")

        # Order 6: Cancelled order
        session6 = BasketService.get_or_create_basket("demo-cancelled")
        BasketService.add_item(session6, sku="QUICHE", qty=1, unit_price_q=1100)
        result6 = BasketService.commit(session6, idempotency_key="DEMO-006")
        order6 = Order.objects.get(ref=result6["order_ref"])
        order6.transition_status("cancelled", actor="customer")
        self.stdout.write(f"  Order {result6['order_ref']}: CANCELLED")

        self.stdout.write(self.style.SUCCESS(f"\n  Created 6 demo orders in various states"))
