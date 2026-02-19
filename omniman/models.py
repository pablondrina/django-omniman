from __future__ import annotations

from decimal import Decimal
import copy
import json

from django.core.serializers.json import DjangoJSONEncoder
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.db import models
from django.db.models import Q

from .ids import generate_line_id


# =============================================================================
# CONVENÇÕES DE VALORES MONETÁRIOS E QUANTIDADES
# =============================================================================
#
# VALORES MONETÁRIOS (preços, totais):
#   - Sempre em CENTAVOS (menor unidade indivisível)
#   - Sufixo "_q" significa "quantum" (ex: unit_price_q, total_q, line_total_q)
#   - Tipo: int ou BigIntegerField
#   - Exemplo: R$ 10,00 = 1000 (centavos)
#   - Motivo: Evita problemas de ponto flutuante em operações financeiras
#
# QUANTIDADES (qty):
#   - Decimal nativo para precisão fracionária
#   - Tipo: Decimal ou DecimalField(max_digits=12, decimal_places=3)
#   - Exemplo: 0.5 kg, 1.750 litros, 2.5 metros
#   - Motivo: Permite quantidades fracionárias com precisão matemática
#
# SERIALIZAÇÃO JSON:
#   - DecimalEncoder converte Decimal → string apenas para JSON
#   - Em Python, qty permanece como Decimal nativo
#   - Campos JSONField que podem conter Decimal usam encoder=DecimalEncoder
#
# =============================================================================


class DecimalEncoder(DjangoJSONEncoder):
    """JSON encoder that handles Decimal by converting to string for precision."""

    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


class SessionManager(models.Manager):
    """
    Manager para Session com suporte a criação atômica com items.

    Uso:
        session = Session.objects.create(
            session_key="S-1",
            channel=channel,
            items=[{"sku": "SKU", "qty": 2, "unit_price_q": 1000}],
        )
    """

    use_in_migrations = True

    def create(self, **kwargs):
        from django.db import transaction

        items = kwargs.pop("items", None)
        with transaction.atomic():
            session = super().create(**kwargs)
            if items is not None:
                # Set items in cache and persist directly (avoids extra UPDATE query)
                session._items_cache = session._normalize_items(items)
                session._persist_items(session._items_cache)
        return session

    def get_or_create(self, defaults=None, **kwargs):
        from django.db import transaction

        defaults = defaults or {}
        items = defaults.pop("items", None)
        with transaction.atomic():
            session, created = super().get_or_create(defaults=defaults, **kwargs)
            if created and items is not None:
                # Set items in cache and persist directly (avoids extra UPDATE query)
                session._items_cache = session._normalize_items(items)
                session._persist_items(session._items_cache)
        return session, created


class Channel(models.Model):
    """
    Canal de origem do pedido (PDV, e-commerce, iFood, etc.)

    Config convencionais (não interpretadas pelo Kernel):
    {
      "icon": "point_of_sale",
      "required_checks_on_commit": ["stock"],
      "terminology": {"order": "Comanda", "order_plural": "Comandas"},
      "status_flow": ["NEW", "IN_PROGRESS", "READY", "COMPLETED"]
    }
    """

    code = models.CharField(_("código"), max_length=64, unique=True)
    name = models.CharField(_("nome"), max_length=128, blank=True, default="")

    pricing_policy = models.CharField(
        _("política de preço"),
        max_length=16,
        choices=[("internal", _("interna")), ("external", _("externa"))],
        default="internal",
    )
    edit_policy = models.CharField(
        _("política de edição"),
        max_length=16,
        choices=[("open", _("aberta")), ("locked", _("bloqueada"))],
        default="open",
    )

    display_order = models.PositiveIntegerField(_("ordem de exibição"), default=0, db_index=True)
    config = models.JSONField(_("configuração"), default=dict, blank=True)
    is_active = models.BooleanField(_("ativo"), default=True)

    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)

    class Meta:
        verbose_name = _("canal")
        verbose_name_plural = _("canais")
        ordering = ("display_order", "id")

    def __str__(self) -> str:
        return self.name or self.code


class Session(models.Model):
    objects = SessionManager()
    """
    Unidade mutável pré-commit (carrinho/comanda).

    Items schema:
    [{"line_id": "L-abc123", "sku": "CROISSANT", "qty": 2, "unit_price_q": 1200, "meta": {}}]

    Data schema (checks, issues):
    {
      "checks": {"stock": {"rev": 12, "at": "...", "result": {...}}},
      "issues": [{"id": "ISS-abc", "source": "stock", "code": "stock.insufficient", "blocking": true, "message": "...", "context": {...}}]
    }
    """

    session_key = models.CharField(_("chave da sessão"), max_length=64)
    channel = models.ForeignKey(Channel, verbose_name=_("canal de venda"), on_delete=models.PROTECT)

    handle_type = models.CharField(_("tipo de identificação"), max_length=32, null=True, blank=True)
    handle_ref = models.CharField(_("identificador"), max_length=64, null=True, blank=True)

    state = models.CharField(
        _("status"),
        max_length=16,
        choices=[("open", _("aberta")), ("committed", _("fechada")), ("abandoned", _("abandonada"))],
        default="open",
        db_index=True,
    )

    pricing_policy = models.CharField(
        _("política de preço"),
        max_length=16,
        choices=[("internal", _("interna")), ("external", _("externa"))],
        default="internal",
    )
    edit_policy = models.CharField(
        _("política de edição"),
        max_length=16,
        choices=[("open", _("aberta")), ("locked", _("bloqueada"))],
        default="open",
    )

    rev = models.IntegerField(_("revisão"), default=0, db_index=True)

    # Itens são persistidos em SessionLine e expostos via propriedade `items`
    data = models.JSONField(_("dados"), default=dict)
    pricing = models.JSONField(_("precificação"), default=dict, blank=True)
    pricing_trace = models.JSONField(_("trace de precificação"), default=list, blank=True)

    commit_token = models.CharField(_("token de commit"), max_length=64, null=True, blank=True, db_index=True)

    opened_at = models.DateTimeField(_("aberta em"), auto_now_add=True)
    committed_at = models.DateTimeField(_("fechada em"), null=True, blank=True)
    updated_at = models.DateTimeField(_("atualizada em"), auto_now=True)

    class Meta:
        verbose_name = _("sessão")
        verbose_name_plural = _("sessões")
        constraints = [
            models.UniqueConstraint(fields=["channel", "session_key"], name="uniq_session_channel_key"),
            models.UniqueConstraint(
                fields=["channel", "handle_type", "handle_ref"],
                condition=Q(state="open") & Q(handle_type__isnull=False) & Q(handle_ref__isnull=False),
                name="uniq_open_session_handle",
            ),
        ]

    def __str__(self) -> str:
        # Regra (v0.5.2): se existir um identificador humano (ex.: comanda/mesa),
        # use-o como "nome" no Admin/UX.
        if self.handle_ref:
            if self.handle_type:
                handle_type = (
                    str(self.handle_type)
                    .replace("_", " ")
                    .replace("-", " ")
                    .strip()
                    .title()
                )
                return f"{handle_type}: {self.handle_ref}"
            return str(self.handle_ref)
        return f"{self.channel.code}:{self.session_key}"

    # ------------------------------------------------------------------ items API

    @property
    def items(self) -> list[dict]:
        if not hasattr(self, "_items_cache"):
            self._items_cache = self._load_items_from_lines()
        return copy.deepcopy(getattr(self, "_items_cache", []))

    @items.setter
    def items(self, value: list[dict]):
        self._items_cache = self._normalize_items(value or [])

    def invalidate_items_cache(self) -> None:
        if hasattr(self, "_items_cache"):
            delattr(self, "_items_cache")

    def refresh_from_db(self, *args, **kwargs):
        super().refresh_from_db(*args, **kwargs)
        self.invalidate_items_cache()

    def save(self, *args, **kwargs):
        items_snapshot = getattr(self, "_items_cache", None)
        super().save(*args, **kwargs)
        if items_snapshot is not None:
            self._persist_items(items_snapshot)

    # ------------------------------------------------------------------ internal

    def _load_items_from_lines(self) -> list[dict]:
        payload: list[dict] = []
        for item in self.session_items.order_by("id"):
            payload.append(item.to_payload())
        return payload

    def _normalize_items(self, items: list[dict]) -> list[dict]:
        normalized: list[dict] = []
        for raw in items:
            line_id = raw.get("line_id") or generate_line_id()
            qty = Decimal(str(raw.get("qty", 0)))
            unit_price_q = int(raw.get("unit_price_q", 0) or 0)
            line_total_q = raw.get("line_total_q")
            if line_total_q is None:
                line_total_q = int(qty * unit_price_q)
            normalized.append(
                {
                    "line_id": line_id,
                    "sku": raw.get("sku", ""),
                    "name": raw.get("name", ""),
                    # Keep as Decimal for precision; JSON serialization handles conversion
                    "qty": qty,
                    "unit_price_q": unit_price_q,
                    "line_total_q": int(line_total_q),
                    "meta": raw.get("meta", {}) or {},
                }
            )
        return normalized

    def _persist_items(self, items: list[dict]) -> None:
        existing = {si.line_id: si for si in self.session_items.all()}
        seen: set[str] = set()
        for item in items:
            line_id = item["line_id"]
            seen.add(line_id)
            defaults = self._item_defaults(item)
            session_item = existing.get(line_id)
            if session_item:
                updated_fields: list[str] = []
                for field, value in defaults.items():
                    if getattr(session_item, field) != value:
                        setattr(session_item, field, value)
                        updated_fields.append(field)
                if updated_fields:
                    session_item.save(update_fields=updated_fields)
            else:
                SessionItem.objects.create(session=self, line_id=line_id, **defaults)

        for line_id, session_item in existing.items():
            if line_id not in seen:
                session_item.delete()

        self._items_cache = copy.deepcopy(items)

    def _item_defaults(self, item: dict) -> dict:
        qty = Decimal(str(item.get("qty", 0)))
        unit_price_q = int(item.get("unit_price_q", 0) or 0)
        line_total_q = item.get("line_total_q")
        if line_total_q is None:
            line_total_q = int(qty * unit_price_q)
        return {
            "sku": item.get("sku", ""),
            "name": item.get("name", ""),
            "qty": qty,
            "unit_price_q": unit_price_q,
            "line_total_q": int(line_total_q),
            "meta": item.get("meta", {}) or {},
        }


class SessionItem(models.Model):
    """Item de uma sessão (equivalente a SessionLine, renomeado para consistência com OrderItem)."""

    session = models.ForeignKey(
        Session,
        on_delete=models.CASCADE,
        related_name="session_items",
        verbose_name=_("sessão"),
    )
    line_id = models.CharField(_("ID da linha"), max_length=64)
    sku = models.CharField(_("SKU"), max_length=64, blank=True, default="")
    name = models.CharField(_("nome"), max_length=200, blank=True, default="")
    qty = models.DecimalField(_("quantidade"), max_digits=12, decimal_places=3)
    unit_price_q = models.BigIntegerField(_("preço unitário (q)"), default=0)
    line_total_q = models.BigIntegerField(_("total da linha (q)"), default=0)
    meta = models.JSONField(_("metadados"), default=dict, blank=True)
    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)
    updated_at = models.DateTimeField(_("atualizado em"), auto_now=True)

    class Meta:
        verbose_name = _("item da sessão")
        verbose_name_plural = _("itens da sessão")
        constraints = [
            models.UniqueConstraint(
                fields=["session", "line_id"],
                name="uniq_session_item_line_id",
            )
        ]

    def __str__(self) -> str:
        return f"{self.line_id} ({self.sku})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.session.invalidate_items_cache()

    def delete(self, *args, **kwargs):
        session = self.session
        super().delete(*args, **kwargs)
        session.invalidate_items_cache()

    def to_payload(self) -> dict:
        return {
            "line_id": self.line_id,
            "sku": self.sku,
            "name": self.name,
            # Keep as Decimal for precision; JSON serialization handles conversion
            "qty": self.qty,
            "unit_price_q": self.unit_price_q,
            "line_total_q": self.line_total_q,
            "meta": self.meta or {},
        }


class Order(models.Model):
    """
    Pedido canônico (selado, imutável).

    O snapshot contém o estado da Session no momento do commit para validação futura.

    Status Canônicos (semânticos):
    - new: Pedido recebido, aguardando processamento
    - confirmed: Confirmado (disponibilidade OK, pagamento pode estar pendente ou já recebido)
    - processing: Em preparação/produção
    - ready: Pronto para retirada/despacho
    - dispatched: Em trânsito (só para delivery)
    - delivered: Entregue ao destinatário
    - completed: Finalizado com sucesso
    - cancelled: Cancelado (qualquer motivo)
    - returned: Devolvido (pós-entrega)

    Fluxos por Tipo de Canal:

    1. Canal Externo (iFood, Rappi):
       Pedido chega → NEW → CONFIRMED (auto, já vem pago)
       → PROCESSING → READY → DISPATCHED → COMPLETED
       Bridge traduz eventos externos para transições.

    2. E-commerce (Shop):
       Intenção → NEW → (validar disponibilidade) → CONFIRMED → (pagamento)
       → PROCESSING → READY → [DISPATCHED] → COMPLETED
       DISPATCHED só se for entrega.

    3. PDV (Point of Sale):
       Venda → NEW → CONFIRMED → COMPLETED (quase imediato)
       Fluxo simplificado, geralmente síncrono.

    Customização por Canal:
    - Channel.config["order_flow"]["transitions"]: Transições permitidas
    - Channel.config["order_flow"]["terminal_statuses"]: Status terminais
    - Channel.config["status_labels"]: Terminologia operacional (ex: "Em Preparo")
    - Channel.config["auto_transitions"]["on_create"]: Auto-transição ao criar

    Timestamps de Lifecycle:
    Cada transição grava automaticamente o timestamp correspondente (confirmed_at, etc.)
    para B.I. e auditoria. OrderEvent mantém o audit log completo.

    Extensão Futura (REVIEW):
    Se surgir necessidade de validação de alternativas quando produto indisponível,
    pode-se adicionar status "review" entre NEW e CONFIRMED:
    NEW → REVIEW (alternativas sugeridas) → CONFIRMED (usuário aprova)
    Por ora, não implementado - validação de disponibilidade é feita antes do commit.
    """

    class Status(models.TextChoices):
        """Status canônicos do pedido."""
        NEW = "new", _("novo")
        CONFIRMED = "confirmed", _("confirmado")
        PROCESSING = "processing", _("em preparo")
        READY = "ready", _("pronto")
        DISPATCHED = "dispatched", _("despachado")
        DELIVERED = "delivered", _("entregue")
        COMPLETED = "completed", _("concluído")
        CANCELLED = "cancelled", _("cancelado")
        RETURNED = "returned", _("devolvido")

    # Aliases para retrocompatibilidade
    STATUS_NEW = Status.NEW
    STATUS_CONFIRMED = Status.CONFIRMED
    STATUS_PROCESSING = Status.PROCESSING
    STATUS_READY = Status.READY
    STATUS_DISPATCHED = Status.DISPATCHED
    STATUS_DELIVERED = Status.DELIVERED
    STATUS_COMPLETED = Status.COMPLETED
    STATUS_CANCELLED = Status.CANCELLED
    STATUS_RETURNED = Status.RETURNED
    STATUS_CHOICES = Status.choices

    # Transições padrão (usado quando canal não define order_flow)
    DEFAULT_TRANSITIONS = {
        Status.NEW: [Status.CONFIRMED, Status.CANCELLED],
        Status.CONFIRMED: [Status.PROCESSING, Status.READY, Status.CANCELLED],
        Status.PROCESSING: [Status.READY, Status.CANCELLED],
        Status.READY: [Status.DISPATCHED, Status.COMPLETED],
        Status.DISPATCHED: [Status.DELIVERED, Status.RETURNED],
        Status.DELIVERED: [Status.COMPLETED, Status.RETURNED],
        Status.COMPLETED: [],
        Status.CANCELLED: [],
        Status.RETURNED: [Status.COMPLETED],
    }

    TERMINAL_STATUSES = [Status.COMPLETED, Status.CANCELLED]

    ref = models.CharField(_("referência"), max_length=64, unique=True)
    channel = models.ForeignKey(Channel, verbose_name=_("canal de venda"), on_delete=models.PROTECT)
    session_key = models.CharField(_("chave da sessão"), max_length=64, db_index=True, default="")

    handle_type = models.CharField(_("tipo de identificação"), max_length=32, null=True, blank=True)
    handle_ref = models.CharField(_("identificador"), max_length=64, null=True, blank=True)
    external_ref = models.CharField(_("referência externa"), max_length=128, null=True, blank=True, db_index=True)

    status = models.CharField(
        _("status"),
        max_length=32,
        choices=Status.choices,
        default=Status.NEW,
        db_index=True,
    )

    snapshot = models.JSONField(_("snapshot"), default=dict, blank=True, encoder=DecimalEncoder)

    currency = models.CharField(_("moeda"), max_length=3, default="BRL")
    total_q = models.BigIntegerField(_("total (q)"), default=0)

    # Timestamps de lifecycle (para B.I. e auditoria)
    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)
    updated_at = models.DateTimeField(_("atualizado em"), auto_now=True)
    confirmed_at = models.DateTimeField(_("confirmado em"), null=True, blank=True)
    processing_at = models.DateTimeField(_("em preparo em"), null=True, blank=True)
    ready_at = models.DateTimeField(_("pronto em"), null=True, blank=True)
    dispatched_at = models.DateTimeField(_("despachado em"), null=True, blank=True)
    delivered_at = models.DateTimeField(_("entregue em"), null=True, blank=True)
    completed_at = models.DateTimeField(_("concluído em"), null=True, blank=True)
    cancelled_at = models.DateTimeField(_("cancelado em"), null=True, blank=True)

    class Meta:
        verbose_name = _("pedido")
        verbose_name_plural = _("pedidos")
        ordering = ("-created_at", "id")

    def __str__(self) -> str:
        if self.handle_ref and self.handle_type:
            handle_type = (
                str(self.handle_type)
                .replace("_", " ")
                .replace("-", " ")
                .strip()
                .title()
            )
            return f"{handle_type}: {self.handle_ref}"
        return self.ref

    # ------------------------------------------------------------------ status

    def get_transitions(self) -> dict[str, list[str]]:
        """Retorna o mapa de transições do canal ou o padrão."""
        flow = (self.channel.config or {}).get("order_flow", {})
        return flow.get("transitions", self.DEFAULT_TRANSITIONS)

    def get_terminal_statuses(self) -> list[str]:
        """Retorna os status terminais do canal ou o padrão."""
        flow = (self.channel.config or {}).get("order_flow", {})
        return flow.get("terminal_statuses", self.TERMINAL_STATUSES)

    def get_allowed_transitions(self) -> list[str]:
        """Retorna os próximos status válidos a partir do status atual."""
        transitions = self.get_transitions()
        return transitions.get(self.status, [])

    def can_transition_to(self, new_status: str) -> bool:
        """Verifica se a transição para new_status é permitida."""
        return new_status in self.get_allowed_transitions()

    # Mapeamento status → campo timestamp
    STATUS_TIMESTAMP_FIELDS = {
        STATUS_CONFIRMED: "confirmed_at",
        STATUS_PROCESSING: "processing_at",
        STATUS_READY: "ready_at",
        STATUS_DISPATCHED: "dispatched_at",
        STATUS_DELIVERED: "delivered_at",
        STATUS_COMPLETED: "completed_at",
        STATUS_CANCELLED: "cancelled_at",
    }

    def transition_status(self, new_status: str, actor: str = "system") -> None:
        """
        Transiciona o status do pedido validando regras do canal.

        Args:
            new_status: Novo status desejado
            actor: Identificador de quem está fazendo a transição

        Raises:
            InvalidTransition: Se a transição não for permitida
        """
        from omniman.exceptions import InvalidTransition

        # Verifica se está em status terminal
        if self.status in self.get_terminal_statuses():
            raise InvalidTransition(
                code="terminal_status",
                message=f"Pedido em status terminal '{self.status}' não permite transições",
                context={"current_status": self.status, "requested_status": new_status},
            )

        # Verifica se a transição é permitida
        allowed = self.get_allowed_transitions()
        if new_status not in allowed:
            raise InvalidTransition(
                code="invalid_transition",
                message=f"Transição {self.status} → {new_status} não permitida",
                context={
                    "current_status": self.status,
                    "requested_status": new_status,
                    "allowed_transitions": allowed,
                },
            )

        old_status = self.status
        self.status = new_status

        # Atualiza timestamp do novo status
        update_fields = ["status", "updated_at"]
        ts_field = self.STATUS_TIMESTAMP_FIELDS.get(new_status)
        if ts_field and getattr(self, ts_field) is None:
            setattr(self, ts_field, timezone.now())
            update_fields.append(ts_field)

        self.save(update_fields=update_fields)

        # Registra evento
        self.emit_event(
            event_type="status_changed",
            actor=actor,
            payload={
                "old_status": old_status,
                "new_status": new_status,
            },
        )

    def emit_event(self, event_type: str, actor: str = "system", payload: dict | None = None) -> "OrderEvent":
        """
        Emite um evento no audit log do pedido.

        Args:
            event_type: Tipo do evento (ex: "status_changed", "note_added")
            actor: Identificador de quem gerou o evento
            payload: Dados adicionais do evento

        Returns:
            OrderEvent criado
        """
        return OrderEvent.objects.create(
            order=self,
            type=event_type,
            actor=actor,
            payload=payload or {},
        )


class OrderItem(models.Model):
    """
    Item de um pedido.
    """

    order = models.ForeignKey(Order, verbose_name=_("pedido"), on_delete=models.CASCADE, related_name="items")

    line_id = models.CharField(_("ID da linha"), max_length=64)
    sku = models.CharField(_("SKU"), max_length=64)
    name = models.CharField(_("nome"), max_length=200, blank=True, default="")

    qty = models.DecimalField(_("quantidade"), max_digits=12, decimal_places=3)
    unit_price_q = models.BigIntegerField(_("preço unitário (q)"))
    line_total_q = models.BigIntegerField(_("total da linha (q)"))

    meta = models.JSONField(_("metadados"), default=dict, blank=True)

    class Meta:
        verbose_name = _("item do pedido")
        verbose_name_plural = _("itens do pedido")

    def __str__(self) -> str:
        return f"{self.sku} x {self.qty}"


class OrderEvent(models.Model):
    """
    Audit log append-only para pedidos.
    """

    order = models.ForeignKey(Order, verbose_name=_("pedido"), on_delete=models.CASCADE, related_name="events")

    type = models.CharField(_("tipo"), max_length=64, db_index=True)
    actor = models.CharField(_("ator"), max_length=128)
    payload = models.JSONField(_("payload"), default=dict)

    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)

    class Meta:
        verbose_name = _("evento do pedido")
        verbose_name_plural = _("eventos do pedido")
        ordering = ("created_at",)

    def __str__(self) -> str:
        return f"{self.type} @ {self.created_at}"


class Directive(models.Model):
    """
    Tarefa assíncrona (at-least-once).
    """

    topic = models.CharField(_("tópico"), max_length=64, db_index=True)
    status = models.CharField(
        _("status"),
        max_length=16,
        choices=[
            ("queued", _("em fila")),
            ("running", _("em execução")),
            ("done", _("concluído")),
            ("failed", _("falhou")),
        ],
        default="queued",
        db_index=True,
    )
    payload = models.JSONField(_("payload"), default=dict, blank=True, encoder=DecimalEncoder)

    attempts = models.IntegerField(_("tentativas"), default=0)
    available_at = models.DateTimeField(_("disponível em"), default=timezone.now, db_index=True)
    last_error = models.TextField(_("último erro"), blank=True, default="")

    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)
    updated_at = models.DateTimeField(_("atualizado em"), auto_now=True)

    class Meta:
        verbose_name = _("diretiva")
        verbose_name_plural = _("diretivas")

    def __str__(self) -> str:
        if self.pk:
            return f"Diretiva #{self.pk} ({self.topic})"
        return "Nova diretiva"


class IdempotencyKey(models.Model):
    """
    Dedupe/replay guard para operações idempotentes.
    """

    scope = models.CharField(_("escopo"), max_length=64)
    key = models.CharField(_("chave"), max_length=128)

    status = models.CharField(
        _("status"),
        max_length=16,
        choices=[
            ("in_progress", _("em andamento")),
            ("done", _("concluído")),
            ("failed", _("falhou")),
        ],
        default="in_progress",
    )

    response_code = models.IntegerField(_("código de resposta"), null=True, blank=True)
    response_body = models.JSONField(_("corpo da resposta"), null=True, blank=True)

    expires_at = models.DateTimeField(_("expira em"), null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)

    class Meta:
        verbose_name = _("chave de idempotência")
        verbose_name_plural = _("chaves de idempotência")
        unique_together = ("scope", "key")

    def __str__(self) -> str:
        return f"{self.scope}:{self.key}"
