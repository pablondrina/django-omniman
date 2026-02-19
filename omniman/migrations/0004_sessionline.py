from __future__ import annotations

from django.db import migrations, models
import django.db.models.deletion


def copy_session_items(apps, schema_editor):
    Session = apps.get_model("omniman", "Session")
    SessionLine = apps.get_model("omniman", "SessionLine")
    db_alias = schema_editor.connection.alias

    for session in Session.objects.using(db_alias).all():
        items = session.items or []
        for idx, item in enumerate(items):
            line_id = item.get("line_id") or f"legacy-{session.pk}-{idx}"
            SessionLine.objects.using(db_alias).create(
                session=session,
                line_id=line_id,
                sku=item.get("sku", ""),
                name=item.get("name", ""),
                qty=item.get("qty", 0) or 0,
                unit_price_q=item.get("unit_price_q", 0) or 0,
                line_total_q=item.get("line_total_q", 0) or 0,
                meta=item.get("meta", {}) or {},
            )


class Migration(migrations.Migration):

    dependencies = [
        ("omniman", "0003_alter_channel_options_alter_directive_options_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="SessionLine",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("line_id", models.CharField(max_length=64, verbose_name="ID da linha")),
                ("sku", models.CharField(blank=True, default="", max_length=64, verbose_name="SKU")),
                ("name", models.CharField(blank=True, default="", max_length=200, verbose_name="nome")),
                (
                    "qty",
                    models.DecimalField(decimal_places=3, max_digits=12, verbose_name="quantidade"),
                ),
                (
                    "unit_price_q",
                    models.BigIntegerField(default=0, verbose_name="preço unitário (q)"),
                ),
                (
                    "line_total_q",
                    models.BigIntegerField(default=0, verbose_name="total da linha (q)"),
                ),
                (
                    "meta",
                    models.JSONField(blank=True, default=dict, verbose_name="metadados"),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="criado em"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="atualizado em"),
                ),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lines",
                        to="omniman.session",
                        verbose_name="sessão",
                    ),
                ),
            ],
            options={
                "verbose_name": "item da sessão",
                "verbose_name_plural": "itens da sessão",
            },
        ),
        migrations.AddConstraint(
            model_name="sessionline",
            constraint=models.UniqueConstraint(
                fields=("session", "line_id"), name="uniq_session_line_id"
            ),
        ),
        migrations.RunPython(copy_session_items, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="session",
            name="items",
        ),
    ]
