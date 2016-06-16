# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('jobs', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Attr',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, verbose_name='ID', serialize=False)),
                ('value', models.CharField(max_length=255)),
            ],
            options={
                'db_table': 'attr',
            },
        ),
        migrations.CreateModel(
            name='AttrName',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, verbose_name='ID', serialize=False)),
                ('name', models.CharField(max_length=63, unique=True)),
            ],
            options={
                'db_table': 'attr_name',
            },
        ),
        migrations.CreateModel(
            name='CompareJobsCache',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, verbose_name='ID', serialize=False)),
                ('attr_values', models.TextField()),
                ('verdict1', models.CharField(max_length=1, choices=[('0', 'Total safe'), ('1', 'Found all unsafes'), ('2', 'Found not all unsafes'), ('3', 'Unknown'), ('4', 'Unmatched')])),
                ('verdict2', models.CharField(max_length=1, choices=[('0', 'Total safe'), ('1', 'Found all unsafes'), ('2', 'Found not all unsafes'), ('3', 'Unknown'), ('4', 'Unmatched')])),
                ('reports1', models.CharField(max_length=1000)),
                ('reports2', models.CharField(max_length=1000)),
            ],
            options={
                'db_table': 'cache_report_jobs_compare',
            },
        ),
        migrations.CreateModel(
            name='CompareJobsInfo',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, verbose_name='ID', serialize=False)),
                ('files_diff', models.TextField()),
            ],
            options={
                'db_table': 'cache_report_jobs_compare_info',
            },
        ),
        migrations.CreateModel(
            name='Component',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, verbose_name='ID', serialize=False)),
                ('name', models.CharField(max_length=15, unique=True)),
            ],
            options={
                'db_table': 'component',
            },
        ),
        migrations.CreateModel(
            name='ComponentResource',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, verbose_name='ID', serialize=False)),
                ('cpu_time', models.BigIntegerField()),
                ('wall_time', models.BigIntegerField()),
                ('memory', models.BigIntegerField()),
                ('component', models.ForeignKey(to='reports.Component', on_delete=django.db.models.deletion.PROTECT, null=True)),
            ],
            options={
                'db_table': 'cache_report_component_resource',
            },
        ),
        migrations.CreateModel(
            name='ComponentUnknown',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, verbose_name='ID', serialize=False)),
                ('number', models.PositiveIntegerField(default=0)),
                ('component', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='reports.Component')),
            ],
            options={
                'db_table': 'cache_report_component_unknown',
            },
        ),
        migrations.CreateModel(
            name='Computer',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, verbose_name='ID', serialize=False)),
                ('description', models.TextField()),
            ],
            options={
                'db_table': 'computer',
            },
        ),
        migrations.CreateModel(
            name='Report',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, verbose_name='ID', serialize=False)),
                ('identifier', models.CharField(max_length=255, unique=True)),
            ],
            options={
                'db_table': 'report',
            },
        ),
        migrations.CreateModel(
            name='ReportAttr',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, verbose_name='ID', serialize=False)),
                ('attr', models.ForeignKey(to='reports.Attr')),
            ],
            options={
                'db_table': 'report_attrs',
            },
        ),
        migrations.CreateModel(
            name='ReportComponentLeaf',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, verbose_name='ID', serialize=False)),
            ],
            options={
                'db_table': 'cache_report_component_leaf',
            },
        ),
        migrations.CreateModel(
            name='ReportRoot',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, verbose_name='ID', serialize=False)),
                ('job', models.OneToOneField(to='jobs.Job')),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.SET_NULL, null=True)),
            ],
            options={
                'db_table': 'report_root',
            },
        ),
        migrations.CreateModel(
            name='Verdict',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, verbose_name='ID', serialize=False)),
                ('unsafe', models.PositiveIntegerField(default=0)),
                ('unsafe_bug', models.PositiveIntegerField(default=0)),
                ('unsafe_target_bug', models.PositiveIntegerField(default=0)),
                ('unsafe_false_positive', models.PositiveIntegerField(default=0)),
                ('unsafe_unknown', models.PositiveIntegerField(default=0)),
                ('unsafe_unassociated', models.PositiveIntegerField(default=0)),
                ('unsafe_inconclusive', models.PositiveIntegerField(default=0)),
                ('safe', models.PositiveIntegerField(default=0)),
                ('safe_missed_bug', models.PositiveIntegerField(default=0)),
                ('safe_incorrect_proof', models.PositiveIntegerField(default=0)),
                ('safe_unknown', models.PositiveIntegerField(default=0)),
                ('safe_unassociated', models.PositiveIntegerField(default=0)),
                ('safe_inconclusive', models.PositiveIntegerField(default=0)),
                ('unknown', models.PositiveIntegerField(default=0)),
            ],
            options={
                'db_table': 'cache_report_verdict',
            },
        ),
        migrations.CreateModel(
            name='ReportComponent',
            fields=[
                ('report_ptr', models.OneToOneField(to='reports.Report', serialize=False, parent_link=True, auto_created=True, primary_key=True)),
                ('cpu_time', models.BigIntegerField(null=True)),
                ('wall_time', models.BigIntegerField(null=True)),
                ('memory', models.BigIntegerField(null=True)),
                ('start_date', models.DateTimeField()),
                ('finish_date', models.DateTimeField(null=True)),
                ('log', models.CharField(max_length=128, null=True)),
                ('archive', models.ForeignKey(to='jobs.File', related_name='reports1', on_delete=django.db.models.deletion.SET_NULL, null=True)),
                ('component', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='reports.Component')),
                ('computer', models.ForeignKey(to='reports.Computer')),
                ('data', models.ForeignKey(to='jobs.File', related_name='reports2', null=True)),
            ],
            options={
                'db_table': 'report_component',
            },
            bases=('reports.report',),
        ),
        migrations.CreateModel(
            name='ReportSafe',
            fields=[
                ('report_ptr', models.OneToOneField(to='reports.Report', serialize=False, parent_link=True, auto_created=True, primary_key=True)),
                ('proof', models.CharField(max_length=128)),
                ('verdict', models.CharField(max_length=1, default='4', choices=[('0', 'Unknown'), ('1', 'Incorrect proof'), ('2', 'Missed target bug'), ('3', 'Incompatible marks'), ('4', 'Without marks')])),
                ('archive', models.ForeignKey(to='jobs.File')),
            ],
            options={
                'db_table': 'report_safe',
            },
            bases=('reports.report',),
        ),
        migrations.CreateModel(
            name='ReportUnknown',
            fields=[
                ('report_ptr', models.OneToOneField(to='reports.Report', serialize=False, parent_link=True, auto_created=True, primary_key=True)),
                ('problem_description', models.CharField(max_length=128)),
                ('archive', models.ForeignKey(to='jobs.File')),
                ('component', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='reports.Component')),
            ],
            options={
                'db_table': 'report_unknown',
            },
            bases=('reports.report',),
        ),
        migrations.CreateModel(
            name='ReportUnsafe',
            fields=[
                ('report_ptr', models.OneToOneField(to='reports.Report', serialize=False, parent_link=True, auto_created=True, primary_key=True)),
                ('error_trace', models.CharField(max_length=128)),
                ('verdict', models.CharField(max_length=1, default='5', choices=[('0', 'Unknown'), ('1', 'Bug'), ('2', 'Target bug'), ('3', 'False positive'), ('4', 'Incompatible marks'), ('5', 'Without marks')])),
                ('archive', models.ForeignKey(to='jobs.File')),
            ],
            options={
                'db_table': 'report_unsafe',
            },
            bases=('reports.report',),
        ),
        migrations.AddField(
            model_name='reportattr',
            name='report',
            field=models.ForeignKey(to='reports.Report', related_name='attrs'),
        ),
        migrations.AddField(
            model_name='report',
            name='parent',
            field=models.ForeignKey(to='reports.Report', related_name='+', null=True),
        ),
        migrations.AddField(
            model_name='report',
            name='root',
            field=models.ForeignKey(to='reports.ReportRoot'),
        ),
        migrations.AddField(
            model_name='comparejobsinfo',
            name='root1',
            field=models.ForeignKey(to='reports.ReportRoot', related_name='+'),
        ),
        migrations.AddField(
            model_name='comparejobsinfo',
            name='root2',
            field=models.ForeignKey(to='reports.ReportRoot', related_name='+'),
        ),
        migrations.AddField(
            model_name='comparejobsinfo',
            name='user',
            field=models.OneToOneField(to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='comparejobscache',
            name='info',
            field=models.ForeignKey(to='reports.CompareJobsInfo'),
        ),
        migrations.AddField(
            model_name='attr',
            name='name',
            field=models.ForeignKey(to='reports.AttrName'),
        ),
        migrations.AddField(
            model_name='verdict',
            name='report',
            field=models.OneToOneField(to='reports.ReportComponent'),
        ),
        migrations.AddField(
            model_name='reportcomponentleaf',
            name='report',
            field=models.ForeignKey(to='reports.ReportComponent', related_name='leaves'),
        ),
        migrations.AddField(
            model_name='reportcomponentleaf',
            name='safe',
            field=models.ForeignKey(to='reports.ReportSafe', related_name='leaves', null=True),
        ),
        migrations.AddField(
            model_name='reportcomponentleaf',
            name='unknown',
            field=models.ForeignKey(to='reports.ReportUnknown', related_name='leaves', null=True),
        ),
        migrations.AddField(
            model_name='reportcomponentleaf',
            name='unsafe',
            field=models.ForeignKey(to='reports.ReportUnsafe', related_name='leaves', null=True),
        ),
        migrations.AddField(
            model_name='componentunknown',
            name='report',
            field=models.ForeignKey(to='reports.ReportComponent', related_name='unknowns_cache'),
        ),
        migrations.AddField(
            model_name='componentresource',
            name='report',
            field=models.ForeignKey(to='reports.ReportComponent', related_name='resources_cache'),
        ),
    ]
