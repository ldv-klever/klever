from __future__ import unicode_literals

from django.db import migrations, models


def set_marks_type(apps, schema_editor):
    for mrep in apps.get_model("marks", "MarkUnsafeReport").objects.filter(manual=True):
        mrep.type = '1'
        mrep.author = mrep.mark.author
        mrep.save()
    for mrep in apps.get_model("marks", "MarkSafeReport").objects.filter(manual=True):
        mrep.type = '1'
        mrep.author = mrep.mark.author
        mrep.save()
    for mrep in apps.get_model("marks", "MarkUnknownReport").objects.filter(manual=True):
        mrep.type = '1'
        mrep.author = mrep.mark.author
        mrep.save()


class Migration(migrations.Migration):
    dependencies = [('marks', '0010_auto_20170505_1534')]
    operations = [migrations.RunPython(set_marks_type)]