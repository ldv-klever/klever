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
from django.db.models.deletion import CASCADE, SET_NULL, PROTECT
import reports.models

total_verdict_choices = [
    ('0', 'Total safe'),
    ('1', 'Found all unsafes'),
    ('2', 'Found not all unsafes'),
    ('3', 'Unknown'),
    ('4', 'Unmatched'),
    ('5', 'Broken')
]
safe_verdict_choices = [
    ('0', 'Unknown'),
    ('1', 'Incorrect proof'),
    ('2', 'Missed target bug'),
    ('3', 'Incompatible marks'),
    ('4', 'Without marks')
]
unsafe_verdict_choices = [
    ('0', 'Unknown'),
    ('1', 'Bug'),
    ('2', 'Target bug'),
    ('3', 'False positive'),
    ('4', 'Incompatible marks'),
    ('5', 'Without marks')
]


class Migration(migrations.Migration):
    initial = True
    dependencies = [('jobs', '0001_initial'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name='AttrName',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(db_index=True, max_length=63, unique=True)),
            ],
            options={'db_table': 'attr_name'},
        ),
        migrations.CreateModel(
            name='Attr',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.ForeignKey(on_delete=CASCADE, to='reports.AttrName')),
                ('value', models.CharField(max_length=255)),
            ],
            options={'db_table': 'attr'},
        ),
        migrations.CreateModel(
            name='ReportRoot',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('job', models.OneToOneField(on_delete=CASCADE, to='jobs.Job')),
                ('user', models.ForeignKey(null=True, on_delete=SET_NULL, related_name='+',
                                           to=settings.AUTH_USER_MODEL)),
            ],
            options={'db_table': 'report_root'},
        ),
        migrations.CreateModel(
            name='Report',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('root', models.ForeignKey(on_delete=CASCADE, to='reports.ReportRoot')),
                ('parent', models.ForeignKey(null=True, on_delete=CASCADE, related_name='+', to='reports.Report')),
                ('identifier', models.CharField(max_length=255, unique=True)),
            ],
            options={'db_table': 'report'},
        ),
        migrations.CreateModel(
            name='ReportAttr',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('report', models.ForeignKey(on_delete=CASCADE, related_name='attrs', to='reports.Report')),
                ('attr', models.ForeignKey(on_delete=CASCADE, to='reports.Attr')),
            ],
            options={'db_table': 'report_attrs'},
        ),
        migrations.CreateModel(
            name='Computer',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('description', models.TextField()),
            ],
            options={'db_table': 'computer'},
        ),
        migrations.CreateModel(
            name='Component',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(db_index=True, max_length=20, unique=True)),
            ],
            options={'db_table': 'component'},
        ),
        migrations.CreateModel(
            name='ReportComponent',
            fields=[
                ('report_ptr', models.OneToOneField(auto_created=True, on_delete=CASCADE, parent_link=True,
                                                    primary_key=True, serialize=False, to='reports.Report')),
                ('computer', models.ForeignKey(on_delete=CASCADE, to='reports.Computer')),
                ('component', models.ForeignKey(on_delete=PROTECT, to='reports.Component')),
                ('verification', models.BooleanField(default=False)),
                ('cpu_time', models.BigIntegerField(null=True)),
                ('wall_time', models.BigIntegerField(null=True)),
                ('memory', models.BigIntegerField(null=True)),
                ('start_date', models.DateTimeField()),
                ('finish_date', models.DateTimeField(null=True)),
                ('log', models.FileField(null=True, upload_to=reports.models.get_component_path)),
                ('data', models.FileField(null=True, upload_to=reports.models.get_component_path)),
                ('verifier_input', models.FileField(null=True, upload_to=reports.models.get_component_path)),
                ('covnum', models.PositiveSmallIntegerField(default=0)),
            ],
            options={'db_table': 'report_component'},
            bases=('reports.report',),
        ),
        migrations.CreateModel(
            name='ComponentInstances',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('report', models.ForeignKey(on_delete=CASCADE, to='reports.ReportComponent')),
                ('component', models.ForeignKey(on_delete=CASCADE, to='reports.Component')),
                ('in_progress', models.PositiveIntegerField(default=0)),
                ('total', models.PositiveIntegerField(default=0)),
            ],
            options={'db_table': 'cache_report_component_instances'},
        ),
        migrations.CreateModel(
            name='ComponentResource',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('report', models.ForeignKey(on_delete=CASCADE, related_name='resources_cache',
                                             to='reports.ReportComponent')),
                ('cpu_time', models.BigIntegerField(default=0)),
                ('wall_time', models.BigIntegerField(default=0)),
                ('memory', models.BigIntegerField(default=0)),
                ('component', models.ForeignKey(null=True, on_delete=PROTECT, to='reports.Component')),
            ],
            options={'db_table': 'cache_report_component_resource'},
        ),
        migrations.CreateModel(
            name='CoverageArchive',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('report', models.ForeignKey(on_delete=CASCADE, related_name='coverages',
                                             to='reports.ReportComponent')),
                ('identifier', models.CharField(default='', max_length=128)),
                ('archive', models.FileField(upload_to=reports.models.get_coverage_arch_dir)),

            ],
            options={'db_table': 'report_coverage_archive'},
        ),
        migrations.CreateModel(
            name='CoverageFile',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('archive', models.ForeignKey(on_delete=CASCADE, to='reports.CoverageArchive')),
                ('name', models.CharField(max_length=1024)),
                ('file', models.FileField(null=True, upload_to=reports.models.get_coverage_dir)),
                ('covered_lines', models.PositiveIntegerField(default=0)),
                ('covered_funcs', models.PositiveIntegerField(default=0)),
                ('total_lines', models.PositiveIntegerField(default=0)),
                ('total_funcs', models.PositiveIntegerField(default=0)),
            ],
            options={'db_table': 'cache_report_coverage_file'},
        ),
        migrations.CreateModel(
            name='CoverageDataValue',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('hashsum', models.CharField(max_length=255)),
                ('name', models.CharField(max_length=128)),
                ('value', models.TextField()),
            ],
            options={'db_table': 'cache_report_coverage_data_values'},
        ),
        migrations.CreateModel(
            name='CoverageData',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('covfile', models.ForeignKey(on_delete=CASCADE, to='reports.CoverageFile')),
                ('line', models.PositiveIntegerField()),
                ('data', models.ForeignKey(on_delete=CASCADE, to='reports.CoverageDataValue')),
            ],
            options={'db_table': 'cache_report_coverage_data'},
        ),
        migrations.CreateModel(
            name='CoverageDataStatistics',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=128)),
                ('data', models.FileField(upload_to='CoverageData')),
                ('archive', models.ForeignKey(on_delete=CASCADE, to='reports.CoverageArchive')),
            ],
            options={'db_table': 'cache_report_coverage_data_stat'},
        ),
        migrations.CreateModel(
            name='ReportSafe',
            fields=[
                ('report_ptr', models.OneToOneField(auto_created=True, on_delete=CASCADE, parent_link=True,
                                                    primary_key=True, serialize=False, to='reports.Report')),
                ('proof', models.FileField(null=True, upload_to='Safes/%Y/%m')),
                ('verdict', models.CharField(choices=safe_verdict_choices, default='4', max_length=1)),
                ('memory', models.BigIntegerField()),
                ('cpu_time', models.BigIntegerField()),
                ('wall_time', models.BigIntegerField()),
                ('has_confirmed', models.BooleanField(default=False)),
            ],
            options={'db_table': 'report_safe'},
            bases=('reports.report',),
        ),
        migrations.CreateModel(
            name='ReportUnsafe',
            fields=[
                ('report_ptr', models.OneToOneField(auto_created=True, on_delete=CASCADE, parent_link=True,
                                                    primary_key=True, serialize=False, to='reports.Report')),
                ('error_trace', models.FileField(upload_to='Unsafes/%Y/%m')),
                ('verdict', models.CharField(choices=unsafe_verdict_choices, default='5', max_length=1)),
                ('memory', models.BigIntegerField()),
                ('cpu_time', models.BigIntegerField()),
                ('wall_time', models.BigIntegerField()),
                ('has_confirmed', models.BooleanField(default=False)),
            ],
            options={'db_table': 'report_unsafe'},
            bases=('reports.report',),
        ),
        migrations.CreateModel(
            name='ReportUnknown',
            fields=[
                ('report_ptr', models.OneToOneField(auto_created=True, on_delete=CASCADE, parent_link=True,
                                                    primary_key=True, serialize=False, to='reports.Report')),
                ('problem_description', models.FileField(upload_to='Unknowns/%Y/%m')),
                ('component', models.ForeignKey(on_delete=PROTECT, to='reports.Component')),
                ('memory', models.BigIntegerField(null=True)),
                ('cpu_time', models.BigIntegerField(null=True)),
                ('wall_time', models.BigIntegerField(null=True)),
            ],
            options={'db_table': 'report_unknown'},
            bases=('reports.report',),
        ),
        migrations.CreateModel(
            name='CompareJobsInfo',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('user', models.ForeignKey(on_delete=CASCADE, to=settings.AUTH_USER_MODEL)),
                ('root1', models.ForeignKey(on_delete=CASCADE, related_name='+', to='reports.ReportRoot')),
                ('root2', models.ForeignKey(on_delete=CASCADE, related_name='+', to='reports.ReportRoot')),
                ('files_diff', models.TextField()),
            ],
            options={'db_table': 'cache_report_jobs_compare_info'},
        ),
        migrations.CreateModel(
            name='CompareJobsCache',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('info', models.ForeignKey(on_delete=CASCADE, to='reports.CompareJobsInfo')),
                ('attr_values', models.CharField(db_index=True, max_length=64)),
                ('verdict1', models.CharField(choices=total_verdict_choices, max_length=1)),
                ('verdict2', models.CharField(choices=total_verdict_choices, max_length=1)),
                ('reports1', models.TextField()),
                ('reports2', models.TextField()),
            ],
            options={'db_table': 'cache_report_jobs_compare'},
        ),

        migrations.CreateModel(
            name='ComponentUnknown',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('report', models.ForeignKey(on_delete=CASCADE, related_name='unknowns_cache',
                                             to='reports.ReportComponent')),
                ('number', models.PositiveIntegerField(default=0)),
                ('component', models.ForeignKey(on_delete=PROTECT, to='reports.Component')),
            ],
            options={'db_table': 'cache_report_component_unknown'},
        ),
        migrations.CreateModel(
            name='ReportComponentLeaf',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('report', models.ForeignKey(on_delete=CASCADE, related_name='leaves', to='reports.ReportComponent')),
                ('safe', models.ForeignKey(null=True, on_delete=CASCADE, related_name='leaves',
                                           to='reports.ReportSafe')),
                ('unsafe', models.ForeignKey(null=True, on_delete=CASCADE, related_name='leaves',
                                             to='reports.ReportUnsafe')),
                ('unknown', models.ForeignKey(null=True, on_delete=CASCADE, related_name='leaves',
                                              to='reports.ReportUnknown')),
            ],
            options={'db_table': 'cache_report_component_leaf'},
        ),
        migrations.CreateModel(
            name='Verdict',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('report', models.OneToOneField(on_delete=CASCADE, to='reports.ReportComponent')),
                ('unsafe', models.PositiveIntegerField(default=0)),
                ('unsafe_bug', models.PositiveIntegerField(default=0)),
                ('unsafe_target_bug', models.PositiveIntegerField(default=0)),
                ('unsafe_false_positive', models.PositiveIntegerField(default=0)),
                ('unsafe_unknown', models.PositiveIntegerField(default=0)),
                ('unsafe_unassociated', models.PositiveIntegerField(default=0)),
                ('unsafe_inconclusive', models.PositiveIntegerField(default=0)),
                ('safe', models.PositiveIntegerField(default=0)),
                ('safe_missed_bug', models.PositiveIntegerField(default=0)),
                ('safe_incorrect_proof', models.PositiveIntegerField(default=0)),
                ('safe_unknown', models.PositiveIntegerField(default=0)),
                ('safe_unassociated', models.PositiveIntegerField(default=0)),
                ('safe_inconclusive', models.PositiveIntegerField(default=0)),
                ('unknown', models.PositiveIntegerField(default=0)),
            ],
            options={'db_table': 'cache_report_verdict'},
        ),
        migrations.AlterIndexTogether(name='comparejobscache', index_together={('info', 'verdict1', 'verdict2')}),
        migrations.AlterIndexTogether(name='attr', index_together={('name', 'value')}),
    ]
