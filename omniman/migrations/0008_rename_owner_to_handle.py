"""
Migration: Rename owner_type/owner_ref → handle_type/handle_ref

Breaking change v0.6.0:
- Semântica: "handle" é neutro (identificador de contexto), não implica "dono"
- Consistente com terminologia do DECISION_COMPASS.md
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("omniman", "0007_rename_status_created_to_new"),
    ]

    operations = [
        # ======== Session ========
        # Remover constraint antiga
        migrations.RemoveConstraint(
            model_name="session",
            name="uniq_open_session_owner",
        ),
        # Renomear campos
        migrations.RenameField(
            model_name="session",
            old_name="owner_type",
            new_name="handle_type",
        ),
        migrations.RenameField(
            model_name="session",
            old_name="owner_ref",
            new_name="handle_ref",
        ),
        # Recriar constraint com novo nome
        migrations.AddConstraint(
            model_name="session",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    ("state", "open"),
                    ("handle_type__isnull", False),
                    ("handle_ref__isnull", False),
                ),
                fields=["channel", "handle_type", "handle_ref"],
                name="uniq_open_session_handle",
            ),
        ),

        # ======== Order ========
        migrations.RenameField(
            model_name="order",
            old_name="owner_type",
            new_name="handle_type",
        ),
        migrations.RenameField(
            model_name="order",
            old_name="owner_ref",
            new_name="handle_ref",
        ),
    ]
