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

from django.db import migrations, models
from django.contrib.postgres.fields import JSONField

import uuid


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ('jobs', '0001_initial'),
        ('reports', '0001_initial'),
        ('marks', '0001_initial'),
    ]

    operations = [

        migrations.CreateModel(name='ReportSafeCache', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('attrs', JSONField(default=dict)),
            ('marks_total', models.PositiveIntegerField(default=0)),
            ('marks_confirmed', models.PositiveIntegerField(default=0)),
            ('verdict', models.CharField(choices=[
                ('0', 'Unknown'), ('1', 'Incorrect proof'), ('2', 'Missed target bug'),
                ('3', 'Incompatible marks'), ('4', 'Without marks')
            ], default='4', max_length=1)),
            ('tags', JSONField(default=dict)),
            ('job', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='+', to='jobs.Job')),
            ('report', models.OneToOneField(
                on_delete=models.deletion.CASCADE, related_name='cache', to='reports.ReportSafe'
            )),
        ], options={'db_table': 'cache_safe'}),

        migrations.CreateModel(name='ReportUnknownCache', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('attrs', JSONField(default=dict)),
            ('marks_total', models.PositiveIntegerField(default=0)),
            ('marks_confirmed', models.PositiveIntegerField(default=0)),
            ('problems', JSONField(default=dict)),
            ('job', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='+', to='jobs.Job')),
            ('report', models.OneToOneField(
                on_delete=models.deletion.CASCADE, related_name='cache', to='reports.ReportUnknown'
            )),
        ], options={'db_table': 'cache_unknown'}),

        migrations.CreateModel(name='ReportUnsafeCache', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('attrs', JSONField(default=dict)),
            ('marks_total', models.PositiveIntegerField(default=0)),
            ('marks_confirmed', models.PositiveIntegerField(default=0)),
            ('verdict', models.CharField(choices=[
                ('0', 'Unknown'), ('1', 'Bug'), ('2', 'Target bug'), ('3', 'False positive'),
                ('4', 'Incompatible marks'), ('5', 'Without marks')
            ], default='5', max_length=1)),
            ('tags', JSONField(default=dict)),
            ('job', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='+', to='jobs.Job')),
            ('report', models.OneToOneField(
                on_delete=models.deletion.CASCADE, related_name='cache', to='reports.ReportUnsafe'
            )),
        ], options={'db_table': 'cache_unsafe'}),

        migrations.CreateModel(name='SafeMarkAssociationChanges', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('identifier', models.UUIDField(default=uuid.uuid4)),
            ('kind', models.CharField(choices=[('0', 'Changed'), ('1', 'New'), ('2', 'Deleted')], max_length=1)),
            ('verdict_old', models.CharField(choices=[
                ('0', 'Unknown'), ('1', 'Incorrect proof'), ('2', 'Missed target bug'),
                ('3', 'Incompatible marks'), ('4', 'Without marks')
            ], max_length=1)),
            ('verdict_new', models.CharField(choices=[
                ('0', 'Unknown'), ('1', 'Incorrect proof'), ('2', 'Missed target bug'),
                ('3', 'Incompatible marks'), ('4', 'Without marks')
            ], max_length=1)),
            ('tags_old', JSONField()),
            ('tags_new', JSONField()),
            ('job', models.ForeignKey(on_delete=models.deletion.CASCADE, to='jobs.Job')),
            ('mark', models.ForeignKey(on_delete=models.deletion.CASCADE, to='marks.MarkSafe')),
            ('report', models.ForeignKey(on_delete=models.deletion.CASCADE, to='reports.ReportSafe')),
        ], options={'db_table': 'cache_safe_mark_associations_changes'}),

        migrations.CreateModel(name='UnknownMarkAssociationChanges', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('identifier', models.UUIDField(default=uuid.uuid4)),
            ('kind', models.CharField(choices=[('0', 'Changed'), ('1', 'New'), ('2', 'Deleted')], max_length=1)),
            ('problems_old', JSONField(default=dict)),
            ('problems_new', JSONField(default=dict)),
            ('job', models.ForeignKey(on_delete=models.deletion.CASCADE, to='jobs.Job')),
            ('mark', models.ForeignKey(on_delete=models.deletion.CASCADE, to='marks.MarkUnknown')),
            ('report', models.ForeignKey(on_delete=models.deletion.CASCADE, to='reports.ReportUnknown')),
        ], options={'db_table': 'cache_unknown_mark_associations_changes'}),

        migrations.CreateModel(name='UnsafeMarkAssociationChanges', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('identifier', models.UUIDField(default=uuid.uuid4)),
            ('kind', models.CharField(choices=[('0', 'Changed'), ('1', 'New'), ('2', 'Deleted')], max_length=1)),
            ('verdict_old', models.CharField(choices=[
                ('0', 'Unknown'), ('1', 'Bug'), ('2', 'Target bug'), ('3', 'False positive'),
                ('4', 'Incompatible marks'), ('5', 'Without marks')
            ], max_length=1)),
            ('verdict_new', models.CharField(choices=[
                ('0', 'Unknown'), ('1', 'Bug'), ('2', 'Target bug'), ('3', 'False positive'),
                ('4', 'Incompatible marks'), ('5', 'Without marks')
            ], max_length=1)),
            ('tags_old', JSONField()),
            ('tags_new', JSONField()),
            ('job', models.ForeignKey(on_delete=models.deletion.CASCADE, to='jobs.Job')),
            ('mark', models.ForeignKey(on_delete=models.deletion.CASCADE, to='marks.MarkUnsafe')),
            ('report', models.ForeignKey(on_delete=models.deletion.CASCADE, to='reports.ReportUnsafe')),
        ], options={'db_table': 'cache_unsafe_mark_associations_changes'}),

    ]
