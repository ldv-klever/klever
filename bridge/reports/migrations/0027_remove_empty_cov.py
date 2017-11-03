from __future__ import unicode_literals

from django.db import migrations


def clear_coverages(apps, schema_editor):
    apps.get_model("reports", "CoverageArchive").objects.filter(archive='').delete()


class Migration(migrations.Migration):
    dependencies = [('reports', '0026_auto_20171012_1416')]
    operations = [migrations.RunPython(clear_coverages)]
