Production Deployment
=====================

This guide covers deploying Omniman to production environments.


Pre-Deployment Checklist
------------------------

Before deploying to production:

.. code-block:: text

   [ ] DEBUG = False
   [ ] SECRET_KEY from environment variable
   [ ] ALLOWED_HOSTS configured
   [ ] Database properly configured
   [ ] Static files collected
   [ ] HTTPS enforced
   [ ] Logging configured
   [ ] Error monitoring setup
   [ ] Backup strategy defined


Django Settings
---------------

Security Settings
~~~~~~~~~~~~~~~~~

.. code-block:: python

   # settings/production.py

   import os

   DEBUG = False
   SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]

   ALLOWED_HOSTS = [
       "api.example.com",
       "www.example.com",
   ]

   # HTTPS
   SECURE_SSL_REDIRECT = True
   SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
   SESSION_COOKIE_SECURE = True
   CSRF_COOKIE_SECURE = True
   SECURE_HSTS_SECONDS = 31536000
   SECURE_HSTS_INCLUDE_SUBDOMAINS = True

   # Content Security
   SECURE_CONTENT_TYPE_NOSNIFF = True
   X_FRAME_OPTIONS = "DENY"

Database Configuration
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # PostgreSQL (recommended)
   DATABASES = {
       "default": {
           "ENGINE": "django.db.backends.postgresql",
           "NAME": os.environ["DB_NAME"],
           "USER": os.environ["DB_USER"],
           "PASSWORD": os.environ["DB_PASSWORD"],
           "HOST": os.environ["DB_HOST"],
           "PORT": os.environ.get("DB_PORT", "5432"),
           "CONN_MAX_AGE": 60,
           "OPTIONS": {
               "connect_timeout": 10,
           },
       }
   }

Cache Configuration
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Redis cache
   CACHES = {
       "default": {
           "BACKEND": "django.core.cache.backends.redis.RedisCache",
           "LOCATION": os.environ["REDIS_URL"],
           "OPTIONS": {
               "CLIENT_CLASS": "django_redis.client.DefaultClient",
           },
       }
   }

   # Session backend
   SESSION_ENGINE = "django.contrib.sessions.backends.cache"
   SESSION_CACHE_ALIAS = "default"

Static Files
~~~~~~~~~~~~

.. code-block:: python

   # Whitenoise for static files
   MIDDLEWARE = [
       "django.middleware.security.SecurityMiddleware",
       "whitenoise.middleware.WhiteNoiseMiddleware",
       # ... other middleware
   ]

   STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
   STATIC_ROOT = BASE_DIR / "staticfiles"


Logging Configuration
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   LOGGING = {
       "version": 1,
       "disable_existing_loggers": False,
       "formatters": {
           "verbose": {
               "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
               "style": "{",
           },
           "json": {
               "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
               "format": "%(levelname)s %(asctime)s %(module)s %(message)s",
           },
       },
       "handlers": {
           "console": {
               "class": "logging.StreamHandler",
               "formatter": "json",
           },
       },
       "root": {
           "handlers": ["console"],
           "level": "INFO",
       },
       "loggers": {
           "django": {
               "handlers": ["console"],
               "level": "INFO",
               "propagate": False,
           },
           "omniman": {
               "handlers": ["console"],
               "level": "INFO",
               "propagate": False,
           },
       },
   }


Web Server Setup
----------------

Gunicorn
~~~~~~~~

.. code-block:: bash

   # Install
   pip install gunicorn

   # Run
   gunicorn myproject.wsgi:application \
       --bind 0.0.0.0:8000 \
       --workers 4 \
       --threads 2 \
       --worker-class gthread \
       --timeout 30 \
       --access-logfile - \
       --error-logfile -

Gunicorn configuration file:

.. code-block:: python

   # gunicorn.conf.py

   import multiprocessing

   bind = "0.0.0.0:8000"
   workers = multiprocessing.cpu_count() * 2 + 1
   threads = 2
   worker_class = "gthread"
   timeout = 30
   keepalive = 5
   max_requests = 1000
   max_requests_jitter = 100

   # Logging
   accesslog = "-"
   errorlog = "-"
   loglevel = "info"

   # Security
   limit_request_line = 4094
   limit_request_fields = 100

Nginx Configuration
~~~~~~~~~~~~~~~~~~~

.. code-block:: nginx

   # /etc/nginx/sites-available/omniman

   upstream omniman {
       server 127.0.0.1:8000;
       keepalive 32;
   }

   server {
       listen 80;
       server_name api.example.com;
       return 301 https://$server_name$request_uri;
   }

   server {
       listen 443 ssl http2;
       server_name api.example.com;

       ssl_certificate /etc/letsencrypt/live/api.example.com/fullchain.pem;
       ssl_certificate_key /etc/letsencrypt/live/api.example.com/privkey.pem;
       ssl_protocols TLSv1.2 TLSv1.3;
       ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
       ssl_prefer_server_ciphers off;

       location /static/ {
           alias /var/www/omniman/staticfiles/;
           expires 30d;
           add_header Cache-Control "public, immutable";
       }

       location / {
           proxy_pass http://omniman;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;

           proxy_connect_timeout 30s;
           proxy_read_timeout 30s;
           proxy_send_timeout 30s;
       }
   }


Database Migrations
-------------------

.. code-block:: bash

   # Run migrations
   python manage.py migrate --noinput

   # Create superuser (first deployment)
   python manage.py createsuperuser

   # Collect static files
   python manage.py collectstatic --noinput


Environment Variables
---------------------

.. code-block:: bash

   # .env.production

   # Django
   DJANGO_SETTINGS_MODULE=myproject.settings.production
   DJANGO_SECRET_KEY=your-secret-key-here
   DEBUG=false

   # Database
   DB_NAME=omniman
   DB_USER=omniman
   DB_PASSWORD=secure-password
   DB_HOST=db.example.com
   DB_PORT=5432

   # Redis
   REDIS_URL=redis://redis.example.com:6379/0

   # Email
   EMAIL_HOST=smtp.example.com
   EMAIL_PORT=587
   EMAIL_HOST_USER=noreply@example.com
   EMAIL_HOST_PASSWORD=email-password

   # Integrations
   STRIPE_SECRET_KEY=sk_live_xxx
   STRIPE_WEBHOOK_SECRET=whsec_xxx
   IFOOD_CLIENT_ID=xxx
   IFOOD_CLIENT_SECRET=xxx


Monitoring
----------

Health Check Endpoint
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # views.py

   from django.http import JsonResponse
   from django.db import connection

   def health_check(request):
       """Health check endpoint for load balancers."""
       try:
           # Check database
           with connection.cursor() as cursor:
               cursor.execute("SELECT 1")

           return JsonResponse({
               "status": "healthy",
               "database": "ok",
           })
       except Exception as e:
           return JsonResponse({
               "status": "unhealthy",
               "error": str(e),
           }, status=503)

   # urls.py
   urlpatterns = [
       path("health/", health_check, name="health-check"),
   ]

Sentry Integration
~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # settings/production.py

   import sentry_sdk
   from sentry_sdk.integrations.django import DjangoIntegration

   sentry_sdk.init(
       dsn=os.environ["SENTRY_DSN"],
       integrations=[DjangoIntegration()],
       traces_sample_rate=0.1,
       send_default_pii=False,
       environment="production",
   )

Prometheus Metrics
~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Install django-prometheus
   pip install django-prometheus

   # settings.py
   INSTALLED_APPS = [
       # ...
       "django_prometheus",
   ]

   MIDDLEWARE = [
       "django_prometheus.middleware.PrometheusBeforeMiddleware",
       # ... other middleware
       "django_prometheus.middleware.PrometheusAfterMiddleware",
   ]

   # urls.py
   urlpatterns = [
       path("", include("django_prometheus.urls")),
   ]


Backup Strategy
---------------

Database Backup
~~~~~~~~~~~~~~~

.. code-block:: bash

   # PostgreSQL backup script
   #!/bin/bash

   DATE=$(date +%Y%m%d_%H%M%S)
   BACKUP_DIR=/backups/postgresql
   FILENAME="${BACKUP_DIR}/omniman_${DATE}.sql.gz"

   pg_dump -h $DB_HOST -U $DB_USER $DB_NAME | gzip > $FILENAME

   # Keep last 7 days
   find $BACKUP_DIR -name "*.sql.gz" -mtime +7 -delete

   # Upload to S3
   aws s3 cp $FILENAME s3://my-backups/omniman/

Automated Backup Schedule
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   # /etc/cron.d/omniman-backup

   # Daily backup at 2 AM
   0 2 * * * root /opt/omniman/scripts/backup.sh

   # Hourly backup of recent data
   0 * * * * root /opt/omniman/scripts/incremental-backup.sh


Scaling Considerations
----------------------

Horizontal Scaling
~~~~~~~~~~~~~~~~~~

.. code-block:: text

   Load Balancer
        │
        ├── Web Server 1 (Gunicorn)
        ├── Web Server 2 (Gunicorn)
        └── Web Server 3 (Gunicorn)
                │
                ├── PostgreSQL (Primary)
                │       └── PostgreSQL (Replica)
                │
                └── Redis Cluster


Session Affinity
~~~~~~~~~~~~~~~~

For webhook processing, ensure session affinity or use distributed locking:

.. code-block:: python

   from django.core.cache import cache

   def process_webhook_with_lock(order_id, payload):
       lock_key = f"webhook_lock:{order_id}"

       # Acquire lock
       if not cache.add(lock_key, "1", timeout=30):
           return  # Another worker processing

       try:
           process_webhook(order_id, payload)
       finally:
           cache.delete(lock_key)


See Also
--------

- :doc:`docker` - Docker deployment
- :doc:`performance` - Performance optimization
- :doc:`../reference/settings` - Settings reference
