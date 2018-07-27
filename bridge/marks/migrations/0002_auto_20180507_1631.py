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


class Migration(migrations.Migration):
    dependencies = [('reports', '0004_alter_fields'), ('marks', '0001_initial')]

    operations = [
        migrations.CreateModel(
            name='MarkUnknownAttr',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('mark', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='attrs',
                                           to='marks.MarkUnknownHistory')),
                ('is_compare', models.BooleanField(default=True)),
                ('attr', models.ForeignKey(on_delete=models.deletion.CASCADE, to='reports.Attr')),
            ],
            options={'db_table': 'mark_unknown_attr'},
        ),
        migrations.AlterField(model_name='marksafe', name='change_date', field=models.DateTimeField()),
        migrations.AlterField(model_name='markunknown', name='change_date', field=models.DateTimeField()),
        migrations.AlterField(model_name='markunsafe', name='change_date', field=models.DateTimeField()),
    ]
