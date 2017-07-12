from __future__ import unicode_literals

from django.db import migrations


def update_confirmed(apps, schema_editor):
    from bridge.vars import ASSOCIATION_TYPE
    MarkSafeReport = apps.get_model("marks", "MarkSafeReport")
    MarkUnsafeReport = apps.get_model("marks", "MarkUnsafeReport")
    ReportUnsafe = apps.get_model("reports", "ReportUnsafe")
    ReportSafe = apps.get_model("reports", "ReportSafe")

    safes_with_confirmed = set(r_id for r_id, in MarkSafeReport.objects.filter(type=ASSOCIATION_TYPE[1][0]).values_list('report_id'))
    unsafes_with_confirmed = set(r_id for r_id, in MarkUnsafeReport.objects.filter(type=ASSOCIATION_TYPE[1][0]).values_list('report_id'))
    ReportSafe.objects.filter(id__in=safes_with_confirmed).update(has_confirmed=True)
    ReportUnsafe.objects.filter(id__in=unsafes_with_confirmed).update(has_confirmed=True)


class Migration(migrations.Migration):
    dependencies = [('reports', '0007_auto_20170526_1727'), ('marks', '0013_auto_20170516_1157')]
    operations = [migrations.RunPython(update_confirmed)]
