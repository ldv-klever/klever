from __future__ import unicode_literals

from django.db import migrations


def update_job_status(apps, schema_editor):
    apps.get_model("jobs", "Job").objects.filter(status='7').update(status='8')
    apps.get_model("jobs", "Job").objects.filter(status='6').update(status='7')
    apps.get_model("jobs", "RunHistory").objects.filter(status='7').update(status='8')
    apps.get_model("jobs", "RunHistory").objects.filter(status='6').update(status='7')


class Migration(migrations.Migration):
    dependencies = [('jobs', '0010_auto_20171218_1724')]
    operations = [migrations.RunPython(update_job_status)]