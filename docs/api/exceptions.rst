Exceptions Reference
====================

Omniman defines specific exceptions for different error scenarios.


OmnimanError
------------

.. py:exception:: omniman.exceptions.OmnimanError

   Base class for all Omniman exceptions.

   All Omniman exceptions inherit from this class.


ValidationError
---------------

.. py:exception:: omniman.exceptions.ValidationError(code, message, context=None)

   Raised when validation fails.

   :param code: Machine-readable error code
   :param message: Human-readable message
   :param context: Additional error data

   **Attributes:**

   .. py:attribute:: code
      :type: str

      Error code (e.g., "missing_sku", "invalid_qty").

   .. py:attribute:: message
      :type: str

      Human-readable error message.

   .. py:attribute:: context
      :type: dict

      Additional context data.

   **Common Codes:**

   - ``missing_sku``: SKU is required
   - ``invalid_qty``: Quantity must be > 0
   - ``unknown_line_id``: Line ID not found
   - ``missing_unit_price_q``: Price required for external pricing
   - ``unsupported_op``: Operation type not supported
   - ``invalid_merge``: Invalid merge operation

   **Example:**

   .. code-block:: python

      from omniman.exceptions import ValidationError

      try:
          ModifyService.modify_session(
              session_key="SESS-001",
              channel_code="pos",
              ops=[{"op": "add_line", "qty": -1}],  # Invalid qty
          )
      except ValidationError as e:
          print(f"Code: {e.code}")      # "invalid_qty"
          print(f"Message: {e.message}")  # "Quantity must be > 0"


SessionError
------------

.. py:exception:: omniman.exceptions.SessionError(code, message, context=None)

   Raised for session-related errors.

   :param code: Machine-readable error code
   :param message: Human-readable message
   :param context: Additional error data

   **Common Codes:**

   - ``not_found``: Session not found
   - ``already_committed``: Session already committed
   - ``already_abandoned``: Session was abandoned
   - ``locked``: Session has edit_policy=locked

   **Example:**

   .. code-block:: python

      from omniman.exceptions import SessionError

      try:
          ModifyService.modify_session(
              session_key="NONEXISTENT",
              channel_code="pos",
              ops=[],
          )
      except SessionError as e:
          if e.code == "not_found":
              print("Session does not exist")
          elif e.code == "already_committed":
              print("Cannot modify committed session")


CommitError
-----------

.. py:exception:: omniman.exceptions.CommitError(code, message, context=None)

   Raised when session commit fails.

   :param code: Machine-readable error code
   :param message: Human-readable message
   :param context: Additional error data

   **Common Codes:**

   - ``blocking_issues``: Session has blocking issues
   - ``stale_check``: Required check is outdated
   - ``missing_check``: Required check not found
   - ``hold_expired``: Stock/payment hold expired
   - ``already_committed``: Session already committed
   - ``abandoned``: Session was abandoned
   - ``in_progress``: Commit already in progress with this key
   - ``validation_failed``: Commit-stage validation failed

   **Example:**

   .. code-block:: python

      from omniman.exceptions import CommitError

      try:
          result = CommitService.commit(
              session_key="SESS-001",
              channel_code="pos",
              idempotency_key="COMMIT-001",
          )
      except CommitError as e:
          if e.code == "blocking_issues":
              issues = e.context.get("issues", [])
              for issue in issues:
                  print(f"Issue: {issue['message']}")

          elif e.code == "stale_check":
              check_code = e.context.get("check_code")
              print(f"Re-run check: {check_code}")

          elif e.code == "hold_expired":
              print("Stock reservation expired, re-check needed")


DirectiveError
--------------

.. py:exception:: omniman.exceptions.DirectiveError(code, message, context=None)

   Raised during directive processing.

   :param code: Machine-readable error code
   :param message: Human-readable message
   :param context: Additional error data

   **Common Codes:**

   - ``no_handler``: No handler registered for topic
   - ``handler_failed``: Handler raised an exception

   **Example:**

   .. code-block:: python

      from omniman.exceptions import DirectiveError

      try:
          process_directive(directive)
      except DirectiveError as e:
          if e.code == "no_handler":
              print(f"No handler for topic: {e.context.get('topic')}")


IssueResolveError
-----------------

.. py:exception:: omniman.exceptions.IssueResolveError(code, message, context=None)

   Raised when issue resolution fails.

   :param code: Machine-readable error code
   :param message: Human-readable message
   :param context: Additional error data

   **Common Codes:**

   - ``session_not_found``: Session not found
   - ``issue_not_found``: Issue not found in session
   - ``no_resolver``: No resolver for issue source
   - ``action_not_found``: Action not found in issue
   - ``stale_action``: Action is outdated (rev mismatch)
   - ``resolver_error``: Resolver raised an exception

   **Example:**

   .. code-block:: python

      from omniman.exceptions import IssueResolveError

      try:
          ResolveService.resolve(
              session_key="SESS-001",
              channel_code="pos",
              issue_id="ISS-123",
              action_id="adjust_qty",
          )
      except IssueResolveError as e:
          if e.code == "issue_not_found":
              print("Issue was already resolved")
          elif e.code == "no_resolver":
              print(f"No resolver for: {e.context.get('source')}")


IdempotencyError
----------------

.. py:exception:: omniman.exceptions.IdempotencyError(code, message, context=None)

   Raised for idempotency-related errors.

   :param code: Machine-readable error code
   :param message: Human-readable message
   :param context: Additional error data

   **Common Codes:**

   - ``in_progress``: Operation with this key already in progress
   - ``conflict``: Different result for same key

   **Example:**

   .. code-block:: python

      from omniman.exceptions import IdempotencyError

      try:
          # Concurrent commits with same key
          result = commit_with_key("COMMIT-123")
      except IdempotencyError as e:
          if e.code == "in_progress":
              print("Wait for other commit to complete")


InvalidTransition
-----------------

.. py:exception:: omniman.exceptions.InvalidTransition(code, message, context=None)

   Raised when order status transition is not allowed.

   :param code: Machine-readable error code
   :param message: Human-readable message
   :param context: Additional error data

   **Common Codes:**

   - ``invalid_transition``: Transition not allowed by flow
   - ``terminal_status``: Current status is terminal

   **Example:**

   .. code-block:: python

      from omniman.exceptions import InvalidTransition

      try:
          order.transition_status("completed")  # Skip steps
      except InvalidTransition as e:
          if e.code == "invalid_transition":
              allowed = e.context.get("allowed_transitions", [])
              print(f"Allowed transitions: {allowed}")

          elif e.code == "terminal_status":
              print(f"Order in terminal status: {e.context.get('current_status')}")


Error Handling Patterns
-----------------------

Catching All Omniman Errors
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from omniman.exceptions import OmnimanError

   try:
       # Any Omniman operation
       pass
   except OmnimanError as e:
       # Catch any Omniman exception
       logger.error(f"Omniman error: {e}")

Specific Error Handling
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from omniman.exceptions import (
       ValidationError,
       SessionError,
       CommitError,
   )

   try:
       session = ModifyService.modify_session(...)
       result = CommitService.commit(...)

   except ValidationError as e:
       # Handle validation errors
       return {"error": e.code, "message": e.message}

   except SessionError as e:
       # Handle session errors
       if e.code == "not_found":
           raise Http404("Session not found")
       raise

   except CommitError as e:
       # Handle commit errors
       if e.code == "blocking_issues":
           return {"issues": e.context["issues"]}
       raise

API Response Formatting
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from rest_framework.response import Response
   from rest_framework import status
   from omniman.exceptions import OmnimanError

   def handle_omniman_error(e: OmnimanError) -> Response:
       """Convert Omniman exception to API response."""

       status_map = {
           "not_found": status.HTTP_404_NOT_FOUND,
           "already_committed": status.HTTP_409_CONFLICT,
           "blocking_issues": status.HTTP_409_CONFLICT,
           "stale_check": status.HTTP_409_CONFLICT,
           "invalid_transition": status.HTTP_400_BAD_REQUEST,
       }

       http_status = status_map.get(e.code, status.HTTP_400_BAD_REQUEST)

       return Response(
           {
               "error": {
                   "code": e.code,
                   "message": e.message,
                   "context": e.context,
               }
           },
           status=http_status,
       )


See Also
--------

- :doc:`models` - Model reference
- :doc:`../guides/issues-resolution` - Issue resolution guide
