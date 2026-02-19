REST API Reference
==================

Omniman provides a RESTful API built on Django REST Framework.


Base URL
--------

All API endpoints are relative to your configured API base URL:

.. code-block:: text

   http://localhost:8000/api/


Authentication
--------------

The API supports multiple authentication methods:

Session Authentication
~~~~~~~~~~~~~~~~~~~~~~

For browser-based clients using Django sessions:

.. code-block:: http

   GET /api/sessions/ HTTP/1.1
   Cookie: sessionid=xxx

Token Authentication
~~~~~~~~~~~~~~~~~~~~

For API clients using tokens:

.. code-block:: http

   GET /api/sessions/ HTTP/1.1
   Authorization: Token your-api-token

Configuration
~~~~~~~~~~~~~

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


Sessions API
------------

List Sessions
~~~~~~~~~~~~~

.. http:get:: /api/sessions/

   List all sessions.

   **Query Parameters:**

   - **channel_code** (*string*) -- Filter by channel code
   - **state** (*string*) -- Filter by state (open, committed, abandoned)
   - **handle_type** (*string*) -- Filter by owner type
   - **handle_ref** (*string*) -- Filter by owner reference

   **Example Request:**

   .. code-block:: http

      GET /api/sessions/?channel_code=pos&state=open HTTP/1.1
      Host: localhost:8000

   **Example Response:**

   .. code-block:: json

      [
          {
              "id": 1,
              "session_key": "SESS-ABC123",
              "channel_code": "pos",
              "state": "open",
              "handle_type": "table",
              "handle_ref": "5",
              "items": [],
              "total_q": 0,
              "rev": 0,
              "created_at": "2025-12-18T10:00:00Z"
          }
      ]

   :statuscode 200: Success
   :statuscode 401: Not authenticated


Create Session
~~~~~~~~~~~~~~

.. http:post:: /api/sessions/

   Create a new session.

   **Request Body:**

   .. code-block:: json

      {
          "channel_code": "pos",
          "handle_type": "table",
          "handle_ref": "5"
      }

   **Fields:**

   - **channel_code** (*string, required*) -- Channel code
   - **handle_type** (*string, optional*) -- Owner type identifier
   - **handle_ref** (*string, optional*) -- Owner reference

   **Example Response:**

   .. code-block:: json

      {
          "session_key": "SESS-ABC123XYZ",
          "channel_code": "pos",
          "state": "open",
          "items": [],
          "total_q": 0
      }

   :statuscode 201: Created
   :statuscode 400: Validation error
   :statuscode 401: Not authenticated


Get Session
~~~~~~~~~~~

.. http:get:: /api/sessions/(session_key)/

   Get session details.

   **Example Response:**

   .. code-block:: json

      {
          "session_key": "SESS-ABC123",
          "channel_code": "pos",
          "state": "open",
          "handle_type": "table",
          "handle_ref": "5",
          "items": [
              {
                  "line_id": "L-abc123",
                  "sku": "COFFEE",
                  "name": "Espresso",
                  "qty": 2,
                  "unit_price_q": 500,
                  "line_total_q": 1000
              }
          ],
          "total_q": 1000,
          "rev": 1,
          "data": {
              "checks": {},
              "issues": []
          }
      }

   :statuscode 200: Success
   :statuscode 404: Session not found


Modify Session
~~~~~~~~~~~~~~

.. http:post:: /api/sessions/(session_key)/modify/

   Modify session items.

   **Request Body:**

   .. code-block:: json

      {
          "channel_code": "pos",
          "ops": [
              {
                  "op": "add_line",
                  "sku": "COFFEE",
                  "name": "Espresso",
                  "qty": 2,
                  "unit_price_q": 500
              }
          ]
      }

   **Operations:**

   **add_line** - Add a new item:

   .. code-block:: json

      {
          "op": "add_line",
          "sku": "SKU001",
          "name": "Product Name",
          "qty": 1,
          "unit_price_q": 1000,
          "meta": {"notes": "Extra"}
      }

   **remove_line** - Remove an item:

   .. code-block:: json

      {
          "op": "remove_line",
          "line_id": "L-abc123"
      }

   **set_qty** - Update quantity:

   .. code-block:: json

      {
          "op": "set_qty",
          "line_id": "L-abc123",
          "qty": 3
      }

   **replace_sku** - Replace product:

   .. code-block:: json

      {
          "op": "replace_sku",
          "line_id": "L-abc123",
          "sku": "NEW-SKU",
          "unit_price_q": 1200
      }

   **set_data** - Set session data:

   .. code-block:: json

      {
          "op": "set_data",
          "path": "customer.name",
          "value": "John Doe"
      }

   **Example Response:**

   .. code-block:: json

      {
          "session_key": "SESS-ABC123",
          "state": "open",
          "items": [...],
          "total_q": 1000,
          "rev": 2
      }

   :statuscode 200: Success
   :statuscode 400: Validation error
   :statuscode 404: Session not found
   :statuscode 409: Session locked or committed


Commit Session
~~~~~~~~~~~~~~

.. http:post:: /api/sessions/(session_key)/commit/

   Commit session and create order.

   **Request Body:**

   .. code-block:: json

      {
          "channel_code": "pos",
          "idempotency_key": "COMMIT-ABC123"
      }

   **Fields:**

   - **channel_code** (*string, required*) -- Channel code
   - **idempotency_key** (*string, required*) -- Unique key for idempotency

   **Example Response (Success):**

   .. code-block:: json

      {
          "order_ref": "ORD-20251218-ABC123",
          "order_id": 42,
          "status": "committed",
          "total_q": 2500,
          "items_count": 3
      }

   **Example Response (Error):**

   .. code-block:: json

      {
          "error": {
              "code": "blocking_issues",
              "message": "Existem issues bloqueantes",
              "issues": [
                  {
                      "code": "insufficient_stock",
                      "sku": "COFFEE",
                      "message": "Only 2 units available"
                  }
              ]
          }
      }

   :statuscode 201: Order created
   :statuscode 400: Validation error
   :statuscode 409: Blocking issues or stale checks
   :statuscode 404: Session not found


Orders API
----------

List Orders
~~~~~~~~~~~

.. http:get:: /api/orders/

   List all orders.

   **Query Parameters:**

   - **channel_code** (*string*) -- Filter by channel
   - **status** (*string*) -- Filter by status
   - **created_after** (*datetime*) -- Filter by creation date
   - **created_before** (*datetime*) -- Filter by creation date

   **Example Response:**

   .. code-block:: json

      [
          {
              "ref": "ORD-20251218-ABC123",
              "channel_code": "pos",
              "status": "new",
              "total_q": 2500,
              "items_count": 3,
              "created_at": "2025-12-18T10:00:00Z"
          }
      ]


Get Order
~~~~~~~~~

.. http:get:: /api/orders/(ref)/

   Get order details.

   **Example Response:**

   .. code-block:: json

      {
          "ref": "ORD-20251218-ABC123",
          "channel_code": "pos",
          "status": "new",
          "handle_type": "table",
          "handle_ref": "5",
          "items": [
              {
                  "line_id": "L-abc123",
                  "sku": "COFFEE",
                  "name": "Espresso",
                  "qty": 2,
                  "unit_price_q": 500,
                  "line_total_q": 1000
              }
          ],
          "total_q": 2500,
          "events": [
              {
                  "type": "created",
                  "actor": "admin",
                  "created_at": "2025-12-18T10:00:00Z"
              }
          ],
          "created_at": "2025-12-18T10:00:00Z"
      }


Update Order Status
~~~~~~~~~~~~~~~~~~~

.. http:post:: /api/orders/(ref)/transition/

   Transition order status.

   **Request Body:**

   .. code-block:: json

      {
          "status": "confirmed",
          "actor": "admin@example.com"
      }

   **Example Response:**

   .. code-block:: json

      {
          "ref": "ORD-20251218-ABC123",
          "status": "confirmed",
          "previous_status": "new"
      }

   :statuscode 200: Success
   :statuscode 400: Invalid transition
   :statuscode 404: Order not found


Channels API
------------

List Channels
~~~~~~~~~~~~~

.. http:get:: /api/channels/

   List all active channels.

   **Example Response:**

   .. code-block:: json

      [
          {
              "code": "pos",
              "name": "POS POS",
              "pricing_policy": "internal",
              "is_active": true
          },
          {
              "code": "ecommerce",
              "name": "E-commerce",
              "pricing_policy": "external",
              "is_active": true
          }
      ]


Get Channel
~~~~~~~~~~~

.. http:get:: /api/channels/(code)/

   Get channel details.

   **Example Response:**

   .. code-block:: json

      {
          "code": "pos",
          "name": "POS POS",
          "pricing_policy": "internal",
          "edit_policy": "open",
          "config": {
              "order_flow": {
                  "initial_status": "new",
                  "transitions": {...}
              }
          },
          "is_active": true
      }


Error Responses
---------------

All error responses follow a consistent format:

.. code-block:: json

   {
       "error": {
           "code": "error_code",
           "message": "Human-readable message",
           "context": {
               "field": "additional context"
           }
       }
   }

Common Error Codes
~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1

   * - Code
     - Description
     - Status
   * - ``not_found``
     - Resource not found
     - 404
   * - ``validation_error``
     - Request validation failed
     - 400
   * - ``missing_field``
     - Required field missing
     - 400
   * - ``invalid_operation``
     - Invalid operation type
     - 400
   * - ``already_committed``
     - Session already committed
     - 409
   * - ``blocking_issues``
     - Issues prevent commit
     - 409
   * - ``stale_check``
     - Check is outdated
     - 409
   * - ``invalid_transition``
     - Status transition not allowed
     - 400


Pagination
----------

List endpoints support pagination:

.. code-block:: http

   GET /api/orders/?page=2&page_size=20 HTTP/1.1

Response includes pagination metadata:

.. code-block:: json

   {
       "count": 150,
       "next": "http://localhost:8000/api/orders/?page=3",
       "previous": "http://localhost:8000/api/orders/?page=1",
       "results": [...]
   }


Rate Limiting
-------------

API requests may be rate limited. Check response headers:

.. code-block:: http

   X-RateLimit-Limit: 100
   X-RateLimit-Remaining: 95
   X-RateLimit-Reset: 1703073600


See Also
--------

- :doc:`models` - Model reference
- :doc:`exceptions` - Exception reference
