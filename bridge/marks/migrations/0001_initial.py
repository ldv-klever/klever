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
        ('reports', '0001_initial'),
        ('jobs', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ComponentMarkUnknownProblem',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('number', models.PositiveIntegerField(default=0)),
                ('component', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='reports.Component', related_name='+')),
            ],
            options={
                'db_table': 'cache_report_component_mark_unknown_problem',
            },
        ),
        migrations.CreateModel(
            name='ErrorTraceConvertionCache',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('converted', models.ForeignKey(to='jobs.File')),
            ],
            options={
                'db_table': 'cache_error_trace_converted',
            },
        ),
        migrations.CreateModel(
            name='MarkAssociationsChanges',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('identifier', models.CharField(unique=True, max_length=255)),
                ('table_data', models.TextField()),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'cache_mark_associations_changes',
            },
        ),
        migrations.CreateModel(
            name='MarkSafe',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('identifier', models.CharField(unique=True, max_length=255)),
                ('format', models.PositiveSmallIntegerField(default=1)),
                ('version', models.PositiveSmallIntegerField(default=1)),
                ('status', models.CharField(choices=[('0', 'Unreported'), ('1', 'Reported'), ('2', 'Fixed'), ('3', 'Rejected')], default='0', max_length=1)),
                ('is_modifiable', models.BooleanField(default=True)),
                ('change_date', models.DateTimeField(auto_now=True)),
                ('description', models.TextField(default='')),
                ('type', models.CharField(choices=[('0', 'Created'), ('1', 'Preset'), ('2', 'Uploaded')], default='0', max_length=1)),
                ('verdict', models.CharField(choices=[('0', 'Unknown'), ('1', 'Incorrect proof'), ('2', 'Missed target bug')], default='0', max_length=1)),
                ('author', models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, related_name='marksafe', null=True)),
                ('job', models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, to='jobs.Job', related_name='marksafe', null=True)),
                ('prime', models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, to='reports.ReportSafe', related_name='prime_marks', null=True)),
            ],
            options={
                'db_table': 'mark_safe',
            },
        ),
        migrations.CreateModel(
            name='MarkSafeAttr',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('is_compare', models.BooleanField(default=True)),
                ('attr', models.ForeignKey(to='reports.Attr')),
            ],
            options={
                'db_table': 'mark_safe_attr',
            },
        ),
        migrations.CreateModel(
            name='MarkSafeHistory',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('version', models.PositiveSmallIntegerField()),
                ('status', models.CharField(choices=[('0', 'Unreported'), ('1', 'Reported'), ('2', 'Fixed'), ('3', 'Rejected')], default='0', max_length=1)),
                ('change_date', models.DateTimeField()),
                ('comment', models.TextField()),
                ('description', models.TextField()),
                ('verdict', models.CharField(choices=[('0', 'Unknown'), ('1', 'Incorrect proof'), ('2', 'Missed target bug')], max_length=1)),
                ('author', models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, related_name='marksafehistory', null=True)),
                ('mark', models.ForeignKey(to='marks.MarkSafe', related_name='versions')),
            ],
            options={
                'db_table': 'mark_safe_history',
            },
        ),
        migrations.CreateModel(
            name='MarkSafeReport',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('mark', models.ForeignKey(to='marks.MarkSafe', related_name='markreport_set')),
                ('report', models.ForeignKey(to='reports.ReportSafe', related_name='markreport_set')),
            ],
            options={
                'db_table': 'cache_mark_safe_report',
            },
        ),
        migrations.CreateModel(
            name='MarkSafeTag',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('mark_version', models.ForeignKey(to='marks.MarkSafeHistory', related_name='tags')),
            ],
            options={
                'db_table': 'cache_mark_safe_tag',
            },
        ),
        migrations.CreateModel(
            name='MarkUnknown',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('identifier', models.CharField(unique=True, max_length=255)),
                ('format', models.PositiveSmallIntegerField(default=1)),
                ('version', models.PositiveSmallIntegerField(default=1)),
                ('status', models.CharField(choices=[('0', 'Unreported'), ('1', 'Reported'), ('2', 'Fixed'), ('3', 'Rejected')], default='0', max_length=1)),
                ('is_modifiable', models.BooleanField(default=True)),
                ('change_date', models.DateTimeField(auto_now=True)),
                ('description', models.TextField(default='')),
                ('type', models.CharField(choices=[('0', 'Created'), ('1', 'Preset'), ('2', 'Uploaded')], default='0', max_length=1)),
                ('function', models.TextField()),
                ('problem_pattern', models.CharField(max_length=15)),
                ('link', models.URLField(null=True)),
                ('author', models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, related_name='markunknown', null=True)),
                ('component', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='reports.Component')),
                ('job', models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, to='jobs.Job', related_name='markunknown', null=True)),
                ('prime', models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, to='reports.ReportUnknown', related_name='prime_marks', null=True)),
            ],
            options={
                'db_table': 'mark_unknown',
            },
        ),
        migrations.CreateModel(
            name='MarkUnknownHistory',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('version', models.PositiveSmallIntegerField()),
                ('status', models.CharField(choices=[('0', 'Unreported'), ('1', 'Reported'), ('2', 'Fixed'), ('3', 'Rejected')], default='0', max_length=1)),
                ('change_date', models.DateTimeField()),
                ('comment', models.TextField()),
                ('description', models.TextField()),
                ('function', models.TextField()),
                ('problem_pattern', models.CharField(max_length=100)),
                ('link', models.URLField(null=True)),
                ('author', models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, related_name='markunknownhistory', null=True)),
                ('mark', models.ForeignKey(to='marks.MarkUnknown', related_name='versions')),
            ],
            options={
                'db_table': 'mark_unknown_history',
            },
        ),
        migrations.CreateModel(
            name='MarkUnknownReport',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('mark', models.ForeignKey(to='marks.MarkUnknown', related_name='markreport_set')),
            ],
            options={
                'db_table': 'cache_mark_unknown_report',
            },
        ),
        migrations.CreateModel(
            name='MarkUnsafe',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('identifier', models.CharField(unique=True, max_length=255)),
                ('format', models.PositiveSmallIntegerField(default=1)),
                ('version', models.PositiveSmallIntegerField(default=1)),
                ('status', models.CharField(choices=[('0', 'Unreported'), ('1', 'Reported'), ('2', 'Fixed'), ('3', 'Rejected')], default='0', max_length=1)),
                ('is_modifiable', models.BooleanField(default=True)),
                ('change_date', models.DateTimeField(auto_now=True)),
                ('description', models.TextField(default='')),
                ('type', models.CharField(choices=[('0', 'Created'), ('1', 'Preset'), ('2', 'Uploaded')], default='0', max_length=1)),
                ('verdict', models.CharField(choices=[('0', 'Unknown'), ('1', 'Bug'), ('2', 'Target bug'), ('3', 'False positive')], default='0', max_length=1)),
                ('author', models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, related_name='markunsafe', null=True)),
                ('error_trace', models.ForeignKey(to='jobs.File')),
            ],
            options={
                'db_table': 'mark_unsafe',
            },
        ),
        migrations.CreateModel(
            name='MarkUnsafeAttr',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('is_compare', models.BooleanField(default=True)),
                ('attr', models.ForeignKey(to='reports.Attr')),
            ],
            options={
                'db_table': 'mark_unsafe_attr',
            },
        ),
        migrations.CreateModel(
            name='MarkUnsafeCompare',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('name', models.CharField(max_length=30)),
                ('description', models.CharField(default='', max_length=1000)),
            ],
            options={
                'db_table': 'mark_unsafe_compare',
            },
        ),
        migrations.CreateModel(
            name='MarkUnsafeConvert',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('name', models.CharField(max_length=30)),
                ('description', models.CharField(default='', max_length=1000)),
            ],
            options={
                'db_table': 'mark_unsafe_convert',
            },
        ),
        migrations.CreateModel(
            name='MarkUnsafeHistory',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('version', models.PositiveSmallIntegerField()),
                ('status', models.CharField(choices=[('0', 'Unreported'), ('1', 'Reported'), ('2', 'Fixed'), ('3', 'Rejected')], default='0', max_length=1)),
                ('change_date', models.DateTimeField()),
                ('comment', models.TextField()),
                ('description', models.TextField()),
                ('verdict', models.CharField(choices=[('0', 'Unknown'), ('1', 'Bug'), ('2', 'Target bug'), ('3', 'False positive')], max_length=1)),
                ('author', models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, related_name='markunsafehistory', null=True)),
                ('function', models.ForeignKey(to='marks.MarkUnsafeCompare')),
                ('mark', models.ForeignKey(to='marks.MarkUnsafe', related_name='versions')),
            ],
            options={
                'db_table': 'mark_unsafe_history',
            },
        ),
        migrations.CreateModel(
            name='MarkUnsafeReport',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('result', models.FloatField()),
                ('broken', models.BooleanField(default=False)),
                ('error', models.TextField(null=True)),
                ('mark', models.ForeignKey(to='marks.MarkUnsafe', related_name='markreport_set')),
                ('report', models.ForeignKey(to='reports.ReportUnsafe', related_name='markreport_set')),
            ],
            options={
                'db_table': 'cache_mark_unsafe_report',
            },
        ),
        migrations.CreateModel(
            name='MarkUnsafeTag',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('mark_version', models.ForeignKey(to='marks.MarkUnsafeHistory', related_name='tags')),
            ],
            options={
                'db_table': 'cache_mark_unsafe_tag',
            },
        ),
        migrations.CreateModel(
            name='ReportSafeTag',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('number', models.IntegerField(default=0)),
                ('report', models.ForeignKey(to='reports.ReportComponent', related_name='safe_tags')),
            ],
            options={
                'db_table': 'cache_report_safe_tag',
            },
        ),
        migrations.CreateModel(
            name='ReportUnsafeTag',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('number', models.IntegerField(default=0)),
                ('report', models.ForeignKey(to='reports.ReportComponent', related_name='unsafe_tags')),
            ],
            options={
                'db_table': 'cache_report_unsafe_tag',
            },
        ),
        migrations.CreateModel(
            name='SafeReportTag',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('number', models.PositiveIntegerField(default=0)),
                ('report', models.ForeignKey(to='reports.ReportSafe', related_name='tags')),
            ],
            options={
                'db_table': 'cache_safe_report_safe_tag',
            },
        ),
        migrations.CreateModel(
            name='SafeTag',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('tag', models.CharField(max_length=32)),
                ('description', models.TextField(default='')),
                ('populated', models.BooleanField(default=False)),
                ('parent', models.ForeignKey(to='marks.SafeTag', related_name='children', null=True)),
            ],
            options={
                'db_table': 'mark_safe_tag',
            },
        ),
        migrations.CreateModel(
            name='UnknownProblem',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('name', models.CharField(max_length=15)),
            ],
            options={
                'db_table': 'cache_mark_unknown_problem',
            },
        ),
        migrations.CreateModel(
            name='UnsafeReportTag',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('number', models.PositiveIntegerField(default=0)),
                ('report', models.ForeignKey(to='reports.ReportUnsafe', related_name='tags')),
            ],
            options={
                'db_table': 'cache_unsafe_report_unsafe_tag',
            },
        ),
        migrations.CreateModel(
            name='UnsafeTag',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('tag', models.CharField(max_length=32)),
                ('description', models.TextField(default='')),
                ('populated', models.BooleanField(default=False)),
                ('parent', models.ForeignKey(to='marks.UnsafeTag', related_name='children', null=True)),
            ],
            options={
                'db_table': 'mark_unsafe_tag',
            },
        ),
        migrations.AddField(
            model_name='unsafereporttag',
            name='tag',
            field=models.ForeignKey(to='marks.UnsafeTag'),
        ),
        migrations.AddField(
            model_name='safereporttag',
            name='tag',
            field=models.ForeignKey(to='marks.SafeTag'),
        ),
        migrations.AddField(
            model_name='reportunsafetag',
            name='tag',
            field=models.ForeignKey(to='marks.UnsafeTag', related_name='+'),
        ),
        migrations.AddField(
            model_name='reportsafetag',
            name='tag',
            field=models.ForeignKey(to='marks.SafeTag', related_name='+'),
        ),
        migrations.AddField(
            model_name='markunsafetag',
            name='tag',
            field=models.ForeignKey(to='marks.UnsafeTag', related_name='+'),
        ),
        migrations.AddField(
            model_name='markunsafeattr',
            name='mark',
            field=models.ForeignKey(to='marks.MarkUnsafeHistory', related_name='attrs'),
        ),
        migrations.AddField(
            model_name='markunsafe',
            name='function',
            field=models.ForeignKey(to='marks.MarkUnsafeCompare'),
        ),
        migrations.AddField(
            model_name='markunsafe',
            name='job',
            field=models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, to='jobs.Job', related_name='markunsafe', null=True),
        ),
        migrations.AddField(
            model_name='markunsafe',
            name='prime',
            field=models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, to='reports.ReportUnsafe', related_name='prime_marks', null=True),
        ),
        migrations.AddField(
            model_name='markunknownreport',
            name='problem',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='marks.UnknownProblem'),
        ),
        migrations.AddField(
            model_name='markunknownreport',
            name='report',
            field=models.ForeignKey(to='reports.ReportUnknown', related_name='markreport_set'),
        ),
        migrations.AddField(
            model_name='marksafetag',
            name='tag',
            field=models.ForeignKey(to='marks.SafeTag', related_name='+'),
        ),
        migrations.AddField(
            model_name='marksafeattr',
            name='mark',
            field=models.ForeignKey(to='marks.MarkSafeHistory', related_name='attrs'),
        ),
        migrations.AddField(
            model_name='errortraceconvertioncache',
            name='function',
            field=models.ForeignKey(to='marks.MarkUnsafeConvert'),
        ),
        migrations.AddField(
            model_name='errortraceconvertioncache',
            name='unsafe',
            field=models.ForeignKey(to='reports.ReportUnsafe'),
        ),
        migrations.AddField(
            model_name='componentmarkunknownproblem',
            name='problem',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='marks.UnknownProblem', related_name='+', null=True),
        ),
        migrations.AddField(
            model_name='componentmarkunknownproblem',
            name='report',
            field=models.ForeignKey(to='reports.ReportComponent', related_name='mark_unknowns_cache'),
        ),
    ]
