Settings Reference
==================

This page documents all Omniman configuration settings.


Core Settings
-------------

OMNIMAN
~~~~~~~

Main configuration dictionary:

.. code-block:: python

   # settings.py

   OMNIMAN = {
       # Session settings
       "SESSION_KEY_PREFIX": "SESS-",
       "SESSION_KEY_LENGTH": 12,
       "SESSION_TTL_HOURS": 24,

       # Order settings
       "ORDER_REF_PREFIX": "ORD-",
       "ORDER_REF_DATE_FORMAT": "%Y%m%d",

       # ID generation
       "LINE_ID_PREFIX": "L-",
       "LINE_ID_LENGTH": 8,

       # Default channel
       "DEFAULT_CHANNEL": None,

       # Pricing
       "DEFAULT_PRICING_BACKEND": None,
       "PRICING_CACHE_TTL": 300,

       # Stock
       "DEFAULT_STOCK_BACKEND": None,
       "STOCK_HOLD_TTL_MINUTES": 15,
   }

SESSION_KEY_PREFIX
^^^^^^^^^^^^^^^^^^

Prefix for auto-generated session keys.

Default: ``"SESS-"``

.. code-block:: python

   OMNIMAN = {
       "SESSION_KEY_PREFIX": "BASKET-",  # Results in BASKET-ABC123
   }

SESSION_KEY_LENGTH
^^^^^^^^^^^^^^^^^^

Length of the random part of session keys.

Default: ``12``

SESSION_TTL_HOURS
^^^^^^^^^^^^^^^^^

Default time-to-live for sessions (hours).

Default: ``24``

ORDER_REF_PREFIX
^^^^^^^^^^^^^^^^

Prefix for order references.

Default: ``"ORD-"``

ORDER_REF_DATE_FORMAT
^^^^^^^^^^^^^^^^^^^^^

Date format in order references.

Default: ``"%Y%m%d"``

.. code-block:: python

   # Results in ORD-20251218-ABC123
   OMNIMAN = {
       "ORDER_REF_DATE_FORMAT": "%Y%m%d",
   }


Channel Configuration
---------------------

Channel.config
~~~~~~~~~~~~~~

JSON configuration for channels:

.. code-block:: python

   channel.config = {
       # Pricing
       "pricing_policy": "internal",  # internal, external
       "pricing_backend": "myapp.pricing.Backend",

       # Stock
       "check_stock_on_add": True,
       "stock_backend": "myapp.stock.Backend",

       # Checks
       "required_checks_on_commit": ["stock"],
       "checks": {
           "stock": {
               "directive_topic": "stock.hold",
               "hold_ttl_minutes": 15,
           },
       },

       # Post-commit
       "post_commit_directives": ["stock.commit"],

       # Order flow
       "order_flow": {
           "initial_status": "new",
           "transitions": {
               "new": ["confirmed", "cancelled"],
               "confirmed": ["completed"],
           },
           "terminal_statuses": ["completed", "cancelled"],
           "auto_transitions": {
               "on_stock_commit": "confirmed",
           },
       },

       # UI
       "terminology": {
           "session": "Atendimento",
           "order": "Pedido",
           "commit": "Finalizar",
       },
       "icon": "point_of_sale",
   }

pricing_policy
^^^^^^^^^^^^^^

How prices are determined:

- ``internal``: Prices from operation payload
- ``external``: Prices from PricingBackend

required_checks_on_commit
^^^^^^^^^^^^^^^^^^^^^^^^^

List of check codes required before commit.

.. code-block:: python

   "required_checks_on_commit": ["stock", "payment"],

post_commit_directives
^^^^^^^^^^^^^^^^^^^^^^

Directive topics to create after successful commit.

.. code-block:: python

   "post_commit_directives": ["stock.commit", "notification.email"],

order_flow
^^^^^^^^^^

Status state machine configuration:

.. code-block:: python

   "order_flow": {
       "initial_status": "new",
       "transitions": {
           "new": ["confirmed", "cancelled"],
           "confirmed": ["processing", "cancelled"],
           "processing": ["ready"],
           "ready": ["completed"],
       },
       "terminal_statuses": ["completed", "cancelled"],
       "auto_transitions": {
           "on_stock_commit": "confirmed",
           "on_payment_confirm": "confirmed",
       },
   }

terminology
^^^^^^^^^^^

Localized terms for UI:

.. code-block:: python

   "terminology": {
       "session": "Carrinho",
       "order": "Pedido",
       "commit": "Finalizar",
       "item": "Item",
   }


POS Settings
------------------

OMNIMAN_FRONTDESK
~~~~~~~~~~~~~~~~~

.. code-block:: python

   OMNIMAN_FRONTDESK = {
       "DEFAULT_CHANNEL": "pos",
       "AUTO_COMMIT_ON_EMPTY": False,
       "SHOW_PRICING_COLUMN": True,
       "SHOW_STOCK_COLUMN": True,
       "PRODUCT_AUTOCOMPLETE_LIMIT": 20,
   }


Stock Settings
--------------

OMNIMAN_STOCK
~~~~~~~~~~~~~

.. code-block:: python

   OMNIMAN_STOCK = {
       "BACKEND": "myapp.stock.StockBackend",
       "HOLD_TTL_MINUTES": 15,
       "RELEASE_EXPIRED_HOLDS_INTERVAL": 60,  # seconds
   }


Pricing Settings
----------------

OMNIMAN_PRICING
~~~~~~~~~~~~~~~

.. code-block:: python

   OMNIMAN_PRICING = {
       "DEFAULT_BACKEND": "myapp.pricing.PricingBackend",
       "CACHE_TTL": 300,
       "CACHE_PREFIX": "price:",
   }


Payment Settings
----------------

OMNIMAN_PAYMENT
~~~~~~~~~~~~~~~

.. code-block:: python

   OMNIMAN_PAYMENT = {
       "BACKENDS": {
           "stripe": {
               "class": "omniman.contrib.payment.adapters.stripe.StripeBackend",
               "config": {
                   "api_key": os.environ["STRIPE_SECRET_KEY"],
                   "webhook_secret": os.environ["STRIPE_WEBHOOK_SECRET"],
               },
           },
           "efi": {
               "class": "omniman.contrib.payment.adapters.efi.EfiBackend",
               "config": {
                   "client_id": os.environ["EFI_CLIENT_ID"],
                   "client_secret": os.environ["EFI_CLIENT_SECRET"],
               },
           },
       },
       "DEFAULT_BACKEND": "stripe",
   }


iFood Settings
--------------

OMNIMAN_IFOOD
~~~~~~~~~~~~~

.. code-block:: python

   OMNIMAN_IFOOD = {
       "CLIENT_ID": os.environ["IFOOD_CLIENT_ID"],
       "CLIENT_SECRET": os.environ["IFOOD_CLIENT_SECRET"],
       "MERCHANT_ID": os.environ["IFOOD_MERCHANT_ID"],
       "SANDBOX": True,
       "WEBHOOK_SECRET": os.environ["IFOOD_WEBHOOK_SECRET"],
   }


REST Framework Settings
-----------------------

Recommended DRF settings:

.. code-block:: python

   REST_FRAMEWORK = {
       "DEFAULT_AUTHENTICATION_CLASSES": [
           "rest_framework.authentication.SessionAuthentication",
           "rest_framework.authentication.TokenAuthentication",
       ],
       "DEFAULT_PERMISSION_CLASSES": [
           "rest_framework.permissions.IsAuthenticated",
       ],
       "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
       "PAGE_SIZE": 50,
       "DEFAULT_RENDERER_CLASSES": [
           "rest_framework.renderers.JSONRenderer",
       ],
       "EXCEPTION_HANDLER": "omniman.api.exception_handler",
   }


Environment Variables
---------------------

Recommended environment variables:

.. code-block:: bash

   # Django
   DJANGO_SECRET_KEY=your-secret-key
   DJANGO_DEBUG=false
   DJANGO_ALLOWED_HOSTS=api.example.com

   # Database
   DATABASE_URL=postgres://user:pass@host:5432/dbname

   # Redis
   REDIS_URL=redis://localhost:6379/0

   # Stripe
   STRIPE_SECRET_KEY=sk_live_xxx
   STRIPE_WEBHOOK_SECRET=whsec_xxx

   # iFood
   IFOOD_CLIENT_ID=xxx
   IFOOD_CLIENT_SECRET=xxx
   IFOOD_MERCHANT_ID=xxx

   # Sentry
   SENTRY_DSN=https://xxx@sentry.io/xxx


See Also
--------

- :doc:`../getting-started/installation` - Installation guide
- :doc:`../deployment/production` - Production deployment
