# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [('reports', '0004_custom')]

    operations = [
        migrations.AlterField(model_name='reportsafe', name='archive', field=models.ForeignKey(to='jobs.File')),
        migrations.AlterField(model_name='reportunknown', name='archive', field=models.ForeignKey(to='jobs.File')),
        migrations.AlterField(model_name='reportunsafe', name='archive', field=models.ForeignKey(to='jobs.File'))
    ]
