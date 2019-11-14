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

from django.conf import settings
from django.db import migrations, models

import uuid
import mptt.fields
import bridge.utils


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [

        migrations.CreateModel(name='Job', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('identifier', models.UUIDField(db_index=True, default=uuid.uuid4, unique=True)),
            ('name', models.CharField(db_index=True, max_length=150, unique=True)),
            ('version', models.PositiveSmallIntegerField(default=1)),
            ('status', models.CharField(choices=[
                ('0', 'Not solved'), ('1', 'Pending'), ('2', 'Is solving'), ('3', 'Solved'), ('4', 'Failed'),
                ('5', 'Corrupted'), ('6', 'Cancelling'), ('7', 'Cancelled'), ('8', 'Terminated')
            ], default='0', max_length=1)),
            ('weight', models.CharField(
                choices=[('0', 'Full-weight'), ('1', 'Lightweight')], default='0', max_length=1
            )),
            ('lft', models.PositiveIntegerField(editable=False)),
            ('rght', models.PositiveIntegerField(editable=False)),
            ('tree_id', models.PositiveIntegerField(db_index=True, editable=False)),
            ('level', models.PositiveIntegerField(editable=False)),
            ('author', models.ForeignKey(
                blank=True, null=True, on_delete=models.deletion.SET_NULL,
                related_name='jobs', to=settings.AUTH_USER_MODEL
            )),
            ('coverage_details', models.CharField(choices=[
                ('0', 'Original C source files'), ('1', 'C source files including models'), ('2', 'All source files')
            ], default='0', max_length=1)),
        ], options={'db_table': 'job'}),

        migrations.CreateModel(name='JobFile', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('hash_sum', models.CharField(db_index=True, max_length=255)),
            ('file', models.FileField(upload_to='Job')),
        ], options={'db_table': 'job_file'}, bases=(bridge.utils.WithFilesMixin, models.Model)),

        migrations.CreateModel(name='JobHistory', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('version', models.PositiveSmallIntegerField()),
            ('change_date', models.DateTimeField()),
            ('comment', models.CharField(blank=True, default='', max_length=255)),
            ('name', models.CharField(max_length=150)),
            ('global_role', models.CharField(choices=[
                ('0', 'No access'), ('1', 'Observer'), ('2', 'Expert'),
                ('3', 'Observer and Operator'), ('4', 'Expert and Operator')
            ], default='0', max_length=1)),
            ('change_author', models.ForeignKey(
                blank=True, null=True, on_delete=models.deletion.SET_NULL,
                related_name='+', to=settings.AUTH_USER_MODEL
            )),
            ('job', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='versions', to='jobs.Job')),
        ], options={'db_table': 'jobhistory', 'ordering': ('-version',)}),

        migrations.CreateModel(name='RunHistory', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('date', models.DateTimeField(db_index=True)),
            ('status', models.CharField(choices=[
                ('0', 'Not solved'), ('1', 'Pending'), ('2', 'Is solving'), ('3', 'Solved'), ('4', 'Failed'),
                ('5', 'Corrupted'), ('6', 'Cancelling'), ('7', 'Cancelled'), ('8', 'Terminated')
            ], default='1', max_length=1)),
            ('configuration', models.ForeignKey(on_delete=models.deletion.CASCADE, to='jobs.JobFile')),
            ('job', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='run_history', to='jobs.Job')),
            ('operator', models.ForeignKey(
                null=True, on_delete=models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL
            )),
        ], options={'db_table': 'job_run_history'}),

        migrations.CreateModel(name='FileSystem', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('name', models.CharField(max_length=1024)),
            ('file', models.ForeignKey(on_delete=models.deletion.CASCADE, to='jobs.JobFile')),
            ('job_version', models.ForeignKey(
                on_delete=models.deletion.CASCADE, related_name='files', to='jobs.JobHistory'
            )),
        ], options={'db_table': 'file_system'}),

        migrations.CreateModel(name='UserRole', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('role', models.CharField(choices=[
                ('0', 'No access'), ('1', 'Observer'), ('2', 'Expert'),
                ('3', 'Observer and Operator'), ('4', 'Expert and Operator')
            ], max_length=1)),
            ('job_version', models.ForeignKey(on_delete=models.deletion.CASCADE, to='jobs.JobHistory')),
            ('user', models.ForeignKey(on_delete=models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
        ], options={'db_table': 'user_job_role'}),

        migrations.AddField(model_name='job', name='parent', field=mptt.fields.TreeForeignKey(
            blank=True, null=True, on_delete=models.deletion.CASCADE, related_name='children', to='jobs.Job'
        )),

        migrations.AlterIndexTogether(name='jobhistory', index_together={('job', 'version')}),

    ]
