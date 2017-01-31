from __future__ import unicode_literals

from django.db import migrations


def clear_converted_cache(apps, schema_editor):
    apps.get_model("marks", "ErrorTraceConvertionCache").objects.filter(function__name='call_forests').delete()
    apps.get_model("marks", "ErrorTraceConvertionCache").objects.filter(function__name='forests_callbacks').delete()


class Migration(migrations.Migration):
    dependencies = [('marks', '0001_initial')]
    operations = [migrations.RunPython(clear_converted_cache)]