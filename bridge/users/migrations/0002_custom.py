# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='view',
            name='type',
            field=models.CharField(choices=[('1', 'job tree'), ('2', 'job view'), ('3', 'component children list'), ('4', 'unsafes list'), ('5', 'safes list'), ('6', 'unknowns list'), ('7', 'unsafe marks'), ('8', 'safe marks'), ('9', 'unknown marks')], default='1', max_length=1),
        ),
    ]
