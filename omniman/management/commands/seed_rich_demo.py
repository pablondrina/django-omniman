from __future__ import annotations

import random
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Iterable, Sequence

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management import BaseCommand
from django.db import transaction
from django.utils import timezone

from omniman.ids import generate_idempotency_key, generate_line_id, generate_order_ref
from omniman.models import (
    Channel,
    Directive,
    IdempotencyKey,
    Order,
    OrderEvent,
    OrderItem,
    Session,
)


class Command(BaseCommand):
    help = (
        "Gera dados ricos (-N..+N dias) para testes: canais, sessões, pedidos, "
        "diretivas e idempotência com diversos status."
    )

    def add_arguments(self, parser):
        parser.add_argument("--seed", type=int, default=101)
        parser.add_argument("--reset", action="store_true", help="Remove sessões/pedidos/diretivas/idempotência antes de popular.")
        parser.add_argument("--reset-catalog", action="store_true", help="Também apaga catálogo de exemplo antes de recriar.")
        parser.add_argument("--days-back", type=int, default=7)
        parser.add_argument("--days-forward", type=int, default=7)
        parser.add_argument("--channels", default="pos,shop,ifood,admin")
        parser.add_argument("--sessions-per-day", type=int, default=12)
        parser.add_argument("--orders-per-day", type=int, default=14)
        parser.add_argument("--directives-per-day", type=int, default=18)
        parser.add_argument("--idempotency-per-day", type=int, default=10)
        parser.add_argument(
            "--create-superuser-if-missing",
            action="store_true",
            help="Cria um usuário admin/admin caso não exista superuser.",
        )
        parser.add_argument(
            "--skip-examples",
            action="store_true",
            help="Não recria canais/produtos de exemplo automaticamente.",
        )
        parser.add_argument(
            "--only-base",
            action="store_true",
            help="Cria apenas os dados base (canais/produtos) e encerra.",
        )
        parser.add_argument(
            "--no-seed-channels",
            action="store_false",
            dest="seed_channels",
            default=True,
            help="Não altera canais durante o seed.",
        )
        parser.add_argument(
            "--no-seed-catalog",
            action="store_false",
            dest="seed_catalog",
            default=True,
            help="Não altera o catálogo de exemplo durante o seed.",
        )

    @transaction.atomic
    def handle(self, *args, **opts):
        rnd = random.Random(int(opts["seed"]))
        days_back = int(opts["days_back"])
        days_forward = int(opts["days_forward"])
        channel_codes = [c.strip() for c in str(opts["channels"]).split(",") if c.strip()]

        if opts["reset"] or opts["reset_catalog"]:
            self._reset_data(reset_catalog=bool(opts["reset_catalog"]))

        seed_channels = bool(opts.get("seed_channels", True))
        seed_catalog = bool(opts.get("seed_catalog", True))
        if opts["skip_examples"]:
            seed_channels = False
            seed_catalog = False

        if opts.get("only_base"):
            self._seed_examples(seed_channels=seed_channels, seed_catalog=seed_catalog)
            if opts["create_superuser_if_missing"]:
                self._ensure_superuser()
            return

        if seed_channels or seed_catalog:
            self._seed_examples(seed_channels=seed_channels, seed_catalog=seed_catalog)

        if opts["create_superuser_if_missing"]:
            self._ensure_superuser()

        channels = list(Channel.objects.filter(code__in=channel_codes).order_by("display_order", "id"))
        if not channels:
            raise SystemExit("Nenhum canal encontrado. Rode `seed_rich_demo --only-base` para criar a base.")

        products = self._load_products()

        today = timezone.localdate()
        stats = {"sessions": 0, "orders": 0, "directives": 0, "idempotency": 0}

        sessions_by_day: dict[int, list[Session]] = defaultdict(list)
        orders_by_day: dict[int, list[Order]] = defaultdict(list)

        for day_offset in range(-days_back, days_forward + 1):
            day = today + timedelta(days=day_offset)
            sessions_today = self._seed_sessions_for_day(
                rnd=rnd,
                day=day,
                day_offset=day_offset,
                per_day=int(opts["sessions_per_day"]),
                channels=channels,
                products=products,
            )
            stats["sessions"] += len(sessions_today)
            sessions_by_day[day_offset] = sessions_today

            orders_today = self._seed_orders_for_day(
                rnd=rnd,
                day=day,
                day_offset=day_offset,
                per_day=int(opts["orders_per_day"]),
                sessions_today=sessions_today,
                channels=channels,
                products=products,
            )
            stats["orders"] += len(orders_today)
            orders_by_day[day_offset] = orders_today

            directives_today = self._seed_directives_for_day(
                rnd=rnd,
                day=day,
                day_offset=day_offset,
                per_day=int(opts["directives_per_day"]),
                sessions=sessions_today,
            )
            stats["directives"] += directives_today

            idem_today = self._seed_idempotency_for_day(
                rnd=rnd,
                day=day,
                per_day=int(opts["idempotency_per_day"]),
                sessions=sessions_today,
                orders=orders_today,
                channels=channels,
            )
            stats["idempotency"] += idem_today

        self.stdout.write(self.style.SUCCESS(f"Sessões geradas: {stats['sessions']}"))
        self.stdout.write(self.style.SUCCESS(f"Pedidos gerados: {stats['orders']}"))
        self.stdout.write(self.style.SUCCESS(f"Diretivas geradas: {stats['directives']}"))
        self.stdout.write(self.style.SUCCESS(f"Entradas de idempotência: {stats['idempotency']}"))

    # --------------------------------------------------------------------- utils

    def _reset_data(self, *, reset_catalog: bool) -> None:
        self.stdout.write(self.style.WARNING("Reset solicitado: limpando dados operacionais..."))
        Session.objects.all().delete()
        Order.objects.all().delete()
        Directive.objects.all().delete()
        IdempotencyKey.objects.all().delete()

        if reset_catalog and apps.is_installed("example.catalog"):
            Product = apps.get_model("catalog", "Product")
            Product.objects.all().delete()

    def _ensure_superuser(self) -> None:
        User = get_user_model()
        if User.objects.filter(is_superuser=True, is_active=True).exists():
            return
        u, created = User.objects.get_or_create(
            username="admin",
            defaults={"email": "admin@example.com", "is_staff": True, "is_superuser": True, "is_active": True},
        )
        if created:
            u.set_password("admin")
        u.is_staff = True
        u.is_superuser = True
        u.is_active = True
        u.save(update_fields=["password", "is_staff", "is_superuser", "is_active"])
        self.stdout.write(self.style.WARNING("Nenhum superuser encontrado. Criei admin/admin."))

    def _load_products(self) -> list:
        if not apps.is_installed("example.catalog"):
            return []
        Product = apps.get_model("catalog", "Product")
        return list(Product.objects.filter(is_active=True))

    def _seed_examples(self, *, seed_channels: bool, seed_catalog: bool) -> None:
        if seed_channels:
            self._seed_channels()
        if seed_catalog:
            self._seed_catalog()

    def _seed_channels(self) -> None:
        examples = [
            {
                "code": "pos",
                "name": "PDV",
                "display_order": 10,
                "config": self._channel_config("point_of_sale", require_stock=True),
            },
            {
                "code": "shop",
                "name": "Catálogo online",
                "display_order": 20,
                "config": self._channel_config("storefront", require_stock=True),
            },
            {
                "code": "ifood",
                "name": "iFood",
                "display_order": 30,
                "config": self._channel_config("delivery_dining", require_stock=True),
                "pricing_policy": "external",
                "edit_policy": "locked",
            },
            {
                "code": "admin",
                "name": "Admin",
                "display_order": 99,
                "config": self._channel_config("settings", require_stock=False),
            },
        ]

        for ch in examples:
            Channel.objects.update_or_create(
                code=ch["code"],
                defaults={
                    "name": ch["name"],
                    "display_order": ch["display_order"],
                    "config": ch["config"],
                    "is_active": True,
                    "pricing_policy": ch.get("pricing_policy", "internal"),
                    "edit_policy": ch.get("edit_policy", "open"),
                },
            )

    def _channel_config(self, icon: str, *, require_stock: bool) -> dict:
        config: dict[str, Any] = {"icon": icon}
        if require_stock:
            config.update(
                {
                    "required_checks_on_commit": ["stock"],
                    "checks": {"stock": {"directive_topic": "stock.hold"}},
                    "post_commit_directives": ["stock.commit"],
                }
            )
        else:
            # Mesmo sem require_stock, adiciona post_commit_directives para execução automática no admin
            config["post_commit_directives"] = ["stock.commit"]
        return config

    def _seed_catalog(self) -> None:
        if not apps.is_installed("example.catalog"):
            self.stdout.write(
                self.style.WARNING(
                    "Catálogo de exemplo não instalado. Adicione 'example.catalog' ao INSTALLED_APPS (ou forneça o seu)."
                )
            )
            return

        Product = apps.get_model("catalog", "Product")
        Inventory = apps.get_model("catalog", "Inventory")
        products = [
            {"sku": "CROISSANT", "name": "Croissant", "price_q": 1200, "currency": "BRL"},
            {"sku": "LATTE", "name": "Café Latte", "price_q": 1600, "currency": "BRL"},
            {"sku": "PAINCHOC", "name": "Pain au Chocolat", "price_q": 1300, "currency": "BRL"},
        ]

        base_stock = 50
        for idx, p in enumerate(products):
            product_obj, _ = Product.objects.update_or_create(sku=p["sku"], defaults={**p, "is_active": True})
            Inventory.objects.update_or_create(
                product=product_obj,
                defaults={"stock_qty": Decimal(str(base_stock - idx * 5))},
            )

    def _random_moment(self, *, rnd: random.Random, day: date, hours: Sequence[int]) -> datetime:
        base = timezone.make_aware(datetime.combine(day, datetime.min.time()))
        hour = rnd.choice(hours)
        minute = rnd.choice([0, 5, 10, 15, 20, 30, 40, 50])
        dt = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
        dt += timedelta(minutes=rnd.randint(-15, 15), seconds=rnd.randint(0, 59))
        return dt

    def _build_items(self, *, rnd: random.Random, products: list, channel: Channel) -> list[dict]:
        count = rnd.randint(1, 4)
        items: list[dict] = []
        for _ in range(count):
            if products:
                product = rnd.choice(products)
                sku = getattr(product, "sku", "SKU")
                unit_price_q = int(getattr(product, "price_q", 0) or 0)
                name = getattr(product, "name", sku)
            else:
                sku = rnd.choice(["LATTE", "CROISSANT", "COMBO", "DRINK"])
                unit_price_q = rnd.choice([900, 1200, 1500, 1800, 2200])
                name = sku.title()

            qty = rnd.choice([1, 1, 2, 2, 3])
            if channel.pricing_policy == "external":
                unit_price_q = max(0, unit_price_q + rnd.choice([-250, -100, 0, 0, 100, 250]))

            items.append(
                {
                    "line_id": generate_line_id(),
                    "sku": sku,
                    "name": name,
                    "qty": float(qty),
                    "unit_price_q": unit_price_q,
                    "meta": {"seed": "seed_rich_demo"},
                }
            )
        return items

    def _calc_total(self, items: Iterable[dict]) -> int:
        total = 0
        for item in items:
            qty = Decimal(str(item.get("qty", 0)))
            total += int(qty * int(item.get("unit_price_q", 0)))
        return total

    # ------------------------------------------------------------- session seed

    def _seed_sessions_for_day(
        self,
        *,
        rnd: random.Random,
        day: date,
        day_offset: int,
        per_day: int,
        channels: Sequence[Channel],
        products: list,
    ) -> list[Session]:
        states = ["open", "committed", "abandoned"]
        sessions: list[Session] = []

        mandatory_states = states if day_offset == 0 else []

        for state in mandatory_states:
            sessions.append(
                self._create_session(
                    rnd=rnd,
                    day=day,
                    state=state,
                    channels=channels,
                    products=products,
                )
            )

        while len(sessions) < per_day:
            state = self._pick_session_state(rnd=rnd, day_offset=day_offset)
            sessions.append(
                self._create_session(
                    rnd=rnd,
                    day=day,
                    state=state,
                    channels=channels,
                    products=products,
                )
            )

        return sessions

    def _pick_session_state(self, *, rnd: random.Random, day_offset: int) -> str:
        if day_offset > 0:
            weights = [0.65, 0.20, 0.15]
        elif day_offset < 0:
            weights = [0.25, 0.55, 0.20]
        else:
            weights = [0.45, 0.35, 0.20]
        return rnd.choices(["open", "committed", "abandoned"], weights=weights, k=1)[0]

    def _create_session(
        self,
        *,
        rnd: random.Random,
        day: date,
        state: str,
        channels: Sequence[Channel],
        products: list,
    ) -> Session:
        channel = rnd.choice(channels)
        handle_type = rnd.choice(["mesa", "comanda", "checkout", "pedido_externo"])
        handle_ref = f"{handle_type[:2].upper()}-{rnd.randint(10, 999)}"
        items = self._build_items(rnd=rnd, products=products, channel=channel)
        total_q = self._calc_total(items)
        opened_at = self._random_moment(rnd=rnd, day=day, hours=[8, 9, 11, 12, 15, 18, 21])

        session = Session.objects.create(
            session_key=f"S-{uuid.UUID(int=rnd.getrandbits(128)).hex[:16]}",
            channel=channel,
            handle_type=handle_type,
            handle_ref=handle_ref,
            state=state,
            pricing_policy=channel.pricing_policy,
            edit_policy=channel.edit_policy,
            rev=rnd.randint(0, 4),
            items=items,
            pricing={"total_q": total_q, "items_count": len(items)},
            pricing_trace=[{"source": "seed_rich_demo", "total_q": total_q}],
            data=self._session_data_for_state(rnd=rnd, state=state),
            commit_token=None,
        )

        committed_at = None
        commit_token = None
        if state == "committed":
            committed_at = opened_at + timedelta(minutes=rnd.randint(5, 75))
            commit_token = generate_idempotency_key()

        Session.objects.filter(pk=session.pk).update(
            opened_at=opened_at,
            updated_at=(committed_at or opened_at) + timedelta(minutes=rnd.randint(2, 25)),
            committed_at=committed_at,
            commit_token=commit_token,
        )

        session.commit_token = commit_token
        session.opened_at = opened_at
        session.committed_at = committed_at
        return session

    def _session_data_for_state(self, *, rnd: random.Random, state: str) -> dict:
        data = {"checks": {}, "issues": []}
        if state == "committed":
            data["checks"]["stock"] = {
                "rev": rnd.randint(0, 4),
                "at": timezone.now().isoformat(),
                "result": {"hold_ref": f"H{rnd.randint(1000, 9999)}", "expires_at": None},
            }
        elif state == "open" and rnd.random() < 0.25:
            issue_id = f"ISS-{uuid.uuid4().hex[:6]}"
            data["issues"] = [
                {
                    "id": issue_id,
                    "source": "stock",
                    "code": "stock.pending_check",
                    "blocking": False,
                    "message": "Checagem de estoque pendente.",
                    "context": {"actions": []},
                }
            ]
        return data

    # --------------------------------------------------------------- order seed

    def _seed_orders_for_day(
        self,
        *,
        rnd: random.Random,
        day: date,
        day_offset: int,
        per_day: int,
        sessions_today: list[Session],
        channels: Sequence[Channel],
        products: list,
    ) -> list[Order]:
        orders: list[Order] = []
        statuses = ["NEW", "IN_PROGRESS", "READY", "COMPLETED", "CANCELED"]
        mandatory_statuses = statuses if day_offset == 0 else []

        committed_sessions = [s for s in sessions_today if s.state == "committed"]
        rnd.shuffle(committed_sessions)

        def pick_status() -> str:
            if day_offset > 0:
                weights = [0.50, 0.30, 0.10, 0.05, 0.05]
            elif day_offset < 0:
                weights = [0.05, 0.10, 0.15, 0.55, 0.15]
            else:
                weights = [0.25, 0.25, 0.20, 0.20, 0.10]
            return rnd.choices(statuses, weights=weights, k=1)[0]

        for status in mandatory_statuses:
            session = committed_sessions.pop() if committed_sessions else rnd.choice(sessions_today)
            orders.append(self._create_order_from_session(rnd=rnd, session=session, day=day, status=status))

        while committed_sessions and len(orders) < per_day:
            session = committed_sessions.pop()
            orders.append(self._create_order_from_session(rnd=rnd, session=session, day=day, status=pick_status()))

        while len(orders) < per_day:
            orders.append(
                self._create_synthetic_order(
                    rnd=rnd,
                    day=day,
                    status=pick_status(),
                    channels=channels,
                    products=products,
                )
            )

        return orders

    def _create_order_from_session(
        self,
        *,
        rnd: random.Random,
        session: Session,
        day: date,
        status: str,
    ) -> Order:
        created_at = self._random_moment(rnd=rnd, day=day, hours=[9, 10, 11, 12, 13, 18, 19, 21])
        total_q = session.pricing.get("total_q", self._calc_total(session.items))

        order = Order.objects.create(
            ref=generate_order_ref(),
            channel=session.channel,
            session_key=session.session_key,
            handle_type=session.handle_type,
            handle_ref=session.handle_ref,
            status=status,
            snapshot={
                "items": session.items,
                "data": session.data,
                "pricing": session.pricing,
                "rev": session.rev,
            },
            total_q=total_q,
        )

        for item in session.items:
            qty = Decimal(str(item.get("qty", 0)))
            unit_price = int(item.get("unit_price_q", 0))
            OrderItem.objects.create(
                order=order,
                line_id=item.get("line_id") or generate_line_id(),
                sku=item.get("sku", ""),
                name=item.get("name", ""),
                qty=qty,
                unit_price_q=unit_price,
                line_total_q=int(qty * unit_price),
                meta=item.get("meta", {}),
            )

        OrderEvent.objects.create(
            order=order,
            type="seed.created",
            actor="seed_rich_demo",
            payload={"session_key": session.session_key, "status": status},
        )

        Order.objects.filter(pk=order.pk).update(
            created_at=created_at,
            updated_at=created_at + timedelta(minutes=rnd.randint(5, 120)),
        )
        order.created_at = created_at
        return order

    def _create_synthetic_order(
        self,
        *,
        rnd: random.Random,
        day: date,
        status: str,
        channels: Sequence[Channel],
        products: list,
    ) -> Order:
        channel = rnd.choice(channels)
        dummy_session = Session(
            session_key=f"SYN-{uuid.uuid4().hex[:10]}",
            channel=channel,
            handle_type=rnd.choice(["mesa", "comanda", "checkout"]),
            handle_ref=f"AUTO-{rnd.randint(100,999)}",
            data={"checks": {}, "issues": []},
            pricing_policy=channel.pricing_policy,
            edit_policy=channel.edit_policy,
            pricing={},
            rev=rnd.randint(0, 3),
        )
        dummy_session.items = self._build_items(rnd=rnd, products=products, channel=channel)
        return self._create_order_from_session(rnd=rnd, session=dummy_session, day=day, status=status)

    # ----------------------------------------------------------- directives/idm

    def _seed_directives_for_day(
        self,
        *,
        rnd: random.Random,
        day: date,
        day_offset: int,
        per_day: int,
        sessions: list[Session],
    ) -> int:
        statuses = ["queued", "running", "done", "failed"]
        mandatory = statuses if day_offset == 0 else []
        created = 0

        def pick_status() -> str:
            if day_offset > 0:
                weights = [0.55, 0.30, 0.10, 0.05]
            elif day_offset < 0:
                weights = [0.05, 0.15, 0.65, 0.15]
            else:
                weights = [0.30, 0.25, 0.35, 0.10]
            return rnd.choices(statuses, weights=weights, k=1)[0]

        topics = ["stock.hold", "stock.commit"]

        def create_directive(status: str) -> None:
            session = rnd.choice(sessions) if sessions else None
            payload = {
                "seed": "seed_rich_demo",
                "channel_code": session.channel.code if session else rnd.choice(["pos", "shop"]),
                "session_key": session.session_key if session else f"S-{uuid.uuid4().hex[:12]}",
            }
            directive = Directive.objects.create(
                topic=rnd.choices(topics, weights=[0.75, 0.25], k=1)[0],
                status=status,
                payload=payload,
            )
            created_at = self._random_moment(rnd=rnd, day=day, hours=[8, 10, 12, 14, 16, 18, 20, 22])
            Directive.objects.filter(pk=directive.pk).update(
                created_at=created_at,
                available_at=created_at + timedelta(minutes=rnd.randint(0, 30)),
                updated_at=created_at + timedelta(minutes=rnd.randint(5, 60)),
            )

        for st in mandatory:
            create_directive(st)
            created += 1

        while created < per_day:
            create_directive(pick_status())
            created += 1

        return created

    def _seed_idempotency_for_day(
        self,
        *,
        rnd: random.Random,
        day: date,
        per_day: int,
        sessions: list[Session],
        orders: list[Order],
        channels: Sequence[Channel],
    ) -> int:
        statuses = ["in_progress", "done", "failed"]
        created = 0

        def pick_status() -> str:
            return rnd.choices(statuses, weights=[0.30, 0.55, 0.15], k=1)[0]

        order_pool = orders or []
        channel = channels[0]

        while created < per_day:
            status = pick_status()
            scope_channel = rnd.choice(channels)
            session = rnd.choice(sessions) if sessions else None
            response_body = None
            response_code = None
            if status == "done" and order_pool:
                order = rnd.choice(order_pool)
                response_body = {"order_ref": order.ref, "status": "committed"}
                response_code = 201

            idem = IdempotencyKey.objects.create(
                scope=f"commit:{scope_channel.code}",
                key=generate_idempotency_key(),
                status=status,
                response_code=response_code,
                response_body=response_body,
                expires_at=timezone.now() + timedelta(days=3),
            )
            created_at = self._random_moment(rnd=rnd, day=day, hours=[7, 9, 11, 13, 15, 17, 19, 21])
            IdempotencyKey.objects.filter(pk=idem.pk).update(created_at=created_at)
            created += 1

        return created
