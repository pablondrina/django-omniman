"""
Omniman Customer Protocols — Interfaces para backends de clientes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class AddressInfo:
    """Address information."""

    label: str
    formatted_address: str
    short_address: str
    complement: str | None = None
    delivery_instructions: str | None = None
    latitude: float | None = None
    longitude: float | None = None


@dataclass
class CustomerInfo:
    """Complete customer information for Session/Order."""

    code: str
    name: str
    customer_type: str = "individual"  # "individual" | "business"
    group_code: str | None = None
    price_list_code: str | None = None
    phone: str | None = None
    email: str | None = None
    default_address: AddressInfo | None = None
    total_orders: int = 0
    is_vip: bool = False
    is_at_risk: bool = False
    favorite_products: list[str] = field(default_factory=list)


@dataclass
class CustomerContext:
    """Complete context for personalization (LLM, greetings, etc.)."""

    info: CustomerInfo
    preferences: dict  # {category: {key: value}}
    recent_orders: list[dict] = field(default_factory=list)
    rfm_segment: str | None = None
    days_since_last_order: int | None = None
    recommended_products: list[str] = field(default_factory=list)


@dataclass
class CustomerValidationResult:
    """Customer validation result."""

    valid: bool
    code: str
    info: CustomerInfo | None = None
    error_code: str | None = None
    message: str | None = None


@runtime_checkable
class CustomerBackend(Protocol):
    """
    Protocol para backends de clientes.

    Implementações devem fornecer métodos para:
    - Buscar informações de cliente
    - Validar se cliente pode operar
    - Obter contexto para personalização
    - Registrar pedidos no histórico
    """

    def get_customer(self, code: str) -> CustomerInfo | None:
        """Get customer information by code."""
        ...

    def validate_customer(self, code: str) -> CustomerValidationResult:
        """Validate if customer can operate."""
        ...

    def get_price_list_code(self, customer_code: str) -> str | None:
        """Return applicable PriceList code for customer."""
        ...

    def get_customer_context(self, code: str) -> CustomerContext | None:
        """Return complete customer context for personalization."""
        ...

    def record_order(self, customer_code: str, order_data: dict) -> bool:
        """Record order in customer history."""
        ...
