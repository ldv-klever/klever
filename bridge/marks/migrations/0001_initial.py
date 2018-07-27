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

status_choices = [('0', 'Unreported'), ('1', 'Reported'), ('2', 'Fixed'), ('3', 'Rejected')]


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ('jobs', '0001_initial'), ('reports', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ConvertedTraces',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('hash_sum', models.CharField(db_index=True, max_length=255)),
                ('file', models.FileField(upload_to='Error-traces')),
            ],
            options={'db_table': 'file'},
        ),
        migrations.CreateModel(
            name='MarkUnsafeConvert',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(db_index=True, max_length=30)),
                ('description', models.CharField(default='', max_length=1000)),
            ],
            options={'db_table': 'mark_unsafe_convert'},
        ),
        migrations.CreateModel(
            name='MarkUnsafeCompare',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(db_index=True, max_length=30)),
                ('description', models.CharField(default='', max_length=1000)),
                ('convert', models.ForeignKey(on_delete=CASCADE, to='marks.MarkUnsafeConvert')),
            ],
            options={'db_table': 'mark_unsafe_compare'},
        ),
        migrations.CreateModel(
            name='ErrorTraceConvertionCache',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('unsafe', models.ForeignKey(on_delete=CASCADE, to='reports.ReportUnsafe')),
                ('function', models.ForeignKey(on_delete=CASCADE, to='marks.MarkUnsafeConvert')),
                ('converted', models.ForeignKey(on_delete=CASCADE, to='marks.ConvertedTraces')),
            ],
            options={'db_table': 'cache_error_trace_converted'},
        ),
        migrations.CreateModel(
            name='MarkAssociationsChanges',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('identifier', models.CharField(max_length=255, unique=True)),
                ('user', models.ForeignKey(on_delete=CASCADE, to=settings.AUTH_USER_MODEL)),
                ('table_data', models.TextField()),
            ],
            options={'db_table': 'cache_mark_associations_changes'},
        ),
        migrations.CreateModel(
            name='MarkSafe',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('identifier', models.CharField(max_length=255, unique=True)),
                ('version', models.PositiveSmallIntegerField(default=1)),
                ('author', models.ForeignKey(null=True, on_delete=SET_NULL, related_name='+',
                                             to=settings.AUTH_USER_MODEL)),
                ('change_date', models.DateTimeField(auto_now=True)),
                ('is_modifiable', models.BooleanField(default=True)),
                ('type', models.CharField(choices=[('0', 'Created'), ('1', 'Preset'), ('2', 'Uploaded')],
                                          default='0', max_length=1)),
                ('job', models.ForeignKey(null=True, on_delete=SET_NULL, related_name='+', to='jobs.Job')),
                ('format', models.PositiveSmallIntegerField(default=1)),
                ('status', models.CharField(choices=status_choices, default='0', max_length=1)),
                ('verdict', models.CharField(
                    choices=[('0', 'Unknown'), ('1', 'Incorrect proof'), ('2', 'Missed target bug')],
                    default='0', max_length=1)),
                ('description', models.TextField(default='')),
            ],
            options={'db_table': 'mark_safe'},
        ),
        migrations.CreateModel(
            name='MarkSafeHistory',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('mark', models.ForeignKey(on_delete=CASCADE, related_name='versions', to='marks.MarkSafe')),
                ('version', models.PositiveSmallIntegerField()),
                ('author', models.ForeignKey(null=True, on_delete=SET_NULL, related_name='+',
                                             to=settings.AUTH_USER_MODEL)),
                ('change_date', models.DateTimeField()),
                ('status', models.CharField(choices=status_choices, default='0', max_length=1)),
                ('verdict', models.CharField(
                    choices=[('0', 'Unknown'), ('1', 'Incorrect proof'), ('2', 'Missed target bug')], max_length=1)),
                ('description', models.TextField()),
                ('comment', models.TextField()),
            ],
            options={'db_table': 'mark_safe_history'},
        ),
        migrations.CreateModel(
            name='MarkSafeAttr',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('mark', models.ForeignKey(on_delete=CASCADE, related_name='attrs', to='marks.MarkSafeHistory')),
                ('attr', models.ForeignKey(on_delete=CASCADE, to='reports.Attr')),
                ('is_compare', models.BooleanField(default=True)),
            ],
            options={'db_table': 'mark_safe_attr'},
        ),
        migrations.CreateModel(
            name='MarkSafeReport',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('mark', models.ForeignKey(on_delete=CASCADE, related_name='markreport_set', to='marks.MarkSafe')),
                ('report', models.ForeignKey(on_delete=CASCADE, related_name='markreport_set',
                                             to='reports.ReportSafe')),
                ('author', models.ForeignKey(null=True, on_delete=SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('type', models.CharField(choices=[('0', 'Automatic'), ('1', 'Confirmed'), ('2', 'Unconfirmed')],
                                          default='0', max_length=1)),
            ],
            options={'db_table': 'cache_mark_safe_report'},
        ),
        migrations.CreateModel(
            name='SafeAssociationLike',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('association', models.ForeignKey(on_delete=CASCADE, to='marks.MarkSafeReport')),
                ('author', models.ForeignKey(on_delete=CASCADE, to=settings.AUTH_USER_MODEL)),
                ('dislike', models.BooleanField(default=False)),
            ],
            options={'db_table': 'mark_safe_association_like'},
        ),
        migrations.CreateModel(
            name='UnknownProblem',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(db_index=True, max_length=15)),
            ],
            options={'db_table': 'cache_mark_unknown_problem'},
        ),
        migrations.CreateModel(
            name='ComponentMarkUnknownProblem',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('report', models.ForeignKey(on_delete=CASCADE, related_name='mark_unknowns_cache',
                                             to='reports.ReportComponent')),
                ('component', models.ForeignKey(on_delete=PROTECT, related_name='+', to='reports.Component')),
                ('problem', models.ForeignKey(null=True, on_delete=PROTECT, to='marks.UnknownProblem')),
                ('number', models.PositiveIntegerField(default=0)),
            ],
            options={'db_table': 'cache_report_component_mark_unknown_problem'},
        ),
        migrations.CreateModel(
            name='MarkUnknown',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('identifier', models.CharField(max_length=255, unique=True)),
                ('version', models.PositiveSmallIntegerField(default=1)),
                ('author', models.ForeignKey(null=True, on_delete=SET_NULL, related_name='+',
                                             to=settings.AUTH_USER_MODEL)),
                ('change_date', models.DateTimeField(auto_now=True)),
                ('is_modifiable', models.BooleanField(default=True)),
                ('type', models.CharField(choices=[('0', 'Created'), ('1', 'Preset'), ('2', 'Uploaded')],
                                          default='0', max_length=1)),
                ('job', models.ForeignKey(null=True, on_delete=SET_NULL, related_name='+', to='jobs.Job')),
                ('format', models.PositiveSmallIntegerField(default=1)),
                ('status', models.CharField(choices=status_choices, default='0', max_length=1)),
                ('component', models.ForeignKey(on_delete=PROTECT, to='reports.Component')),
                ('problem_pattern', models.CharField(max_length=15)),
                ('function', models.TextField()),
                ('is_regexp', models.BooleanField(default=True)),
                ('link', models.URLField(null=True)),
                ('description', models.TextField(default='')),
            ],
            options={'db_table': 'mark_unknown'},
        ),
        migrations.CreateModel(
            name='MarkUnknownHistory',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('mark', models.ForeignKey(on_delete=CASCADE, related_name='versions', to='marks.MarkUnknown')),
                ('version', models.PositiveSmallIntegerField()),
                ('status', models.CharField(choices=status_choices, default='0', max_length=1)),
                ('author', models.ForeignKey(null=True, on_delete=SET_NULL, related_name='+',
                                             to=settings.AUTH_USER_MODEL)),
                ('change_date', models.DateTimeField()),
                ('problem_pattern', models.CharField(max_length=100)),
                ('function', models.TextField()),
                ('is_regexp', models.BooleanField(default=True)),
                ('link', models.URLField(null=True)),
                ('description', models.TextField()),
                ('comment', models.TextField()),
            ],
            options={'db_table': 'mark_unknown_history'},
        ),
        migrations.CreateModel(
            name='MarkUnknownReport',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('mark', models.ForeignKey(on_delete=CASCADE, related_name='markreport_set', to='marks.MarkUnknown')),
                ('report', models.ForeignKey(on_delete=CASCADE, related_name='markreport_set',
                                             to='reports.ReportUnknown')),
                ('author', models.ForeignKey(null=True, on_delete=SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('problem', models.ForeignKey(on_delete=PROTECT, to='marks.UnknownProblem')),
                ('type', models.CharField(choices=[('0', 'Automatic'), ('1', 'Confirmed'), ('2', 'Unconfirmed')],
                                          default='0', max_length=1)),
            ],
            options={'db_table': 'cache_mark_unknown_report'},
        ),
        migrations.CreateModel(
            name='UnknownAssociationLike',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('association', models.ForeignKey(on_delete=CASCADE, to='marks.MarkUnknownReport')),
                ('author', models.ForeignKey(on_delete=CASCADE, to=settings.AUTH_USER_MODEL)),
                ('dislike', models.BooleanField(default=False)),
            ],
            options={'db_table': 'mark_unknown_association_like'},
        ),
        migrations.CreateModel(
            name='MarkUnsafe',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('identifier', models.CharField(max_length=255, unique=True)),
                ('version', models.PositiveSmallIntegerField(default=1)),
                ('author', models.ForeignKey(null=True, on_delete=SET_NULL, related_name='+',
                                             to=settings.AUTH_USER_MODEL)),
                ('change_date', models.DateTimeField(auto_now=True)),
                ('is_modifiable', models.BooleanField(default=True)),
                ('type', models.CharField(choices=[('0', 'Created'), ('1', 'Preset'), ('2', 'Uploaded')],
                                          default='0', max_length=1)),
                ('job', models.ForeignKey(null=True, on_delete=SET_NULL, related_name='+', to='jobs.Job')),
                ('format', models.PositiveSmallIntegerField(default=1)),
                ('status', models.CharField(choices=status_choices, default='0', max_length=1)),
                ('verdict', models.CharField(
                    choices=[('0', 'Unknown'), ('1', 'Bug'), ('2', 'Target bug'), ('3', 'False positive')],
                    default='0', max_length=1)),
                ('function', models.ForeignKey(on_delete=CASCADE, to='marks.MarkUnsafeCompare')),
                ('description', models.TextField(default='')),

            ],
            options={'db_table': 'mark_unsafe'},
        ),
        migrations.CreateModel(
            name='MarkUnsafeHistory',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('mark', models.ForeignKey(on_delete=CASCADE, related_name='versions', to='marks.MarkUnsafe')),
                ('version', models.PositiveSmallIntegerField()),
                ('author', models.ForeignKey(null=True, on_delete=SET_NULL, related_name='+',
                                             to=settings.AUTH_USER_MODEL)),
                ('change_date', models.DateTimeField()),
                ('status', models.CharField(choices=status_choices, default='0', max_length=1)),
                ('verdict', models.CharField(
                    choices=[('0', 'Unknown'), ('1', 'Bug'), ('2', 'Target bug'), ('3', 'False positive')],
                    max_length=1)),
                ('error_trace', models.ForeignKey(on_delete=CASCADE, to='marks.ConvertedTraces')),
                ('function', models.ForeignKey(on_delete=CASCADE, to='marks.MarkUnsafeCompare')),
                ('description', models.TextField()),
                ('comment', models.TextField()),
            ],
            options={'db_table': 'mark_unsafe_history'},
        ),
        migrations.CreateModel(
            name='MarkUnsafeAttr',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('mark', models.ForeignKey(on_delete=CASCADE, related_name='attrs', to='marks.MarkUnsafeHistory')),
                ('attr', models.ForeignKey(on_delete=CASCADE, to='reports.Attr')),
                ('is_compare', models.BooleanField(default=True)),
            ],
            options={'db_table': 'mark_unsafe_attr'},
        ),
        migrations.CreateModel(
            name='MarkUnsafeReport',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('mark', models.ForeignKey(on_delete=CASCADE, related_name='markreport_set', to='marks.MarkUnsafe')),
                ('report', models.ForeignKey(on_delete=CASCADE, related_name='markreport_set',
                                             to='reports.ReportUnsafe')),
                ('author', models.ForeignKey(null=True, on_delete=SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('type', models.CharField(choices=[('0', 'Automatic'), ('1', 'Confirmed'), ('2', 'Unconfirmed')],
                                          default='0', max_length=1)),
                ('result', models.FloatField()),
                ('error', models.TextField(null=True)),
            ],
            options={'db_table': 'cache_mark_unsafe_report'},
        ),
        migrations.CreateModel(
            name='UnsafeAssociationLike',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('association', models.ForeignKey(on_delete=CASCADE, to='marks.MarkUnsafeReport')),
                ('author', models.ForeignKey(on_delete=CASCADE, to=settings.AUTH_USER_MODEL)),
                ('dislike', models.BooleanField(default=False)),
            ],
            options={'db_table': 'mark_unsafe_association_like'},
        ),
        migrations.CreateModel(
            name='SafeTag',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('parent', models.ForeignKey(null=True, on_delete=CASCADE, related_name='children',
                                             to='marks.SafeTag')),
                ('author', models.ForeignKey(on_delete=CASCADE, to=settings.AUTH_USER_MODEL)),
                ('populated', models.BooleanField(default=False)),
                ('tag', models.CharField(db_index=True, max_length=32)),
                ('description', models.TextField(default='')),
            ],
            options={'db_table': 'mark_safe_tag'},
        ),
        migrations.CreateModel(
            name='SafeTagAccess',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('user', models.ForeignKey(on_delete=CASCADE, to=settings.AUTH_USER_MODEL)),
                ('tag', models.ForeignKey(on_delete=CASCADE, to='marks.SafeTag')),
                ('modification', models.BooleanField(default=False)),
                ('child_creation', models.BooleanField(default=False)),
            ],
            options={'db_table': 'marks_safe_tag_access'},
        ),
        migrations.CreateModel(
            name='MarkSafeTag',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('mark_version', models.ForeignKey(on_delete=CASCADE, related_name='tags', to='marks.MarkSafeHistory')),
                ('tag', models.ForeignKey(on_delete=CASCADE, related_name='+', to='marks.SafeTag')),
            ],
            options={'db_table': 'cache_mark_safe_tag'},
        ),
        migrations.CreateModel(
            name='ReportSafeTag',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('report', models.ForeignKey(on_delete=CASCADE, related_name='safe_tags',
                                             to='reports.ReportComponent')),
                ('tag', models.ForeignKey(on_delete=CASCADE, related_name='+', to='marks.SafeTag')),
                ('number', models.IntegerField(default=0)),
            ],
            options={'db_table': 'cache_report_safe_tag'},
        ),
        migrations.CreateModel(
            name='SafeReportTag',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('report', models.ForeignKey(on_delete=CASCADE, related_name='tags', to='reports.ReportSafe')),
                ('tag', models.ForeignKey(on_delete=CASCADE, to='marks.SafeTag')),
                ('number', models.PositiveIntegerField(default=0)),
            ],
            options={'db_table': 'cache_safe_report_safe_tag'},
        ),
        migrations.CreateModel(
            name='UnsafeTag',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('parent', models.ForeignKey(null=True, on_delete=CASCADE, related_name='children',
                                             to='marks.UnsafeTag')),
                ('author', models.ForeignKey(on_delete=CASCADE, to=settings.AUTH_USER_MODEL)),
                ('populated', models.BooleanField(default=False)),
                ('tag', models.CharField(db_index=True, max_length=32)),
                ('description', models.TextField(default='')),
            ],
            options={'db_table': 'mark_unsafe_tag'},
        ),
        migrations.CreateModel(
            name='UnsafeTagAccess',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('user', models.ForeignKey(on_delete=CASCADE, to=settings.AUTH_USER_MODEL)),
                ('tag', models.ForeignKey(on_delete=CASCADE, to='marks.UnsafeTag')),
                ('modification', models.BooleanField(default=False)),
                ('child_creation', models.BooleanField(default=False)),
            ],
            options={'db_table': 'marks_unsafe_tag_access'},
        ),
        migrations.CreateModel(
            name='MarkUnsafeTag',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('mark_version', models.ForeignKey(on_delete=CASCADE, related_name='tags',
                                                   to='marks.MarkUnsafeHistory')),
                ('tag', models.ForeignKey(on_delete=CASCADE, related_name='+', to='marks.UnsafeTag')),
            ],
            options={'db_table': 'cache_mark_unsafe_tag'},
        ),
        migrations.CreateModel(
            name='ReportUnsafeTag',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('report', models.ForeignKey(on_delete=CASCADE, related_name='unsafe_tags',
                                             to='reports.ReportComponent')),
                ('tag', models.ForeignKey(on_delete=CASCADE, related_name='+', to='marks.UnsafeTag')),
                ('number', models.IntegerField(default=0)),
            ],
            options={'db_table': 'cache_report_unsafe_tag'},
        ),
        migrations.CreateModel(
            name='UnsafeReportTag',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('report', models.ForeignKey(on_delete=CASCADE, related_name='tags', to='reports.ReportUnsafe')),
                ('tag', models.ForeignKey(on_delete=CASCADE, to='marks.UnsafeTag')),
                ('number', models.PositiveIntegerField(default=0)),
            ],
            options={'db_table': 'cache_unsafe_report_unsafe_tag'},
        ),

        migrations.AlterIndexTogether(name='markunknown', index_together={('component', 'problem_pattern')}),
    ]
