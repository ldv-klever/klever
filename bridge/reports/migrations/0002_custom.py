# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('jobs', '0001_initial'),
        ('reports', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='reportcomponent',
            name='archive',
            field=models.ForeignKey(related_name='reports1', on_delete=django.db.models.deletion.SET_NULL, to='jobs.File', null=True),
        ),

        migrations.AddField(
            model_name='reportsafe',
            name='archive',
            field=models.ForeignKey(to='jobs.File', null=True),
            preserve_default=False,
        ),

        migrations.AddField(
            model_name='reportunknown',
            name='archive',
            field=models.ForeignKey(to='jobs.File', null=True),
            preserve_default=False,
        ),

        migrations.AddField(
            model_name='reportunsafe',
            name='archive',
            field=models.ForeignKey(to='jobs.File', null=True),
            preserve_default=False,
        )
    ]
