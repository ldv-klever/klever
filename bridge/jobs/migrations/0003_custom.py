from __future__ import unicode_literals

from django.db import migrations


def update_weight(apps, schema_editor):
    apps.get_model("jobs", "Job").objects.filter(light=True).update(weight='2')


class Migration(migrations.Migration):
    dependencies = [('jobs', '0002_auto')]
    operations = [migrations.RunPython(update_weight)]
