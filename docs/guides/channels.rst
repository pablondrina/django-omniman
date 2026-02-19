Channels
========

Channels are the core concept in Omniman for organizing different sales sources.
Each channel represents a distinct way orders can be created: POS, e-commerce,
delivery apps, etc.


What is a Channel?
------------------

A Channel defines:

- **Identity**: Unique code and display name
- **Configuration**: Pricing policy, stock checks, order flow
- **Terminology**: Localized terms for UI
- **Active Status**: Enable/disable without deletion


Creating Channels
-----------------

Via Django ORM
~~~~~~~~~~~~~~

.. code-block:: python

   from omniman.models import Channel

   channel = Channel.objects.create(
       code="ecommerce",
       name="E-commerce Website",
       config={
           "pricing_policy": "external",
           "order_flow": {
               "initial_status": "pending_payment",
               "transitions": {
                   "pending_payment": ["confirmed", "cancelled"],
                   "confirmed": ["processing", "cancelled"],
                   "processing": ["shipped"],
                   "shipped": ["delivered"],
                   "delivered": ["completed"],
               },
           },
       },
   )

Via Admin Interface
~~~~~~~~~~~~~~~~~~~

1. Navigate to **Omniman > Channels**
2. Click **Add Channel**
3. Fill in the required fields
4. Configure the JSON config
5. Save


Channel Configuration
---------------------

The ``config`` field is a JSON object that controls channel behavior.

Pricing Policy
~~~~~~~~~~~~~~

Determines how item prices are resolved:

.. code-block:: python

   # Internal: Prices from operation payload
   {"pricing_policy": "internal"}

   # External: Prices from external service (PricingBackend)
   {"pricing_policy": "external"}

   # Mixed: Try external, fallback to internal
   {"pricing_policy": "mixed"}


Order Flow
~~~~~~~~~~

Defines the status state machine for orders:

.. code-block:: python

   {
       "order_flow": {
           "initial_status": "created",
           "transitions": {
               "created": ["confirmed", "cancelled"],
               "confirmed": ["processing", "cancelled"],
               "processing": ["ready"],
               "ready": ["completed"],
               "completed": [],
               "cancelled": [],
           },
           "terminal_statuses": ["completed", "cancelled"],
           "auto_transitions": {
               "on_stock_commit": "confirmed",
               "on_payment_confirm": "confirmed",
           },
       }
   }

- **initial_status**: Status when order is created
- **transitions**: Map of current status to allowed next statuses
- **terminal_statuses**: Statuses that cannot be changed
- **auto_transitions**: Automatic status changes based on events


Status Labels (Operational Terminology)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Customize how canonical statuses are displayed in the UI:

.. code-block:: python

   {
       "status_labels": {
           "new": "Pendente",
           "confirmed": "Aceito",
           "processing": "Em Preparo",
           "ready": "Pronto p/ Retirada",
           "dispatched": "Saiu p/ Entrega",
           "delivered": "Entregue",
           "completed": "Finalizado",
           "cancelled": "Cancelado",
       }
   }

This allows the same canonical status to have different display names per channel
(e.g., "processing" might be "Em Preparo" for restaurants but "Separando" for warehouses).


Default Stock Threshold
~~~~~~~~~~~~~~~~~~~~~~~

Set a channel-wide default threshold for catalog availability:

.. code-block:: python

   {
       "default_stock_threshold": 5,  # Items below 5 units show warning/auto-pause
   }

The threshold hierarchy is: Listing → Product → Channel.config["default_stock_threshold"] → 0


Stock Configuration
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   {
       "check_stock_on_add": True,     # Validate stock when adding items
       "hold_stock_on_check": True,    # Reserve stock during check
       "stock_hold_ttl_minutes": 15,   # Hold expiration time
   }


Terminology
~~~~~~~~~~~

Customize UI labels per channel:

.. code-block:: python

   {
       "terminology": {
           "session": "Atendimento",    # POS
           "session": "Carrinho",       # E-commerce
           "session": "Comanda",        # Restaurant
           "order": "Pedido",
           "commit": "Finalizar",
           "item": "Item",
       }
   }


Channel Types Examples
----------------------

POS / POS
~~~~~~~~~~~~~~~

.. code-block:: python

   Channel.objects.create(
       code="pos",
       name="Balcão",
       config={
           "pricing_policy": "internal",
           "check_stock_on_add": True,
           "order_flow": {
               "initial_status": "created",
               "transitions": {
                   "created": ["confirmed", "cancelled"],
                   "confirmed": ["completed"],
               },
           },
           "terminology": {
               "session": "Atendimento",
               "order": "Pedido",
           },
       },
   )


E-commerce
~~~~~~~~~~

.. code-block:: python

   Channel.objects.create(
       code="ecommerce",
       name="Loja Virtual",
       config={
           "pricing_policy": "external",
           "check_stock_on_add": True,
           "hold_stock_on_check": True,
           "order_flow": {
               "initial_status": "pending_payment",
               "transitions": {
                   "pending_payment": ["confirmed", "cancelled", "expired"],
                   "confirmed": ["processing"],
                   "processing": ["shipped"],
                   "shipped": ["delivered"],
                   "delivered": ["completed"],
               },
               "auto_transitions": {
                   "on_payment_confirm": "confirmed",
               },
           },
       },
   )


iFood Integration
~~~~~~~~~~~~~~~~~

.. code-block:: python

   Channel.objects.create(
       code="ifood",
       name="iFood",
       config={
           "pricing_policy": "external",  # iFood sends prices
           "external_sync": True,
           "order_flow": {
               "initial_status": "received",
               "transitions": {
                   "received": ["confirmed", "cancelled"],
                   "confirmed": ["preparing"],
                   "preparing": ["ready"],
                   "ready": ["dispatched"],
                   "dispatched": ["delivered"],
                   "delivered": ["completed"],
               },
           },
           "status_mapping": {
               "ifood_PLACED": "received",
               "ifood_CONFIRMED": "confirmed",
               "ifood_PREPARATION_STARTED": "preparing",
               "ifood_READY_TO_PICKUP": "ready",
               "ifood_DISPATCHED": "dispatched",
               "ifood_CONCLUDED": "completed",
               "ifood_CANCELLED": "cancelled",
           },
       },
   )


Restaurant / Table Service
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   Channel.objects.create(
       code="restaurant",
       name="Salão",
       config={
           "pricing_policy": "internal",
           "allow_open_sessions": True,  # Keep session open for additions
           "order_flow": {
               "initial_status": "open",
               "transitions": {
                   "open": ["sent_to_kitchen"],
                   "sent_to_kitchen": ["preparing"],
                   "preparing": ["ready"],
                   "ready": ["served"],
                   "served": ["paid", "open"],  # Can add more items
                   "paid": ["completed"],
               },
           },
           "terminology": {
               "session": "Comanda",
               "commit": "Enviar para Cozinha",
           },
       },
   )


Querying Channels
-----------------

Active Channels
~~~~~~~~~~~~~~~

.. code-block:: python

   # Get all active channels
   channels = Channel.objects.filter(is_active=True)

   # Get specific channel
   channel = Channel.objects.get(code="pos")


Channel by Session
~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from omniman.models import Session

   session = Session.objects.get(session_key="SESS-001")
   channel = session.channel


Channel Configuration Access
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   channel = Channel.objects.get(code="pos")

   # Access config
   pricing_policy = channel.config.get("pricing_policy", "internal")
   order_flow = channel.config.get("order_flow", {})
   terminology = channel.config.get("terminology", {})

   # Get localized term
   session_term = terminology.get("session", "Session")


Best Practices
--------------

1. **Use Meaningful Codes**: Channel codes are used in API calls; keep them short and descriptive.

2. **Consistent Terminology**: Use the terminology config to match your business language.

3. **Plan Order Flow**: Design the order flow state machine before implementing.

4. **Test Status Transitions**: Ensure all status transitions are valid and tested.

5. **Document Channel Config**: Add comments in your setup scripts explaining configuration choices.


See Also
--------

- :doc:`sessions` - Session management
- :doc:`orders` - Order lifecycle
- :doc:`status-flow` - Status transitions in depth
