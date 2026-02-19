"""
Omniman Stock Protocols — Interfaces para backends de estoque.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable


@dataclass
class AvailabilityResult:
    """Resultado de verificação de disponibilidade."""

    available: bool
    available_qty: Decimal
    message: str | None = None


@dataclass
class HoldResult:
    """Resultado de criação de reserva."""

    success: bool
    hold_id: str | None = None
    error_code: str | None = None
    message: str | None = None
    expires_at: datetime | None = None


@dataclass
class Alternative:
    """Produto alternativo sugerido."""

    sku: str
    name: str
    available_qty: Decimal


@runtime_checkable
class StockBackend(Protocol):
    """
    Protocol para backends de estoque.

    Implementações devem fornecer métodos para:
    - Verificar disponibilidade
    - Criar/liberar/confirmar reservas
    - Sugerir alternativas (opcional)
    """

    def check_availability(
        self,
        sku: str,
        quantity: Decimal,
        target_date: date | None = None,
    ) -> AvailabilityResult:
        """
        Verifica disponibilidade de um SKU.

        Args:
            sku: Código do produto
            quantity: Quantidade desejada
            target_date: Data alvo (opcional, para reservas futuras)

        Returns:
            AvailabilityResult com status de disponibilidade
        """
        ...

    def create_hold(
        self,
        sku: str,
        quantity: Decimal,
        expires_at: datetime | None = None,
        reference: str | None = None,
    ) -> HoldResult:
        """
        Cria uma reserva de estoque.

        Args:
            sku: Código do produto
            quantity: Quantidade a reservar
            expires_at: Quando a reserva expira (opcional)
            reference: Referência externa (ex.: session_key)

        Returns:
            HoldResult com status e ID da reserva
        """
        ...

    def release_hold(self, hold_id: str) -> None:
        """
        Libera uma reserva de estoque.

        Args:
            hold_id: ID da reserva a liberar
        """
        ...

    def fulfill_hold(self, hold_id: str, reference: str | None = None) -> None:
        """
        Confirma uma reserva (converte em saída de estoque).

        Args:
            hold_id: ID da reserva a confirmar
            reference: Referência do pedido (ex.: order_ref)
        """
        ...

    def get_alternatives(self, sku: str, quantity: Decimal) -> list[Alternative]:
        """
        Retorna produtos alternativos.

        Args:
            sku: SKU original
            quantity: Quantidade desejada

        Returns:
            Lista de alternativas disponíveis
        """
        ...

    def release_holds_for_reference(self, reference: str) -> int:
        """
        Libera todas as reservas associadas a uma referência (ex.: session_key).

        Usado para garantir idempotência: antes de criar novos holds,
        liberar os anteriores da mesma sessão.

        Args:
            reference: Referência das reservas (ex.: session_key)

        Returns:
            Número de reservas liberadas
        """
        ...







