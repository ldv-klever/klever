from __future__ import unicode_literals

from django.db import migrations


def rename_jobs(apps, schema_editor):
    names = set()
    cnt = 1
    for job in apps.get_model("jobs", "Job").objects.all():
        if job.name in names:
            job.name = "%s #UNIQUE-%s" % (job.name, cnt)
            job.save()
            cnt += 1
        else:
            names.add(job.name)


class Migration(migrations.Migration):
    dependencies = [('jobs', '0012_remove_jobhistory_name')]
    operations = [migrations.RunPython(rename_jobs)]