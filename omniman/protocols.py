"""
Omniman Core Protocols — Interfaces para backends externos.

Este módulo define os protocols (interfaces) que backends devem implementar.
Os protocols vivem no core para que possam ser usados sem dependências circulares.

Implementações concretas vivem em contrib/:
- contrib/payment/adapters/ - Stripe, Pix, Mock
- contrib/stock/adapters/ - Stockman, etc.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


# =============================================================================
# Payment Protocols
# =============================================================================


@dataclass
class PaymentIntent:
    """Intenção de pagamento criada."""

    intent_id: str
    status: str  # "pending", "authorized", "requires_action", "captured", "failed"
    amount_q: int
    currency: str
    client_secret: str | None = None  # Para frontend (Stripe Elements, etc)
    expires_at: datetime | None = None
    metadata: dict | None = None


@dataclass
class CaptureResult:
    """Resultado de captura/autorização."""

    success: bool
    transaction_id: str | None = None
    amount_q: int | None = None
    error_code: str | None = None
    message: str | None = None


@dataclass
class RefundResult:
    """Resultado de reembolso."""

    success: bool
    refund_id: str | None = None
    amount_q: int | None = None
    error_code: str | None = None
    message: str | None = None


@dataclass
class PaymentStatus:
    """Status atual do pagamento."""

    intent_id: str
    status: str  # "pending", "authorized", "captured", "refunded", "failed", "cancelled"
    amount_q: int
    captured_q: int
    refunded_q: int
    currency: str
    metadata: dict | None = None


@runtime_checkable
class PaymentBackend(Protocol):
    """
    Protocol para backends de pagamento.

    Implementações devem fornecer métodos para:
    - Criar intenções de pagamento
    - Autorizar e capturar pagamentos
    - Processar reembolsos
    - Consultar status

    Implementações disponíveis:
    - omniman.contrib.payment.adapters.mock.MockPaymentBackend
    - omniman.contrib.payment.adapters.stripe.StripePaymentBackend
    - omniman.contrib.payment.adapters.pix.PixPaymentBackend
    """

    def create_intent(
        self,
        amount_q: int,
        currency: str,
        *,
        reference: str | None = None,
        metadata: dict | None = None,
    ) -> PaymentIntent:
        """
        Cria intenção de pagamento.

        Args:
            amount_q: Valor em centavos
            currency: Código ISO 4217 (ex: "BRL")
            reference: Referência externa (session_key ou order_ref)
            metadata: Dados adicionais

        Returns:
            PaymentIntent com ID e status
        """
        ...

    def authorize(
        self,
        intent_id: str,
        *,
        payment_method: str | None = None,
    ) -> CaptureResult:
        """
        Autoriza pagamento (não captura ainda).

        Args:
            intent_id: ID da intenção
            payment_method: Método de pagamento (token, card_id, etc)

        Returns:
            CaptureResult com status da autorização
        """
        ...

    def capture(
        self,
        intent_id: str,
        *,
        amount_q: int | None = None,
        reference: str | None = None,
    ) -> CaptureResult:
        """
        Captura pagamento autorizado.

        Args:
            intent_id: ID da intenção
            amount_q: Valor a capturar (None = total)
            reference: Referência do pedido (order_ref)

        Returns:
            CaptureResult com transaction_id
        """
        ...

    def refund(
        self,
        intent_id: str,
        *,
        amount_q: int | None = None,
        reason: str | None = None,
    ) -> RefundResult:
        """
        Processa reembolso.

        Args:
            intent_id: ID da intenção
            amount_q: Valor a reembolsar (None = total)
            reason: Motivo do reembolso

        Returns:
            RefundResult com refund_id
        """
        ...

    def cancel(self, intent_id: str) -> bool:
        """
        Cancela intenção não capturada.

        Returns:
            True se cancelado com sucesso
        """
        ...

    def get_status(self, intent_id: str) -> PaymentStatus:
        """
        Consulta status atual do pagamento.

        Returns:
            PaymentStatus com detalhes
        """
        ...
