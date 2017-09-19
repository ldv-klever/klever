from __future__ import unicode_literals

from django.db import migrations


def change_func_names_and_desc(apps, schema_editor):
    MarkUnsafeConvert = apps.get_model("marks", "MarkUnsafeConvert")
    MarkUnsafeConvert.objects.filter(name='call_forests').update(name='callback_call_forests')
    MarkUnsafeConvert.objects.filter(name='all_forests').update(name='thread_call_forests')
    MarkUnsafeCompare = apps.get_model("marks", "MarkUnsafeCompare")
    MarkUnsafeCompare.objects.filter(name='call_forests_compare').update(name='callback_call_forests')
    MarkUnsafeCompare.objects.filter(name='all_forests_compare').update(name='thread_call_forests')


class Migration(migrations.Migration):
    dependencies = [('marks', '0015_auto_20170714_1459')]
    operations = [migrations.RunPython(change_func_names_and_desc)]
