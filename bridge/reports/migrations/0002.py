from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('reports', '0001_initial')]

    operations = [
        migrations.AlterField(model_name='comparejobscache', name='reports1', field=models.TextField()),
        migrations.AlterField(model_name='comparejobscache', name='reports2', field=models.TextField()),
        migrations.AlterField(model_name='comparejobscache', name='verdict1', field=models.CharField(choices=[
            ('0', 'Total safe'), ('1', 'Found all unsafes'), ('2', 'Found not all unsafes'),
            ('3', 'Unknown'), ('4', 'Unmatched'), ('5', 'Broken')
        ], max_length=1)),
        migrations.AlterField(model_name='comparejobscache', name='verdict2', field=models.CharField(choices=[
            ('0', 'Total safe'), ('1', 'Found all unsafes'), ('2', 'Found not all unsafes'),
            ('3', 'Unknown'), ('4', 'Unmatched'), ('5', 'Broken')
        ], max_length=1)),
        migrations.RenameField(model_name='reportsafe', old_name='verifier_time', new_name='cpu_time'),
        migrations.RenameField(model_name='reportunsafe', old_name='verifier_time', new_name='cpu_time'),
        migrations.AddField(model_name='reportsafe', name='memory', field=models.BigIntegerField(default=0),
                            preserve_default=False),
        migrations.AddField(model_name='reportsafe', name='wall_time', field=models.BigIntegerField(default=0),
                            preserve_default=False),
        migrations.AddField(model_name='reportunknown', name='cpu_time', field=models.BigIntegerField(null=True)),
        migrations.AddField(model_name='reportunknown', name='memory', field=models.BigIntegerField(null=True)),
        migrations.AddField(model_name='reportunknown', name='wall_time', field=models.BigIntegerField(null=True)),
        migrations.AddField(model_name='reportunsafe', name='memory', field=models.BigIntegerField(default=0),
                            preserve_default=False),
        migrations.AddField(model_name='reportunsafe', name='wall_time', field=models.BigIntegerField(default=0),
                            preserve_default=False),
        migrations.RemoveField(model_name='tasksnumbers', name='root'),
        migrations.RemoveField(model_name='reportroot', name='average_time'),
        migrations.RemoveField(model_name='reportroot', name='tasks_total'),
        migrations.DeleteModel(name='TaskStatistic'),
        migrations.DeleteModel(name='TasksNumbers')
    ]
