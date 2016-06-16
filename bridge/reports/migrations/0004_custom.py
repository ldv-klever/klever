# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


def rename_component_log(apps, schema_editor):
    report_model = apps.get_model("reports", "ReportComponent")
    for report in report_model.objects.all():
        if report.log is not None:
            report.log = 'log.txt'
            report.save()


def rename_unsafe_et(apps, schema_editor):
    report_model = apps.get_model("reports", "ReportUnsafe")
    for report in report_model.objects.all():
        report.error_trace = 'error-trace.graphml'
        report.save()


def rename_safe_proof(apps, schema_editor):
    report_model = apps.get_model("reports", "ReportSafe")
    for report in report_model.objects.all():
        report.proof = 'proof.txt'
        report.save()


def rename_unknown_problem(apps, schema_editor):
    report_model = apps.get_model("reports", "ReportUnknown")
    for report in report_model.objects.all():
        report.problem_description = 'problem-description.txt'
        report.save()


class Migration(migrations.Migration):

    dependencies = [
        ('jobs', '0001_initial'),
        ('reports', '0003_custom'),
    ]

    operations = [
        migrations.AlterField(
            model_name='reportcomponent',
            name='log',
            field=models.CharField(max_length=128, null=True),
        ),
        migrations.RunPython(rename_component_log),

        migrations.AlterField(
            model_name='reportsafe',
            name='proof',
            field=models.CharField(max_length=128),
        ),
        migrations.RunPython(rename_safe_proof),

        migrations.AlterField(
            model_name='reportunknown',
            name='problem_description',
            field=models.CharField(max_length=128),
        ),
        migrations.RunPython(rename_unknown_problem),

        migrations.AlterField(
            model_name='reportunsafe',
            name='error_trace',
            field=models.CharField(max_length=128),
        ),
        migrations.RunPython(rename_unsafe_et),

        migrations.RemoveField(model_name='etvfiles', name='file'),
        migrations.RemoveField(model_name='etvfiles', name='unsafe'),
        migrations.DeleteModel(name='ETVFiles'),
        migrations.RemoveField(model_name='reportfiles', name='file'),
        migrations.RemoveField(model_name='reportfiles', name='report'),
        migrations.DeleteModel(name='ReportFiles'),
    ]
