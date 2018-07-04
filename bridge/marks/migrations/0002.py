from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('marks', '0001_initial')]

    operations = [
        migrations.AddField(model_name='markunknownhistory', name='is_regexp', field=models.BooleanField(default=True)),
        migrations.AddField(model_name='markunknown', name='is_regexp', field=models.BooleanField(default=True)),
    ]
