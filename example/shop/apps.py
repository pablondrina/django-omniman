from django.apps import AppConfig


class ShopConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "example.shop"
    verbose_name = "Shop (Example)"

    def ready(self):
        # Register pricing modifier when app is ready
        from omniman import registry
        from .pricing import SimplePricingModifier

        registry.register_modifier(SimplePricingModifier())
