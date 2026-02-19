"""
Basket Service - E-commerce basket integration with Omniman Session.

This module demonstrates how to use Omniman Sessions as shopping baskets.
Session = mutable basket, Order = immutable confirmed order.

Usage:
    from example.shop.basket_service import BasketService

    # Get or create basket
    session = BasketService.get_or_create_basket(channel_code="shop", basket_key="USER-123")

    # Add items
    BasketService.add_item(session, sku="COFFEE", qty=2)

    # Commit (creates Order)
    result = BasketService.commit(session, idempotency_key="CHECKOUT-123")
    print(result["order_ref"])  # ORD-20260119-ABC123
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING
import uuid

from omniman.models import Channel, Order, Session
from omniman.services import ModifyService, CommitService

from .models import Product

if TYPE_CHECKING:
    pass


# Default channel code for the shop
DEFAULT_CHANNEL_CODE = "shop"


class BasketService:
    """
    Service for managing shopping baskets using Omniman Sessions.

    This is a minimal implementation demonstrating the integration.
    In production, you would add:
    - Customer association
    - Fulfillment options
    - Payment integration
    - etc.
    """

    @staticmethod
    def get_or_create_channel() -> Channel:
        """
        Get or create the shop channel.

        The channel configures how Omniman handles sessions:
        - pricing_policy="internal": Omniman looks up prices via modifiers
        - edit_policy="open": Sessions can be freely modified
        """
        channel, _ = Channel.objects.get_or_create(
            code=DEFAULT_CHANNEL_CODE,
            defaults={
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
        )
        return channel

    @classmethod
    def get_or_create_basket(
        cls,
        basket_key: str,
        channel_code: str = DEFAULT_CHANNEL_CODE,
    ) -> Session:
        """
        Get or create a basket (Session) for the given key.

        Args:
            basket_key: Unique identifier for the basket (e.g., user ID, session ID)
            channel_code: Channel code (default: "shop")

        Returns:
            Session object (basket)
        """
        channel = cls.get_or_create_channel()

        session_key = f"BASKET-{basket_key}"
        session, created = Session.objects.get_or_create(
            channel=channel,
            session_key=session_key,
            state="open",
            defaults={},
        )

        # If session was committed, create a new one
        if session.state in ("committed", "abandoned"):
            new_key = f"BASKET-{basket_key}-{uuid.uuid4().hex[:8]}"
            session = Session.objects.create(
                channel=channel,
                session_key=new_key,
                state="open",
            )

        return session

    @classmethod
    def add_item(
        cls,
        session: Session,
        sku: str,
        qty: int = 1,
        unit_price_q: int | None = None,
    ) -> dict:
        """
        Add an item to the basket.

        If the item already exists, increases quantity.

        Args:
            session: The basket session
            sku: Product SKU
            qty: Quantity to add
            unit_price_q: Unit price in cents (optional, will be looked up if not provided)

        Returns:
            dict with success status and updated basket info
        """
        # Check if item already exists
        existing_line = None
        for item in session.items:
            if item.get("sku") == sku:
                existing_line = item
                break

        if existing_line:
            # Update quantity
            new_qty = int(existing_line["qty"]) + qty
            ModifyService.modify_session(
                session_key=session.session_key,
                channel_code=session.channel.code,
                ops=[{
                    "op": "set_qty",
                    "line_id": existing_line["line_id"],
                    "qty": new_qty,
                }],
            )
        else:
            # Add new item
            op = {
                "op": "add_line",
                "sku": sku,
                "qty": qty,
            }

            # Add price if provided (for external pricing)
            # For internal pricing, the modifier will look it up
            if unit_price_q is not None:
                op["unit_price_q"] = unit_price_q

            # Try to get product name
            try:
                product = Product.objects.get(sku=sku, is_active=True)
                op["name"] = product.name
                op["meta"] = {"product_id": product.pk}
            except Product.DoesNotExist:
                pass

            ModifyService.modify_session(
                session_key=session.session_key,
                channel_code=session.channel.code,
                ops=[op],
            )

        session.refresh_from_db()

        return {
            "success": True,
            "total_items": cls.get_total_items(session),
            "subtotal_q": cls.get_subtotal_q(session),
        }

    @classmethod
    def update_item(
        cls,
        session: Session,
        line_id: str,
        qty: int,
    ) -> dict:
        """
        Update item quantity. If qty <= 0, removes the item.

        Args:
            session: The basket session
            line_id: Line item ID
            qty: New quantity (0 to remove)

        Returns:
            dict with success status and updated basket info
        """
        if qty <= 0:
            op = {"op": "remove_line", "line_id": line_id}
        else:
            op = {"op": "set_qty", "line_id": line_id, "qty": qty}

        ModifyService.modify_session(
            session_key=session.session_key,
            channel_code=session.channel.code,
            ops=[op],
        )

        session.refresh_from_db()

        return {
            "success": True,
            "total_items": cls.get_total_items(session),
            "subtotal_q": cls.get_subtotal_q(session),
        }

    @classmethod
    def remove_item(cls, session: Session, line_id: str) -> dict:
        """Remove an item from the basket."""
        return cls.update_item(session, line_id, qty=0)

    @classmethod
    def clear(cls, session: Session) -> dict:
        """Clear all items from the basket."""
        ops = [
            {"op": "remove_line", "line_id": item["line_id"]}
            for item in session.items
        ]

        if ops:
            ModifyService.modify_session(
                session_key=session.session_key,
                channel_code=session.channel.code,
                ops=ops,
            )

        return {"success": True}

    @staticmethod
    def get_total_items(session: Session) -> int:
        """Get total item count in basket."""
        return sum(int(item.get("qty", 0)) for item in session.items)

    @staticmethod
    def get_subtotal_q(session: Session) -> int:
        """Get subtotal in cents."""
        return sum(
            int(item.get("line_total_q", 0))
            for item in session.items
        )

    @staticmethod
    def get_subtotal_display(session: Session) -> str:
        """Get formatted subtotal for display."""
        subtotal_q = BasketService.get_subtotal_q(session)
        return f"R$ {subtotal_q / 100:.2f}"

    @classmethod
    def get_items(cls, session: Session) -> list[dict]:
        """
        Get basket items with enriched product data.

        Returns:
            List of item dicts with product info
        """
        items = []
        for item in session.items:
            product = None
            product_id = item.get("meta", {}).get("product_id")
            if product_id:
                try:
                    product = Product.objects.get(pk=product_id)
                except Product.DoesNotExist:
                    pass

            items.append({
                "line_id": item["line_id"],
                "sku": item["sku"],
                "name": item.get("name", ""),
                "qty": int(item["qty"]),
                "unit_price_q": int(item.get("unit_price_q", 0)),
                "line_total_q": int(item.get("line_total_q", 0)),
                "product": product,
            })

        return items

    @classmethod
    def commit(
        cls,
        session: Session,
        idempotency_key: str | None = None,
    ) -> dict:
        """
        Commit the basket, creating an Order.

        Args:
            session: The basket session
            idempotency_key: Unique key for idempotent commit (prevents duplicates)

        Returns:
            dict with order_ref and status
        """
        if not session.items:
            raise ValueError("Cannot commit empty basket")

        if idempotency_key is None:
            idempotency_key = f"CHECKOUT-{uuid.uuid4().hex}"

        result = CommitService.commit(
            session_key=session.session_key,
            channel_code=session.channel.code,
            idempotency_key=idempotency_key,
        )

        return {
            "success": True,
            "order_ref": result["order_ref"],
            "order_id": result.get("order_id"),
            "status": result.get("status", "committed"),
        }

    @staticmethod
    def get_order(order_ref: str) -> Order | None:
        """Get an order by reference."""
        try:
            return Order.objects.get(ref=order_ref)
        except Order.DoesNotExist:
            return None
