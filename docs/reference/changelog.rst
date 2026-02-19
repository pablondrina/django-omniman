Changelog
=========

All notable changes to Omniman are documented here.

The format is based on `Keep a Changelog <https://keepachangelog.com/>`_,
and this project adheres to `Semantic Versioning <https://semver.org/>`_.


[0.5.9] - 2025-12-18
--------------------

Added
~~~~~

- Order.emit_event() method for audit logging
- Order status transitions with validation
- Channel-configurable order flow
- Idempotent stock holds (one hold per SKU per session)
- Admin "Execute Now" action for directives
- Issue resolution system improvements (auto-recheck on expired holds)

Changed
~~~~~~~

- SessionItem is now an internal implementation detail
- Session.items property provides transparent list[dict] interface
- Improved commit error messages with resolution hints

Fixed
~~~~~

- Stock hold accumulation on multiple checks
- Stale check detection during commit


[0.5.8] - 2025-12-15
--------------------

Added
~~~~~

- Quick add item form with product autocomplete
- Stock validation on item addition
- Default filter for open sessions in admin

Changed
~~~~~~~

- Session admin layout with sidebar
- Improved issue display with action buttons


[0.5.7] - 2025-12-12
--------------------

Added
~~~~~

- Channel.config for flexible configuration
- Pricing policy per channel (internal/external)
- Edit policy per channel (open/locked)

Changed
~~~~~~~

- Session inherits policies from channel on creation


[0.5.6] - 2025-12-10
--------------------

Added
~~~~~

- REST API for sessions, orders, channels
- API exception handler
- Pagination support

Fixed
~~~~~

- Session key uniqueness constraint


[0.5.5] - 2025-12-08
--------------------

Added
~~~~~

- ModifyService with operation pipeline
- CommitService with idempotency support
- SessionWriteService for check results
- ResolveService for issue resolution

Changed
~~~~~~~

- Refactored session modification to use ops


[0.5.4] - 2025-12-05
--------------------

Added
~~~~~

- Directive model for async tasks
- IdempotencyKey model for deduplication
- OrderEvent model for audit log

Changed
~~~~~~~

- Order snapshot includes full session state


[0.5.3] - 2025-12-03
--------------------

Added
~~~~~

- OrderItem model (separate from snapshot)
- Order.total_q field

Fixed
~~~~~

- Decimal precision in quantities


[0.5.2] - 2025-12-01
--------------------

Added
~~~~~

- Session.handle_type and handle_ref fields
- Unique constraint on open session owner

Changed
~~~~~~~

- Session __str__ uses handle_ref if available


[0.5.1] - 2025-11-28
--------------------

Added
~~~~~

- Session.data JSONField for checks/issues
- Session.rev revision tracking

Fixed
~~~~~

- Session state transitions


[0.5.0] - 2025-11-25
--------------------

Initial release
~~~~~~~~~~~~~~~

- Channel model
- Session model with items
- Order model
- Basic admin interface
- Django Unfold integration


Upgrade Guide
-------------

From 0.5.x to 0.6.0 (Upcoming)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The 0.6.0 release will rename Session to Draft:

1. **Model Rename**: ``Session`` → ``Draft``, ``SessionItem`` → ``DraftItem``

2. **Field Rename**: ``session_key`` → ``draft_key``

3. **Migration**: Run provided migration to rename tables

4. **API**: Session endpoints remain for backwards compatibility

.. code-block:: python

   # Before (0.5.x)
   from omniman.models import Session
   session = Session.objects.create(session_key="SESS-001", ...)

   # After (0.6.0)
   from omniman.models import Draft
   draft = Draft.objects.create(draft_key="DRAFT-001", ...)

   # Or use alias
   from omniman.models import Session  # Alias to Draft
   session = Session.objects.create(session_key="SESS-001", ...)


See Also
--------

- :doc:`../guides/sessions` - Session guide
- :doc:`../guides/orders` - Order guide
