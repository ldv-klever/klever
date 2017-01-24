from __future__ import unicode_literals

from django.db import migrations


def get_verifiers_time(apps, schema_editor):
    ReportUnsafe = apps.get_model("reports", "ReportUnsafe")
    ReportSafe = apps.get_model("reports", "ReportSafe")
    ReportComponent = apps.get_model("reports", "ReportComponent")
    for unsafe in ReportUnsafe.objects.filter(root__job__light=False):
        cpu_time = ReportComponent.objects.get(id=unsafe.parent_id).cpu_time
        if cpu_time is not None:
            unsafe.verifier_time = cpu_time
            unsafe.save()
    for safe in ReportSafe.objects.filter(root__job__light=False):
        cpu_time = ReportComponent.objects.get(id=safe.parent_id).cpu_time
        if cpu_time is not None:
            safe.verifier_time = cpu_time
            safe.save()


class Migration(migrations.Migration):
    dependencies = [('reports', '0002_verifier_time')]
    operations = [migrations.RunPython(get_verifiers_time)]
