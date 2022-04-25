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


class Migration(migrations.Migration):
    dependencies = [
        ('marks', '0002_alter_convertedtrace_trace_cache_and_more'),
    ]

    operations = [
        migrations.RemoveField(model_name='markunsafehistory', name='function'),
        migrations.AddField(model_name='markunsafe', name='regexp', field=models.TextField(default='')),
        migrations.AddField(model_name='markunsafehistory', name='regexp', field=models.TextField(default='')),
        migrations.AlterField(model_name='convertedtrace', name='function', field=models.CharField(
            db_index=True, max_length=30, verbose_name='Convert trace function'
        )),
        migrations.AlterField(model_name='markunsafe', name='error_trace', field=models.ForeignKey(
            null=True, on_delete=models.deletion.CASCADE, to='marks.convertedtrace'
        )),
        migrations.AlterField(model_name='markunsafehistory', name='error_trace', field=models.ForeignKey(
            null=True, on_delete=models.deletion.CASCADE, to='marks.convertedtrace'
        )),
        migrations.AlterField(model_name='markunsafe', name='function', field=models.CharField(
            db_index=True, max_length=30, verbose_name='Compare trace function'
        )),
    ]
