# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('jobs', '0001_initial'),
        ('marks', '0002_custom'),
        ('reports', '0004_custom'),
    ]

    operations = [
        migrations.CreateModel(
            name='ErrorTraceConvertionCache',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, primary_key=True, serialize=False)),
                ('converted', models.ForeignKey(to='jobs.File')),
                ('function', models.ForeignKey(to='marks.MarkUnsafeConvert')),
                ('unsafe', models.ForeignKey(to='reports.ReportUnsafe')),
            ],
            options={
                'db_table': 'cache_error_trace_converted',
            },
        ),
    ]
