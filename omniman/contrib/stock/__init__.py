"""
Omniman Stock Contrib — Verificação de disponibilidade e reserva de estoque.

Uso:
    from omniman.contrib.stock.protocols import StockBackend
    from omniman.contrib.stock.handlers import StockHoldHandler
    from omniman.contrib.stock.resolvers import StockIssueResolver

Para usar com Stockman:
    from omniman.contrib.stock.adapters.stockman import StockmanBackend
"""

from .protocols import StockBackend, AvailabilityResult, HoldResult, Alternative

__all__ = [
    "StockBackend",
    "AvailabilityResult",
    "HoldResult",
    "Alternative",
]








