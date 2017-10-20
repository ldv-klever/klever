from __future__ import unicode_literals

from django.db import migrations, models


def clear_coverages(apps, schema_editor):
    apps.get_model("reports", "CoverageArchive").objects.filter(archive='').delete()


class Migration(migrations.Migration):
    dependencies = [('reports', '0025_count_covnum')]
    operations = [migrations.RunPython(clear_coverages)]
