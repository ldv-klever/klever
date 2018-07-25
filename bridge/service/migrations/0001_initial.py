#
# Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
# Ivannikov Institute for System Programming of the Russian Academy of Sciences
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models


task_status_choices = [
    ('PENDING', 'Pending'),
    ('PROCESSING', 'Processing'),
    ('FINISHED', 'Finished'),
    ('ERROR', 'Error'),
    ('CANCELLED', 'Cancelled')
]


class Migration(migrations.Migration):
    initial = True
    dependencies = [('jobs', '0001_initial'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name='NodesConfiguration',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('cpu', models.CharField(max_length=128)),
                ('cores', models.PositiveSmallIntegerField()),
                ('ram', models.BigIntegerField()),
                ('memory', models.BigIntegerField()),
            ],
            options={'db_table': 'nodes_configuration'},
        ),
        migrations.CreateModel(
            name='Scheduler',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('type', models.CharField(choices=[('0', 'Klever'), ('1', 'VerifierCloud')], max_length=1)),
                ('status', models.CharField(choices=[('HEALTHY', 'Healthy'), ('AILING', 'Ailing'),
                                                     ('DISCONNECTED', 'Disconnected')],
                                            default='AILING', max_length=12)),
            ],
            options={'db_table': 'scheduler'},
        ),
        migrations.CreateModel(
            name='SchedulerUser',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('user', models.OneToOneField(on_delete=models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('login', models.CharField(max_length=128)),
                ('password', models.CharField(max_length=128)),
            ],
            options={'db_table': 'scheduler_user'},
        ),
        migrations.CreateModel(
            name='JobProgress',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('job', models.OneToOneField(on_delete=models.deletion.CASCADE, to='jobs.Job')),
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
            ],
        ),
        migrations.CreateModel(
            name='SolvingProgress',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('job', models.OneToOneField(on_delete=models.deletion.CASCADE, to='jobs.Job')),
                ('scheduler', models.ForeignKey(on_delete=models.deletion.CASCADE, to='service.Scheduler')),
                ('priority', models.CharField(choices=[('URGENT', 'Urgent'), ('HIGH', 'High'),
                                                       ('LOW', 'Low'), ('IDLE', 'Idle')], max_length=6)),
                ('start_date', models.DateTimeField(null=True)),
                ('finish_date', models.DateTimeField(null=True)),
                ('tasks_total', models.PositiveIntegerField(default=0)),
                ('tasks_pending', models.PositiveIntegerField(default=0)),
                ('tasks_processing', models.PositiveIntegerField(default=0)),
                ('tasks_finished', models.PositiveIntegerField(default=0)),
                ('tasks_error', models.PositiveIntegerField(default=0)),
                ('tasks_cancelled', models.PositiveIntegerField(default=0)),
                ('solutions', models.PositiveIntegerField(default=0)),
                ('error', models.CharField(max_length=1024, null=True)),
                ('configuration', models.BinaryField()),
                ('fake', models.BooleanField(default=False)),
            ],
            options={'db_table': 'solving_progress'},
        ),
        migrations.CreateModel(
            name='Task',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('progress', models.ForeignKey(on_delete=models.deletion.CASCADE, to='service.SolvingProgress')),
                ('status', models.CharField(choices=task_status_choices, default='PENDING', max_length=10)),
                ('error', models.CharField(max_length=1024, null=True)),
                ('description', models.BinaryField()),
                ('archname', models.CharField(max_length=256)),
                ('archive', models.FileField(upload_to='Service')),
            ],
            options={'db_table': 'task'},
        ),
        migrations.CreateModel(
            name='Solution',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('task', models.OneToOneField(on_delete=models.deletion.CASCADE, to='service.Task')),
                ('description', models.BinaryField()),
                ('archname', models.CharField(max_length=256)),
                ('archive', models.FileField(upload_to='Service')),
            ],
            options={'db_table': 'solution'},
        ),
        migrations.CreateModel(
            name='VerificationTool',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=128)),
                ('version', models.CharField(max_length=128)),
                ('scheduler', models.ForeignKey(on_delete=models.deletion.CASCADE, to='service.Scheduler')),
            ],
            options={'db_table': 'verification_tool'},
        ),
        migrations.CreateModel(
            name='Workload',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('jobs', models.PositiveIntegerField()),
                ('tasks', models.PositiveIntegerField()),
                ('cores', models.PositiveSmallIntegerField()),
                ('ram', models.BigIntegerField()),
                ('memory', models.BigIntegerField()),
                ('for_tasks', models.BooleanField()),
                ('for_jobs', models.BooleanField()),
            ],
            options={'db_table': 'workload'},
        ),
        migrations.CreateModel(
            name='Node',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('workload', models.OneToOneField(null=True, on_delete=models.deletion.SET_NULL, related_name='+',
                                                  to='service.Workload')),
                ('hostname', models.CharField(max_length=128)),
                ('status', models.CharField(
                    choices=[('USER_OCCUPIED', 'User occupied'), ('HEALTHY', 'Healthy'), ('AILING', 'Ailing'),
                             ('DISCONNECTED', 'Disconnected')], max_length=13)),
                ('config', models.ForeignKey(on_delete=models.deletion.CASCADE, to='service.NodesConfiguration')),
            ],
            options={'db_table': 'node'},
        ),
    ]
