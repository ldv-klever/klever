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

from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models

view_choices = [
    ('0', 'component attributes'),
    ('1', 'job tree'),
    ('2', 'job view'),
    ('3', 'component children list'),
    ('4', 'unsafes list'),
    ('5', 'safes list'),
    ('6', 'unknowns list'),
    ('7', 'unsafe marks'),
    ('8', 'safe marks'),
    ('9', 'unknown marks'),
    ('10', 'unsafe associated marks'),
    ('11', 'safe associated marks'),
    ('12', 'unknown associated marks'),
    ('13', 'unsafe mark associated reports'),
    ('14', 'safe mark associated reports'),
    ('15', 'unknown mark associated reports'),
    ('16', 'safe association changes'),
    ('17', 'unsafe association changes'),
    ('18', 'unknown association changes')
]

roles_choices = [('0', 'No access'), ('1', 'Producer'), ('2', 'Manager'), ('3', 'Expert'), ('4', 'Service user')]


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name='Extended',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('user', models.OneToOneField(on_delete=models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('accuracy', models.SmallIntegerField(default=2)),
                ('data_format', models.CharField(choices=[('raw', 'Raw'), ('hum', 'Human-readable')],
                                                 default='hum', max_length=3)),
                ('language', models.CharField(choices=[('en', 'English'), ('ru', 'Русский')],
                                              default='en', max_length=2)),
                ('role', models.CharField(choices=roles_choices, default='0', max_length=1)),
                ('timezone', models.CharField(default='Europe/Moscow', max_length=255)),
                ('assumptions', models.BooleanField(default=False)),
                ('triangles', models.BooleanField(default=False)),
                ('coverage_data', models.BooleanField(default=False)),
            ],
            options={'db_table': 'user_extended'},
        ),
        migrations.CreateModel(
            name='Notifications',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('user', models.OneToOneField(on_delete=models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('settings', models.CharField(max_length=255)),
                ('self_ntf', models.BooleanField(default=True)),
            ],
        ),
        migrations.CreateModel(
            name='View',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('author', models.ForeignKey(on_delete=models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('type', models.CharField(choices=view_choices, default='1', max_length=2)),
                ('shared', models.BooleanField(default=False)),
                ('name', models.CharField(max_length=255)),
                ('view', models.TextField()),
            ],
            options={'db_table': 'view'},
        ),
        migrations.CreateModel(
            name='PreferableView',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('user', models.ForeignKey(on_delete=models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('view', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='+', to='users.View')),
            ],
            options={'db_table': 'user_preferable_view'},
        ),
    ]
