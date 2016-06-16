# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='File',
            fields=[
                ('id', models.AutoField(primary_key=True, verbose_name='ID', auto_created=True, serialize=False)),
                ('hash_sum', models.CharField(max_length=255)),
                ('file', models.FileField(upload_to='Files')),
            ],
            options={
                'db_table': 'file',
            },
        ),
        migrations.CreateModel(
            name='FileSystem',
            fields=[
                ('id', models.AutoField(primary_key=True, verbose_name='ID', auto_created=True, serialize=False)),
                ('name', models.CharField(max_length=150)),
                ('file', models.ForeignKey(to='jobs.File', null=True)),
            ],
            options={
                'db_table': 'file_system',
            },
        ),
        migrations.CreateModel(
            name='Job',
            fields=[
                ('id', models.AutoField(primary_key=True, verbose_name='ID', auto_created=True, serialize=False)),
                ('name', models.CharField(max_length=150)),
                ('format', models.PositiveSmallIntegerField(default=1)),
                ('type', models.CharField(max_length=1, default='0', choices=[('0', 'Verification of Linux kernel modules'), ('1', 'Validation on Linux kernel modules'), ('2', 'Verification of commits in Linux kernel Git repositories'), ('3', 'Validation on commits in Linux kernel Git repositories'), ('4', 'Verification of C programs'), ('5', 'Validation on C programs')])),
                ('version', models.PositiveSmallIntegerField(default=1)),
                ('change_date', models.DateTimeField(auto_now=True)),
                ('identifier', models.CharField(max_length=255, unique=True)),
                ('status', models.CharField(max_length=1, default='0', choices=[('0', 'Not solved'), ('1', 'Pending'), ('2', 'Is solving'), ('3', 'Solved'), ('4', 'Failed'), ('5', 'Corrupted'), ('6', 'Cancelled')])),
                ('change_author', models.ForeignKey(related_name='job', blank=True, to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.SET_NULL, null=True)),
                ('parent', models.ForeignKey(related_name='children', to='jobs.Job', on_delete=django.db.models.deletion.PROTECT, null=True)),
            ],
            options={
                'db_table': 'job',
            },
        ),
        migrations.CreateModel(
            name='JobHistory',
            fields=[
                ('id', models.AutoField(primary_key=True, verbose_name='ID', auto_created=True, serialize=False)),
                ('name', models.CharField(max_length=150)),
                ('version', models.PositiveSmallIntegerField()),
                ('change_date', models.DateTimeField()),
                ('comment', models.CharField(max_length=255, default='')),
                ('global_role', models.CharField(max_length=1, default='0', choices=[('0', 'No access'), ('1', 'Observer'), ('2', 'Expert'), ('3', 'Observer and Operator'), ('4', 'Expert and Operator')])),
                ('description', models.TextField(default='')),
                ('change_author', models.ForeignKey(related_name='jobhistory', blank=True, to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.SET_NULL, null=True)),
                ('job', models.ForeignKey(related_name='versions', to='jobs.Job')),
                ('parent', models.ForeignKey(related_name='+', to='jobs.Job', on_delete=django.db.models.deletion.SET_NULL, null=True)),
            ],
            options={
                'db_table': 'jobhistory',
            },
        ),
        migrations.CreateModel(
            name='RunHistory',
            fields=[
                ('id', models.AutoField(primary_key=True, verbose_name='ID', auto_created=True, serialize=False)),
                ('date', models.DateTimeField()),
                ('status', models.CharField(max_length=1, choices=[('0', 'Not solved'), ('1', 'Pending'), ('2', 'Is solving'), ('3', 'Solved'), ('4', 'Failed'), ('5', 'Corrupted'), ('6', 'Cancelled')])),
                ('configuration', models.ForeignKey(to='jobs.File')),
                ('job', models.ForeignKey(to='jobs.Job')),
                ('operator', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'job_run_history',
            },
        ),
        migrations.CreateModel(
            name='UserRole',
            fields=[
                ('id', models.AutoField(primary_key=True, verbose_name='ID', auto_created=True, serialize=False)),
                ('role', models.CharField(max_length=1, choices=[('0', 'No access'), ('1', 'Observer'), ('2', 'Expert'), ('3', 'Observer and Operator'), ('4', 'Expert and Operator')])),
                ('job', models.ForeignKey(to='jobs.JobHistory')),
                ('user', models.ForeignKey(related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'user_job_role',
            },
        ),
        migrations.AddField(
            model_name='filesystem',
            name='job',
            field=models.ForeignKey(to='jobs.JobHistory'),
        ),
        migrations.AddField(
            model_name='filesystem',
            name='parent',
            field=models.ForeignKey(related_name='children', to='jobs.FileSystem', null=True),
        ),
    ]
