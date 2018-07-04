from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('jobs', '0003')]

    operations = [migrations.AlterField(model_name='job', name='name',
                                        field=models.CharField(db_index=True, max_length=150, unique=True))]
