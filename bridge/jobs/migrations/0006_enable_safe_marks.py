from __future__ import unicode_literals

from django.db import migrations


def enable_safe_marks_for_old_jobs(apps, schema_editor):
    apps.get_model("jobs", "Job").objects.all().update(safe_marks=True)


class Migration(migrations.Migration):
    dependencies = [('jobs', '0005_job_safe_marks')]
    operations = [migrations.RunPython(enable_safe_marks_for_old_jobs)]