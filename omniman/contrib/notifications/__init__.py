"""
Omniman Notifications — Sistema simples e plugável de notificações.

Uso básico:
    from omniman.contrib.notifications import notify

    # Envia notificação usando backend configurado
    notify(
        event="order.confirmed",
        recipient="customer@email.com",
        context={"order_ref": "ORD-123", "total": "R$ 50,00"},
    )

Backends disponíveis:
    - console: Log no console (desenvolvimento)
    - webhook: HTTP POST para qualquer URL (integra com Zapier, n8n, Make, etc)
    - email: Email via Django
    - whatsapp: WhatsApp via API (Twilio, Meta, etc)
    - sms: SMS via API (Twilio, etc)

Configuração via settings.py:
    OMNIMAN_NOTIFICATIONS = {
        "default_backend": "webhook",
        "backends": {
            "webhook": {
                "class": "omniman.contrib.notifications.backends.WebhookBackend",
                "url": "https://hooks.zapier.com/xxx",
            },
            "whatsapp": {
                "class": "omniman.contrib.notifications.backends.WhatsAppBackend",
                "api_url": "https://graph.facebook.com/v17.0/xxx/messages",
                "token": "xxx",
            },
        },
    }

Ou via Channel.config (por canal):
    channel.config = {
        "notifications": {
            "backend": "whatsapp",
            "on_events": ["order.confirmed", "order.ready"],
        }
    }
"""

from .service import notify, get_backend, register_backend
from .protocols import NotificationBackend, NotificationResult

__all__ = [
    "notify",
    "get_backend",
    "register_backend",
    "NotificationBackend",
    "NotificationResult",
]
