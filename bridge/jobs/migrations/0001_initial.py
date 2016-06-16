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
                ('id', models.AutoField(auto_created=True, primary_key=True, verbose_name='ID', serialize=False)),
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
                ('id', models.AutoField(auto_created=True, primary_key=True, verbose_name='ID', serialize=False)),
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
                ('id', models.AutoField(auto_created=True, primary_key=True, verbose_name='ID', serialize=False)),
                ('name', models.CharField(max_length=150)),
                ('format', models.PositiveSmallIntegerField(default=1)),
                ('type', models.CharField(max_length=1, default='0', choices=[('0', 'Verification of Linux kernel modules'), ('1', 'Validation on Linux kernel modules'), ('2', 'Verification of commits in Linux kernel Git repositories'), ('3', 'Validation on commits in Linux kernel Git repositories'), ('4', 'Verification of C programs'), ('5', 'Validation on C programs')])),
                ('version', models.PositiveSmallIntegerField(default=1)),
                ('change_date', models.DateTimeField(auto_now=True)),
                ('identifier', models.CharField(max_length=255, unique=True)),
                ('status', models.CharField(max_length=1, default='0', choices=[('0', 'Not solved'), ('1', 'Pending'), ('2', 'Is solving'), ('3', 'Solved'), ('4', 'Failed'), ('5', 'Corrupted'), ('6', 'Cancelled')])),
                ('change_author', models.ForeignKey(blank=True, to=settings.AUTH_USER_MODEL, related_name='job', on_delete=django.db.models.deletion.SET_NULL, null=True)),
                ('parent', models.ForeignKey(to='jobs.Job', related_name='children', on_delete=django.db.models.deletion.PROTECT, null=True)),
            ],
            options={
                'db_table': 'job',
            },
        ),
        migrations.CreateModel(
            name='JobHistory',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, verbose_name='ID', serialize=False)),
                ('name', models.CharField(max_length=150)),
                ('version', models.PositiveSmallIntegerField()),
                ('change_date', models.DateTimeField()),
                ('comment', models.CharField(max_length=255, default='')),
                ('global_role', models.CharField(max_length=1, default='0', choices=[('0', 'No access'), ('1', 'Observer'), ('2', 'Expert'), ('3', 'Observer and Operator'), ('4', 'Expert and Operator')])),
                ('description', models.TextField(default='')),
                ('change_author', models.ForeignKey(blank=True, to=settings.AUTH_USER_MODEL, related_name='jobhistory', on_delete=django.db.models.deletion.SET_NULL, null=True)),
                ('job', models.ForeignKey(to='jobs.Job', related_name='versions')),
                ('parent', models.ForeignKey(to='jobs.Job', related_name='+', on_delete=django.db.models.deletion.SET_NULL, null=True)),
            ],
            options={
                'db_table': 'jobhistory',
            },
        ),
        migrations.CreateModel(
            name='RunHistory',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, verbose_name='ID', serialize=False)),
                ('date', models.DateTimeField()),
                ('status', models.CharField(max_length=1, choices=[('0', 'Not solved'), ('1', 'Pending'), ('2', 'Is solving'), ('3', 'Solved'), ('4', 'Failed'), ('5', 'Corrupted'), ('6', 'Cancelled')])),
                ('configuration', models.ForeignKey(to='jobs.File')),
                ('job', models.ForeignKey(to='jobs.Job')),
                ('operator', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.SET_NULL, null=True)),
            ],
            options={
                'db_table': 'job_run_history',
            },
        ),
        migrations.CreateModel(
            name='UserRole',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, verbose_name='ID', serialize=False)),
                ('role', models.CharField(max_length=1, choices=[('0', 'No access'), ('1', 'Observer'), ('2', 'Expert'), ('3', 'Observer and Operator'), ('4', 'Expert and Operator')])),
                ('job', models.ForeignKey(to='jobs.JobHistory')),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, related_name='+')),
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
            field=models.ForeignKey(to='jobs.FileSystem', related_name='children', null=True),
        ),
    ]
