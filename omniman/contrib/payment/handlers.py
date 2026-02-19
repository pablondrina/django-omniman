"""
Omniman Payment Handlers — Handlers de diretiva para pagamento.
"""

from __future__ import annotations

import logging
from typing import Any

from omniman.models import Directive

from .protocols import PaymentBackend

logger = logging.getLogger(__name__)


class PaymentCaptureHandler:
    """
    Handler que captura pagamento quando Order é criada.

    Topic: payment.capture

    Comportamento idempotente:
    - Verifica se já foi capturado antes de tentar novamente
    - Re-executar não cobra 2x
    """

    topic = "payment.capture"

    def __init__(self, backend: PaymentBackend):
        self.backend = backend

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from omniman.models import Order, Session

        payload = message.payload
        order_ref = payload.get("order_ref")
        intent_id = payload.get("intent_id")
        amount_q = payload.get("amount_q")

        # Busca intent_id do payload ou da session
        if not intent_id and payload.get("session_key"):
            try:
                session = Session.objects.get(
                    session_key=payload["session_key"],
                    channel__code=payload.get("channel_code"),
                )
                intent_id = session.data.get("payment", {}).get("intent_id")
            except Session.DoesNotExist:
                pass

        if not intent_id:
            logger.warning(
                f"PaymentCaptureHandler: No intent_id found. order_ref={order_ref}"
            )
            message.status = "failed"
            message.last_error = "no_intent_id"
            message.save()
            return

        # Verifica status atual (idempotência)
        current_status = self.backend.get_status(intent_id)
        if current_status.status == "captured":
            logger.info(
                f"PaymentCaptureHandler: Already captured. "
                f"intent_id={intent_id}, order_ref={order_ref}"
            )
            message.status = "done"
            message.save()
            return

        # Tenta capturar
        result = self.backend.capture(
            intent_id,
            amount_q=amount_q,
            reference=order_ref,
        )

        if result.success:
            logger.info(
                f"PaymentCaptureHandler: Captured successfully. "
                f"intent_id={intent_id}, order_ref={order_ref}, "
                f"transaction_id={result.transaction_id}"
            )
            message.status = "done"
            message.payload["transaction_id"] = result.transaction_id
            message.save()

            # Atualiza Order se existir
            if order_ref:
                try:
                    order = Order.objects.get(ref=order_ref)
                    order.emit_event(
                        event_type="payment.captured",
                        payload={
                            "intent_id": intent_id,
                            "transaction_id": result.transaction_id,
                            "amount_q": result.amount_q,
                        },
                        actor="payment.capture",
                    )
                except Order.DoesNotExist:
                    pass
        else:
            logger.error(
                f"PaymentCaptureHandler: Capture failed. "
                f"intent_id={intent_id}, order_ref={order_ref}, "
                f"error={result.error_code}: {result.message}"
            )
            message.status = "failed"
            message.last_error = f"{result.error_code}: {result.message}"
            message.save()


class PaymentRefundHandler:
    """
    Handler que processa reembolso.

    Topic: payment.refund
    """

    topic = "payment.refund"

    def __init__(self, backend: PaymentBackend):
        self.backend = backend

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from omniman.models import Order

        payload = message.payload
        order_ref = payload.get("order_ref")
        intent_id = payload.get("intent_id")
        amount_q = payload.get("amount_q")
        reason = payload.get("reason")

        if not intent_id:
            message.status = "failed"
            message.last_error = "no_intent_id"
            message.save()
            return

        result = self.backend.refund(
            intent_id,
            amount_q=amount_q,
            reason=reason,
        )

        if result.success:
            logger.info(
                f"PaymentRefundHandler: Refunded successfully. "
                f"intent_id={intent_id}, refund_id={result.refund_id}, "
                f"amount_q={result.amount_q}"
            )
            message.status = "done"
            message.payload["refund_id"] = result.refund_id
            message.save()

            # Atualiza Order se existir
            if order_ref:
                try:
                    order = Order.objects.get(ref=order_ref)
                    order.emit_event(
                        event_type="payment.refunded",
                        payload={
                            "intent_id": intent_id,
                            "refund_id": result.refund_id,
                            "amount_q": result.amount_q,
                            "reason": reason,
                        },
                        actor="payment.refund",
                    )
                except Order.DoesNotExist:
                    pass
        else:
            logger.error(
                f"PaymentRefundHandler: Refund failed. "
                f"intent_id={intent_id}, error={result.error_code}: {result.message}"
            )
            message.status = "failed"
            message.last_error = f"{result.error_code}: {result.message}"
            message.save()
