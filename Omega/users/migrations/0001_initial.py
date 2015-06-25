# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='UserExtended',
            fields=[
                ('id', models.AutoField(primary_key=True, verbose_name='ID', auto_created=True, serialize=False)),
                ('change_date', models.DateTimeField(auto_now=True)),
                ('accuracy', models.SmallIntegerField(default=2)),
                ('language', models.CharField(default='en', max_length=2, choices=[('en', 'English'), ('ru', 'Русский')])),
                ('role', models.CharField(default='none', max_length=4, choices=[('none', 'No access'), ('prod', 'Producer'), ('man', 'Manager'), ('prmn', 'Producer and Manager'), ('adm', 'Administrator')])),
                ('timezone', models.CharField(max_length=255)),
                ('change_author', models.ForeignKey(related_name='+', to=settings.AUTH_USER_MODEL)),
                ('user', models.OneToOneField(to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
