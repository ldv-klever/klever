#
# Copyright (c) 2019 ISP RAS (http://www.ispras.ru)
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

from django.contrib.postgres.fields import jsonb
from django.db import migrations, models

import bridge.utils


class Migration(migrations.Migration):
    initial = True
    dependencies = [('jobs', '0001_initial')]

    operations = [

        migrations.CreateModel(name='NodesConfiguration', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('cpu_model', models.CharField(max_length=128, verbose_name='CPU model')),
            ('cpu_number', models.PositiveSmallIntegerField(verbose_name='CPU number')),
            ('ram_memory', models.PositiveIntegerField(verbose_name='RAM memory')),
            ('disk_memory', models.PositiveIntegerField(verbose_name='Disk memory')),
        ], options={'db_table': 'nodes_configuration'}),

        migrations.CreateModel(name='Node', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('config', models.ForeignKey(on_delete=models.deletion.CASCADE, to='service.NodesConfiguration')),
            ('hostname', models.CharField(max_length=128)),
            ('status', models.CharField(choices=[
                ('USER_OCCUPIED', 'User occupied'), ('HEALTHY', 'Healthy'),
                ('AILING', 'Ailing'), ('DISCONNECTED', 'Disconnected')
            ], max_length=13)),
        ], options={'db_table': 'node'}),

        migrations.CreateModel(name='Task', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('status', models.CharField(choices=[
                ('PENDING', 'Pending'), ('PROCESSING', 'Processing'),
                ('FINISHED', 'Finished'), ('ERROR', 'Error'), ('CANCELLED', 'Cancelled')
            ], default='PENDING', max_length=10)),
            ('error', models.CharField(max_length=1024, null=True)),
            ('filename', models.CharField(max_length=256)),
            ('archive', models.FileField(upload_to='Service')),
            ('description', jsonb.JSONField()),
            ('decision', models.ForeignKey(
                on_delete=models.deletion.CASCADE, related_name='tasks', to='jobs.Decision'
            )),
        ], options={'db_table': 'task'}, bases=(bridge.utils.WithFilesMixin, models.Model)),

        migrations.CreateModel(name='Solution', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('decision', models.ForeignKey(
                on_delete=models.deletion.CASCADE, related_name='solutions_set', to='jobs.Decision'
            )),
            ('task', models.OneToOneField(
                on_delete=models.deletion.CASCADE, related_name='solution', to='service.Task'
            )),
            ('filename', models.CharField(max_length=256)),
            ('archive', models.FileField(upload_to='Service')),
            ('description', jsonb.JSONField()),
        ], options={'db_table': 'solution'}, bases=(bridge.utils.WithFilesMixin, models.Model)),

        migrations.CreateModel(name='VerificationTool', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('name', models.CharField(max_length=128)),
            ('version', models.CharField(max_length=128)),
            ('scheduler', models.ForeignKey(on_delete=models.deletion.CASCADE, to='jobs.Scheduler')),
        ], options={'db_table': 'verification_tool'}),

        migrations.CreateModel(name='Workload', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('reserved_cpu_number', models.PositiveSmallIntegerField(verbose_name='Reserved CPU number')),
            ('reserved_ram_memory', models.PositiveIntegerField(verbose_name='Reserved RAM memory')),
            ('reserved_disk_memory', models.PositiveIntegerField(verbose_name='Reserved disk memory')),
            ('running_verification_jobs', models.PositiveIntegerField(verbose_name='Running verification jobs')),
            ('running_verification_tasks', models.PositiveIntegerField(verbose_name='Running verification tasks')),
            ('available_for_jobs', models.BooleanField(verbose_name='Available for jobs')),
            ('available_for_tasks', models.BooleanField(verbose_name='Available for tasks')),
            ('node', models.OneToOneField(
                on_delete=models.deletion.CASCADE, related_name='workload', to='service.Node'
            )),
        ], options={'db_table': 'workload'}),

    ]
