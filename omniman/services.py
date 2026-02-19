"""
Omniman Services — Serviços do Kernel.

- ModifyService: Modifica sessões aplicando ops
- CommitService: Fecha sessões e cria Orders
- SessionWriteService: Write-back de checks
- ResolveService: Resolve issues delegando para resolvers
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from . import registry
from .exceptions import (
    CommitError,
    IdempotencyCacheHit,
    IssueResolveError,
    SessionError,
    ValidationError,
)
from .ids import generate_line_id, generate_order_ref
from .models import Channel, Directive, IdempotencyKey, Order, OrderEvent, OrderItem, Session


logger = logging.getLogger(__name__)


# =============================================================================
# MODIFY SERVICE
# =============================================================================


class ModifyService:
    """
    Serviço para modificar sessões aplicando operações (ops).

    Pipeline:
    1. Lock session (select_for_update)
    2. Apply ops
    3. Run modifiers
    4. Run validators (stage="draft")
    5. Increment rev
    6. Clear checks and issues
    7. Save session
    8. Enqueue directives (se necessário)
    """

    # Ops suportadas pelo Kernel
    SUPPORTED_OPS = {
        "add_line",
        "remove_line",
        "set_qty",
        "replace_sku",
        "set_data",
        "merge_lines",
    }

    @staticmethod
    @transaction.atomic
    def modify_session(
        session_key: str,
        channel_code: str,
        ops: list[dict],
        ctx: dict | None = None,
    ) -> Session:
        """
        Modifica uma sessão aplicando operações.

        Args:
            session_key: Chave da sessão
            channel_code: Código do canal
            ops: Lista de operações a aplicar
            ctx: Contexto adicional (ex.: request, user)

        Returns:
            Session atualizada

        Raises:
            SessionError: Se sessão não encontrada ou não editável
            ValidationError: Se validação falhar
        """
        ctx = ctx or {}

        # 1. Lock session
        try:
            session = Session.objects.select_for_update().get(
                session_key=session_key,
                channel__code=channel_code,
            )
        except Session.DoesNotExist:
            raise SessionError(
                code="not_found",
                message=f"Sessão não encontrada: {channel_code}:{session_key}",
            )

        channel = session.channel

        # Verificar estado
        if session.state == "committed":
            raise SessionError(
                code="already_committed",
                message="Esta sessão já foi finalizada e não pode mais ser alterada.",
                context={"session_key": session_key, "channel": channel.name or channel.code},
            )
        if session.state == "abandoned":
            raise SessionError(
                code="already_abandoned",
                message="Esta sessão foi abandonada e não pode mais ser alterada.",
                context={"session_key": session_key, "channel": channel.name or channel.code},
            )

        # Verificar edit_policy
        if session.edit_policy == "locked":
            raise SessionError(
                code="locked",
                message=(
                    f"Pedidos do canal '{channel.name or channel.code}' não podem ser editados. "
                    "Este canal recebe pedidos prontos de uma plataforma externa."
                ),
                context={
                    "session_key": session_key,
                    "channel": channel.name or channel.code,
                    "edit_policy": session.edit_policy,
                },
            )

        # 2. Apply ops
        items = list(session.items)  # Cópia para modificar
        data = dict(session.data)

        for op in ops:
            items, data = ModifyService._apply_op(items, data, op, session)

        session.items = items
        session.data = data

        # 3. Run modifiers
        for modifier in registry.get_modifiers():
            modifier.apply(channel=channel, session=session, ctx=ctx)

        # 4. Run validators (stage="draft")
        for validator in registry.get_validators(stage="draft"):
            validator.validate(channel=channel, session=session, ctx=ctx)

        # 5. Increment rev
        session.rev += 1

        # 6. Clear checks and issues
        session.data["checks"] = {}
        session.data["issues"] = []

        # 7. Save session
        session.save()

        # 8. Enqueue directives (se configurado no canal)
        required_checks = channel.config.get("required_checks_on_commit", [])
        checks_config = channel.config.get("checks", {})
        for check_code in required_checks:
            check_opts = checks_config.get(check_code, {})
            topic = check_opts.get("directive_topic") or f"{check_code}.hold"
            Directive.objects.create(
                topic=topic,
                payload={
                    "session_key": session.session_key,
                    "channel_code": channel.code,
                    "rev": session.rev,
                    "items": session.items,
                },
            )

        return session

    @staticmethod
    def _apply_op(
        items: list[dict],
        data: dict,
        op: dict,
        session: Session,
    ) -> tuple[list[dict], dict]:
        """Aplica uma operação aos items/data."""
        op_type = op.get("op")

        if op_type not in ModifyService.SUPPORTED_OPS:
            raise ValidationError(
                code="unsupported_op",
                message=f"Operação não suportada: {op_type}",
            )

        if op_type == "add_line":
            return ModifyService._op_add_line(items, data, op, session)
        elif op_type == "remove_line":
            return ModifyService._op_remove_line(items, data, op)
        elif op_type == "set_qty":
            return ModifyService._op_set_qty(items, data, op)
        elif op_type == "replace_sku":
            return ModifyService._op_replace_sku(items, data, op, session)
        elif op_type == "set_data":
            return ModifyService._op_set_data(items, data, op)
        elif op_type == "merge_lines":
            return ModifyService._op_merge_lines(items, data, op)

        return items, data

    @staticmethod
    def _parse_positive_qty(value: Any) -> Decimal:
        """Converte e valida qty (> 0)."""
        try:
            qty = Decimal(str(value))
        except Exception:
            raise ValidationError(code="invalid_qty", message="Quantidade inválida")
        if qty <= 0:
            raise ValidationError(code="invalid_qty", message="Quantidade deve ser > 0")
        return qty

    @staticmethod
    def _op_add_line(items: list[dict], data: dict, op: dict, session: Session) -> tuple[list[dict], dict]:
        """add_line {sku, qty, unit_price_q?, meta?}"""
        if not op.get("sku"):
            raise ValidationError(code="missing_sku", message="SKU é obrigatório")
        qty = ModifyService._parse_positive_qty(op.get("qty"))

        # Regra (v0.5.4+): se pricing_policy=external, unit_price_q é obrigatório em add_line.
        # (No payload, o modifier de pricing não deve preencher isso.)
        if session.pricing_policy == "external" and "unit_price_q" not in op:
            raise ValidationError(
                code="missing_unit_price_q",
                message="unit_price_q é obrigatório quando pricing_policy=external",
            )

        line = {
            "line_id": generate_line_id(),
            "sku": op["sku"],
            "qty": qty,  # Keep as Decimal
            "meta": op.get("meta", {}),
        }
        if "unit_price_q" in op:
            line["unit_price_q"] = int(op["unit_price_q"])
        items.append(line)
        return items, data

    @staticmethod
    def _op_remove_line(items: list[dict], data: dict, op: dict) -> tuple[list[dict], dict]:
        """remove_line {line_id}"""
        line_id = op["line_id"]
        if not any(item.get("line_id") == line_id for item in items):
            raise ValidationError(code="unknown_line_id", message="line_id não encontrado")
        items = [item for item in items if item["line_id"] != line_id]
        return items, data

    @staticmethod
    def _op_set_qty(items: list[dict], data: dict, op: dict) -> tuple[list[dict], dict]:
        """set_qty {line_id, qty}"""
        line_id = op["line_id"]
        qty = ModifyService._parse_positive_qty(op.get("qty"))
        for item in items:
            if item["line_id"] == line_id:
                item["qty"] = qty  # Keep as Decimal
                break
        else:
            raise ValidationError(code="unknown_line_id", message="line_id não encontrado")
        return items, data

    @staticmethod
    def _op_replace_sku(items: list[dict], data: dict, op: dict, session: Session) -> tuple[list[dict], dict]:
        """replace_sku {line_id, sku, unit_price_q?, meta?}"""
        if not op.get("sku"):
            raise ValidationError(code="missing_sku", message="SKU é obrigatório")
        if session.pricing_policy == "external" and "unit_price_q" not in op:
            raise ValidationError(
                code="missing_unit_price_q",
                message="unit_price_q é obrigatório quando pricing_policy=external",
            )
        line_id = op["line_id"]
        for item in items:
            if item["line_id"] == line_id:
                item["sku"] = op["sku"]
                if "unit_price_q" in op:
                    item["unit_price_q"] = int(op["unit_price_q"])
                if "meta" in op:
                    item["meta"] = op["meta"]
                break
        else:
            raise ValidationError(code="unknown_line_id", message="line_id não encontrado")
        return items, data

    @staticmethod
    def _op_set_data(items: list[dict], data: dict, op: dict) -> tuple[list[dict], dict]:
        """set_data {path, value}"""
        path = op["path"]
        value = op["value"]

        # Suporta paths simples como "customer.name"
        keys = path.split(".")
        target = data
        for key in keys[:-1]:
            if key not in target:
                target[key] = {}
            target = target[key]
        target[keys[-1]] = value

        return items, data

    @staticmethod
    def _op_merge_lines(items: list[dict], data: dict, op: dict) -> tuple[list[dict], dict]:
        """merge_lines {from_line_id, into_line_id}"""
        from_id = op["from_line_id"]
        into_id = op["into_line_id"]
        if from_id == into_id:
            raise ValidationError(code="invalid_merge", message="from_line_id e into_line_id devem ser diferentes")

        from_line = None
        into_line = None

        for item in items:
            if item["line_id"] == from_id:
                from_line = item
            elif item["line_id"] == into_id:
                into_line = item

        if from_line and into_line:
            into_qty = Decimal(str(into_line.get("qty", 0)))
            from_qty = Decimal(str(from_line.get("qty", 0)))
            if into_qty <= 0 or from_qty <= 0:
                raise ValidationError(code="invalid_qty", message="Quantidade deve ser > 0")
            into_line["qty"] = into_qty + from_qty  # Keep as Decimal
            items = [item for item in items if item["line_id"] != from_id]
        else:
            raise ValidationError(code="unknown_line_id", message="line_id não encontrado")

        return items, data


# =============================================================================
# COMMIT SERVICE
# =============================================================================


class CommitService:
    """
    Serviço para fechar sessões e criar Orders.

    Pipeline:
    1. Check idempotency (return cached if exists)
    2. Validate session is open
    3. Check required checks are fresh
    4. Check no blocking issues
    5. Run validators (stage="commit")
    6. Create Order + OrderItems
    7. Mark session as committed
    8. Enqueue post-commit directives
    9. Cache response in IdempotencyKey
    """

    @staticmethod
    def commit(
        session_key: str,
        channel_code: str,
        idempotency_key: str,
        ctx: dict | None = None,
    ) -> dict:
        """
        Fecha uma sessão e cria um Order.

        Args:
            session_key: Chave da sessão
            channel_code: Código do canal
            idempotency_key: Chave de idempotência
            ctx: Contexto adicional

        Returns:
            dict com order_ref e dados do pedido

        Raises:
            CommitError: Se commit falhar
            SessionError: Se sessão não encontrada
        """
        ctx = ctx or {}
        idem_scope = f"commit:{channel_code}"

        # 1. Check/create idempotency key (outside main transaction)
        try:
            idem = CommitService._acquire_idempotency_lock(idem_scope, idempotency_key)
        except IdempotencyCacheHit as cache_hit:
            # Cached response from previous successful commit
            return cache_hit.cached_response

        try:
            # 2. Execute commit in atomic transaction
            response = CommitService._do_commit(
                session_key=session_key,
                channel_code=channel_code,
                idempotency_key=idempotency_key,
                ctx=ctx,
            )

            # 3. Mark idempotency key as done (outside transaction)
            idem.status = "done"
            idem.response_body = response
            idem.response_code = 201
            idem.save(update_fields=["status", "response_body", "response_code"])

            return response

        except (CommitError, SessionError, ValidationError):
            # Mark idempotency key as failed (persists even if transaction rolled back)
            idem.status = "failed"
            idem.save(update_fields=["status"])
            raise

        except Exception as e:
            # Unexpected error - mark as failed and re-raise
            idem.status = "failed"
            idem.save(update_fields=["status"])
            logger.exception(f"Unexpected error in commit: {e}")
            raise

    @staticmethod
    def _acquire_idempotency_lock(scope: str, key: str) -> IdempotencyKey:
        """
        Acquire idempotency lock for a commit operation.

        Returns:
            IdempotencyKey with status="in_progress"

        Raises:
            IdempotencyCacheHit: If key exists and has cached response (not an error)
            CommitError: If key is already in progress
        """
        with transaction.atomic():
            try:
                idem = IdempotencyKey.objects.select_for_update(nowait=False).get(
                    scope=scope,
                    key=key,
                )
                # Key exists - check status
                if idem.status == "done" and idem.response_body:
                    raise IdempotencyCacheHit(idem.response_body)
                elif idem.status == "in_progress":
                    raise CommitError(
                        code="in_progress",
                        message="Commit já está em andamento com esta chave",
                    )
                # Status is "failed" - allow retry
                idem.status = "in_progress"
                idem.save(update_fields=["status"])
                return idem

            except IdempotencyKey.DoesNotExist:
                # Create new key
                idem, created = IdempotencyKey.objects.get_or_create(
                    scope=scope,
                    key=key,
                    defaults={
                        "status": "in_progress",
                        "expires_at": timezone.now() + timedelta(hours=24),
                    },
                )
                if not created:
                    # Race condition: another request created it - re-check with lock
                    idem = IdempotencyKey.objects.select_for_update().get(pk=idem.pk)
                    if idem.status == "done" and idem.response_body:
                        raise IdempotencyCacheHit(idem.response_body)
                    elif idem.status == "in_progress":
                        raise CommitError(
                            code="in_progress",
                            message="Commit já está em andamento com esta chave",
                        )
                    # Status is "failed" - allow retry
                    idem.status = "in_progress"
                    idem.save(update_fields=["status"])
                return idem

    @staticmethod
    @transaction.atomic
    def _do_commit(
        session_key: str,
        channel_code: str,
        idempotency_key: str,
        ctx: dict,
    ) -> dict:
        """
        Execute the actual commit logic in an atomic transaction.
        """
        # Lock session
        try:
            session = Session.objects.select_for_update().get(
                session_key=session_key,
                channel__code=channel_code,
            )
        except Session.DoesNotExist:
            raise SessionError(
                code="not_found",
                message=f"Sessão não encontrada: {channel_code}:{session_key}",
            )

        channel = session.channel

        # Validate session is open
        if session.state == "committed":
            # Return existing order (idempotency)
            order = Order.objects.filter(session_key=session_key, channel=channel).first()
            if order:
                return {"order_ref": order.ref, "status": "already_committed"}
            raise CommitError(code="already_committed", message="Sessão já foi fechada")

        if session.state == "abandoned":
            raise CommitError(code="abandoned", message="Sessão foi abandonada")

        # Check required checks are fresh
        required_checks = channel.config.get("required_checks_on_commit", [])
        checks = session.data.get("checks", {})
        now = timezone.now()

        for check_code in required_checks:
            check = checks.get(check_code)
            if not check:
                raise CommitError(
                    code="missing_check",
                    message=f"Check obrigatório não encontrado: {check_code}",
                    context={"check_code": check_code},
                )
            if check.get("rev") != session.rev:
                raise CommitError(
                    code="stale_check",
                    message=f"Check desatualizado: {check_code}",
                    context={
                        "check_code": check_code,
                        "check_rev": check.get("rev"),
                        "session_rev": session.rev,
                    },
                )
            result = check.get("result") or {}
            deadline = result.get("hold_expires_at")
            if deadline:
                expires_dt = CommitService._parse_iso_datetime(deadline)
                if expires_dt is not None and expires_dt <= now:
                    raise CommitError(
                        code="hold_expired",
                        message="Reserva expirada para este check.",
                        context={"check_code": check_code, "expires_at": deadline},
                    )
            for hold in result.get("holds", []):
                expires_at = hold.get("expires_at")
                if not expires_at:
                    continue
                expires_dt = CommitService._parse_iso_datetime(expires_at)
                if expires_dt is not None and expires_dt <= now:
                    raise CommitError(
                        code="hold_expired",
                        message="Reserva expirada para este check.",
                        context={"check_code": check_code, "hold_id": hold.get("hold_id"), "expires_at": expires_at},
                    )

        # Check no blocking issues
        issues = session.data.get("issues", [])
        blocking = [i for i in issues if i.get("blocking")]
        if blocking:
            raise CommitError(
                code="blocking_issues",
                message="Existem issues bloqueantes",
                context={"issues": blocking},
            )

        # Run validators (stage="commit")
        for validator in registry.get_validators(stage="commit"):
            validator.validate(channel=channel, session=session, ctx=ctx)

        # Create Order + OrderItems
        order = Order.objects.create(
            ref=generate_order_ref(),
            channel=channel,
            session_key=session_key,
            handle_type=session.handle_type,
            handle_ref=session.handle_ref,
            status=Order.Status.NEW,
            snapshot={
                "items": session.items,
                "data": session.data,
                "pricing": session.pricing,
                "rev": session.rev,
            },
            total_q=CommitService._calculate_total(session.items),
        )

        for item in session.items:
            # Usa line_total_q existente ou calcula se não existir
            line_total = item.get("line_total_q")
            if line_total is None:
                line_total = int(Decimal(str(item["qty"])) * item.get("unit_price_q", 0))

            OrderItem.objects.create(
                order=order,
                line_id=item["line_id"],
                sku=item["sku"],
                name=item.get("name", ""),
                qty=Decimal(str(item["qty"])),
                unit_price_q=item.get("unit_price_q", 0),
                line_total_q=int(line_total),
                meta=item.get("meta", {}),
            )

        # Create event
        OrderEvent.objects.create(
            order=order,
            type="created",
            actor=ctx.get("actor", "system"),
            payload={"from_session": session_key},
        )

        # Mark session as committed
        session.state = "committed"
        session.committed_at = timezone.now()
        session.commit_token = idempotency_key
        session.save()

        # Enqueue post-commit directives
        post_commit_directives = channel.config.get("post_commit_directives", [])
        stock_holds = None
        stock_check = checks.get("stock")
        if stock_check:
            stock_holds = (stock_check.get("result") or {}).get("holds")
        for topic in post_commit_directives:
            payload = {
                "order_ref": order.ref,
                "channel_code": channel.code,
                "session_key": session.session_key,
            }
            if topic == "stock.commit" and stock_holds:
                payload["holds"] = stock_holds
            Directive.objects.create(
                topic=topic,
                payload=payload,
            )

        return {
            "order_ref": order.ref,
            "order_id": order.pk,
            "status": "committed",
            "total_q": order.total_q,
            "items_count": len(session.items),
        }

    @staticmethod
    def _calculate_total(items: list[dict]) -> int:
        """
        Calcula total do pedido.

        Usa line_total_q se existir (pode ter sido calculado com lógica
        customizada como descontos). Se não existir, calcula qty * unit_price_q.
        """
        total = 0
        for item in items:
            line_total = item.get("line_total_q")
            if line_total is not None:
                total += int(line_total)
            else:
                qty = Decimal(str(item.get("qty", 0)))
                price = item.get("unit_price_q", 0)
                total += int(qty * price)
        return total

    @staticmethod
    def _parse_iso_datetime(value: str | None) -> datetime | None:
        """
        Parse ISO datetime string to timezone-aware datetime.

        If the input has no timezone info, it's assumed to be in UTC
        (not the server's local timezone) to ensure consistent behavior
        regardless of server configuration.
        """
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(value)
        except ValueError:
            return None
        if timezone.is_naive(dt):
            # Assume UTC for naive datetimes (safer than assuming local TZ)
            # Using datetime.timezone.utc (stdlib, no pytz needed)
            from datetime import timezone as dt_timezone
            dt = dt.replace(tzinfo=dt_timezone.utc)
        return dt


# =============================================================================
# SESSION WRITE SERVICE
# =============================================================================


class SessionWriteService:
    """
    Serviço para write-back de resultados de checks.

    Garante que apenas checks com rev compatível são aplicados (stale-safe).
    """

    @staticmethod
    @transaction.atomic
    def apply_check_result(
        session_key: str,
        channel_code: str,
        expected_rev: int,
        check_code: str,
        check_payload: dict,
        issues: list[dict],
    ) -> bool:
        """
        Aplica resultado de check à sessão.

        Args:
            session_key: Chave da sessão
            channel_code: Código do canal
            expected_rev: Rev esperado (stale-safe)
            check_code: Código do check (ex.: "stock")
            check_payload: Resultado do check
            issues: Issues detectadas

        Returns:
            True se aplicado, False se stale
        """
        log_context = {
            "check_code": check_code,
            "session_key": session_key,
            "channel_code": channel_code,
            "expected_rev": expected_rev,
            "has_issues": len(issues) > 0,
        }

        logger.info("Applying check result", extra=log_context)

        try:
            session = Session.objects.select_for_update().get(
                session_key=session_key,
                channel__code=channel_code,
            )
        except Session.DoesNotExist:
            logger.warning("Session not found for check result", extra=log_context)
            return False

        # Stale-safe: só aplica se rev confere
        if session.rev != expected_rev:
            logger.warning(
                "Stale rev for check result",
                extra={**log_context, "session_rev": session.rev},
            )
            return False

        # Só aplica em sessões abertas
        if session.state != "open":
            logger.warning(
                "Session not open for check result",
                extra={**log_context, "session_state": session.state},
            )
            return False

        # Aplica check
        if "checks" not in session.data:
            session.data["checks"] = {}

        session.data["checks"][check_code] = {
            "rev": session.rev,
            "at": timezone.now().isoformat(),
            "result": check_payload,
        }

        # Adiciona issues
        if "issues" not in session.data:
            session.data["issues"] = []

        # Remove issues antigas desta source
        session.data["issues"] = [
            i for i in session.data["issues"] if i.get("source") != check_code
        ]

        # Adiciona novas issues
        session.data["issues"].extend(issues)

        session.save()
        logger.info(
            "Check result applied successfully",
            extra={**log_context, "session_rev": session.rev},
        )
        return True


# =============================================================================
# RESOLVE SERVICE
# =============================================================================


class ResolveService:
    """
    Serviço para resolver issues delegando para resolvers registrados.
    """

    @staticmethod
    @transaction.atomic
    def resolve(
        session_key: str,
        channel_code: str,
        issue_id: str,
        action_id: str,
        ctx: dict | None = None,
    ) -> Session:
        """
        Resolve uma issue aplicando uma action.

        Args:
            session_key: Chave da sessão
            channel_code: Código do canal
            issue_id: ID da issue a resolver
            action_id: ID da action a aplicar
            ctx: Contexto adicional

        Returns:
            Session atualizada

        Raises:
            IssueResolveError: Se resolução falhar
        """
        ctx = ctx or {}

        # Busca sessão com lock para evitar race conditions
        try:
            session = Session.objects.select_for_update().get(
                session_key=session_key,
                channel__code=channel_code,
            )
        except Session.DoesNotExist:
            raise IssueResolveError(
                code="session_not_found",
                message=f"Sessão não encontrada: {channel_code}:{session_key}",
            )

        # Busca issue
        issues = session.data.get("issues", [])
        issue = None
        for i in issues:
            if i.get("id") == issue_id:
                issue = i
                break

        if not issue:
            raise IssueResolveError(
                code="issue_not_found",
                message=f"Issue não encontrada: {issue_id}",
            )

        # Busca resolver pela source
        source = issue.get("source")
        resolver = registry.get_issue_resolver(source)

        if not resolver:
            raise IssueResolveError(
                code="no_resolver",
                message=f"Nenhum resolver registrado para source: {source}",
            )

        # Delega para o resolver
        try:
            return resolver.resolve(
                session=session,
                issue=issue,
                action_id=action_id,
                ctx=ctx,
            )
        except IssueResolveError:
            raise
        except SessionError as exc:
            raise IssueResolveError(code=exc.code, message=exc.message, context=exc.context) from exc
        except ValidationError as exc:
            raise IssueResolveError(code=exc.code, message=exc.message, context=exc.context) from exc
        except Exception as exc:  # pragma: no cover - logger exercise tested via flow
            logger.exception(
                "Resolver %s falhou ao aplicar action %s na issue %s (sessão %s)",
                source,
                action_id,
                issue_id,
                session.session_key,
            )
            raise IssueResolveError(
                code="resolver_error",
                message="Resolver falhou ao aplicar action.",
                context={"source": source, "issue_id": issue_id, "action_id": action_id},
            ) from exc
