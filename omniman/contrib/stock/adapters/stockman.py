"""
Omniman Stockman Adapter — Adapter para integração com Stockman.

Stockman é uma biblioteca Django para gerenciamento de estoque.
Este adapter conecta o contrib/stock ao Stockman.

API do Stockman (convenção: quantity, product, target_date, ...):
- stock.available(product, target_date) -> Decimal
- stock.hold(quantity, product, target_date, purpose, expires_at, **metadata) -> str (hold_id)
- stock.confirm(hold_id) -> Hold
- stock.release(hold_id, reason) -> Hold
- stock.fulfill(hold_id, reference, user) -> Move
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable

from django.core.exceptions import ObjectDoesNotExist

from omniman.contrib.stock.protocols import (
    Alternative,
    AvailabilityResult,
    HoldResult,
    StockBackend,
)

logger = logging.getLogger(__name__)


def _stockman_available() -> bool:
    """Check if Stockman is installed."""
    try:
        from stockman import stock
        return True
    except ImportError:
        return False


class StockmanBackend:
    """
    Adapter que conecta contrib/stock ao Stockman.

    Uso:
        from omniman.contrib.stock.adapters.stockman import StockmanBackend
        from offerman.models import Product

        def get_product(sku: str):
            return Product.objects.get(sku=sku)

        backend = StockmanBackend(product_resolver=get_product)

    O Stockman usa a seguinte API:
    - stock.hold(quantity, product, target_date, ...) -> hold_id (str "hold:{pk}")
    - stock.release(hold_id, reason) -> Hold
    - stock.confirm(hold_id) -> Hold
    - stock.fulfill(hold_id, reference) -> Move
    """

    def __init__(self, product_resolver: Callable[[str], Any]):
        """
        Inicializa o adapter.

        Args:
            product_resolver: Função que recebe SKU e retorna objeto produto
                             (deve ser compatível com Stockman)
        """
        self.get_product = product_resolver

    def check_availability(
        self,
        sku: str,
        quantity: Decimal,
        target_date: date | None = None,
    ) -> AvailabilityResult:
        """
        Verifica disponibilidade usando Stockman.

        Requer que o produto tenha campo gerenciado pelo Stockman.
        """
        if not _stockman_available():
            raise ImportError(
                "Stockman não está instalado. "
                "Instale com: pip install django-stockman"
            )

        from stockman.service import Stock as stock

        try:
            product = self.get_product(sku)
        except ObjectDoesNotExist:
            return AvailabilityResult(
                available=False,
                available_qty=Decimal("0"),
                message=f"Produto não encontrado: {sku}",
            )
        except Exception:
            logger.exception("Unexpected error checking availability for %s", sku)
            raise

        available = stock.available(product, target_date=target_date)

        return AvailabilityResult(
            available=quantity <= available,
            available_qty=Decimal(str(available)),
            message=None if quantity <= available else f"Disponível: {available}",
        )

    def create_hold(
        self,
        sku: str,
        quantity: Decimal,
        expires_at: datetime | None = None,
        reference: str | None = None,
    ) -> HoldResult:
        """
        Cria reserva usando Stockman.

        O Stockman aceita:
        - stock.hold(quantity, product, target_date, purpose, expires_at, **metadata)
        - Retorna hold_id no formato "hold:{pk}"
        """
        if not _stockman_available():
            return HoldResult(
                success=False,
                error_code="stockman_not_installed",
                message="Stockman não está instalado",
            )

        from stockman.service import Stock as stock
        from stockman.exceptions import StockError

        try:
            product = self.get_product(sku)
        except ObjectDoesNotExist:
            return HoldResult(
                success=False,
                error_code="product_not_found",
                message=f"Produto não encontrado: {sku}",
            )
        except Exception:
            logger.exception("Unexpected error resolving product for hold on %s", sku)
            raise

        try:
            # Stockman API: stock.hold(quantity, product, target_date, purpose, expires_at, **metadata)
            # Armazena reference no metadata para busca posterior
            hold_id = stock.hold(
                quantity,
                product,
                target_date=date.today(),  # Default to today if not specified
                expires_at=expires_at,
                reference=reference,  # Será armazenado em metadata
            )

            # Buscar o hold para obter expires_at
            from stockman.models import Hold
            pk = int(hold_id.split(":")[1])
            hold = Hold.objects.get(pk=pk)

            return HoldResult(
                success=True,
                hold_id=hold_id,
                expires_at=hold.expires_at,
            )
        except StockError as e:
            return HoldResult(
                success=False,
                error_code=e.code if hasattr(e, "code") else "hold_failed",
                message=str(e),
            )
        except Exception as e:
            return HoldResult(
                success=False,
                error_code="hold_failed",
                message=str(e),
            )

    def release_hold(self, hold_id: str) -> None:
        """
        Libera reserva usando Stockman.

        Stockman API: stock.release(hold_id, reason) -> Hold
        """
        if not _stockman_available():
            logger.warning("release_hold: Stockman not installed, cannot release hold %s", hold_id)
            return

        from stockman.service import Stock as stock
        from stockman.exceptions import StockError

        try:
            stock.release(hold_id, reason="Liberado via Omniman")
        except StockError as e:
            # INVALID_HOLD ou INVALID_STATUS são esperados se já liberado
            logger.debug("release_hold: Hold %s already released or invalid: %s", hold_id, e)
        except Exception as e:
            logger.warning("release_hold: Failed to release hold %s: %s", hold_id, e)

    def fulfill_hold(self, hold_id: str, reference: str | None = None) -> None:
        """
        Confirma reserva usando Stockman.

        Pipeline:
        1. Confirm (PENDING -> CONFIRMED) se ainda pending
        2. Fulfill (CONFIRMED -> FULFILLED) criando Move de saída

        Idempotência:
        - Hold já FULFILLED → silencioso (sucesso, não levanta exceção)
        - Hold não encontrado → levanta exceção
        - Hold em status inválido (RELEASED) → levanta exceção

        Stockman API:
        - stock.confirm(hold_id) -> Hold
        - stock.fulfill(hold_id, reference, user) -> Move
        """
        if not _stockman_available():
            raise ImportError("Stockman não está instalado. Instale com: pip install django-stockman")

        from stockman.service import Stock as stock
        from stockman.models import Hold
        from stockman.models.enums import HoldStatus
        from stockman.exceptions import StockError

        # Buscar hold para verificar status
        pk = int(hold_id.split(":")[1])
        try:
            hold = Hold.objects.get(pk=pk)
        except Hold.DoesNotExist:
            raise StockError("HOLD_NOT_FOUND", hold_id=hold_id) from None

        # Já fulfillado — idempotente
        if hold.status == HoldStatus.FULFILLED:
            logger.debug("fulfill_hold: hold %s already fulfilled, skipping.", hold_id)
            return

        # Se ainda PENDING, confirmar primeiro
        if hold.status == HoldStatus.PENDING:
            try:
                stock.confirm(hold_id)
            except StockError:
                # Pode ter sido confirmado por outra thread entre o check e o confirm.
                # Refresh e continua.
                hold.refresh_from_db()
                if hold.status not in (HoldStatus.CONFIRMED, HoldStatus.FULFILLED):
                    raise

        # Fulfill — falhas aqui propagam para o handler decidir retry
        stock.fulfill(hold_id, reference=reference)

    def get_alternatives(self, sku: str, quantity: Decimal) -> list[Alternative]:
        """
        Busca alternativas (não implementado por padrão).

        Override este método para implementar lógica de alternativas
        baseada em categorias, tags, etc.
        """
        return []

    def release_holds_for_reference(self, reference: str) -> int:
        """
        Libera todas as reservas associadas a uma referência (ex.: session_key).

        Usado para garantir idempotência: antes de criar novos holds,
        liberar os anteriores da mesma sessão.

        O Stockman armazena reference no campo metadata (não há campo reference direto).
        Buscamos holds por metadata__reference.

        Args:
            reference: Referência das reservas (ex.: session_key)

        Returns:
            Número de reservas liberadas
        """
        if not _stockman_available():
            logger.warning("release_holds_for_reference: Stockman not installed")
            return 0

        from stockman.service import Stock as stock
        from stockman.models import Hold
        from stockman.models.enums import HoldStatus
        from stockman.exceptions import StockError

        try:
            # Buscar holds ativos com esta referência no metadata
            holds = Hold.objects.filter(
                status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED],
                metadata__reference=reference,
            )
            count = 0
            for hold in holds:
                try:
                    stock.release(hold.hold_id, reason="Idempotency cleanup")
                    count += 1
                except StockError:
                    pass  # Já liberado
                except Exception as e:
                    logger.warning(
                        "release_holds_for_reference: Failed to release hold %s: %s",
                        hold.hold_id, e
                    )
            return count
        except Exception as e:
            logger.warning("release_holds_for_reference: Failed for reference %s: %s", reference, e)
            return 0







