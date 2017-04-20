from __future__ import unicode_literals

from django.db import migrations


def remove_light_jobs(apps, schema_editor):
    apps.get_model("jobs", "Job").objects.filter(weight='2').delete()


class Migration(migrations.Migration):
    dependencies = [('jobs', '0007_remove_lightweight')]
    operations = [migrations.RunPython(remove_light_jobs)]
