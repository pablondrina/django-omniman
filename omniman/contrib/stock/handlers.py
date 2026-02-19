"""
Omniman Stock Handlers — Handlers de diretiva para estoque.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from django.utils import timezone

from omniman.ids import generate_action_id, generate_issue_id
from omniman.models import Directive
from omniman.services import SessionWriteService

from .protocols import StockBackend

logger = logging.getLogger(__name__)


class StockHoldHandler:
    """
    Handler que executa verificação + reserva de estoque.

    Topic: stock.hold

    Comportamento idempotente:
    - Antes de criar novos holds, libera os anteriores da mesma sessão
    - Um hold por SKU por sessão (quantidades são agregadas)
    - Executar N vezes = mesmo resultado
    """

    topic = "stock.hold"
    DEFAULT_HOLD_TTL_MINUTES = 15

    def __init__(self, backend: StockBackend):
        self.backend = backend

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from omniman.models import Session

        payload = message.payload
        session_key = payload["session_key"]
        channel_code = payload["channel_code"]
        expected_rev = payload["rev"]

        try:
            session = Session.objects.select_related("channel").get(
                session_key=session_key,
                channel__code=channel_code,
            )
        except Session.DoesNotExist:
            # Session not found - this is an error, not a success
            logger.error(
                "StockHoldHandler: Session not found. "
                f"session_key={session_key}, channel_code={channel_code}"
            )
            message.status = "failed"
            message.last_error = f"Session not found: {channel_code}:{session_key}"
            message.save(update_fields=["status", "last_error", "updated_at"])
            return

        if session.rev != expected_rev:
            # Rev mismatch - this means the session was modified after the directive was created
            # Mark as failed so it can be investigated or retried
            logger.warning(
                "StockHoldHandler: rev mismatch (stale directive). "
                f"session_key={session_key}, expected_rev={expected_rev}, "
                f"session.rev={session.rev}"
            )
            message.status = "failed"
            message.last_error = f"Stale directive: expected rev {expected_rev}, found {session.rev}"
            message.save(update_fields=["status", "last_error", "updated_at"])
            return

        if session.state != "open":
            # Session already committed or abandoned - mark as done (expected scenario)
            logger.info(
                "StockHoldHandler: session not open, skipping. "
                f"session_key={session_key}, state={session.state}"
            )
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        # IDEMPOTÊNCIA: Libera holds anteriores desta sessão antes de criar novos.
        # Isso garante que re-executar o check não acumula holds duplicados.
        if hasattr(self.backend, "release_holds_for_reference"):
            self.backend.release_holds_for_reference(session_key)

        # Agrega quantidades por SKU (um hold por SKU por sessão)
        aggregated_items = self._aggregate_items_by_sku(session.items)

        issues: list[dict] = []
        check_result: dict[str, Any] = {"items": [], "holds": []}
        hold_expirations: list[datetime] = []
        hold_ttl = timedelta(minutes=self.DEFAULT_HOLD_TTL_MINUTES)

        for sku, item_data in aggregated_items.items():
            qty = item_data["qty"]
            line_ids = item_data["line_ids"]

            availability = self.backend.check_availability(sku=sku, quantity=qty)
            check_result["items"].append(
                {
                    "sku": sku,
                    "qty": float(qty),
                    "available": availability.available,
                    "available_qty": float(availability.available_qty),
                }
            )

            if not availability.available:
                # Cria issue para cada line_id afetado
                for line_id in line_ids:
                    issues.append(
                        self._build_issue(
                            sku=sku,
                            line_id=line_id,
                            requested_qty=qty,
                            available_qty=availability.available_qty,
                            message=availability.message,
                            session_rev=session.rev,
                        )
                    )
                continue

            hold_result = self.backend.create_hold(
                sku=sku,
                quantity=qty,
                expires_at=timezone.now() + hold_ttl,
                reference=session_key,
            )
            if not hold_result.success or not hold_result.hold_id:
                for line_id in line_ids:
                    issues.append(
                        self._build_issue(
                            sku=sku,
                            line_id=line_id,
                            requested_qty=qty,
                            available_qty=Decimal("0"),
                            message=hold_result.message or "Não foi possível reservar estoque.",
                            session_rev=session.rev,
                        )
                    )
                continue

            hold_payload = {"sku": sku, "hold_id": hold_result.hold_id, "qty": float(qty)}
            if hold_result.expires_at:
                hold_payload["expires_at"] = hold_result.expires_at.isoformat()
                hold_expirations.append(hold_result.expires_at)
            check_result["holds"].append(hold_payload)

        if hold_expirations:
            check_result["hold_expires_at"] = min(hold_expirations).isoformat()

        logger.info(
            f"StockHoldHandler: attempting to apply check result. "
            f"session_key={session_key}, expected_rev={expected_rev}, "
            f"issues_count={len(issues)}, holds_count={len(check_result.get('holds', []))}"
        )

        applied = SessionWriteService.apply_check_result(
            session_key=session_key,
            channel_code=channel_code,
            expected_rev=expected_rev,
            check_code="stock",
            check_payload=check_result,
            issues=issues,
        )

        if not applied:
            logger.warning(
                f"StockHoldHandler: check result NOT applied (stale_rev). "
                f"session_key={session_key}, expected_rev={expected_rev}, "
                f"issues_count={len(issues)}, holds_count={len(check_result.get('holds', []))}"
            )
        else:
            logger.info(
                f"StockHoldHandler: check result applied successfully. "
                f"session_key={session_key}, expected_rev={expected_rev}"
            )

        message.status = "done" if applied else "failed"
        message.last_error = "" if applied else "stale_rev"
        message.payload["holds"] = check_result.get("holds", [])
        message.save()

    def _aggregate_items_by_sku(self, items: list[dict]) -> dict[str, dict]:
        """
        Agrega itens por SKU, somando quantidades.

        Returns:
            Dict com SKU como chave e {"qty": Decimal, "line_ids": list[str]}
        """
        aggregated: dict[str, dict] = {}
        for item in items:
            sku = item["sku"]
            qty = Decimal(str(item["qty"]))
            line_id = item["line_id"]

            if sku not in aggregated:
                aggregated[sku] = {"qty": Decimal("0"), "line_ids": []}

            aggregated[sku]["qty"] += qty
            aggregated[sku]["line_ids"].append(line_id)

        return aggregated

    def _build_issue(
        self,
        *,
        sku: str,
        line_id: str,
        requested_qty: Decimal,
        available_qty: Decimal,
        message: str | None,
        session_rev: int,
    ) -> dict:
        return {
            "id": generate_issue_id(),
            "source": "stock",
            "code": "stock.insufficient",
            "blocking": True,
            "message": message or f"Estoque insuficiente para {sku}",
            "context": {
                "line_id": line_id,
                "sku": sku,
                "requested_qty": float(requested_qty),
                "available_qty": float(available_qty),
                "actions": self._build_actions(
                    line_id=line_id,
                    requested_qty=requested_qty,
                    available_qty=available_qty,
                    session_rev=session_rev,
                ),
            },
        }

    def _build_actions(
        self,
        *,
        line_id: str,
        requested_qty: Decimal,
        available_qty: Decimal,
        session_rev: int,
    ) -> list[dict]:
        actions: list[dict] = []
        if available_qty > 0:
            actions.append(
                {
                    "id": generate_action_id(),
                    "label": f"Ajustar para {available_qty} unidade(s)",
                    "rev": session_rev,
                    "ops": [{"op": "set_qty", "line_id": line_id, "qty": float(available_qty)}],
                }
            )
        actions.append(
            {
                "id": generate_action_id(),
                "label": "Remover item",
                "rev": session_rev,
                "ops": [{"op": "remove_line", "line_id": line_id}],
            }
        )
        return actions


class StockCommitHandler:
    """
    Handler para confirmação de reservas de estoque.

    Topic: stock.commit
    """

    topic = "stock.commit"

    def __init__(self, backend: StockBackend):
        self.backend = backend

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from omniman.models import Session

        payload = message.payload
        holds = payload.get("holds") or []
        order_ref = payload.get("order_ref")

        if not holds and payload.get("session_key") and payload.get("channel_code"):
            try:
                session = Session.objects.get(
                    session_key=payload["session_key"],
                    channel__code=payload["channel_code"],
                )
                holds = (
                    session.data.get("checks", {})
                    .get("stock", {})
                    .get("result", {})
                    .get("holds", [])
                )
            except Session.DoesNotExist:
                holds = []

        for hold in holds:
            hold_id = hold.get("hold_id")
            if hold_id:
                self.backend.fulfill_hold(hold_id, reference=order_ref)

        message.status = "done"
        message.save()







