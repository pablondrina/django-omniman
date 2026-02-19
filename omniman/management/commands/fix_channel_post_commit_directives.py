"""
Comando para garantir que todos os canais ativos tenham post_commit_directives configurado.

Isso é necessário para que a execução automática de diretivas funcione no Admin.
"""

from django.core.management.base import BaseCommand

from omniman.models import Channel


class Command(BaseCommand):
    help = "Garante que todos os canais ativos tenham post_commit_directives configurado"

    def handle(self, *args, **options):
        channels = Channel.objects.filter(is_active=True)
        updated_count = 0

        for channel in channels:
            config = channel.config.copy()
            post_commit = config.get("post_commit_directives", [])

            if "stock.commit" not in post_commit:
                post_commit.append("stock.commit")
                config["post_commit_directives"] = post_commit
                channel.config = config
                channel.save(update_fields=["config"])
                updated_count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f'✓ Canal "{channel.code}" atualizado com post_commit_directives'
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'  Canal "{channel.code}" já está configurado')
                )

        if updated_count == 0:
            self.stdout.write(self.style.SUCCESS("Todos os canais já estão configurados!"))
        else:
            self.stdout.write(
                self.style.SUCCESS(f"\n{updated_count} canal(is) atualizado(s).")
            )


