# Generated by Django 5.2 on 2025-05-05 10:01

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('product_service_management', '0003_alter_attributes_description_alter_attributes_value'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Cart',
            fields=[
                ('cart_id', models.UUIDField(editable=False, primary_key=True, serialize=False)),
                ('session_key', models.CharField(blank=True, db_index=True, max_length=40, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='CartItem',
            fields=[
                ('cart_item_id', models.UUIDField(editable=False, primary_key=True, serialize=False)),
                ('quantity', models.PositiveIntegerField()),
                ('cart', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='cart_management.cart')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='product_service_management.product')),
            ],
        ),
        migrations.AddConstraint(
            model_name='cart',
            constraint=models.UniqueConstraint(condition=models.Q(('user__isnull', False)), fields=('user',), name='unique_user_cart'),
        ),
        migrations.AddConstraint(
            model_name='cart',
            constraint=models.UniqueConstraint(condition=models.Q(('session_key__isnull', False)), fields=('session_key',), name='unique_session_cart'),
        ),
        migrations.AlterUniqueTogether(
            name='cartitem',
            unique_together={('cart', 'product')},
        ),
    ]
