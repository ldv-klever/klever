from __future__ import unicode_literals

from django.db import migrations, models
import reports.models


class Migration(migrations.Migration):
    dependencies = [('reports', '0003')]

    operations = [
        migrations.AlterField(model_name='coveragearchive', name='archive',
                              field=models.FileField(upload_to=reports.models.get_coverage_arch_dir)),
    ]