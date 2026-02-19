Performance Optimization
========================

This guide covers performance optimization for Omniman deployments.


Database Optimization
---------------------

Indexes
~~~~~~~

Ensure proper indexes for common queries:

.. code-block:: python

   # Custom indexes in models
   class Session(models.Model):
       class Meta:
           indexes = [
               models.Index(fields=["channel", "state"]),
               models.Index(fields=["handle_type", "handle_ref"]),
               models.Index(fields=["created_at"]),
           ]

   class Order(models.Model):
       class Meta:
           indexes = [
               models.Index(fields=["channel", "status"]),
               models.Index(fields=["created_at"]),
               models.Index(fields=["external_ref"]),
           ]

Query Optimization
~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Bad: N+1 queries
   sessions = Session.objects.filter(state="open")
   for session in sessions:
       print(session.channel.name)  # Query per session

   # Good: Select related
   sessions = Session.objects.filter(state="open").select_related("channel")
   for session in sessions:
       print(session.channel.name)  # No additional queries

   # Prefetch related items
   orders = Order.objects.prefetch_related("items", "events")

Connection Pooling
~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # settings.py

   DATABASES = {
       "default": {
           "ENGINE": "django.db.backends.postgresql",
           # ...
           "CONN_MAX_AGE": 60,  # Keep connections alive
           "CONN_HEALTH_CHECKS": True,  # Django 4.1+
       }
   }

   # For high traffic, use PgBouncer
   # DATABASES["default"]["HOST"] = "pgbouncer"


Caching Strategy
----------------

Session Caching
~~~~~~~~~~~~~~~

.. code-block:: python

   from django.core.cache import cache

   def get_session_with_cache(session_key, channel_code):
       cache_key = f"session:{channel_code}:{session_key}"
       session_data = cache.get(cache_key)

       if session_data is None:
           session = Session.objects.select_related("channel").get(
               session_key=session_key,
               channel__code=channel_code,
           )
           session_data = {
               "id": session.id,
               "items": session.items,
               "rev": session.rev,
               "data": session.data,
           }
           cache.set(cache_key, session_data, timeout=300)

       return session_data

   def invalidate_session_cache(session_key, channel_code):
       cache_key = f"session:{channel_code}:{session_key}"
       cache.delete(cache_key)

Channel Caching
~~~~~~~~~~~~~~~

.. code-block:: python

   from functools import lru_cache
   from django.core.cache import cache

   def get_channel_cached(channel_code):
       cache_key = f"channel:{channel_code}"
       channel_data = cache.get(cache_key)

       if channel_data is None:
           channel = Channel.objects.get(code=channel_code)
           channel_data = {
               "id": channel.id,
               "code": channel.code,
               "config": channel.config,
               "pricing_policy": channel.pricing_policy,
           }
           cache.set(cache_key, channel_data, timeout=3600)

       return channel_data

Response Caching
~~~~~~~~~~~~~~~~

.. code-block:: python

   from django.views.decorators.cache import cache_page
   from django.utils.decorators import method_decorator
   from rest_framework.views import APIView

   class ChannelListView(APIView):
       @method_decorator(cache_page(60 * 15))  # 15 minutes
       def get(self, request):
           channels = Channel.objects.filter(is_active=True)
           return Response(...)


API Optimization
----------------

Pagination
~~~~~~~~~~

.. code-block:: python

   # settings.py

   REST_FRAMEWORK = {
       "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.CursorPagination",
       "PAGE_SIZE": 50,
   }

   # Custom pagination
   class OrderPagination(CursorPagination):
       page_size = 50
       ordering = "-created_at"
       cursor_query_param = "cursor"

Selective Serialization
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   class SessionSerializer(serializers.ModelSerializer):
       class Meta:
           model = Session
           fields = ["session_key", "state", "total_q"]

   class SessionDetailSerializer(serializers.ModelSerializer):
       items = serializers.SerializerMethodField()

       class Meta:
           model = Session
           fields = ["session_key", "state", "items", "data", "rev"]

   class SessionViewSet(viewsets.ModelViewSet):
       def get_serializer_class(self):
           if self.action == "list":
               return SessionSerializer
           return SessionDetailSerializer

Conditional Requests
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from rest_framework.decorators import api_view
   from django.http import HttpResponseNotModified

   @api_view(["GET"])
   def get_session(request, session_key):
       session = Session.objects.get(session_key=session_key)

       # ETag based on revision
       etag = f'"{session.rev}"'

       if request.META.get("HTTP_IF_NONE_MATCH") == etag:
           return HttpResponseNotModified()

       response = Response(SessionSerializer(session).data)
       response["ETag"] = etag
       return response


Async Processing
----------------

Directive Queue
~~~~~~~~~~~~~~~

Use a task queue for directive processing:

.. code-block:: python

   # Using Celery
   from celery import shared_task
   from omniman.models import Directive
   from omniman.registry import registry

   @shared_task
   def process_directive(directive_id):
       directive = Directive.objects.get(id=directive_id)

       if directive.status != "queued":
           return

       directive.status = "running"
       directive.save()

       handler = registry.get_handler(directive.topic)
       if handler:
           try:
               result = handler.handle(directive, {})
               directive.status = "done"
               directive.result = result
           except Exception as e:
               directive.status = "failed"
               directive.last_error = str(e)
       else:
           directive.status = "failed"
           directive.last_error = f"No handler for {directive.topic}"

       directive.save()

   # Trigger on directive creation
   from django.db.models.signals import post_save
   from django.dispatch import receiver

   @receiver(post_save, sender=Directive)
   def queue_directive(sender, instance, created, **kwargs):
       if created and instance.status == "queued":
           process_directive.delay(instance.id)


Bulk Operations
---------------

Bulk Create
~~~~~~~~~~~

.. code-block:: python

   # Bad: Individual creates
   for item in items:
       OrderItem.objects.create(order=order, **item)

   # Good: Bulk create
   order_items = [
       OrderItem(order=order, **item)
       for item in items
   ]
   OrderItem.objects.bulk_create(order_items)

Bulk Update
~~~~~~~~~~~

.. code-block:: python

   # Update all pending directives
   Directive.objects.filter(status="queued").update(
       status="running",
       updated_at=timezone.now(),
   )


Load Testing
------------

Locust Configuration
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # locustfile.py

   from locust import HttpUser, task, between

   class OmnimanUser(HttpUser):
       wait_time = between(1, 3)

       @task(3)
       def create_session(self):
           self.client.post("/api/sessions/", json={
               "channel_code": "pos",
           })

       @task(5)
       def modify_session(self):
           self.client.post("/api/sessions/SESS-001/modify/", json={
               "channel_code": "pos",
               "ops": [
                   {"op": "add_line", "sku": "COFFEE", "qty": 1, "unit_price_q": 500},
               ],
           })

       @task(2)
       def commit_session(self):
           self.client.post("/api/sessions/SESS-001/commit/", json={
               "channel_code": "pos",
               "idempotency_key": f"COMMIT-{time.time()}",
           })

Run Load Test
~~~~~~~~~~~~~

.. code-block:: bash

   # Install locust
   pip install locust

   # Run test
   locust -f locustfile.py --host=http://localhost:8000

   # Headless mode
   locust -f locustfile.py \
       --host=http://localhost:8000 \
       --users 100 \
       --spawn-rate 10 \
       --run-time 5m \
       --headless


Monitoring Performance
----------------------

Django Debug Toolbar (Development)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # settings/development.py

   INSTALLED_APPS += ["debug_toolbar"]
   MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]
   INTERNAL_IPS = ["127.0.0.1"]

Silk Profiler
~~~~~~~~~~~~~

.. code-block:: python

   # settings.py

   INSTALLED_APPS += ["silk"]
   MIDDLEWARE += ["silk.middleware.SilkyMiddleware"]

   SILKY_PYTHON_PROFILER = True
   SILKY_PYTHON_PROFILER_BINARY = True
   SILKY_MAX_RECORDED_REQUESTS = 1000

Database Query Logging
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # settings.py

   LOGGING = {
       "loggers": {
           "django.db.backends": {
               "level": "DEBUG",
               "handlers": ["console"],
           },
       },
   }


Best Practices Summary
----------------------

1. **Database**

   - Use ``select_related`` and ``prefetch_related``
   - Add indexes for common query patterns
   - Use connection pooling

2. **Caching**

   - Cache frequently accessed data
   - Invalidate cache on updates
   - Use appropriate TTLs

3. **API**

   - Paginate large result sets
   - Use cursor pagination for large datasets
   - Support conditional requests (ETags)

4. **Async**

   - Process directives asynchronously
   - Use task queues (Celery, RQ)
   - Batch operations when possible

5. **Monitoring**

   - Profile queries in development
   - Monitor response times in production
   - Set up alerts for slow queries


See Also
--------

- :doc:`production` - Production deployment
- :doc:`docker` - Docker deployment
