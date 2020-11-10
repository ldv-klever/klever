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

from django.conf import settings
from django.db import migrations, models
from django.utils.timezone import now

import uuid
import mptt.fields
import bridge.utils


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [

        migrations.CreateModel(name='JobFile', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('hash_sum', models.CharField(db_index=True, max_length=255, unique=True)),
            ('file', models.FileField(upload_to='JobFile')),
        ], options={'db_table': 'job_file'}, bases=(bridge.utils.WithFilesMixin, models.Model)),

        migrations.CreateModel(name='PresetJob', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('identifier', models.UUIDField(db_index=True, null=True)),
            ('name', models.CharField(db_index=True, max_length=150, unique=True, verbose_name='Name')),
            ('type', models.CharField(choices=[
                ('0', 'Directory'), ('1', 'Leaf'), ('2', 'Custom directory')
            ], max_length=1)),
            ('check_date', models.DateTimeField()),
            ('lft', models.PositiveIntegerField(editable=False)),
            ('rght', models.PositiveIntegerField(editable=False)),
            ('tree_id', models.PositiveIntegerField(db_index=True, editable=False)),
            ('level', models.PositiveIntegerField(editable=False)),
            ('parent', mptt.fields.TreeForeignKey(
                blank=True, null=True, on_delete=models.deletion.CASCADE,
                related_name='children', to='jobs.PresetJob'
            )),
            ('creation_date', models.DateTimeField(auto_now_add=True)),
        ], options={'db_table': 'job_preset', 'verbose_name': 'Preset job'}),

        migrations.CreateModel(name='PresetFile', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('name', models.CharField(max_length=1024)),
            ('file', models.ForeignKey(on_delete=models.deletion.PROTECT, to='jobs.JobFile')),
            ('preset', models.ForeignKey(on_delete=models.deletion.CASCADE, to='jobs.PresetJob')),
        ], options={'db_table': 'job_preset_file'}),

        migrations.CreateModel(name='Job', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('identifier', models.UUIDField(db_index=True, default=uuid.uuid4, unique=True)),
            ('name', models.CharField(db_index=True, max_length=150)),
            ('author', models.ForeignKey(
                blank=True, null=True, on_delete=models.deletion.SET_NULL,
                related_name='+', to=settings.AUTH_USER_MODEL
            )),
            ('creation_date', models.DateTimeField(auto_now_add=True)),
            ('preset', models.ForeignKey(on_delete=models.deletion.CASCADE, to='jobs.PresetJob')),
            ('global_role', models.CharField(choices=[
                ('0', 'No access'), ('1', 'Observer'), ('2', 'Expert'),
                ('3', 'Observer and Operator'), ('4', 'Expert and Operator')
            ], default='0', max_length=1)),
        ], options={'db_table': 'job'}),

        migrations.CreateModel(name='UserRole', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('role', models.CharField(choices=[
                ('0', 'No access'), ('1', 'Observer'), ('2', 'Expert'),
                ('3', 'Observer and Operator'), ('4', 'Expert and Operator')
            ], max_length=1)),
            ('job', models.ForeignKey(on_delete=models.deletion.CASCADE, to='jobs.Job')),
            ('user', models.ForeignKey(on_delete=models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
        ], options={'db_table': 'user_job_role'}),

        migrations.CreateModel(name='UploadedJobArchive', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('archive', models.FileField(upload_to='UploadedJobs')),
            ('status', models.CharField(choices=[
                ('0', 'Pending'), ('1', 'Extracting archive files'), ('2', 'Uploading files'), ('3', 'Uploading job'),
                ('4', 'Uploading decisions cache'), ('5', 'Uploading original sources'),
                ('6', 'Uploading reports trees'), ('7', 'Uploading safes'), ('8', 'Uploading unsafes'),
                ('9', 'Uploading unknowns'), ('10', 'Uploading attributes'), ('11', 'Uploading coverage'),
                ('12', 'Associating marks and cache recalculation'), ('13', 'Finished'), ('14', 'Failed')
            ], default='0', max_length=2)),
            ('start_date', models.DateTimeField(auto_now_add=True)),
            ('finish_date', models.DateTimeField(null=True)),
            ('error', models.TextField(null=True)),
            ('author', models.ForeignKey(on_delete=models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ('job', models.ForeignKey(null=True, on_delete=models.deletion.SET_NULL, related_name='+', to='jobs.Job')),
            ('name', models.CharField(max_length=128)),
            ('step_progress', models.PositiveIntegerField(default=0)),
        ], options={'db_table': 'job_uploaded_archives'}),

        migrations.CreateModel(name='Scheduler', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('type', models.CharField(choices=[
                ('Klever', 'Klever'), ('VerifierCloud', 'VerifierCloud')
            ], db_index=True, max_length=15)),
            ('status', models.CharField(choices=[
                ('HEALTHY', 'Healthy'), ('AILING', 'Ailing'), ('DISCONNECTED', 'Disconnected')
            ], default='AILING', max_length=15)),
        ], options={'db_table': 'scheduler'}),

        migrations.CreateModel(name='Decision', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('job', models.ForeignKey(on_delete=models.deletion.CASCADE, to='jobs.Job')),
            ('identifier', models.UUIDField(db_index=True, default=uuid.uuid4, unique=True)),
            ('title', models.CharField(blank=True, max_length=128)),
            ('scheduler', models.ForeignKey(on_delete=models.deletion.CASCADE, to='jobs.Scheduler')),
            ('operator', models.ForeignKey(
                null=True, on_delete=models.deletion.SET_NULL, related_name='decisions', to=settings.AUTH_USER_MODEL
            )),
            ('status', models.CharField(choices=[
                ('0', 'Hidden'), ('1', 'Pending'), ('2', 'Is solving'), ('3', 'Solved'), ('4', 'Failed'),
                ('5', 'Corrupted'), ('6', 'Cancelling'), ('7', 'Cancelled'), ('8', 'Terminated')
            ], default='1', max_length=1)),
            ('weight', models.CharField(choices=[
                ('0', 'Full-weight'), ('1', 'Lightweight')
            ], default='0', max_length=1)),
            ('priority', models.CharField(choices=[
                ('URGENT', 'Urgent'), ('HIGH', 'High'), ('LOW', 'Low'), ('IDLE', 'Idle')
            ], max_length=6)),
            ('error', models.TextField(null=True)),
            ('start_date', models.DateTimeField(default=now)),
            ('finish_date', models.DateTimeField(null=True)),
            ('tasks_total', models.PositiveIntegerField(default=0)),
            ('tasks_pending', models.PositiveIntegerField(default=0)),
            ('tasks_processing', models.PositiveIntegerField(default=0)),
            ('tasks_finished', models.PositiveIntegerField(default=0)),
            ('tasks_error', models.PositiveIntegerField(default=0)),
            ('tasks_cancelled', models.PositiveIntegerField(default=0)),
            ('solutions', models.PositiveIntegerField(default=0)),
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
            ('configuration', models.ForeignKey(on_delete=models.deletion.CASCADE, to='jobs.JobFile')),
        ], options={'db_table': 'decision'}),

        migrations.CreateModel(name='FileSystem', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('name', models.CharField(max_length=1024)),
            ('file', models.ForeignKey(on_delete=models.deletion.PROTECT, to='jobs.JobFile')),
            ('decision', models.ForeignKey(
                on_delete=models.deletion.CASCADE, related_name='files', to='jobs.Decision'
            )),
        ], options={'db_table': 'file_system'}),

    ]
