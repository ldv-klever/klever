from __future__ import unicode_literals

from django.db import migrations


def clear_cache(apps, schema_editor):
    apps.get_model("reports", "CompareJobsInfo").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [('reports', '0012_reportcomponent_coverage_arch')]
    operations = [migrations.RunPython(clear_cache)]