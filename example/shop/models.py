"""
Example Product model for demonstrating Omniman integration.

This is a minimal catalog implementation. In real projects, you would
have a more complete catalog with categories, images, variants, etc.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class Product(models.Model):
    """
    Simple product model for the example shop.

    In production, you would likely have:
    - Categories and tags
    - Multiple images
    - Variants (size, color)
    - Inventory tracking
    - etc.
    """

    sku = models.CharField(_("SKU"), max_length=64, unique=True)
    name = models.CharField(_("name"), max_length=200)
    description = models.TextField(_("description"), blank=True, default="")

    # Price in cents (or smallest currency unit)
    price_q = models.BigIntegerField(_("price (q)"), default=0)

    is_active = models.BooleanField(_("active"), default=True)

    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("product")
        verbose_name_plural = _("products")
        ordering = ("name",)

    def __str__(self) -> str:
        return f"{self.name} ({self.sku})"

    @property
    def price_display(self) -> str:
        """Returns formatted price for display."""
        return f"R$ {self.price_q / 100:.2f}"
