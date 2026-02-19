Installation
============

This guide will help you install and configure Omniman in your Django project.


Requirements
------------

- Python 3.11 or higher
- Django 5.0 or higher
- Django REST Framework 3.15 or higher


Install from PyPI
-----------------

.. code-block:: bash

   pip install django-omniman

Or with optional dependencies:

.. code-block:: bash

   # With stock management
   pip install django-omniman[stock]

   # With payment integration
   pip install django-omniman[payment]

   # All extras
   pip install django-omniman[stock,payment,dev]


Install from Source
-------------------

.. code-block:: bash

   git clone https://github.com/your-org/omniman.git
   cd omniman
   pip install -e .


Configure Django Settings
-------------------------

Add Omniman to your ``INSTALLED_APPS``:

.. code-block:: python

   # settings.py

   INSTALLED_APPS = [
       # Django apps
       "django.contrib.admin",
       "django.contrib.auth",
       "django.contrib.contenttypes",
       "django.contrib.sessions",
       "django.contrib.messages",
       "django.contrib.staticfiles",

       # Third-party
       "unfold",  # Admin UI (optional but recommended)
       "unfold.contrib.filters",
       "rest_framework",

       # Omniman
       "omniman",
       # "omniman.contrib.stock",    # Optional: Stock management
       # "omniman.contrib.payment",  # Optional: Payment processing

       # Your apps
       "myapp",
   ]


Configure REST Framework
------------------------

.. code-block:: python

   # settings.py

   REST_FRAMEWORK = {
       "DEFAULT_AUTHENTICATION_CLASSES": [
           "rest_framework.authentication.SessionAuthentication",
           "rest_framework.authentication.TokenAuthentication",
       ],
       "DEFAULT_PERMISSION_CLASSES": [
           "rest_framework.permissions.IsAuthenticated",
       ],
   }


Run Migrations
--------------

.. code-block:: bash

   python manage.py migrate omniman


Configure URLs
--------------

Add Omniman URLs to your project:

.. code-block:: python

   # urls.py

   from django.urls import path, include

   urlpatterns = [
       path("admin/", admin.site.urls),
       path("api/", include("omniman.api.urls")),
   ]


Create Initial Data
-------------------

Create at least one Channel to start using Omniman:

.. code-block:: python

   python manage.py shell

   >>> from omniman.models import Channel
   >>> Channel.objects.create(
   ...     code="pos",
   ...     name="Point of Sale",
   ...     config={
   ...         "pricing_policy": "internal",
   ...         "order_flow": {
   ...             "initial_status": "created",
   ...             "transitions": {
   ...                 "created": ["confirmed", "cancelled"],
   ...                 "confirmed": ["completed", "cancelled"],
   ...             },
   ...         },
   ...     },
   ... )


Verify Installation
-------------------

Start the development server and access the admin:

.. code-block:: bash

   python manage.py runserver

Visit ``http://localhost:8000/admin/`` and you should see the Omniman models
(Channel, Session, Order, etc.) in the admin interface.


Next Steps
----------

- :doc:`quickstart` - Create your first session and order
- :doc:`tutorial` - Build a complete POS system
- :doc:`../guides/channels` - Learn about channel configuration
