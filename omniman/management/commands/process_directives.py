from __future__ import annotations

import time
from typing import Sequence

from django.core.management import BaseCommand
from django.utils import timezone

from omniman import registry
from omniman.models import Directive


class Command(BaseCommand):
    help = "Processa diretivas enfileiradas usando os handlers registrados."

    def add_arguments(self, parser):
        parser.add_argument(
            "--topic",
            action="append",
            dest="topics",
            default=None,
            help="Topic específico para processar (pode repetir a opção). Omitido = todos os registrados.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="Quantidade máxima de diretivas processadas nesta execução (default: 50).",
        )
        parser.add_argument(
            "--watch",
            action="store_true",
            help="Mantém o comando rodando em loop (worker simples).",
        )
        parser.add_argument(
            "--interval",
            type=float,
            default=2.0,
            help="Intervalo (segundos) entre execuções quando usado com --watch (default: 2s).",
        )

    def handle(self, *args, **opts):
        topics: Sequence[str] | None = opts.get("topics")
        if topics:
            topics = [t for t in topics if t]
        else:
            topics = sorted(registry.get_directive_handlers().keys())

        if not topics:
            self.stdout.write(self.style.WARNING("Nenhum handler registrado. Nada a fazer."))
            return

        limit = max(int(opts.get("limit") or 1), 1)
        watch = bool(opts.get("watch"))
        interval = max(float(opts.get("interval") or 1.0), 0.5)

        def _cycle():
            now = timezone.now()
            qs = (
                Directive.objects.filter(status="queued", topic__in=topics, available_at__lte=now)
                .order_by("available_at", "id")
            )
            directives = list(qs[:limit])
            if not directives:
                self.stdout.write(self.style.WARNING("Nenhuma diretiva em fila para os tópicos informados."))
                return False

            processed = 0
            failures = 0

            for directive in directives:
                handler = registry.get_directive_handler(directive.topic)
                if not handler:
                    self.stdout.write(
                        self.style.WARNING(f"Ignorando tópico {directive.topic}: nenhum handler registrado.")
                    )
                    continue

                directive.status = "running"
                directive.attempts += 1
                directive.save(update_fields=["status", "attempts", "updated_at"])

                try:
                    handler.handle(message=directive, ctx={"actor": "process_directives"})
                    processed += 1
                except Exception as exc:  # pragma: no cover - mensagem impressa varia com exceção
                    directive.status = "failed"
                    directive.last_error = str(exc)
                    directive.save(update_fields=["status", "last_error", "updated_at"])
                    failures += 1
                    self.stderr.write(
                        self.style.ERROR(f"Erro ao processar {directive.topic} #{directive.pk}: {exc}")
                    )

            self.stdout.write(self.style.SUCCESS(f"Diretivas concluídas: {processed}"))
            if failures:
                self.stdout.write(self.style.ERROR(f"Diretivas com erro: {failures}"))
            return True

        if not watch:
            _cycle()
            return

        self.stdout.write(self.style.WARNING("Worker iniciado: Ctrl+C para sair."))
        try:
            while True:
                had_work = _cycle()
                time.sleep(interval if had_work else interval)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Worker encerrado."))
