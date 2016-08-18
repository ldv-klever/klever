#
# Copyright (c) 2014-2015 ISPRAS (http://www.ispras.ru)
# Institute for System Programming of the Russian Academy of Sciences
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

from django.db import migrations, models
from django.conf import settings
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('jobs', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Node',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('status', models.CharField(choices=[('USER_OCCUPIED', 'User occupied'), ('HEALTHY', 'Healthy'), ('AILING', 'Ailing'), ('DISCONNECTED', 'Disconnected')], max_length=13)),
                ('hostname', models.CharField(max_length=128)),
            ],
            options={
                'db_table': 'node',
            },
        ),
        migrations.CreateModel(
            name='NodesConfiguration',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('cpu', models.CharField(max_length=128)),
                ('cores', models.PositiveSmallIntegerField()),
                ('ram', models.BigIntegerField()),
                ('memory', models.BigIntegerField()),
            ],
            options={
                'db_table': 'nodes_configuration',
            },
        ),
        migrations.CreateModel(
            name='Scheduler',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('type', models.CharField(choices=[('0', 'Klever'), ('1', 'VerifierCloud')], max_length=1)),
                ('status', models.CharField(choices=[('HEALTHY', 'Healthy'), ('AILING', 'Ailing'), ('DISCONNECTED', 'Disconnected')], default='AILING', max_length=12)),
            ],
            options={
                'db_table': 'scheduler',
            },
        ),
        migrations.CreateModel(
            name='SchedulerUser',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('login', models.CharField(max_length=128)),
                ('password', models.CharField(max_length=128)),
                ('user', models.OneToOneField(to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'scheduler_user',
            },
        ),
        migrations.CreateModel(
            name='Solution',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('description', models.BinaryField()),
                ('archname', models.CharField(max_length=256)),
                ('archive', models.FileField(upload_to='Service')),
            ],
            options={
                'db_table': 'solution',
            },
        ),
        migrations.CreateModel(
            name='SolvingProgress',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('priority', models.CharField(choices=[('URGENT', 'Urgent'), ('HIGH', 'High'), ('LOW', 'Low'), ('IDLE', 'Idle')], max_length=6)),
                ('start_date', models.DateTimeField(null=True)),
                ('finish_date', models.DateTimeField(null=True)),
                ('tasks_total', models.PositiveIntegerField(default=0)),
                ('tasks_pending', models.PositiveIntegerField(default=0)),
                ('tasks_processing', models.PositiveIntegerField(default=0)),
                ('tasks_finished', models.PositiveIntegerField(default=0)),
                ('tasks_error', models.PositiveIntegerField(default=0)),
                ('tasks_cancelled', models.PositiveIntegerField(default=0)),
                ('solutions', models.PositiveIntegerField(default=0)),
                ('error', models.CharField(null=True, max_length=1024)),
                ('configuration', models.BinaryField()),
                ('job', models.OneToOneField(to='jobs.Job')),
                ('scheduler', models.ForeignKey(to='service.Scheduler')),
            ],
            options={
                'db_table': 'solving_progress',
            },
        ),
        migrations.CreateModel(
            name='Task',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('status', models.CharField(choices=[('PENDING', 'Pending'), ('PROCESSING', 'Processing'), ('FINISHED', 'Finished'), ('ERROR', 'Error'), ('CANCELLED', 'Cancelled')], default='PENDING', max_length=10)),
                ('error', models.CharField(null=True, max_length=1024)),
                ('description', models.BinaryField()),
                ('archname', models.CharField(max_length=256)),
                ('archive', models.FileField(upload_to='Service')),
                ('progress', models.ForeignKey(to='service.SolvingProgress')),
            ],
            options={
                'db_table': 'task',
            },
        ),
        migrations.CreateModel(
            name='VerificationTool',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('name', models.CharField(max_length=128)),
                ('version', models.CharField(max_length=128)),
                ('scheduler', models.ForeignKey(to='service.Scheduler')),
            ],
            options={
                'db_table': 'verification_tool',
            },
        ),
        migrations.CreateModel(
            name='Workload',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('jobs', models.PositiveIntegerField()),
                ('tasks', models.PositiveIntegerField()),
                ('cores', models.PositiveSmallIntegerField()),
                ('ram', models.BigIntegerField()),
                ('memory', models.BigIntegerField()),
                ('for_tasks', models.BooleanField()),
                ('for_jobs', models.BooleanField()),
            ],
            options={
                'db_table': 'workload',
            },
        ),
        migrations.AddField(
            model_name='solution',
            name='task',
            field=models.OneToOneField(to='service.Task'),
        ),
        migrations.AddField(
            model_name='node',
            name='config',
            field=models.ForeignKey(to='service.NodesConfiguration'),
        ),
        migrations.AddField(
            model_name='node',
            name='workload',
            field=models.OneToOneField(on_delete=django.db.models.deletion.SET_NULL, to='service.Workload', null=True),
        ),
    ]
