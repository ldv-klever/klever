# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import tarfile
import hashlib
from io import BytesIO
from django.core.files import File as NewFile
from django.core.exceptions import ObjectDoesNotExist
from django.db import migrations, models
import django.db.models.deletion


def compress_files(files, f_model):
    tar_p = BytesIO()
    with tarfile.open(fileobj=tar_p, mode='w:gz') as arch:
        for f_id, f_name in files:
            t = tarfile.TarInfo(f_name)
            with f_model.objects.get(pk=f_id).file as fp:
                fp.seek(0, 2)
                t.size = fp.tell()
                fp.seek(0)
                arch.addfile(t, fp)
    tar_p.seek(0)

    md5 = hashlib.md5()
    while True:
        data = tar_p.read(2 ** 20)
        if not data:
            break
        md5.update(data)
    tar_p.seek(0)
    check_sum = md5.hexdigest()

    try:
        return f_model.objects.get(hash_sum=check_sum)
    except ObjectDoesNotExist:
        db_file = f_model()
        db_file.file.save('data.tar.gz', NewFile(tar_p))
        db_file.hash_sum = check_sum
        db_file.save()
        return db_file


def create_component_archives(apps, schema_editor):
    report_model = apps.get_model("reports", "ReportComponent")
    file_model = apps.get_model("jobs", "File")
    for report in report_model.objects.all():
        report_files = []
        if report.log is not None:
            report_files.append((report.log.pk, 'log.txt'))
        for f in report.files.all():
            report_files.append((f.file.pk, f.name))
        report.archive = compress_files(report_files, file_model)
        report.save()


def create_unsafe_archives(apps, schema_editor):
    report_model = apps.get_model("reports", "ReportUnsafe")
    file_model = apps.get_model("jobs", "File")
    for report in report_model.objects.all():
        report_files = [(report.error_trace.pk, 'error-trace.graphml')]
        for f in report.files.all():
            report_files.append((f.file.pk, f.name))
        report.archive = compress_files(report_files, file_model)
        report.save()


def create_safe_archives(apps, schema_editor):
    report_model = apps.get_model("reports", "ReportSafe")
    file_model = apps.get_model("jobs", "File")
    for report in report_model.objects.all():
        report.archive = compress_files([(report.proof.pk, 'proof.txt')], file_model)
        report.save()


def create_unknown_archives(apps, schema_editor):
    report_model = apps.get_model("reports", "ReportUnknown")
    file_model = apps.get_model("jobs", "File")
    for report in report_model.objects.all():
        report.archive = compress_files([(report.problem_description.pk, 'problem-description.txt')], file_model)
        report.save()


class Migration(migrations.Migration):

    dependencies = [
        ('jobs', '0001_initial'),
        ('reports', '0002_custom'),
    ]

    operations = [
        migrations.RunPython(create_component_archives),
        migrations.RunPython(create_safe_archives),
        migrations.RunPython(create_unknown_archives),
        migrations.RunPython(create_unsafe_archives)
    ]
