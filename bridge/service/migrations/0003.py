from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('jobs', '0001_initial'), ('service', '0001_initial')]

    operations = [
        migrations.CreateModel(
            name='JobProgress',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('total_sj', models.PositiveIntegerField(null=True)),
                ('failed_sj', models.PositiveIntegerField(null=True)),
                ('solved_sj', models.PositiveIntegerField(null=True)),
                ('expected_time_sj', models.PositiveIntegerField(null=True)),
                ('start_sj', models.DateTimeField(null=True)),
                ('finish_sj', models.DateTimeField(null=True)),
                ('gag_text_sj', models.CharField(max_length=128, null=True)),
                ('total_ts', models.PositiveIntegerField(null=True)),
                ('failed_ts', models.PositiveIntegerField(null=True)),
                ('solved_ts', models.PositiveIntegerField(null=True)),
                ('expected_time_ts', models.PositiveIntegerField(null=True)),
                ('start_ts', models.DateTimeField(null=True)),
                ('finish_ts', models.DateTimeField(null=True)),
                ('gag_text_ts', models.CharField(max_length=128, null=True)),
                ('job', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to='jobs.Job')),
            ],
        ),
    ]
