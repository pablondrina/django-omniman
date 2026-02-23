from __future__ import annotations

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class OmnimanConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "omniman"
    verbose_name = _("Central Omnicanal")









