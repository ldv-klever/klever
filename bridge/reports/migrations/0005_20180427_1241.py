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

from django.db import migrations, models

import reports.models


class Migration(migrations.Migration):
    dependencies = [('reports', '0004')]

    operations = [
        migrations.CreateModel(
            name='AttrFile',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file', models.FileField(upload_to=reports.models.get_attr_data_path)),
                ('root', models.ForeignKey(on_delete=models.deletion.CASCADE, to='reports.ReportRoot')),
            ],
            options={'db_table': 'report_attr_file'},
        ),
        migrations.CreateModel(
            name='ErrorTraceSource',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('archive', models.FileField(upload_to='Unsafes/Sources/%Y/%m')),
                ('root', models.ForeignKey(on_delete=models.deletion.CASCADE, to='reports.ReportRoot')),
            ],
            options={'db_table': 'report_et_source'},
        ),
        migrations.RemoveField(model_name='comparejobsinfo', name='files_diff'),
        migrations.AddField(
            model_name='comparejobsinfo', name='attr_names',
            field=models.CharField(default='', max_length=64), preserve_default=False
        ),
        migrations.AddField(model_name='reportattr', name='associate', field=models.BooleanField(default=False)),
        migrations.AddField(model_name='reportattr', name='compare', field=models.BooleanField(default=False)),
        migrations.AddField(
            model_name='reportattr', name='data',
            field=models.ForeignKey(null=True, on_delete=models.deletion.CASCADE, to='reports.AttrFile'),
        ),
        migrations.AddField(
            model_name='reportunsafe', name='trace_id', field=models.CharField(max_length=32, null=True)
        ),
        migrations.AddField(
            model_name='reportunsafe', name='source',
            field=models.ForeignKey(null=True, on_delete=models.deletion.CASCADE, to='reports.ErrorTraceSource'),
        ),
    ]
