Stock Module
============

The Stock contrib module provides stock validation and reservation
for Omniman sessions.


Overview
--------

The stock module implements:

- Stock validation on item addition
- Stock holds (reservations) with TTL
- Idempotent hold/release operations
- Issue generation for stock problems


Architecture
------------

.. code-block:: text

   ModifyService
        │
        ▼
   ┌─────────────┐
   │ stock.hold  │
   │  Directive  │
   └──────┬──────┘
          │
          ▼
   ┌─────────────────────┐
   │  StockHoldHandler   │
   │                     │
   │  - Check stock      │
   │  - Create holds     │
   │  - Generate issues  │
   └──────┬──────────────┘
          │
          ▼
   ┌─────────────────────┐
   │  SessionWriteService│
   │                     │
   │  - Save check result│
   │  - Save issues      │
   └─────────────────────┘


Configuration
-------------

Channel Configuration
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   Channel.objects.create(
       code="pos",
       config={
           "check_stock_on_add": True,
           "required_checks_on_commit": ["stock"],
           "post_commit_directives": ["stock.commit"],
           "checks": {
               "stock": {
                   "directive_topic": "stock.hold",
                   "hold_ttl_minutes": 15,
               },
           },
       },
   )

Stock Backend
~~~~~~~~~~~~~

.. code-block:: python

   # settings.py

   OMNIMAN_STOCK = {
       "BACKEND": "myapp.stock.StockBackend",
       "HOLD_TTL_MINUTES": 15,
   }


Stock Protocol
--------------

.. code-block:: python

   from typing import Protocol
   from dataclasses import dataclass

   @dataclass
   class StockHold:
       hold_id: str
       sku: str
       qty: float
       expires_at: str

   @dataclass
   class StockResult:
       available: bool
       holds: list[StockHold]
       issues: list[dict]

   class StockBackend(Protocol):
       """Protocol for stock backends."""

       def check_availability(
           self,
           items: list[dict],
           session_key: str,
       ) -> StockResult:
           """Check stock availability for items."""
           ...

       def create_holds(
           self,
           items: list[dict],
           session_key: str,
           ttl_minutes: int = 15,
       ) -> list[StockHold]:
           """Create stock reservations."""
           ...

       def release_holds(
           self,
           session_key: str,
       ) -> None:
           """Release all holds for session."""
           ...

       def commit_holds(
           self,
           holds: list[StockHold],
           order_ref: str,
       ) -> None:
           """Convert holds to permanent stock deduction."""
           ...


Implementation Example
----------------------

Simple Stock Backend
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # myapp/stock.py

   from django.utils import timezone
   from datetime import timedelta
   from catalog.models import Product, StockHold as StockHoldModel
   from omniman.ids import generate_id

   class SimpleStockBackend:
       """Simple stock backend using Django models."""

       def check_availability(self, items, session_key):
           issues = []
           available = True

           for item in items:
               try:
                   product = Product.objects.get(sku=item["sku"])
                   requested = item["qty"]

                   # Consider existing holds
                   held = StockHoldModel.objects.filter(
                       sku=item["sku"],
                       expires_at__gt=timezone.now(),
                   ).exclude(session_key=session_key).aggregate(
                       total=Sum("qty")
                   )["total"] or 0

                   available_qty = product.stock - held

                   if available_qty < requested:
                       available = False
                       issues.append({
                           "code": "insufficient_stock",
                           "sku": item["sku"],
                           "requested": requested,
                           "available": available_qty,
                           "message": f"Only {available_qty} units available",
                           "blocking": True,
                           "actions": [
                               {
                                   "action": "adjust_qty",
                                   "label": f"Adjust to {available_qty}",
                                   "params": {"qty": available_qty},
                               },
                               {
                                   "action": "remove_item",
                                   "label": "Remove item",
                               },
                           ],
                       })

               except Product.DoesNotExist:
                   available = False
                   issues.append({
                       "code": "product_not_found",
                       "sku": item["sku"],
                       "message": f"Product {item['sku']} not found",
                       "blocking": True,
                   })

           return StockResult(
               available=available,
               holds=[],
               issues=issues,
           )

       def create_holds(self, items, session_key, ttl_minutes=15):
           # Release existing holds for this session
           self.release_holds(session_key)

           holds = []
           expires_at = timezone.now() + timedelta(minutes=ttl_minutes)

           for item in items:
               hold = StockHoldModel.objects.create(
                   hold_id=generate_id("H"),
                   session_key=session_key,
                   sku=item["sku"],
                   qty=item["qty"],
                   expires_at=expires_at,
               )
               holds.append(StockHold(
                   hold_id=hold.hold_id,
                   sku=hold.sku,
                   qty=hold.qty,
                   expires_at=expires_at.isoformat(),
               ))

           return holds

       def release_holds(self, session_key):
           StockHoldModel.objects.filter(session_key=session_key).delete()

       def commit_holds(self, holds, order_ref):
           for hold_data in holds:
               try:
                   hold = StockHoldModel.objects.get(hold_id=hold_data["hold_id"])
                   product = Product.objects.get(sku=hold.sku)

                   # Deduct stock
                   product.stock -= hold.qty
                   product.save()

                   # Delete hold
                   hold.delete()

               except (StockHoldModel.DoesNotExist, Product.DoesNotExist):
                   # Hold expired or product removed, try direct deduction
                   pass


Stock Handlers
--------------

StockHoldHandler
~~~~~~~~~~~~~~~~

.. code-block:: python

   from omniman.registry import registry
   from omniman.services import SessionWriteService

   @registry.register_handler("stock.hold")
   class StockHoldHandler:
       """Handler for stock hold directives."""

       def __init__(self):
           self.backend = get_stock_backend()

       def handle(self, directive, ctx):
           payload = directive.payload
           session_key = payload["session_key"]
           channel_code = payload["channel_code"]
           expected_rev = payload["rev"]
           items = payload["items"]

           # Check availability
           result = self.backend.check_availability(items, session_key)

           check_payload = {}

           if result.available:
               # Create holds
               holds = self.backend.create_holds(
                   items=items,
                   session_key=session_key,
                   ttl_minutes=15,
               )
               check_payload = {
                   "holds": [
                       {
                           "hold_id": h.hold_id,
                           "sku": h.sku,
                           "qty": h.qty,
                           "expires_at": h.expires_at,
                       }
                       for h in holds
                   ],
                   "hold_expires_at": holds[0].expires_at if holds else None,
               }

           # Write result to session
           applied = SessionWriteService.apply_check_result(
               session_key=session_key,
               channel_code=channel_code,
               expected_rev=expected_rev,
               check_code="stock",
               check_payload=check_payload,
               issues=result.issues,
           )

           return {"applied": applied, "available": result.available}

StockCommitHandler
~~~~~~~~~~~~~~~~~~

.. code-block:: python

   @registry.register_handler("stock.commit")
   class StockCommitHandler:
       """Handler for stock commit directives."""

       def __init__(self):
           self.backend = get_stock_backend()

       def handle(self, directive, ctx):
           payload = directive.payload
           order_ref = payload["order_ref"]
           holds = payload.get("holds", [])

           # Commit holds
           self.backend.commit_holds(holds, order_ref)

           return {"committed": True}


Issue Resolver
--------------

.. code-block:: python

   @registry.register_resolver("stock")
   class StockIssueResolver:
       """Resolver for stock issues."""

       def resolve(self, session, issue, action_id, ctx):
           if action_id == "adjust_qty":
               return self._adjust_qty(session, issue, ctx)
           elif action_id == "remove_item":
               return self._remove_item(session, issue, ctx)
           else:
               raise IssueResolveError(
                   code="unknown_action",
                   message=f"Unknown action: {action_id}",
               )

       def _adjust_qty(self, session, issue, ctx):
           line_id = issue.get("line_id")
           new_qty = issue.get("available", 0)

           if new_qty <= 0:
               return self._remove_item(session, issue, ctx)

           return ModifyService.modify_session(
               session_key=session.session_key,
               channel_code=session.channel.code,
               ops=[{"op": "set_qty", "line_id": line_id, "qty": new_qty}],
               ctx=ctx,
           )

       def _remove_item(self, session, issue, ctx):
           line_id = issue.get("line_id")

           return ModifyService.modify_session(
               session_key=session.session_key,
               channel_code=session.channel.code,
               ops=[{"op": "remove_line", "line_id": line_id}],
               ctx=ctx,
           )


Testing
-------

.. code-block:: python

   import pytest
   from omniman.models import Session, Channel
   from omniman.services import ModifyService, CommitService
   from myapp.stock import SimpleStockBackend

   @pytest.fixture
   def stock_backend(mocker):
       backend = SimpleStockBackend()
       mocker.patch(
           "omniman.contrib.stock.get_stock_backend",
           return_value=backend,
       )
       return backend

   def test_stock_check_sufficient(stock_backend, session, product):
       product.stock = 10
       product.save()

       result = stock_backend.check_availability(
           items=[{"sku": product.sku, "qty": 5}],
           session_key=session.session_key,
       )

       assert result.available
       assert len(result.issues) == 0

   def test_stock_check_insufficient(stock_backend, session, product):
       product.stock = 2
       product.save()

       result = stock_backend.check_availability(
           items=[{"sku": product.sku, "qty": 5}],
           session_key=session.session_key,
       )

       assert not result.available
       assert len(result.issues) == 1
       assert result.issues[0]["code"] == "insufficient_stock"


See Also
--------

- :doc:`../guides/issues-resolution` - Issue resolution
- :doc:`pricing` - Pricing module
