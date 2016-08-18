#
# Copyright (c) 2014-2015 ISPRAS (http://www.ispras.ru)
# Institute for System Programming of the Russian Academy of Sciences
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

from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Extended',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('first_name', models.CharField(max_length=255)),
                ('last_name', models.CharField(max_length=255)),
                ('accuracy', models.SmallIntegerField(default=2)),
                ('data_format', models.CharField(choices=[('raw', 'Raw'), ('hum', 'Human-readable')], default='hum', max_length=3)),
                ('language', models.CharField(choices=[('en', 'English'), ('ru', 'Русский')], default='en', max_length=2)),
                ('role', models.CharField(choices=[('0', 'No access'), ('1', 'Producer'), ('2', 'Manager'), ('3', 'Expert'), ('4', 'Service user')], default='0', max_length=1)),
                ('timezone', models.CharField(default='Europe/Moscow', max_length=255)),
                ('assumptions', models.BooleanField(default=False)),
                ('user', models.OneToOneField(to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'user_extended',
            },
        ),
        migrations.CreateModel(
            name='Notifications',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('settings', models.CharField(max_length=255)),
                ('self_ntf', models.BooleanField(default=True)),
                ('user', models.OneToOneField(to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='PreferableView',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'user_preferable_view',
            },
        ),
        migrations.CreateModel(
            name='View',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, serialize=False, primary_key=True)),
                ('type', models.CharField(choices=[('1', 'job tree'), ('2', 'job view'), ('3', 'component children list'), ('4', 'unsafes list'), ('5', 'safes list'), ('6', 'unknowns list'), ('7', 'unsafe marks'), ('8', 'safe marks'), ('9', 'unknown marks')], default='1', max_length=1)),
                ('name', models.CharField(max_length=255)),
                ('view', models.TextField()),
                ('author', models.ForeignKey(to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'view',
            },
        ),
        migrations.AddField(
            model_name='preferableview',
            name='view',
            field=models.ForeignKey(to='users.View', related_name='+'),
        ),
    ]
