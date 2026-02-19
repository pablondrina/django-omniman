"""
Django Omniman — Headless Omnichannel Order Hub para Django.

Uso básico:
    from omniman.models import Channel, Session, Order
    from omniman.services import ModifyService, CommitService
    from omniman import registry

Para extensões (contrib):
    from omniman.contrib.stock import StockBackend
    from omniman.contrib.pricing import PricingBackend
"""

__title__ = "Django Omniman"
__version__ = "0.1.0a1"
__author__ = "Pablo Valentini"
