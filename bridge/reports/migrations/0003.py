from __future__ import unicode_literals

from django.db import migrations, models, transaction


def clear_coverages(apps, schema_editor):
    apps.get_model("reports", "CoverageArchive").objects.filter(archive='').delete()


def set_leaf_resources(apps, schema_editor):
    with transaction.atomic():
        for safe in apps.get_model("reports", "ReportSafe").objects\
                .filter(parent__reportcomponent__verification=True)\
                .select_related('parent__reportcomponent'):
            safe.wall_time = safe.parent.reportcomponent.wall_time
            safe.memory = safe.parent.reportcomponent.memory
            safe.save()
    with transaction.atomic():
        for unsafe in apps.get_model("reports", "ReportUnsafe").objects\
                .filter(parent__reportcomponent__verification=True)\
                .select_related('parent__reportcomponent'):
            unsafe.wall_time = unsafe.parent.reportcomponent.wall_time
            unsafe.memory = unsafe.parent.reportcomponent.memory
            unsafe.save()
    with transaction.atomic():
        for unknown in apps.get_model("reports", "ReportUnknown").objects\
                .filter(parent__reportcomponent__verification=True)\
                .select_related('parent__reportcomponent'):
            unknown.cpu_time = unknown.parent.reportcomponent.cpu_time
            unknown.wall_time = unknown.parent.reportcomponent.wall_time
            unknown.memory = unknown.parent.reportcomponent.memory
            unknown.save()


class Migration(migrations.Migration):
    dependencies = [('reports', '0002')]
    operations = [
        migrations.RunPython(clear_coverages),
        migrations.RunPython(set_leaf_resources),
    ]