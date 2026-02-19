"""
Django AppConfig para contrib/refs.
"""

from django.apps import AppConfig


class RefsConfig(AppConfig):
    name = "omniman.contrib.refs"
    label = "refs"
    verbose_name = "Omniman Refs"

    def ready(self):
        """Registra RefTypes padrão quando a app carrega."""
        from omniman.contrib.refs.registry import register_ref_type
        from omniman.contrib.refs.types import DEFAULT_REF_TYPES

        for ref_type in DEFAULT_REF_TYPES:
            try:
                register_ref_type(ref_type)
            except ValueError:
                # Já registrado (pode acontecer em reloads)
                pass
