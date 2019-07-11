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
    dependencies = [('marks', '0002_auto_20190702_1444')]

    operations = [
        migrations.RemoveField(model_name='marksafehistory', name='status'),
        migrations.RemoveField(model_name='markunknownhistory', name='status'),
        migrations.AddField(model_name='markunsafe', name='status', field=models.CharField(choices=[
            ('0', 'Unreported'), ('1', 'Reported'), ('2', 'Fixed'), ('3', 'Rejected')
        ], max_length=1, null=True)),
        migrations.AlterField(model_name='markunsafehistory', name='status', field=models.CharField(choices=[
            ('0', 'Unreported'), ('1', 'Reported'), ('2', 'Fixed'), ('3', 'Rejected')
        ], max_length=1, null=True)),
    ]
