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
    dependencies = [('tools', '0002_auto_20180605_1656')]
    operations = [
        migrations.AlterField(model_name='calllogs', name='execution_time',
                              field=models.DecimalField(decimal_places=4, max_digits=14, null=True)),
        migrations.AlterField(model_name='calllogs', name='return_time',
                              field=models.DecimalField(decimal_places=4, max_digits=14, null=True)),
        migrations.AlterField(model_name='calllogs', name='wait1', field=models.FloatField(default=0)),
        migrations.AlterField(model_name='calllogs', name='wait2', field=models.FloatField(default=0)),
    ]
