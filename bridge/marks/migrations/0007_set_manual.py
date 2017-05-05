from __future__ import unicode_literals

from django.db import migrations
from django.db.models import F


def set_manual(apps, schema_editor):
    apps.get_model("marks", "MarkSafeReport").objects.filter(report=F('mark__prime')).update(manual=True)
    apps.get_model("marks", "MarkUnsafeReport").objects.filter(report=F('mark__prime')).update(manual=True)
    apps.get_model("marks", "MarkUnknownReport").objects.filter(report=F('mark__prime')).update(manual=True)


class Migration(migrations.Migration):
    dependencies = [
        ('marks', '0006_mr_manual')
    ]
    operations = [migrations.RunPython(set_manual)]
