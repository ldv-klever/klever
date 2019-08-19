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

import django.contrib.postgres.fields.jsonb
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('reports', '0003_auto_20190812_1310')]

    operations = [
        migrations.CreateModel(name='CoverageDataStatistics', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('name', models.CharField(max_length=255)),
            ('data', django.contrib.postgres.fields.jsonb.JSONField()),
            ('coverage', models.ForeignKey(on_delete=models.deletion.CASCADE, to='reports.CoverageArchive')),
        ], options={'db_table': 'report_coverage_data_statistics'}),

        migrations.CreateModel(name='CoverageStatistics', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('identifier', models.PositiveIntegerField()),
            ('parent', models.PositiveIntegerField(null=True)),
            ('is_leaf', models.BooleanField()),
            ('name', models.CharField(max_length=128)),
            ('path', models.TextField(null=True)),
            ('lines_covered', models.PositiveIntegerField(default=0)),
            ('lines_total', models.PositiveIntegerField(default=0)),
            ('funcs_covered', models.PositiveIntegerField(default=0)),
            ('funcs_total', models.PositiveIntegerField(default=0)),
            ('depth', models.PositiveIntegerField(default=0)),
            ('coverage', models.ForeignKey(on_delete=models.deletion.CASCADE, to='reports.CoverageArchive')),
        ], options={'db_table': 'report_coverage_statistics'}),
    ]
