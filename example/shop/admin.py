"""
Admin configuration for example shop.
"""

from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Product


@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = ("sku", "name", "price_display", "is_active")
    list_filter = ("is_active",)
    search_fields = ("sku", "name")
    ordering = ("name",)

    fieldsets = (
        (None, {"fields": ("sku", "name", "description")}),
        ("Pricing", {"fields": ("price_q",)}),
        ("Status", {"fields": ("is_active",)}),
    )

    def price_display(self, obj):
        return obj.price_display

    price_display.short_description = "Price"
