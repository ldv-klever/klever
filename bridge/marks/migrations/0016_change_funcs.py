from __future__ import unicode_literals

from django.db import migrations

desc1 = """
This function is extracting the error trace call stack forests.
The forest is a couple of call trees under callback action.
Call tree is tree of function names in their execution order.
All its leaves are names of functions which calls or statements
are marked with the "note" or "warn" attribute. Returns list of forests.
"""
desc2 = """
This function is extracting the error trace call stack forests.
The forest is a couple of call trees in the same thread
if it doesn't have callback actions at all.
Otherwise the forest is a couple of call trees under callback action.
Call tree is tree of function names in their execution order.
All its leaves are names of functions which calls or statements
are marked with the "note" or "warn" attribute. Return list of forests.
"""
desc3 = '\nJaccard index of "callback_call_forests" convertion.\n'
desc4 = '\nJaccard index of "thread_call_forests" convertion.\n'


def change_func_names_and_desc(apps, schema_editor):
    MarkUnsafeConvert = apps.get_model("marks", "MarkUnsafeConvert")
    MarkUnsafeConvert.objects.filter(name='call_forests').update(name='callback_call_forests', description=desc1)
    MarkUnsafeConvert.objects.filter(name='all_forests').update(name='thread_call_forests', description=desc2)
    MarkUnsafeCompare = apps.get_model("marks", "MarkUnsafeCompare")
    MarkUnsafeCompare.objects.filter(name='call_forests_compare').update(name='callback_call_forests', description=desc3)
    MarkUnsafeCompare.objects.filter(name='all_forests_compare').update(name='thread_call_forests', description=desc4)


class Migration(migrations.Migration):
    dependencies = [('marks', '0015_auto_20170714_1459')]
    operations = [migrations.RunPython(change_func_names_and_desc)]
