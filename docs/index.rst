Django Omniman
==============

**A headless omnichannel order hub for Django.**

Omniman provides a flexible kernel for managing orders across multiple sales channels.
It follows the **SIREL** philosophy: **Simple**, **Robust**, **Elegant**.

.. code-block:: text

   Session (mutable) → Order (immutable) → Directive (async)
    Basket/Tab/Draft       Confirmed           Stock, Payment


What Omniman IS
---------------

- A **headless kernel** for order management
- A **protocol-based registry** for extensibility
- A **rev-based versioning system** for stale-safe writes
- An **audit-first** architecture with immutable orders
- **Channel-agnostic**: same core, different behaviors per channel

What Omniman is NOT
-------------------

- **Not a complete e-commerce solution** - no product catalog, no customer management
- **Not an opinionated UI** - the kernel is headless; you build the UI
- **Not a payment gateway** - use contrib/payment or bring your own
- **Not a stock manager** - use contrib/stock or bring your own
- **Not a shopping basket** - Session is a generic pre-commit state, not tied to e-commerce

.. warning::

   Omniman is extremely flexible. This flexibility can lead to incorrect implementations
   if you don't understand the contracts below and the :doc:`14 invariants <concepts/invariants>`.


The Three Contracts
-------------------

**1. Kernel is headless and agnostic.**
No opinions on your catalog, customers, UI, or payment provider.
Channels abstract away origin differences (POS, e-commerce, marketplace).

**2. Everything goes through Services.**
Never modify Session fields directly.
``ModifyService`` increments ``rev``, invalidates stale checks, and runs Modifiers.
Skipping it breaks consistency guarantees.

**3. Side effects are Directives.**
Stock reservations, payments, notifications — all happen asynchronously via Directives
with at-least-once semantics. Handlers **must** be idempotent.


Common Mistakes
^^^^^^^^^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 30 30 40

   * - Mistake
     - What breaks
     - Do this instead
   * - Modify Session without ``ModifyService``
     - ``rev`` doesn't increment, checks stay stale
     - Always use ``ModifyService.modify_session()``
   * - Commit without ``idempotency_key``
     - Duplicate orders on retry
     - Always pass ``idempotency_key`` in production
   * - IO in Validators or Modifiers
     - Unpredictable failures, untestable code
     - Validators are pure gates; Modifiers are pure transforms
   * - Non-idempotent Directive handler
     - Duplicate stock moves, double charges
     - Check if already processed before acting
   * - Ignore ``pricing_policy`` in Modifier
     - External prices silently overwritten
     - Check ``session.pricing_policy`` before repricing
   * - Write checks without ``expected_rev``
     - Race conditions in concurrent edits
     - Use ``SessionWriteService.write_check(expected_rev=...)``

See :doc:`concepts/philosophy` for the full design principles (P1-P5), anti-patterns, and decision checklist.
See :doc:`concepts/invariants` for the 14 inviolable system contracts with code examples.


Philosophy: SIREL
-----------------

Every decision in Omniman follows three principles:

.. list-table::
   :header-rows: 1
   :widths: 15 85

   * - Principle
     - Question to Ask
   * - **Simple**
     - Can this be done in a simpler way? Am I adding unnecessary complexity?
   * - **Robust**
     - What if this runs twice? What if data is stale? Does it handle failures?
   * - **Elegant**
     - Is the API intuitive? Is the code readable? Does it follow Django patterns?


Core Flow
---------

.. code-block:: text

   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
   │   Session   │ ──► │    Order    │ ──► │  Directive  │
   │  (mutable)  │     │ (immutable) │     │   (async)   │
   └─────────────┘     └─────────────┘     └─────────────┘

1. **Session**: Mutable pre-commit state (basket, tab, draft—depends on your use case).
2. **Order**: Immutable snapshot created at commit time. The source of truth.
3. **Directive**: Async tasks for side effects (stock, payment, notifications).


Quick Start
-----------

.. code-block:: bash

   pip install django-omniman

.. code-block:: python

   # settings.py
   INSTALLED_APPS = [
       "unfold",
       "rest_framework",
       "omniman",
   ]

.. code-block:: bash

   python manage.py migrate

See :doc:`getting-started/quickstart` for a complete example.


Table of Contents
-----------------

.. toctree::
   :maxdepth: 2
   :caption: Getting Started

   getting-started/installation
   getting-started/quickstart
   getting-started/tutorial

.. toctree::
   :maxdepth: 2
   :caption: Concepts

   concepts/philosophy
   concepts/invariants
   concepts/channels
   concepts/sessions
   concepts/orders
   concepts/directives

.. toctree::
   :maxdepth: 2
   :caption: Guides

   guides/channels
   guides/sessions
   guides/orders
   guides/pricing
   guides/status-flow
   guides/issues-resolution

.. toctree::
   :maxdepth: 2
   :caption: Contrib Modules

   contrib/pricing
   contrib/stock

.. toctree::
   :maxdepth: 2
   :caption: Integrations

   integrations/ifood
   integrations/payments
   integrations/custom

.. toctree::
   :maxdepth: 2
   :caption: API Reference

   api/models
   api/services
   api/rest-api
   api/exceptions

.. toctree::
   :maxdepth: 2
   :caption: Deployment

   deployment/production
   deployment/docker
   deployment/performance

.. toctree::
   :maxdepth: 1
   :caption: Reference

   reference/settings
   reference/changelog
   reference/faq


Indices
-------

* :ref:`genindex`
* :ref:`modindex`
