# -*- coding: utf-8 -*-
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
                ('id', models.AutoField(primary_key=True, verbose_name='ID', auto_created=True, serialize=False)),
                ('first_name', models.CharField(max_length=255)),
                ('last_name', models.CharField(max_length=255)),
                ('accuracy', models.SmallIntegerField(default=2)),
                ('data_format', models.CharField(max_length=3, default='hum', choices=[('raw', 'Raw'), ('hum', 'Human-readable')])),
                ('language', models.CharField(max_length=2, default='en', choices=[('en', 'English'), ('ru', 'Русский')])),
                ('role', models.CharField(max_length=1, default='0', choices=[('0', 'No access'), ('1', 'Producer'), ('2', 'Manager'), ('3', 'Expert'), ('4', 'Service user')])),
                ('timezone', models.CharField(max_length=255, default='Europe/Moscow')),
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
                ('id', models.AutoField(primary_key=True, verbose_name='ID', auto_created=True, serialize=False)),
                ('settings', models.CharField(max_length=255)),
                ('self_ntf', models.BooleanField(default=True)),
                ('user', models.OneToOneField(to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='PreferableView',
            fields=[
                ('id', models.AutoField(primary_key=True, verbose_name='ID', auto_created=True, serialize=False)),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'user_preferable_view',
            },
        ),
        migrations.CreateModel(
            name='View',
            fields=[
                ('id', models.AutoField(primary_key=True, verbose_name='ID', auto_created=True, serialize=False)),
                ('type', models.CharField(max_length=1, default='1', choices=[('4', 'unsafes list'), ('5', 'safes list'), ('7', 'unsafe marks'), ('3', 'component children list'), ('9', 'unknown marks'), ('6', 'unknowns list'), ('8', 'safe marks'), ('2', 'job view'), ('1', 'job tree')])),
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
            field=models.ForeignKey(related_name='+', to='users.View'),
        ),
    ]
