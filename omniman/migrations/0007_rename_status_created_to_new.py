# Generated manually on 2025-12-18

from django.db import migrations, models


def migrate_created_to_new(apps, schema_editor):
    """Converte status 'created' para 'new'."""
    Order = apps.get_model('omniman', 'Order')
    Order.objects.filter(status='created').update(status='new')


def reverse_new_to_created(apps, schema_editor):
    """Reverte 'new' para 'created'."""
    Order = apps.get_model('omniman', 'Order')
    Order.objects.filter(status='new').update(status='created')


class Migration(migrations.Migration):

    dependencies = [
        ('omniman', '0006_order_status_canonical'),
    ]

    operations = [
        # Primeiro converte os dados existentes
        migrations.RunPython(migrate_created_to_new, reverse_new_to_created),
        # Depois altera o campo com os novos choices
        migrations.AlterField(
            model_name='order',
            name='status',
            field=models.CharField(
                choices=[
                    ('new', 'novo'),
                    ('confirmed', 'confirmado'),
                    ('processing', 'em preparo'),
                    ('ready', 'pronto'),
                    ('dispatched', 'despachado'),
                    ('delivered', 'entregue'),
                    ('completed', 'concluído'),
                    ('cancelled', 'cancelado'),
                    ('returned', 'devolvido'),
                ],
                db_index=True,
                default='new',
                max_length=32,
                verbose_name='status',
            ),
        ),
    ]

