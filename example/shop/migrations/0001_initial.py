# Generated migration for example shop

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Product",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("sku", models.CharField(max_length=64, unique=True, verbose_name="SKU")),
                ("name", models.CharField(max_length=200, verbose_name="name")),
                (
                    "description",
                    models.TextField(blank=True, default="", verbose_name="description"),
                ),
                ("price_q", models.BigIntegerField(default=0, verbose_name="price (q)")),
                ("is_active", models.BooleanField(default=True, verbose_name="active")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="created at")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="updated at")),
            ],
            options={
                "verbose_name": "product",
                "verbose_name_plural": "products",
                "ordering": ("name",),
            },
        ),
    ]
