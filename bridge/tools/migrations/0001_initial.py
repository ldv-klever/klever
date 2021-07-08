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

import os
import shutil

from django.conf import settings
from django.db import migrations, models


def clear_media(apps, schema_editor):
    for obj in os.listdir(settings.MEDIA_ROOT):
        full_path = os.path.join(settings.MEDIA_ROOT, obj)
        if os.path.isdir(full_path):
            shutil.rmtree(full_path)
    for obj in os.listdir(settings.LOGS_DIR):
        if obj != '.gitignore':
            full_path = os.path.join(settings.LOGS_DIR, obj)
            try:
                os.remove(full_path)
            except Exception as e:
                try:
                    with open(full_path, mode='w', encoding='utf-8') as fp:
                        fp.write('')
                except Exception as e_w:
                    print(e)
                    print(e_w)


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [

        migrations.CreateModel(name='CallLogs', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('name', models.CharField(db_index=True, max_length=64)),
            ('enter_time', models.DecimalField(decimal_places=4, max_digits=14)),
            ('execution_time', models.DecimalField(decimal_places=4, max_digits=14, null=True)),
            ('return_time', models.DecimalField(decimal_places=4, max_digits=14, null=True)),
            ('execution_delta', models.FloatField(default=0)),
            ('wait1', models.FloatField(default=0)),
            ('wait2', models.FloatField(default=0)),
            ('is_failed', models.BooleanField(default=True)),
        ], options={'db_table': 'tools_call_logs'}),

        migrations.CreateModel(name='LockTable', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('name', models.CharField(db_index=True, max_length=64, unique=True)),
            ('locked', models.BooleanField(default=False)),
        ], options={'db_table': 'lock_table'}),

        migrations.RunPython(clear_media),

    ]
