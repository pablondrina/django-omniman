from __future__ import annotations

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("omniman", "0004_sessionline"),
    ]

    operations = [
        # 1. Remove old constraint
        migrations.RemoveConstraint(
            model_name="sessionline",
            name="uniq_session_line_id",
        ),
        # 2. Rename model
        migrations.RenameModel(
            old_name="SessionLine",
            new_name="SessionItem",
        ),
        # 3. Update related_name (lines -> session_items)
        migrations.AlterField(
            model_name="sessionitem",
            name="session",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="session_items",
                to="omniman.session",
                verbose_name="sessão",
            ),
        ),
        # 4. Add new constraint with updated name
        migrations.AddConstraint(
            model_name="sessionitem",
            constraint=models.UniqueConstraint(
                fields=("session", "line_id"), name="uniq_session_item_line_id"
            ),
        ),
    ]
