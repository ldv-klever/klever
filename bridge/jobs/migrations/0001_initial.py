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
from django.db.models.deletion import CASCADE, SET_NULL

roles_choices = [
    ('0', 'No access'),
    ('1', 'Observer'),
    ('2', 'Expert'),
    ('3', 'Observer and Operator'),
    ('4', 'Expert and Operator')
]

status_choices = [
    ('0', 'Not solved'),
    ('1', 'Pending'),
    ('2', 'Is solving'),
    ('3', 'Solved'),
    ('4', 'Failed'),
    ('5', 'Corrupted'),
    ('6', 'Cancelling'),
    ('7', 'Cancelled'),
    ('8', 'Terminated')
]

job_types = [
    ('0', 'Verification of Linux kernel modules'),
    ('3', 'Validation on commits in Linux kernel Git repositories')
]


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name='Job',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('parent', models.ForeignKey(null=True, on_delete=CASCADE, related_name='children', to='jobs.Job')),
                ('identifier', models.CharField(db_index=True, max_length=255, unique=True)),
                ('version', models.PositiveSmallIntegerField(default=1)),
                ('format', models.PositiveSmallIntegerField(default=1)),
                ('type', models.CharField(choices=job_types, default='0', max_length=1)),
                ('change_author', models.ForeignKey(blank=True, null=True, on_delete=SET_NULL, related_name='+',
                                                    to=settings.AUTH_USER_MODEL)),
                ('change_date', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(db_index=True, max_length=150, unique=True)),
                ('status', models.CharField(choices=status_choices, default='0', max_length=1)),
                ('weight', models.CharField(choices=[('0', 'Full-weight'), ('1', 'Lightweight')],
                                            default='0', max_length=1)),
                ('safe_marks', models.BooleanField(default=False)),
            ],
            options={'db_table': 'job'},
        ),
        migrations.CreateModel(
            name='JobFile',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('hash_sum', models.CharField(db_index=True, max_length=255)),
                ('file', models.FileField(upload_to='Job')),
            ],
            options={'db_table': 'job_file'},
        ),
        migrations.CreateModel(
            name='JobHistory',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('job', models.ForeignKey(on_delete=CASCADE, related_name='versions', to='jobs.Job')),
                ('parent', models.ForeignKey(null=True, on_delete=SET_NULL, related_name='+', to='jobs.Job')),
                ('version', models.PositiveSmallIntegerField()),
                ('change_author', models.ForeignKey(null=True, on_delete=SET_NULL,
                                                    related_name='+', to=settings.AUTH_USER_MODEL)),
                ('change_date', models.DateTimeField()),
                ('global_role', models.CharField(choices=roles_choices, default='0', max_length=1)),
                ('description', models.TextField(default='')),
                ('comment', models.CharField(default='', max_length=255)),
            ],
            options={'db_table': 'jobhistory'},
        ),
        migrations.CreateModel(
            name='FileSystem',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('parent', models.ForeignKey(null=True, on_delete=CASCADE,
                                             related_name='children', to='jobs.FileSystem')),
                ('job', models.ForeignKey(on_delete=CASCADE, to='jobs.JobHistory')),
                ('name', models.CharField(max_length=128)),
                ('file', models.ForeignKey(null=True, on_delete=CASCADE, to='jobs.JobFile')),
            ],
            options={'db_table': 'file_system'},
        ),
        migrations.CreateModel(
            name='RunHistory',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('job', models.ForeignKey(on_delete=CASCADE, to='jobs.Job')),
                ('operator', models.ForeignKey(null=True, on_delete=SET_NULL,
                                               related_name='+', to=settings.AUTH_USER_MODEL)),
                ('date', models.DateTimeField()),
                ('status', models.CharField(choices=status_choices, default='1', max_length=1)),
                ('configuration', models.ForeignKey(on_delete=CASCADE, to='jobs.JobFile')),
            ],
            options={'db_table': 'job_run_history'},
        ),
        migrations.CreateModel(
            name='UserRole',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('user', models.ForeignKey(on_delete=CASCADE, to=settings.AUTH_USER_MODEL)),
                ('job', models.ForeignKey(on_delete=CASCADE, to='jobs.JobHistory')),
                ('role', models.CharField(choices=roles_choices, max_length=1)),
            ],
            options={'db_table': 'user_job_role'},
        ),
        migrations.AlterIndexTogether(name='jobhistory', index_together={('job', 'version')}),
    ]
