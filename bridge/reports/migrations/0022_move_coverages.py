from __future__ import unicode_literals

from django.db import migrations


def move_coverages(apps, schema_editor):
    CoverageArchive = apps.get_model("reports", "CoverageArchive")
    ReportComponent = apps.get_model("reports", "ReportComponent")

    for r in ReportComponent.objects.exclude(coverage=''):
        carch = CoverageArchive(report=r)
        carch.archive.name = r.coverage.name
        carch.save()
    apps.get_model("reports", "CoverageDataStatistics").objects.all().delete()
    apps.get_model("reports", "CoverageFile").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [('reports', '0021_coveragearchive')]
    operations = [migrations.RunPython(move_coverages)]
