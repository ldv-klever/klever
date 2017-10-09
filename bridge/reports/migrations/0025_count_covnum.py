from __future__ import unicode_literals

from django.db import migrations, models


def count_covnum(apps, schema_editor):
    reports_with_cov = set(x for x, in apps.get_model("reports", "CoverageArchive").objects.values_list('report_id'))
    apps.get_model("reports", "ReportComponent").objects.filter(id__in=reports_with_cov).update(covnum=1)


class Migration(migrations.Migration):
    dependencies = [('reports', '0024_reportcomponent_covnum')]
    operations = [migrations.RunPython(count_covnum)]
