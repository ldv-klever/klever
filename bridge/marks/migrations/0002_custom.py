# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


def add_default_error(apps, schema_editor):
    mr_model = apps.get_model("marks", "MarkUnsafeReport")
    for mr in mr_model.objects.all():
        if mr.broken:
            mr.error = 'Unknown error'
            mr.save()


class Migration(migrations.Migration):

    dependencies = [('marks', '0001_initial')]

    operations = [
        migrations.AddField(model_name='markunsafereport', name='error', field=models.TextField(null=True)),
        migrations.RunPython(add_default_error)
    ]
