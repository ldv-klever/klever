from __future__ import unicode_literals

from django.db import migrations


def set_verification(apps, schema_editor):
    ReportComponent = apps.get_model("reports", "ReportComponent")
    ReportUnsafe = apps.get_model("reports", "ReportUnsafe")
    ReportSafe = apps.get_model("reports", "ReportSafe")
    ReportUnknown = apps.get_model("reports", "ReportUnknown")
    verification_reports = set()
    for leaf in ReportUnsafe.objects.exclude(parent__parent=None):
        if leaf.parent.parent is not None:
            verification_reports.add(leaf.parent_id)
    for leaf in ReportSafe.objects.exclude(parent__parent=None):
        if leaf.parent.parent is not None:
            verification_reports.add(leaf.parent_id)
    for leaf in ReportUnknown.objects.exclude(parent__parent=None):
        if leaf.parent.parent is not None:
            verification_reports.add(leaf.parent_id)
    ReportComponent.objects.filter(id__in=verification_reports).update(verification=True)


class Migration(migrations.Migration):
    dependencies = [('reports', '0004_auto')]
    operations = [migrations.RunPython(set_verification)]
