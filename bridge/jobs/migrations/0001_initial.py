#
# Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
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
    ]

    operations = [
        migrations.CreateModel(
            name='File',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('hash_sum', models.CharField(max_length=255)),
                ('file', models.FileField(upload_to='Files')),
            ],
            options={
                'db_table': 'file',
            },
        ),
        migrations.CreateModel(
            name='FileSystem',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('name', models.CharField(max_length=150)),
                ('file', models.ForeignKey(null=True, to='jobs.File')),
            ],
            options={
                'db_table': 'file_system',
            },
        ),
        migrations.CreateModel(
            name='Job',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('name', models.CharField(max_length=150)),
                ('format', models.PositiveSmallIntegerField(default=1)),
                ('type', models.CharField(choices=[('0', 'Verification of Linux kernel modules'), ('1', 'Validation on Linux kernel modules'), ('2', 'Verification of commits in Linux kernel Git repositories'), ('3', 'Validation on commits in Linux kernel Git repositories'), ('4', 'Verification of C programs'), ('5', 'Validation on C programs')], default='0', max_length=1)),
                ('version', models.PositiveSmallIntegerField(default=1)),
                ('change_date', models.DateTimeField(auto_now=True)),
                ('identifier', models.CharField(unique=True, max_length=255)),
                ('status', models.CharField(choices=[('0', 'Not solved'), ('1', 'Pending'), ('2', 'Is solving'), ('3', 'Solved'), ('4', 'Failed'), ('5', 'Corrupted'), ('6', 'Cancelled')], default='0', max_length=1)),
                ('change_author', models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, related_name='job', blank=True, null=True)),
                ('parent', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='jobs.Job', related_name='children', null=True)),
            ],
            options={
                'db_table': 'job',
            },
        ),
        migrations.CreateModel(
            name='JobHistory',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('name', models.CharField(max_length=150)),
                ('version', models.PositiveSmallIntegerField()),
                ('change_date', models.DateTimeField()),
                ('comment', models.CharField(default='', max_length=255)),
                ('global_role', models.CharField(choices=[('0', 'No access'), ('1', 'Observer'), ('2', 'Expert'), ('3', 'Observer and Operator'), ('4', 'Expert and Operator')], default='0', max_length=1)),
                ('description', models.TextField(default='')),
                ('change_author', models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, related_name='jobhistory', blank=True, null=True)),
                ('job', models.ForeignKey(to='jobs.Job', related_name='versions')),
                ('parent', models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, to='jobs.Job', related_name='+', null=True)),
            ],
            options={
                'db_table': 'jobhistory',
            },
        ),
        migrations.CreateModel(
            name='RunHistory',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('date', models.DateTimeField()),
                ('status', models.CharField(choices=[('0', 'Not solved'), ('1', 'Pending'), ('2', 'Is solving'), ('3', 'Solved'), ('4', 'Failed'), ('5', 'Corrupted'), ('6', 'Cancelled')], max_length=1)),
                ('configuration', models.ForeignKey(to='jobs.File')),
                ('job', models.ForeignKey(to='jobs.Job')),
                ('operator', models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, null=True)),
            ],
            options={
                'db_table': 'job_run_history',
            },
        ),
        migrations.CreateModel(
            name='UserRole',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('role', models.CharField(choices=[('0', 'No access'), ('1', 'Observer'), ('2', 'Expert'), ('3', 'Observer and Operator'), ('4', 'Expert and Operator')], max_length=1)),
                ('job', models.ForeignKey(to='jobs.JobHistory')),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, related_name='+')),
            ],
            options={
                'db_table': 'user_job_role',
            },
        ),
        migrations.AddField(
            model_name='filesystem',
            name='job',
            field=models.ForeignKey(to='jobs.JobHistory'),
        ),
        migrations.AddField(
            model_name='filesystem',
            name='parent',
            field=models.ForeignKey(to='jobs.FileSystem', related_name='children', null=True),
        ),
    ]
