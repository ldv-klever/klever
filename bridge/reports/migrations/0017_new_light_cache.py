from __future__ import unicode_literals

from django.db import migrations


def fill_resources(apps, schema_editor):
    ComponentResource = apps.get_model("reports", "LightResource")
    LightResource = apps.get_model("reports", "LightResource")

    cores = {}
    for report in apps.get_model("reports", "ReportComponent").objects.filter(parent=None):
        cores[report.root_id] = report.id

    resources = []
    for lr in LightResource.objects.all():
        resources.append(ComponentResource(
            report_id=cores[lr.report_id], component=lr.component,
            cpu_time=lr.cpu_time, wall_time=lr.wall_time, memory=lr.memory
        ))
    ComponentResource.objects.bulk_create(resources)
    LightResource.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [('reports', '0016_create_coverage_cache')]
    operations = [migrations.RunPython(fill_resources)]
