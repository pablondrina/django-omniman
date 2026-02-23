from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class Fulfillment(models.Model):
    """
    Fulfillment de um pedido (ou parte dele).

    Um pedido pode ter múltiplos fulfillments:
    - Split shipping (2 pacotes separados)
    - Partial fulfillment (parte dos itens pronta antes)
    - Multi-source (itens de estoques/locais diferentes)

    Lifecycle: pending → in_progress → shipped → delivered (ou cancelled)
    """

    class Status(models.TextChoices):
        PENDING = "pending", _("pendente")
        IN_PROGRESS = "in_progress", _("em andamento")
        SHIPPED = "shipped", _("enviado")
        DELIVERED = "delivered", _("entregue")
        CANCELLED = "cancelled", _("cancelado")

    order = models.ForeignKey(
        "omniman.Order",
        verbose_name=_("pedido"),
        on_delete=models.CASCADE,
        related_name="fulfillments",
    )

    status = models.CharField(
        _("status"),
        max_length=32,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    tracking_code = models.CharField(_("código de rastreio"), max_length=128, blank=True, default="")
    tracking_url = models.URLField(_("URL de rastreio"), blank=True, default="")
    carrier = models.CharField(_("transportadora"), max_length=64, blank=True, default="")
    notes = models.TextField(_("observações"), blank=True, default="")
    meta = models.JSONField(_("metadados"), default=dict, blank=True)

    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)
    updated_at = models.DateTimeField(_("atualizado em"), auto_now=True)
    shipped_at = models.DateTimeField(_("enviado em"), null=True, blank=True)
    delivered_at = models.DateTimeField(_("entregue em"), null=True, blank=True)

    class Meta:
        app_label = "omniman"
        verbose_name = _("fulfillment")
        verbose_name_plural = _("fulfillments")
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"Fulfillment #{self.pk} ({self.get_status_display()})"


class FulfillmentItem(models.Model):
    """
    Item incluído em um fulfillment.

    Permite fulfillment parcial: nem todos os itens do pedido
    precisam estar no mesmo fulfillment.
    """

    fulfillment = models.ForeignKey(
        Fulfillment,
        verbose_name=_("fulfillment"),
        on_delete=models.CASCADE,
        related_name="items",
    )
    order_item = models.ForeignKey(
        "omniman.OrderItem",
        verbose_name=_("item do pedido"),
        on_delete=models.CASCADE,
        related_name="fulfillment_items",
    )
    qty = models.DecimalField(_("quantidade"), max_digits=12, decimal_places=3)

    class Meta:
        app_label = "omniman"
        verbose_name = _("item do fulfillment")
        verbose_name_plural = _("itens do fulfillment")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(qty__gt=0),
                name="fulfillment_item_qty_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.order_item.sku} x {self.qty}"
