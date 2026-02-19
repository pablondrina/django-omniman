from __future__ import annotations

import uuid

from django.core.management.base import BaseCommand

from example.catalog.backends import ExampleStockBackend
from example.catalog.models import Inventory, Product

from omniman.ids import generate_idempotency_key, generate_session_key
from omniman.management.commands.seed_rich_demo import Command as SeedCommand
from omniman.models import Channel, Directive, Session
from omniman.services import CommitService, ModifyService


class Command(BaseCommand):
    help = "Simula um pedido do e-commerce (canal 'shop') exercitando stock.hold e commit."

    def add_arguments(self, parser):
        parser.add_argument("--sku", default="PAINCHOC", help="SKU do produto (default: PAINCHOC)")
        parser.add_argument("--qty", type=int, default=2, help="Quantidade (default: 2)")

    def handle(self, *args, **opts):
        sku = str(opts["sku"]).upper()
        qty = int(opts["qty"])
        if qty <= 0:
            raise SystemExit("Quantidade deve ser > 0")

        channel = Channel.objects.filter(code="shop").first()
        if not channel:
            self.stdout.write(self.style.WARNING("Canal shop não encontrado. Criando base de exemplo..."))
            seed_cmd = SeedCommand()
            seed_cmd._seed_examples(seed_channels=True, seed_catalog=True)
            channel = Channel.objects.get(code="shop")

        try:
            product = Product.objects.get(sku=sku)
        except Product.DoesNotExist:
            raise SystemExit(f"Produto {sku} não encontrado. Rode `seed_rich_demo --only-base` primeiro.")

        session = Session.objects.create(
            session_key=generate_session_key(),
            channel=channel,
            handle_type="web_order",
            handle_ref=f"shop:{uuid.uuid4().hex[:8]}",
            state="open",
            pricing_policy=channel.pricing_policy,
            edit_policy=channel.edit_policy,
            items=[],
            data={"checks": {}, "issues": []},
        )

        ModifyService.modify_session(
            session_key=session.session_key,
            channel_code=channel.code,
            ops=[
                {
                    "op": "add_line",
                    "sku": sku,
                    "qty": qty,
                    "unit_price_q": product.price_q,
                }
            ],
            ctx={"actor": "simulate_shop_order"},
        )

        backend = ExampleStockBackend(
            product_resolver=lambda s: Product.objects.get(sku=s),
            inventory_resolver=lambda s: Inventory.objects.get_or_create(
                product=Product.objects.get(sku=s),
                defaults={"stock_qty": 0},
            )[0],
        )

        directives = Directive.objects.filter(
            topic="stock.hold", status="queued", payload__session_key=session.session_key
        )
        for directive in directives:
            from omniman.contrib.stock.handlers import StockHoldHandler

            StockHoldHandler(backend=backend).handle(message=directive, ctx={})

        result = CommitService.commit(
            session_key=session.session_key,
            channel_code=channel.code,
            idempotency_key=generate_idempotency_key(),
            ctx={"actor": "simulate_shop_order"},
        )

        post_directives = Directive.objects.filter(
            topic="stock.commit", status="queued", payload__order_ref=result["order_ref"]
        )
        for directive in post_directives:
            from omniman.contrib.stock.handlers import StockCommitHandler

            StockCommitHandler(backend=backend).handle(message=directive, ctx={})

        inventory = Inventory.objects.get(product__sku=sku)
        self.stdout.write(self.style.SUCCESS(f"Pedido criado: {result['order_ref']}"))
        self.stdout.write(self.style.SUCCESS(f"Estoque atualizado de {sku}: {inventory.stock_qty} unidades"))
