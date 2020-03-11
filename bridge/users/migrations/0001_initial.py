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


import django.contrib.auth.models
import django.contrib.auth.validators
import django.contrib.postgres.fields.jsonb
import django.utils.timezone

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [('auth', '0009_alter_user_last_name_max_length')]

    operations = [

        migrations.CreateModel(name='User', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('password', models.CharField(max_length=128, verbose_name='password')),
            ('last_login', models.DateTimeField(blank=True, null=True, verbose_name='last login')),
            ('is_superuser', models.BooleanField(
                default=False, verbose_name='superuser status',
                help_text='Designates that this user has all permissions without explicitly assigning them.'
            )),
            ('username', models.CharField(
                error_messages={'unique': 'A user with that username already exists.'},
                help_text='Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.',
                max_length=150, unique=True, verbose_name='username',
                validators=[django.contrib.auth.validators.UnicodeUsernameValidator()]
            )),
            ('first_name', models.CharField(blank=True, max_length=30, verbose_name='first name')),
            ('last_name', models.CharField(blank=True, max_length=150, verbose_name='last name')),
            ('email', models.EmailField(blank=True, max_length=254, verbose_name='email address')),
            ('is_staff', models.BooleanField(
                default=False, verbose_name='staff status',
                help_text='Designates whether the user can log into this admin site.'
            )),
            ('is_active', models.BooleanField(
                default=True, verbose_name='active',
                help_text='Designates whether this user should be treated as active. '
                          'Unselect this instead of deleting accounts.'
            )),
            ('date_joined', models.DateTimeField(default=django.utils.timezone.now, verbose_name='date joined')),
            ('accuracy', models.SmallIntegerField(
                default=2, verbose_name='The number of significant figures',
                help_text='This setting is used just for the human-readable data format'
            )),
            ('data_format', models.CharField(
                choices=[('raw', 'Raw'), ('hum', 'Human-readable')], default='hum',
                help_text='Most of dates are not updated automatically, so '
                          'human-readable dates could become outdated until you reload page by hand',
                max_length=3, verbose_name='Data format'
            )),
            ('language', models.CharField(
                choices=[('en', 'English'), ('ru', 'Русский')], default='en', max_length=2, verbose_name='Language'
            )),
            ('role', models.CharField(choices=[
                ('0', 'No access'), ('1', 'Producer'), ('2', 'Manager'), ('3', 'Expert'), ('4', 'Service user')
            ], default='0', max_length=1, verbose_name='Role')),
            ('timezone', models.CharField(default='Europe/Moscow', max_length=255, verbose_name='Time zone')),
            ('assumptions', models.BooleanField(
                default=False, verbose_name='Error trace assumptions',
                help_text='This setting turns on visualization of error trace assumptions. '
                          'This can take very much time for big error traces.',
            )),
            ('triangles', models.BooleanField(
                default=False, verbose_name='Error trace closing triangles',
                help_text='This setting turns on visualization of error trace '
                          'closing triangles at the end of each thread.'
            )),
            ('coverage_data', models.BooleanField(
                default=False, verbose_name='Coverage data',
                help_text='This setting turns on visualization of coverage data and its statistic.'
            )),
            ('groups', models.ManyToManyField(
                blank=True,
                help_text='The groups this user belongs to. A user will get all '
                          'permissions granted to each of their groups.',
                related_name='user_set', related_query_name='user', to='auth.Group', verbose_name='groups'
            )),
            ('user_permissions', models.ManyToManyField(
                blank=True, help_text='Specific permissions for this user.', related_name='user_set',
                related_query_name='user', to='auth.Permission', verbose_name='user permissions'
            )),
            ('default_threshold', models.FloatField(
                default=0, verbose_name='Default unsafe marks threshold',
                help_text='This setting sets default unsafe marks threshold on its creation'
             )),
        ], options={
            'verbose_name': 'user',
            'verbose_name_plural': 'users',
            'db_table': 'users',
            'abstract': False,
            'swappable': 'AUTH_USER_MODEL',
        }, managers=[('objects', django.contrib.auth.models.UserManager())]),

        migrations.CreateModel(name='DataView', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('type', models.CharField(choices=[
                ('0', 'component attributes'), ('1', 'jobTree'), ('2', 'DecisionResults'),
                ('3', 'reportChildren'), ('4', 'SafesAndUnsafesList'), ('5', 'SafesAndUnsafesList'),
                ('6', 'UnknownsList'), ('7', 'marksList'), ('8', 'marksList'), ('9', 'marksList'),
                ('10', 'UnsafeAssMarks'), ('11', 'SafeAssMarks'), ('12', 'UnknownAssMarks'),
                ('13', 'UnsafeAssReports'), ('14', 'SafeAndUnknownAssReports'), ('15', 'SafeAndUnknownAssReports'),
                ('16', 'AssociationChanges'), ('17', 'AssociationChanges'), ('18', 'AssociationChanges')
            ], max_length=2)),
            ('shared', models.BooleanField(default=False)),
            ('name', models.CharField(max_length=255)),
            ('view', django.contrib.postgres.fields.jsonb.JSONField()),
            ('author', models.ForeignKey(
                on_delete=models.deletion.CASCADE, related_name='views', to=settings.AUTH_USER_MODEL
            )),
        ], options={'db_table': 'data_view'}),

        migrations.CreateModel(name='PreferableView', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('user', models.ForeignKey(on_delete=models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ('view', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='+', to='users.DataView')),
        ], options={'db_table': 'user_preferable_view'}),

        migrations.CreateModel(name='SchedulerUser', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('login', models.CharField(max_length=128, verbose_name='Username')),
            ('password', models.CharField(max_length=128)),
            ('user', models.OneToOneField(on_delete=models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
        ], options={'db_table': 'scheduler_user'}),

    ]
