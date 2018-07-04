from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('jobs', '0001_initial')]

    operations = [
        migrations.AlterField(model_name='job', name='status', field=models.CharField(choices=[
            ('0', 'Not solved'), ('1', 'Pending'), ('2', 'Is solving'), ('3', 'Solved'), ('4', 'Failed'),
            ('5', 'Corrupted'), ('6', 'Cancelling'), ('7', 'Cancelled'), ('8', 'Terminated')
        ], default='0', max_length=1)),
        migrations.AlterField(model_name='runhistory', name='status', field=models.CharField(choices=[
            ('0', 'Not solved'), ('1', 'Pending'), ('2', 'Is solving'), ('3', 'Solved'), ('4', 'Failed'),
            ('5', 'Corrupted'), ('6', 'Cancelling'), ('7', 'Cancelled'), ('8', 'Terminated')
        ], default='1', max_length=1)),
        migrations.RemoveField(model_name='job', name='type'),
        migrations.RemoveField(model_name='jobhistory', name='name')
    ]
