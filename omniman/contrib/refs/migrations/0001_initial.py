import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Ref",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "ref_type",
                    models.CharField(
                        db_index=True,
                        help_text="Slug do RefType (ex: POS_TABLE, ORDER_NUMBER)",
                        max_length=32,
                    ),
                ),
                (
                    "target_kind",
                    models.CharField(
                        choices=[("SESSION", "Session"), ("ORDER", "Order")],
                        help_text="Tipo do target associado",
                        max_length=8,
                    ),
                ),
                (
                    "target_id",
                    models.UUIDField(
                        db_index=True,
                        help_text="ID do target (Session.id ou Order.id)",
                    ),
                ),
                (
                    "value",
                    models.CharField(
                        db_index=True,
                        help_text="Valor normalizado do localizador (ex: '12', '001', 'ABC123')",
                        max_length=64,
                    ),
                ),
                (
                    "scope",
                    models.JSONField(
                        default=dict,
                        help_text="Scope de unicidade (ex: {store_id: 1, business_date: '2025-12-19'})",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        db_index=True,
                        default=True,
                        help_text="Se False, Ref está desativada (não resolve)",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Ref",
                "verbose_name_plural": "Refs",
            },
        ),
        migrations.CreateModel(
            name="RefSequence",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "sequence_name",
                    models.CharField(
                        db_index=True,
                        help_text="Nome da sequência (geralmente o RefType.slug)",
                        max_length=32,
                    ),
                ),
                (
                    "scope_hash",
                    models.CharField(
                        db_index=True,
                        help_text="Hash do scope para particionamento",
                        max_length=64,
                    ),
                ),
                (
                    "scope",
                    models.JSONField(
                        default=dict,
                        help_text="Scope original (para debug/auditoria)",
                    ),
                ),
                (
                    "last_value",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="Último valor gerado nesta sequência",
                    ),
                ),
            ],
            options={
                "verbose_name": "Ref Sequence",
                "verbose_name_plural": "Ref Sequences",
            },
        ),
        migrations.AddIndex(
            model_name="ref",
            index=models.Index(
                fields=["ref_type", "value", "is_active"],
                name="ref_type_value_active_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="ref",
            index=models.Index(
                fields=["target_kind", "target_id", "is_active"],
                name="ref_target_active_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="refsequence",
            constraint=models.UniqueConstraint(
                fields=("sequence_name", "scope_hash"),
                name="unique_sequence_scope",
            ),
        ),
    ]
