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
    dependencies = [('marks', '0001_initial')]

    operations = [
        migrations.AddField(model_name='marksafereport', name='associated', field=models.BooleanField(default=True)),
        migrations.AddField(model_name='markunknownreport', name='associated', field=models.BooleanField(default=True)),
        migrations.AddField(model_name='markunsafe', name='threshold', field=models.FloatField(default=0)),
        migrations.AddField(model_name='markunsafehistory', name='threshold', field=models.FloatField(default=0)),
        migrations.AddField(model_name='markunsafereport', name='associated', field=models.BooleanField(default=True)),
    ]
