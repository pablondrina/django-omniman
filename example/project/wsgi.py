"""
WSGI config for Omniman example project.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "example.project.settings")

application = get_wsgi_application()
