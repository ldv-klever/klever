from __future__ import unicode_literals

from django.db import migrations


def set_marks_type(apps, schema_editor):
    apps.get_model("marks", "MarkUnsafeReport").objects.filter(manual=True).update(type='1')
    apps.get_model("marks", "MarkSafeReport").objects.filter(manual=True).update(type='1')
    apps.get_model("marks", "MarkUnknownReport").objects.filter(manual=True).update(type='1')


class Migration(migrations.Migration):
    dependencies = [('marks', '0010_auto_20170505_1534')]
    operations = [migrations.RunPython(set_marks_type)]