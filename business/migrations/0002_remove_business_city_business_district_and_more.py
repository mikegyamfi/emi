# Generated by Django 5.2 on 2025-04-30 13:13

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('business', '0001_initial'),
        ('market_intelligence', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='business',
            name='city',
        ),
        migrations.AddField(
            model_name='business',
            name='district',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='market_intelligence.district'),
        ),
        migrations.AddField(
            model_name='business',
            name='tin_number',
            field=models.CharField(default='hrllo', max_length=100, unique=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='business',
            name='town',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='market_intelligence.town'),
        ),
        migrations.AlterField(
            model_name='business',
            name='region',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='market_intelligence.region'),
        ),
    ]
