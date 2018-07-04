from __future__ import unicode_literals

from django.db import migrations, models


def update_job_status(apps, schema_editor):
    apps.get_model("jobs", "Job").objects.filter(status='7').update(status='8')
    apps.get_model("jobs", "Job").objects.filter(status='6').update(status='7')
    apps.get_model("jobs", "RunHistory").objects.filter(status='7').update(status='8')
    apps.get_model("jobs", "RunHistory").objects.filter(status='6').update(status='7')


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
    dependencies = [('jobs', '0002')]
    operations = [
        migrations.RunPython(update_job_status),
        migrations.RunPython(rename_jobs)
    ]



