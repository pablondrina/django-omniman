Issue Resolution
================

Omniman's issue resolution system handles validation problems
during the session lifecycle.


Overview
--------

The system handles situations where a session cannot be committed due to issues like:

- Insufficient stock
- Invalid products
- Price mismatches
- Payment failures
- Custom validation failures

Instead of simply failing, the system provides:

1. Clear issue descriptions
2. Suggested resolution actions
3. Automatic re-validation after fixes


Issue Structure
---------------

.. code-block:: python

   {
       "code": "insufficient_stock",
       "sku": "PAINCHOC",
       "line_id": "L-abc123",
       "requested": 5,
       "available": 2,
       "message": "Only 2 units of Pain au Chocolat available",
       "actions": [
           {
               "action": "adjust_qty",
               "label": "Adjust to available",
               "params": {"qty": 2},
           },
           {
               "action": "remove_item",
               "label": "Remove item",
               "params": {},
           },
       ],
   }

Issue Fields
~~~~~~~~~~~~

- **code**: Issue type identifier
- **sku**: Related product (if applicable)
- **line_id**: Related line item (if applicable)
- **message**: Human-readable description
- **actions**: Suggested resolutions


Issue Types
-----------

Stock Issues
~~~~~~~~~~~~

.. code-block:: python

   # Insufficient stock
   {
       "code": "insufficient_stock",
       "sku": "COFFEE",
       "requested": 10,
       "available": 3,
       "message": "Only 3 units available",
   }

   # Out of stock
   {
       "code": "out_of_stock",
       "sku": "CAKE",
       "message": "Product is out of stock",
   }

   # Stock hold expired
   {
       "code": "stock_hold_expired",
       "sku": "COFFEE",
       "message": "Stock reservation expired, re-check required",
   }

Product Issues
~~~~~~~~~~~~~~

.. code-block:: python

   # Product not found
   {
       "code": "product_not_found",
       "sku": "INVALID-SKU",
       "message": "Product not found in catalog",
   }

   # Product inactive
   {
       "code": "product_inactive",
       "sku": "OLD-PRODUCT",
       "message": "Product is no longer available",
   }

Price Issues
~~~~~~~~~~~~

.. code-block:: python

   # Price mismatch
   {
       "code": "price_mismatch",
       "sku": "COFFEE",
       "session_price": 500,
       "current_price": 600,
       "message": "Price has changed since item was added",
   }

   # Price not found
   {
       "code": "price_not_found",
       "sku": "NEW-PRODUCT",
       "message": "Could not determine price",
   }

Validation Issues
~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Minimum order
   {
       "code": "minimum_order",
       "minimum": 5000,
       "current": 3500,
       "message": "Minimum order is R$ 50.00",
   }

   # Invalid quantity
   {
       "code": "invalid_qty",
       "line_id": "L-abc123",
       "message": "Quantity must be positive",
   }


Handling Issues
---------------

Detecting Issues
~~~~~~~~~~~~~~~~

.. code-block:: python

   from omniman.models import Session

   session = Session.objects.get(session_key="SESS-001")
   issues = session.data.get("issues", [])

   if issues:
       print(f"Session has {len(issues)} issue(s)")
       for issue in issues:
           print(f"  - {issue['code']}: {issue['message']}")

Commit with Issues
~~~~~~~~~~~~~~~~~~

CommitService raises an exception when issues exist:

.. code-block:: python

   from omniman.services import CommitService
   from omniman.exceptions import CommitError

   try:
       result = CommitService.commit(
           session_key="SESS-001",
           channel_code="pos",
       )
   except CommitError as e:
       if e.code == "has_issues":
           print("Cannot commit, resolve issues first:")
           for issue in e.issues:
               print(f"  - {issue['message']}")


Resolving Issues
----------------

Using Actions
~~~~~~~~~~~~~

Actions provide suggested fixes:

.. code-block:: python

   issue = session.data["issues"][0]

   for action in issue.get("actions", []):
       print(f"Option: {action['label']}")
       print(f"  Action: {action['action']}")
       print(f"  Params: {action['params']}")

   # Example: adjust quantity
   if action["action"] == "adjust_qty":
       ModifyService.modify_session(
           session_key="SESS-001",
           channel_code="pos",
           ops=[
               {
                   "op": "set_qty",
                   "line_id": issue["line_id"],
                   "qty": action["params"]["qty"],
               },
           ],
       )

   # Example: remove item
   if action["action"] == "remove_item":
       ModifyService.modify_session(
           session_key="SESS-001",
           channel_code="pos",
           ops=[
               {
                   "op": "remove_line",
                   "line_id": issue["line_id"],
               },
           ],
       )

Automatic Re-validation
~~~~~~~~~~~~~~~~~~~~~~~

After resolving issues, re-run validation:

.. code-block:: python

   from omniman.services import CheckService

   # Run stock check
   CheckService.run_check(
       session_key="SESS-001",
       channel_code="pos",
       check_type="stock",
   )

   # Check if issues resolved
   session.refresh_from_db()
   issues = session.data.get("issues", [])

   if not issues:
       # Now can commit
       result = CommitService.commit(...)


Creating Custom Issue Handlers
------------------------------

Issue Resolver Protocol
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from typing import Protocol

   class IssueResolver(Protocol):
       """Protocol for issue resolution handlers."""

       def get_issues(
           self,
           session,
           context: dict | None = None,
       ) -> list[dict]:
           """
           Check for issues and return list.

           Returns:
               List of issue dicts
           """
           ...

       def get_actions(
           self,
           issue: dict,
           session,
       ) -> list[dict]:
           """
           Get resolution actions for an issue.

           Returns:
               List of action dicts
           """
           ...

Stock Issue Resolver
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from omniman.registry import registry
   from catalog.models import Product

   @registry.register_resolver("stock")
   class StockIssueResolver:
       """Resolver for stock-related issues."""

       def get_issues(self, session, context=None):
           issues = []

           for item in session.items:
               try:
                   product = Product.objects.get(sku=item["sku"])
                   if product.stock < item["qty"]:
                       issues.append({
                           "code": "insufficient_stock",
                           "sku": item["sku"],
                           "line_id": item["line_id"],
                           "requested": item["qty"],
                           "available": product.stock,
                           "message": f"Only {product.stock} available",
                       })
               except Product.DoesNotExist:
                   issues.append({
                       "code": "product_not_found",
                       "sku": item["sku"],
                       "line_id": item["line_id"],
                       "message": f"Product {item['sku']} not found",
                   })

           return issues

       def get_actions(self, issue, session):
           actions = []

           if issue["code"] == "insufficient_stock":
               if issue["available"] > 0:
                   actions.append({
                       "action": "adjust_qty",
                       "label": f"Adjust to {issue['available']}",
                       "params": {"qty": issue["available"]},
                   })

               actions.append({
                   "action": "remove_item",
                   "label": "Remove item",
                   "params": {},
               })

           elif issue["code"] == "product_not_found":
               actions.append({
                   "action": "remove_item",
                   "label": "Remove item",
                   "params": {},
               })

           return actions


Admin Integration
-----------------

You can display issues in the admin:

.. code-block:: python

   # admin.py

   from django.contrib import admin
   from django.utils.html import format_html
   from omniman.models import Session

   @admin.register(Session)
   class SessionAdmin(admin.ModelAdmin):

       @admin.display(description="Issues")
       def issues_display(self, obj):
           issues = obj.data.get("issues", [])
           if not issues:
               return format_html('<span style="color: green;">No issues</span>')

           html = '<ul style="margin: 0; padding-left: 1rem;">'
           for issue in issues:
               html += f'<li style="color: red;">{issue["message"]}</li>'
           html += '</ul>'
           return format_html(html)

       def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
           extra_context = extra_context or {}

           if object_id:
               obj = self.get_object(request, object_id)
               if obj:
                   issues = obj.data.get("issues", [])
                   extra_context["has_issues"] = len(issues) > 0
                   extra_context["issues"] = issues

           return super().changeform_view(request, object_id, form_url, extra_context)


Commit Flow with Issue Resolution
----------------------------------

.. code-block:: text

   User clicks "Commit"
          │
          ▼
   ┌──────────────────┐
   │ Check for issues │
   └────────┬─────────┘
            │
      ┌─────┴─────┐
      │           │
   No issues   Has issues
      │           │
      ▼           ▼
   ┌───────┐  ┌──────────────┐
   │ Commit │  │ Show issues  │
   │ Order  │  │ with actions │
   └───────┘  └──────┬───────┘
                     │
                     ▼
              ┌──────────────┐
              │ User resolves│
              │    issues    │
              └──────┬───────┘
                     │
                     ▼
              ┌──────────────┐
              │ Re-validate  │◀────┐
              └──────┬───────┘     │
                     │             │
               ┌─────┴─────┐       │
               │           │       │
            No issues   Has issues─┘
               │
               ▼
            ┌───────┐
            │ Commit │
            │ Order  │
            └───────┘


Best Practices
--------------

1. **Clear Messages**: Write user-friendly issue messages.

2. **Provide Actions**: Always suggest resolution actions when possible.

3. **Re-validate After Fix**: Run checks after user resolves issues.

4. **Log Issues**: Track issue frequency for analytics.

5. **Test Edge Cases**: Test scenarios with multiple simultaneous issues.


See Also
--------

- :doc:`sessions` - Session management
- :doc:`../api/rest-api` - REST API reference
- :doc:`../api/exceptions` - CommitError reference
