from __future__ import unicode_literals

from django.db import migrations


def set_tags_author(apps, schema_editor):
    root_job = apps.get_model("jobs", "Job").objects.filter(parent=None).exclude(change_author=None).first()
    if root_job:
        apps.get_model("marks", "SafeTag").objects.all().update(author=root_job.change_author)
        apps.get_model("marks", "UnsafeTag").objects.all().update(author=root_job.change_author)
    else:
        apps.get_model("marks", "SafeTag").objects.all().delete()
        apps.get_model("marks", "UnsafeTag").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ('marks', '0003_add_author_field'),
        ('jobs', '0007_remove_lightweight')
    ]
    operations = [migrations.RunPython(set_tags_author)]
