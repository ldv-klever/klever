#
# Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
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

import os
import time
from django.db import models
from django.db.models.signals import pre_delete
from django.dispatch.dispatcher import receiver
from django.contrib.auth.models import User
from django.core.files import File
from django.utils.timezone import now
from bridge.vars import UNSAFE_VERDICTS, SAFE_VERDICTS, COMPARE_VERDICT
from bridge.utils import RemoveFilesBeforeDelete, logger
from jobs.models import Job


def get_component_path(instance, filename):
    curr_date = now()
    return os.path.join('Reports', instance.component.name, str(curr_date.year), str(curr_date.month), filename)


def get_coverage_arch_dir(instance, filename):
    curr_date = now()
    return os.path.join('Reports', instance.report.component.name, str(curr_date.year), str(curr_date.month), filename)


def get_coverage_dir(instance, filename):
    return os.path.join('Reports', 'CoverageCache', 'CovArch-%s' % instance.archive_id, filename)


def get_attr_data_path(instance, filename):
    return os.path.join('Reports', 'AttrData', 'Root-%s' % str(instance.root_id), filename)


class ReportRoot(models.Model):
    user = models.ForeignKey(User, models.SET_NULL, null=True, related_name='+')
    job = models.OneToOneField(Job, models.CASCADE)

    class Meta:
        db_table = 'report_root'


@receiver(pre_delete, sender=ReportRoot)
def reportroot_delete_signal(**kwargs):
    t1 = time.time()
    RemoveFilesBeforeDelete(kwargs['instance'])
    logger.info('Deleting ReportRoot files took %s seconds.' % (time.time() - t1))


class AttrName(models.Model):
    name = models.CharField(max_length=63, unique=True, db_index=True)

    class Meta:
        db_table = 'attr_name'


class Attr(models.Model):
    name = models.ForeignKey(AttrName, models.CASCADE)
    value = models.CharField(max_length=255)

    class Meta:
        db_table = 'attr'
        index_together = ["name", "value"]


class Report(models.Model):
    root = models.ForeignKey(ReportRoot, models.CASCADE)
    parent = models.ForeignKey('self', models.CASCADE, null=True, related_name='children')
    identifier = models.CharField(max_length=255, unique=True)

    class Meta:
        db_table = 'report'


class AttrFile(models.Model):
    root = models.ForeignKey(ReportRoot, models.CASCADE)
    file = models.FileField(upload_to=get_attr_data_path)

    class Meta:
        db_table = 'report_attr_file'


@receiver(pre_delete, sender=AttrFile)
def attrfile_delete_signal(**kwargs):
    source = kwargs['instance']
    source.file.storage.delete(source.file.path)


class ReportAttr(models.Model):
    attr = models.ForeignKey(Attr, models.CASCADE)
    report = models.ForeignKey(Report, models.CASCADE, related_name='attrs')
    compare = models.BooleanField(default=False)
    associate = models.BooleanField(default=False)
    data = models.ForeignKey(AttrFile, models.CASCADE, null=True)

    class Meta:
        db_table = 'report_attrs'


class Computer(models.Model):
    description = models.TextField()

    class Meta:
        db_table = 'computer'


class Component(models.Model):
    name = models.CharField(max_length=20, unique=True, db_index=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'component'


class ReportComponent(Report):
    computer = models.ForeignKey(Computer, models.CASCADE)
    component = models.ForeignKey(Component, models.PROTECT)
    verification = models.BooleanField(default=False)
    cpu_time = models.BigIntegerField(null=True)
    wall_time = models.BigIntegerField(null=True)
    memory = models.BigIntegerField(null=True)
    start_date = models.DateTimeField()
    finish_date = models.DateTimeField(null=True)
    log = models.FileField(upload_to=get_component_path, null=True)
    covnum = models.PositiveSmallIntegerField(default=0)
    verifier_input = models.FileField(upload_to=get_component_path, null=True)
    data = models.FileField(upload_to=get_component_path, null=True)

    def new_data(self, fname, fp, save=False):
        self.data.save(fname, File(fp), save)

    def add_log(self, fname, fp, save=False):
        self.log.save(fname, File(fp), save)

    def add_verifier_input(self, fname, fp, save=False):
        self.verifier_input.save(fname, File(fp), save)

    class Meta:
        db_table = 'report_component'


@receiver(pre_delete, sender=ReportComponent)
def report_component_delete_signal(**kwargs):
    report = kwargs['instance']
    if report.log:
        report.log.storage.delete(report.log.path)
    if report.verifier_input:
        report.verifier_input.storage.delete(report.verifier_input.path)
    if report.data:
        report.data.storage.delete(report.data.path)


class CoverageArchive(models.Model):
    report = models.ForeignKey(ReportComponent, models.CASCADE, related_name='coverages')
    identifier = models.CharField(max_length=128, default='')
    archive = models.FileField(upload_to=get_coverage_arch_dir)

    def save_archive(self, fname, fp):
        self.archive.save(fname, File(fp), True)

    class Meta:
        db_table = 'report_coverage_archive'


@receiver(pre_delete, sender=CoverageArchive)
def coverage_archive_delete_signal(**kwargs):
    arch = kwargs['instance']
    arch.archive.storage.delete(arch.archive.path)


class ErrorTraceSource(models.Model):
    root = models.ForeignKey(ReportRoot, models.CASCADE)
    archive = models.FileField(upload_to='Unsafes/Sources/%Y/%m')

    def add_sources(self, fname, fp, save=False):
        self.archive.save(fname, File(fp), save)

    class Meta:
        db_table = 'report_et_source'


@receiver(pre_delete, sender=ErrorTraceSource)
def source_delete_signal(**kwargs):
    source = kwargs['instance']
    source.archive.storage.delete(source.archive.path)


class ReportUnsafe(Report):
    trace_id = models.CharField(max_length=32, unique=True, db_index=True)
    error_trace = models.FileField(upload_to='Unsafes/%Y/%m')
    source = models.ForeignKey(ErrorTraceSource, models.CASCADE)
    verdict = models.CharField(max_length=1, choices=UNSAFE_VERDICTS, default='5')
    memory = models.BigIntegerField()
    cpu_time = models.BigIntegerField()
    wall_time = models.BigIntegerField()
    has_confirmed = models.BooleanField(default=False)

    def add_trace(self, fname, fp, save=False):
        self.error_trace.save(fname, File(fp), save)

    class Meta:
        db_table = 'report_unsafe'


@receiver(pre_delete, sender=ReportUnsafe)
def unsafe_delete_signal(**kwargs):
    unsafe = kwargs['instance']
    unsafe.error_trace.storage.delete(unsafe.error_trace.path)


class ReportSafe(Report):
    proof = models.FileField(upload_to='Safes/%Y/%m', null=True)
    verdict = models.CharField(max_length=1, choices=SAFE_VERDICTS, default='4')
    memory = models.BigIntegerField()
    cpu_time = models.BigIntegerField()
    wall_time = models.BigIntegerField()
    has_confirmed = models.BooleanField(default=False)

    def add_proof(self, fname, fp, save=False):
        self.proof.save(fname, File(fp), save)

    class Meta:
        db_table = 'report_safe'


@receiver(pre_delete, sender=ReportSafe)
def safe_delete_signal(**kwargs):
    safe = kwargs['instance']
    if safe.proof:
        safe.proof.storage.delete(safe.proof.path)


class ReportUnknown(Report):
    component = models.ForeignKey(Component, models.PROTECT)
    problem_description = models.FileField(upload_to='Unknowns/%Y/%m')
    memory = models.BigIntegerField(null=True)
    cpu_time = models.BigIntegerField(null=True)
    wall_time = models.BigIntegerField(null=True)

    def add_problem_desc(self, fname, fp, save=False):
        self.problem_description.save(fname, File(fp), save)

    class Meta:
        db_table = 'report_unknown'


@receiver(pre_delete, sender=ReportUnknown)
def unknown_delete_signal(**kwargs):
    unknown = kwargs['instance']
    unknown.problem_description.storage.delete(unknown.problem_description.path)


class ReportComponentLeaf(models.Model):
    report = models.ForeignKey(ReportComponent, models.CASCADE, related_name='leaves')
    safe = models.ForeignKey(ReportSafe, models.CASCADE, null=True, related_name='leaves')
    unsafe = models.ForeignKey(ReportUnsafe, models.CASCADE, null=True, related_name='leaves')
    unknown = models.ForeignKey(ReportUnknown, models.CASCADE, null=True, related_name='leaves')

    class Meta:
        db_table = 'cache_report_component_leaf'


class Verdict(models.Model):
    report = models.OneToOneField(ReportComponent, models.CASCADE)
    unsafe = models.PositiveIntegerField(default=0)
    unsafe_bug = models.PositiveIntegerField(default=0)
    unsafe_target_bug = models.PositiveIntegerField(default=0)
    unsafe_false_positive = models.PositiveIntegerField(default=0)
    unsafe_unknown = models.PositiveIntegerField(default=0)
    unsafe_unassociated = models.PositiveIntegerField(default=0)
    unsafe_inconclusive = models.PositiveIntegerField(default=0)
    safe = models.PositiveIntegerField(default=0)
    safe_missed_bug = models.PositiveIntegerField(default=0)
    safe_incorrect_proof = models.PositiveIntegerField(default=0)
    safe_unknown = models.PositiveIntegerField(default=0)
    safe_unassociated = models.PositiveIntegerField(default=0)
    safe_inconclusive = models.PositiveIntegerField(default=0)
    unknown = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "cache_report_verdict"


class ComponentResource(models.Model):
    report = models.ForeignKey(ReportComponent, models.CASCADE, related_name='resources_cache')
    component = models.ForeignKey(Component, models.PROTECT, null=True)
    cpu_time = models.BigIntegerField(default=0)
    wall_time = models.BigIntegerField(default=0)
    memory = models.BigIntegerField(default=0)

    class Meta:
        db_table = 'cache_report_component_resource'


class CompareJobsInfo(models.Model):
    user = models.ForeignKey(User, models.CASCADE)
    root1 = models.ForeignKey(ReportRoot, models.CASCADE, related_name='+')
    root2 = models.ForeignKey(ReportRoot, models.CASCADE, related_name='+')
    attr_names = models.CharField(max_length=64)

    class Meta:
        db_table = 'cache_report_jobs_compare_info'


class CompareJobsCache(models.Model):
    info = models.ForeignKey(CompareJobsInfo, models.CASCADE)
    attr_values = models.CharField(max_length=64, db_index=True)
    verdict1 = models.CharField(max_length=1, choices=COMPARE_VERDICT)
    verdict2 = models.CharField(max_length=1, choices=COMPARE_VERDICT)
    reports1 = models.TextField()
    reports2 = models.TextField()

    class Meta:
        db_table = 'cache_report_jobs_compare'
        index_together = ["info", "verdict1", "verdict2"]


class ComponentInstances(models.Model):
    report = models.ForeignKey(ReportComponent, models.CASCADE)
    component = models.ForeignKey(Component, models.CASCADE)
    in_progress = models.PositiveIntegerField(default=0)
    total = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'cache_report_component_instances'


class CoverageFile(models.Model):
    archive = models.ForeignKey(CoverageArchive, models.CASCADE)
    name = models.CharField(max_length=1024)
    file = models.FileField(upload_to=get_coverage_dir, null=True)
    covered_lines = models.PositiveIntegerField(default=0)
    covered_funcs = models.PositiveIntegerField(default=0)
    total_lines = models.PositiveIntegerField(default=0)
    total_funcs = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'cache_report_coverage_file'


@receiver(pre_delete, sender=CoverageFile)
def coverage_file_delete_signal(**kwargs):
    covfile = kwargs['instance']
    if covfile.file:
        covfile.file.storage.delete(covfile.file.path)


class CoverageDataValue(models.Model):
    hashsum = models.CharField(max_length=255)
    name = models.CharField(max_length=128)
    value = models.TextField()

    class Meta:
        db_table = 'cache_report_coverage_data_values'


class CoverageData(models.Model):
    covfile = models.ForeignKey(CoverageFile, models.CASCADE)
    line = models.PositiveIntegerField()
    data = models.ForeignKey(CoverageDataValue, models.CASCADE)

    class Meta:
        db_table = 'cache_report_coverage_data'


class CoverageDataStatistics(models.Model):
    archive = models.ForeignKey(CoverageArchive, models.CASCADE)
    name = models.CharField(max_length=128)
    data = models.FileField(upload_to='CoverageData')

    class Meta:
        db_table = 'cache_report_coverage_data_stat'


@receiver(pre_delete, sender=CoverageDataStatistics)
def coverage_data_stat_delete_signal(**kwargs):
    covdatastat = kwargs['instance']
    covdatastat.data.storage.delete(covdatastat.data.path)
