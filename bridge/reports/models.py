#
# Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
# Institute for System Programming of the Russian Academy of Sciences
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


def get_coverage_dir(instance, filename):
    return os.path.join('Reports', 'CoverageCache', 'Report-%s' % instance.report_id, filename)


class AttrName(models.Model):
    name = models.CharField(max_length=63, unique=True, db_index=True)

    class Meta:
        db_table = 'attr_name'


class Attr(models.Model):
    name = models.ForeignKey(AttrName)
    value = models.CharField(max_length=255)

    class Meta:
        db_table = 'attr'
        index_together = ["name", "value"]


class ReportRoot(models.Model):
    user = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name='+')
    job = models.OneToOneField(Job)
    tasks_total = models.PositiveIntegerField(default=0)
    average_time = models.BigIntegerField(default=0)

    class Meta:
        db_table = 'report_root'


@receiver(pre_delete, sender=ReportRoot)
def reportroot_delete_signal(**kwargs):
    t1 = time.time()
    RemoveFilesBeforeDelete(kwargs['instance'])
    logger.info('Deleting ReportRoot files took %s seconds.' % (time.time() - t1))


class Report(models.Model):
    root = models.ForeignKey(ReportRoot)
    parent = models.ForeignKey('self', null=True, related_name='+')
    identifier = models.CharField(max_length=255, unique=True)

    class Meta:
        db_table = 'report'


class ReportAttr(models.Model):
    attr = models.ForeignKey(Attr)
    report = models.ForeignKey(Report, related_name='attrs')

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
    computer = models.ForeignKey(Computer)
    component = models.ForeignKey(Component, on_delete=models.PROTECT)
    verification = models.BooleanField(default=False)
    cpu_time = models.BigIntegerField(null=True)
    wall_time = models.BigIntegerField(null=True)
    memory = models.BigIntegerField(null=True)
    start_date = models.DateTimeField()
    finish_date = models.DateTimeField(null=True)
    log = models.FileField(upload_to=get_component_path, null=True)
    coverage = models.FileField(upload_to=get_component_path, null=True)
    verifier_input = models.FileField(upload_to=get_component_path, null=True)
    data = models.FileField(upload_to=get_component_path, null=True)

    def new_data(self, fname, fp, save=False):
        self.data.save(fname, File(fp), save)

    def add_log(self, fname, fp, save=False):
        self.log.save(fname, File(fp), save)

    def add_coverage(self, fname, fp, save=False):
        self.coverage.save(fname, File(fp), save)

    def add_verifier_input(self, fname, fp, save=False):
        self.verifier_input.save(fname, File(fp), save)

    class Meta:
        db_table = 'report_component'


@receiver(pre_delete, sender=ReportComponent)
def report_component_delete_signal(**kwargs):
    report = kwargs['instance']
    if report.log:
        report.log.storage.delete(report.log.path)
    if report.coverage:
        report.coverage.storage.delete(report.coverage.path)
    if report.verifier_input:
        report.verifier_input.storage.delete(report.verifier_input.path)
    if report.data:
        report.data.storage.delete(report.data.path)


class ReportUnsafe(Report):
    error_trace = models.FileField(upload_to='Unsafes/%Y/%m')
    verdict = models.CharField(max_length=1, choices=UNSAFE_VERDICTS, default='5')
    verifier_time = models.BigIntegerField()
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
    verifier_time = models.BigIntegerField()
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
    component = models.ForeignKey(Component, on_delete=models.PROTECT)
    problem_description = models.FileField(upload_to='Unknowns/%Y/%m')

    def add_problem_desc(self, fname, fp, save=False):
        self.problem_description.save(fname, File(fp), save)

    class Meta:
        db_table = 'report_unknown'


@receiver(pre_delete, sender=ReportUnknown)
def unknown_delete_signal(**kwargs):
    unknown = kwargs['instance']
    unknown.problem_description.storage.delete(unknown.problem_description.path)


class ReportComponentLeaf(models.Model):
    report = models.ForeignKey(ReportComponent, related_name='leaves')
    safe = models.ForeignKey(ReportSafe, null=True, related_name='leaves')
    unsafe = models.ForeignKey(ReportUnsafe, null=True, related_name='leaves')
    unknown = models.ForeignKey(ReportUnknown, null=True, related_name='leaves')

    class Meta:
        db_table = 'cache_report_component_leaf'


class Verdict(models.Model):
    report = models.OneToOneField(ReportComponent)
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
    report = models.ForeignKey(ReportComponent, related_name='resources_cache')
    component = models.ForeignKey(Component, null=True, on_delete=models.PROTECT)
    cpu_time = models.BigIntegerField(default=0)
    wall_time = models.BigIntegerField(default=0)
    memory = models.BigIntegerField(default=0)

    class Meta:
        db_table = 'cache_report_component_resource'


class ComponentUnknown(models.Model):
    report = models.ForeignKey(ReportComponent, related_name='unknowns_cache')
    component = models.ForeignKey(Component, on_delete=models.PROTECT)
    number = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'cache_report_component_unknown'


class CompareJobsInfo(models.Model):
    user = models.ForeignKey(User)
    root1 = models.ForeignKey(ReportRoot, related_name='+')
    root2 = models.ForeignKey(ReportRoot, related_name='+')
    files_diff = models.TextField()

    class Meta:
        db_table = 'cache_report_jobs_compare_info'


class CompareJobsCache(models.Model):
    info = models.ForeignKey(CompareJobsInfo)
    attr_values = models.CharField(max_length=64, db_index=True)
    verdict1 = models.CharField(max_length=1, choices=COMPARE_VERDICT)
    verdict2 = models.CharField(max_length=1, choices=COMPARE_VERDICT)
    reports1 = models.CharField(max_length=1000)
    reports2 = models.CharField(max_length=1000)

    class Meta:
        db_table = 'cache_report_jobs_compare'
        index_together = ["info", "verdict1", "verdict2"]


class TasksNumbers(models.Model):
    root = models.OneToOneField(ReportRoot)
    bt_total = models.PositiveIntegerField(default=0)
    bt_num = models.PositiveIntegerField(default=0)
    avtg_total = models.PositiveIntegerField(default=0)
    avtg_fail = models.PositiveIntegerField(default=0)
    vtg_fail = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'report_tasks_numbers'


class TaskStatistic(models.Model):
    number_of_tasks = models.BigIntegerField(default=0)
    average_time = models.BigIntegerField(default=0)

    class Meta:
        db_table = 'cache_report_task_statistic'


class ComponentInstances(models.Model):
    report = models.ForeignKey(ReportComponent)
    component = models.ForeignKey(Component)
    in_progress = models.PositiveIntegerField(default=0)
    total = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'cache_report_component_instances'


class CoverageFile(models.Model):
    report = models.ForeignKey(ReportComponent)
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
    covfile = models.ForeignKey(CoverageFile)
    line = models.PositiveIntegerField()
    data = models.ForeignKey(CoverageDataValue)

    class Meta:
        db_table = 'cache_report_coverage_data'


class CoverageDataStatistics(models.Model):
    report = models.ForeignKey(ReportComponent)
    name = models.CharField(max_length=128)
    data = models.FileField(upload_to='CoverageData')

    class Meta:
        db_table = 'cache_report_coverage_data_stat'


@receiver(pre_delete, sender=CoverageDataStatistics)
def coverage_data_stat_delete_signal(**kwargs):
    covdatastat = kwargs['instance']
    covdatastat.data.storage.delete(covdatastat.data.path)
