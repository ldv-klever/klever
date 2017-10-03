from __future__ import unicode_literals

from django.db import migrations


def set_convert(apps, schema_editor):
    conversions = {}
    for conv_f in apps.get_model("marks", "MarkUnsafeConvert").objects.all():
        conversions[conv_f.name] = conv_f

    for comp_f in apps.get_model("marks", "MarkUnsafeCompare").objects.all():
        if comp_f.name in conversions:
            comp_f.convert = conversions[comp_f.name]
            comp_f.save()
        else:
            comp_f.delete()


class Migration(migrations.Migration):
    dependencies = [('marks', '0017_markunsafecompare_convert')]
    operations = [migrations.RunPython(set_convert)]
