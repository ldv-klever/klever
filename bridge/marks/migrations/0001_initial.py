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
from django.contrib.postgres.fields import JSONField, ArrayField
from django.db import migrations, models
from django.utils.timezone import now

import uuid
import mptt.fields
import bridge.utils


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('jobs', '0001_initial'),
        ('reports', '0001_initial'),
    ]

    operations = [

        migrations.CreateModel(name='ConvertedTrace', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('hash_sum', models.CharField(db_index=True, max_length=255)),
            ('file', models.FileField(upload_to='Error-traces')),
            ('function', models.CharField(db_index=True, max_length=30)),
            ('trace_cache', JSONField()),
        ], options={'db_table': 'cache_marks_trace'}, bases=(bridge.utils.WithFilesMixin, models.Model)),

        migrations.CreateModel(name='MarkSafe', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('identifier', models.UUIDField(default=uuid.uuid4, unique=True)),
            ('version', models.PositiveSmallIntegerField(default=1)),
            ('is_modifiable', models.BooleanField(default=True)),
            ('source', models.CharField(choices=[
                ('0', 'Created'), ('1', 'Preset'), ('2', 'Uploaded')
            ], default='0', max_length=1)),
            ('cache_attrs', JSONField(default=dict)),
            ('verdict', models.CharField(choices=[
                ('0', 'Unknown'), ('1', 'Incorrect proof'), ('2', 'Missed target bug')
            ], max_length=1)),
            ('cache_tags', ArrayField(base_field=models.CharField(max_length=32), default=list, size=None)),
            ('author', models.ForeignKey(
                null=True, on_delete=models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL
            )),
            ('job', models.ForeignKey(null=True, on_delete=models.deletion.SET_NULL, related_name='+', to='jobs.Job')),
        ], options={'verbose_name': 'Safes mark', 'db_table': 'mark_safe'}),

        migrations.CreateModel(name='MarkSafeHistory', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('version', models.PositiveSmallIntegerField()),
            ('change_date', models.DateTimeField(default=now)),
            ('comment', models.TextField(blank=True, default='')),
            ('description', models.TextField(blank=True, default='')),
            ('verdict', models.CharField(choices=[
                ('0', 'Unknown'), ('1', 'Incorrect proof'), ('2', 'Missed target bug')
            ], max_length=1)),
            ('author', models.ForeignKey(
                null=True, on_delete=models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL
            )),
            ('mark', models.ForeignKey(
                on_delete=models.deletion.CASCADE, related_name='versions', to='marks.MarkSafe'
            )),
        ], options={'verbose_name': 'Safes mark version', 'db_table': 'mark_safe_history'}),

        migrations.CreateModel(name='MarkSafeAttr', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('name', models.CharField(db_index=True, max_length=64)),
            ('value', models.CharField(max_length=255)),
            ('is_compare', models.BooleanField(default=True)),
            ('mark_version', models.ForeignKey(
                on_delete=models.deletion.CASCADE, related_name='attrs', to='marks.MarkSafeHistory'
            )),
        ], options={'db_table': 'mark_safe_attr', 'ordering': ('id',)}),

        migrations.CreateModel(name='MarkSafeReport', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('type', models.CharField(choices=[
                ('0', 'Automatic'), ('1', 'Confirmed'), ('2', 'Unconfirmed')
            ], default='0', max_length=1)),
            ('author', models.ForeignKey(null=True, on_delete=models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ('mark', models.ForeignKey(
                on_delete=models.deletion.CASCADE, related_name='markreport_set', to='marks.MarkSafe'
            )),
            ('report', models.ForeignKey(
                on_delete=models.deletion.CASCADE, related_name='markreport_set', to='reports.ReportSafe'
            )),
            ('associated', models.BooleanField(default=True)),
        ], options={'db_table': 'cache_mark_safe_report'}),

        migrations.CreateModel(name='SafeTag', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('name', models.CharField(db_index=True, max_length=32)),
            ('description', models.TextField(blank=True, default='')),
            ('populated', models.BooleanField(default=False)),
            ('lft', models.PositiveIntegerField(editable=False)),
            ('rght', models.PositiveIntegerField(editable=False)),
            ('tree_id', models.PositiveIntegerField(db_index=True, editable=False)),
            ('level', models.PositiveIntegerField(editable=False)),
            ('author', models.ForeignKey(null=True, on_delete=models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
        ], options={'db_table': 'mark_safe_tag'}),

        migrations.CreateModel(name='MarkSafeTag', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('mark_version', models.ForeignKey(
                on_delete=models.deletion.CASCADE, related_name='tags', to='marks.MarkSafeHistory'
            )),
            ('tag', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='+', to='marks.SafeTag')),
        ], options={'db_table': 'cache_mark_safe_tag'}),

        migrations.CreateModel(name='MarkUnknown', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('identifier', models.UUIDField(default=uuid.uuid4, unique=True)),
            ('version', models.PositiveSmallIntegerField(default=1)),
            ('is_modifiable', models.BooleanField(default=True)),
            ('source', models.CharField(choices=[
                ('0', 'Created'), ('1', 'Preset'), ('2', 'Uploaded')
            ], default='0', max_length=1)),
            ('cache_attrs', JSONField(default=dict)),
            ('component', models.CharField(max_length=20)),
            ('function', models.TextField()),
            ('is_regexp', models.BooleanField(default=True)),
            ('problem_pattern', models.CharField(max_length=20)),
            ('link', models.URLField(blank=True, null=True)),
            ('author', models.ForeignKey(
                null=True, on_delete=models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL
            )),
            ('job', models.ForeignKey(null=True, on_delete=models.deletion.SET_NULL, related_name='+', to='jobs.Job')),
        ], options={'verbose_name': 'Unknowns mark', 'db_table': 'mark_unknown'}),

        migrations.CreateModel(name='MarkUnknownHistory', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('version', models.PositiveSmallIntegerField()),
            ('change_date', models.DateTimeField(default=now)),
            ('comment', models.TextField(blank=True, default='')),
            ('description', models.TextField(blank=True, default='')),
            ('function', models.TextField()),
            ('is_regexp', models.BooleanField(default=True)),
            ('problem_pattern', models.CharField(max_length=20)),
            ('link', models.URLField(blank=True, null=True)),
            ('author', models.ForeignKey(
                null=True, on_delete=models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL
            )),
            ('mark', models.ForeignKey(
                on_delete=models.deletion.CASCADE, related_name='versions', to='marks.MarkUnknown'
            )),
        ], options={'verbose_name': 'Unknowns mark version', 'db_table': 'mark_unknown_history'}),

        migrations.CreateModel(name='MarkUnknownAttr', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('name', models.CharField(db_index=True, max_length=64)),
            ('value', models.CharField(max_length=255)),
            ('is_compare', models.BooleanField(default=True)),
            ('mark_version', models.ForeignKey(
                on_delete=models.deletion.CASCADE, related_name='attrs', to='marks.MarkUnknownHistory'
            )),
        ], options={'db_table': 'mark_unknown_attr'}),

        migrations.CreateModel(name='MarkUnknownReport', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('problem', models.CharField(db_index=True, max_length=20)),
            ('type', models.CharField(choices=[
                ('0', 'Automatic'), ('1', 'Confirmed'), ('2', 'Unconfirmed')
            ], default='0', max_length=1)),
            ('author', models.ForeignKey(null=True, on_delete=models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ('mark', models.ForeignKey(
                on_delete=models.deletion.CASCADE, related_name='markreport_set', to='marks.MarkUnknown'
            )),
            ('report', models.ForeignKey(
                on_delete=models.deletion.CASCADE, related_name='markreport_set', to='reports.ReportUnknown'
            )),
            ('associated', models.BooleanField(default=True)),
        ], options={'db_table': 'cache_mark_unknown_report'}),

        migrations.CreateModel(name='MarkUnsafe', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('identifier', models.UUIDField(default=uuid.uuid4, unique=True)),
            ('version', models.PositiveSmallIntegerField(default=1)),
            ('is_modifiable', models.BooleanField(default=True)),
            ('source', models.CharField(choices=[
                ('0', 'Created'), ('1', 'Preset'), ('2', 'Uploaded')
            ], default='0', max_length=1)),
            ('cache_attrs', JSONField(default=dict)),
            ('function', models.CharField(db_index=True, max_length=30)),
            ('verdict', models.CharField(choices=[
                ('0', 'Unknown'), ('1', 'Bug'), ('2', 'Target bug'), ('3', 'False positive')
            ], max_length=1)),
            ('cache_tags', ArrayField(base_field=models.CharField(max_length=32), default=list, size=None)),
            ('author', models.ForeignKey(
                null=True, on_delete=models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL
            )),
            ('error_trace', models.ForeignKey(on_delete=models.deletion.CASCADE, to='marks.ConvertedTrace')),
            ('job', models.ForeignKey(null=True, on_delete=models.deletion.SET_NULL, related_name='+', to='jobs.Job')),
            ('threshold', models.FloatField(default=0)),
            ('status', models.CharField(choices=[
                ('0', 'Unreported'), ('1', 'Reported'), ('2', 'Fixed'), ('3', 'Rejected')
            ], max_length=1, null=True)),
        ], options={'verbose_name': 'Unsafes mark', 'db_table': 'mark_unsafe'}),

        migrations.CreateModel(name='MarkUnsafeHistory', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('version', models.PositiveSmallIntegerField()),
            ('status', models.CharField(choices=[
                ('0', 'Unreported'), ('1', 'Reported'), ('2', 'Fixed'), ('3', 'Rejected')
            ], max_length=1, null=True)),
            ('change_date', models.DateTimeField(default=now)),
            ('comment', models.TextField(blank=True, default='')),
            ('description', models.TextField(blank=True, default='')),
            ('function', models.CharField(db_index=True, max_length=30)),
            ('verdict', models.CharField(choices=[
                ('0', 'Unknown'), ('1', 'Bug'), ('2', 'Target bug'), ('3', 'False positive')
            ], max_length=1)),
            ('author', models.ForeignKey(
                null=True, on_delete=models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL
            )),
            ('error_trace', models.ForeignKey(on_delete=models.deletion.CASCADE, to='marks.ConvertedTrace')),
            ('mark', models.ForeignKey(
                on_delete=models.deletion.CASCADE, related_name='versions', to='marks.MarkUnsafe'
            )),
            ('threshold', models.FloatField(default=0)),
        ], options={'verbose_name': 'Unsafes mark version', 'db_table': 'mark_unsafe_history'}),

        migrations.CreateModel(name='MarkUnsafeAttr', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('name', models.CharField(db_index=True, max_length=64)),
            ('value', models.CharField(max_length=255)),
            ('is_compare', models.BooleanField(default=True)),
            ('mark_version', models.ForeignKey(
                on_delete=models.deletion.CASCADE, related_name='attrs', to='marks.MarkUnsafeHistory'
            )),
        ], options={'db_table': 'mark_unsafe_attr', 'ordering': ('id',)}),

        migrations.CreateModel(name='MarkUnsafeReport', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('type', models.CharField(choices=[
                ('0', 'Automatic'), ('1', 'Confirmed'), ('2', 'Unconfirmed')
            ], default='0', max_length=1)),
            ('result', models.FloatField()),
            ('error', models.TextField(null=True)),
            ('author', models.ForeignKey(null=True, on_delete=models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ('mark', models.ForeignKey(
                on_delete=models.deletion.CASCADE, related_name='markreport_set', to='marks.MarkUnsafe'
            )),
            ('report', models.ForeignKey(
                on_delete=models.deletion.CASCADE, related_name='markreport_set', to='reports.ReportUnsafe'
            )),
            ('associated', models.BooleanField(default=True)),
        ], options={'db_table': 'cache_mark_unsafe_report'}),

        migrations.CreateModel(name='SafeAssociationLike', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('dislike', models.BooleanField(default=False)),
            ('association', models.ForeignKey(on_delete=models.deletion.CASCADE, to='marks.MarkSafeReport')),
            ('author', models.ForeignKey(on_delete=models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
        ], options={'db_table': 'mark_safe_association_like'}),

        migrations.CreateModel(name='SafeTagAccess', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('modification', models.BooleanField(default=False)),
            ('child_creation', models.BooleanField(default=False)),
            ('tag', models.ForeignKey(on_delete=models.deletion.CASCADE, to='marks.SafeTag')),
            ('user', models.ForeignKey(on_delete=models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
        ], options={'db_table': 'marks_safe_tag_access'}),

        migrations.CreateModel(name='UnknownAssociationLike', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('dislike', models.BooleanField(default=False)),
            ('association', models.ForeignKey(on_delete=models.deletion.CASCADE, to='marks.MarkUnknownReport')),
            ('author', models.ForeignKey(on_delete=models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
        ], options={'db_table': 'mark_unknown_association_like'}),

        migrations.CreateModel(name='UnsafeAssociationLike', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('dislike', models.BooleanField(default=False)),
            ('association', models.ForeignKey(on_delete=models.deletion.CASCADE, to='marks.MarkUnsafeReport')),
            ('author', models.ForeignKey(on_delete=models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
        ], options={'db_table': 'mark_unsafe_association_like'}),

        migrations.CreateModel(name='UnsafeConvertionCache', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('converted', models.ForeignKey(on_delete=models.deletion.CASCADE, to='marks.ConvertedTrace')),
            ('unsafe', models.ForeignKey(on_delete=models.deletion.CASCADE, to='reports.ReportUnsafe')),
        ], options={'db_table': 'cache_error_trace_converted'}),

        migrations.CreateModel(name='UnsafeTag', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('name', models.CharField(db_index=True, max_length=32)),
            ('description', models.TextField(blank=True, default='')),
            ('populated', models.BooleanField(default=False)),
            ('lft', models.PositiveIntegerField(editable=False)),
            ('rght', models.PositiveIntegerField(editable=False)),
            ('tree_id', models.PositiveIntegerField(db_index=True, editable=False)),
            ('level', models.PositiveIntegerField(editable=False)),
            ('author', models.ForeignKey(null=True, on_delete=models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
        ], options={'db_table': 'mark_unsafe_tag'}),

        migrations.CreateModel(name='MarkUnsafeTag', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('mark_version', models.ForeignKey(
                on_delete=models.deletion.CASCADE, related_name='tags', to='marks.MarkUnsafeHistory'
            )),
            ('tag', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='+', to='marks.UnsafeTag')),
        ], options={'db_table': 'cache_mark_unsafe_tag'}),

        migrations.CreateModel(name='UnsafeTagAccess', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('modification', models.BooleanField(default=False)),
            ('child_creation', models.BooleanField(default=False)),
            ('tag', models.ForeignKey(on_delete=models.deletion.CASCADE, to='marks.UnsafeTag')),
            ('user', models.ForeignKey(on_delete=models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
        ], options={'db_table': 'marks_unsafe_tag_access'}),

        migrations.AddField(model_name='unsafetag', name='parent', field=mptt.fields.TreeForeignKey(
            null=True, on_delete=models.deletion.CASCADE, related_name='children', to='marks.UnsafeTag'
        )),

        migrations.AddField(model_name='safetag', name='parent', field=mptt.fields.TreeForeignKey(
            null=True, on_delete=models.deletion.CASCADE, related_name='children', to='marks.SafeTag'
        )),

        migrations.AlterIndexTogether(name='markunknown', index_together={('component', 'problem_pattern')}),
    ]
