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
import uuid

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import JSONField, ArrayField
from django.db import models
from django.db.models.signals import post_delete
from django.core.files import File
from django.utils.timezone import now
from mptt.models import MPTTModel, TreeForeignKey

from bridge.utils import CheckArchiveError, WithFilesMixin, remove_instance_files
from bridge.vars import COMPARE_VERDICT, REPORT_ARCHIVE
from users.models import User
from jobs.models import Job

MAX_COMPONENT_LEN = 20
ORIGINAL_SOURCES_DIR = 'OriginalSources'
COVERAGE_STAT_COLOR = ['#f18fa6', '#f1c0b2', '#f9e19b', '#e4f495', '#acf1a8']


def get_component_path(instance, filename):
    curr_date = now()
    return os.path.join('Reports', instance.component, str(curr_date.year), str(curr_date.month), filename)


def get_coverage_arch_dir(instance, filename):
    curr_date = now()
    return os.path.join('Reports', instance.report.component, str(curr_date.year), str(curr_date.month), filename)


def get_coverage_dir(instance, filename):
    return os.path.join('Reports', 'CoverageCache', 'CovArch-%s' % instance.archive_id, filename)


def get_attr_data_path(instance, filename):
    return os.path.join('Reports', 'AttrData', 'Root-%s' % str(instance.root_id), filename)


class ReportRoot(models.Model):
    user = models.ForeignKey(User, models.SET_NULL, null=True, related_name='roots')
    job = models.OneToOneField(Job, models.CASCADE)
    resources = JSONField(default=dict)
    instances = JSONField(default=dict)

    class Meta:
        db_table = 'report_root'


class AttrBase(models.Model):
    name = models.CharField(max_length=64, db_index=True)
    value = models.CharField(max_length=255)

    class Meta:
        abstract = True


class Report(MPTTModel):
    root = models.ForeignKey(ReportRoot, models.CASCADE)
    parent = TreeForeignKey('self', models.CASCADE, null=True, related_name='children')
    identifier = models.CharField(max_length=255, db_index=True)
    cpu_time = models.BigIntegerField(null=True)
    wall_time = models.BigIntegerField(null=True)
    memory = models.BigIntegerField(null=True)

    class Meta:
        db_table = 'report'
        unique_together = [('root', 'identifier')]
        index_together = [('root', 'identifier')]


class AttrFile(WithFilesMixin, models.Model):
    root = models.ForeignKey(ReportRoot, models.CASCADE)
    file = models.FileField(upload_to=get_attr_data_path)

    class Meta:
        db_table = 'report_attr_file'


class ReportAttr(AttrBase):
    report = models.ForeignKey(Report, models.CASCADE, related_name='attrs')
    compare = models.BooleanField(default=False)
    associate = models.BooleanField(default=False)
    data = models.ForeignKey(AttrFile, models.CASCADE, null=True)

    class Meta:
        db_table = 'report_attrs'
        indexes = [models.Index(fields=['name', 'value'])]


class Computer(models.Model):
    identifier = models.CharField(max_length=128, db_index=True)
    display = models.CharField(max_length=512)
    data = JSONField()

    class Meta:
        db_table = 'computer'


class OriginalSources(WithFilesMixin, models.Model):
    identifier = models.CharField(max_length=128, unique=True, db_index=True)
    archive = models.FileField(upload_to=ORIGINAL_SOURCES_DIR)

    def add_archive(self, fp, save=False):
        self.archive.save(REPORT_ARCHIVE['original_sources'], File(fp), save)
        if not os.path.isfile(os.path.join(settings.MEDIA_ROOT, self.archive.name)):
            raise CheckArchiveError('OriginalSources.archive was not saved')

    class Meta:
        db_table = 'report_original_sources'
        ordering = ('identifier',)


class AdditionalSources(WithFilesMixin, models.Model):
    root = models.ForeignKey(ReportRoot, models.CASCADE)
    archive = models.FileField(upload_to='Sources/%Y/%m')

    def add_archive(self, fp, save=False):
        self.archive.save(REPORT_ARCHIVE['additional_sources'], File(fp), save)
        if not os.path.isfile(os.path.join(settings.MEDIA_ROOT, self.archive.name)):
            raise CheckArchiveError('AdditionalSources.archive was not saved')

    class Meta:
        db_table = 'report_additional_sources'


class ReportComponent(WithFilesMixin, Report):
    computer = models.ForeignKey(Computer, models.CASCADE)
    component = models.CharField(max_length=MAX_COMPONENT_LEN)
    verification = models.BooleanField(default=False)

    start_date = models.DateTimeField(default=now)
    finish_date = models.DateTimeField(null=True)

    data = JSONField(null=True)
    log = models.FileField(upload_to=get_component_path, null=True)
    verifier_files = models.FileField(upload_to=get_component_path, null=True)

    # Sources for Verification reports
    original_sources = models.ForeignKey(OriginalSources, models.PROTECT, null=True)
    additional_sources = models.ForeignKey(AdditionalSources, models.CASCADE, null=True)

    def add_log(self, fp, save=False):
        self.log.save(REPORT_ARCHIVE['log'], File(fp), save)
        if not os.path.isfile(os.path.join(settings.MEDIA_ROOT, self.log.name)):
            raise CheckArchiveError('ReportComponent.log was not saved')

    def add_verifier_files(self, fp, save=False):
        self.verifier_files.save(REPORT_ARCHIVE['verifier_files'], File(fp), save)
        if not os.path.isfile(os.path.join(settings.MEDIA_ROOT, self.verifier_files.name)):
            raise CheckArchiveError('ReportComponent.verifier_files was not saved')

    class Meta:
        db_table = 'report_component'


class ReportComponentLeaf(models.Model):
    report = models.ForeignKey(ReportComponent, models.CASCADE, related_name='leaves')
    content_type = models.ForeignKey(ContentType, models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    class Meta:
        db_table = 'cache_report_component_leaf'


class CoverageArchive(WithFilesMixin, models.Model):
    report = models.ForeignKey(ReportComponent, models.CASCADE, related_name='coverages')
    name = models.CharField(max_length=128, default='-')
    identifier = models.CharField(max_length=128, default='')
    archive = models.FileField(upload_to=get_coverage_arch_dir)
    total = JSONField(null=True)
    has_extra = models.BooleanField(default=False)

    def add_coverage(self, fp, save=False):
        self.archive.save(REPORT_ARCHIVE['coverage'], File(fp), save=save)

    class Meta:
        db_table = 'report_coverage_archive'


class CoverageStatistics(models.Model):
    coverage = models.ForeignKey(CoverageArchive, models.CASCADE)
    identifier = models.PositiveIntegerField()
    parent = models.PositiveIntegerField(null=True)
    is_leaf = models.BooleanField()
    name = models.CharField(max_length=128)
    path = models.TextField(null=True)
    depth = models.PositiveIntegerField(default=0)

    lines_covered = models.PositiveIntegerField(default=0)
    lines_total = models.PositiveIntegerField(default=0)
    funcs_covered = models.PositiveIntegerField(default=0)
    funcs_total = models.PositiveIntegerField(default=0)

    lines_covered_extra = models.PositiveIntegerField(default=0)
    lines_total_extra = models.PositiveIntegerField(default=0)
    funcs_covered_extra = models.PositiveIntegerField(default=0)
    funcs_total_extra = models.PositiveIntegerField(default=0)

    def calculate_color(self, div):
        color_id = int(div * len(COVERAGE_STAT_COLOR))
        if color_id >= len(COVERAGE_STAT_COLOR):
            color_id = len(COVERAGE_STAT_COLOR) - 1
        elif color_id < 0:
            color_id = 0
        return COVERAGE_STAT_COLOR[color_id]

    @property
    def lines_percentage(self):
        if not self.lines_total:
            return '-'
        return '{}%'.format(round(100 * self.lines_covered / self.lines_total))

    @property
    def funcs_percentage(self):
        if not self.funcs_total:
            return '-'
        return '{}%'.format(round(100 * self.funcs_covered / self.funcs_total))

    @property
    def lines_color(self):
        if not self.lines_total:
            return None
        return self.calculate_color(self.lines_covered / self.lines_total)

    @property
    def funcs_color(self):
        if not self.funcs_total:
            return None
        return self.calculate_color(self.funcs_covered / self.funcs_total)

    @property
    def lines_percentage_extra(self):
        if not self.lines_total_extra:
            return '-'
        return '{}%'.format(round(100 * self.lines_covered_extra / self.lines_total_extra))

    @property
    def funcs_percentage_extra(self):
        if not self.funcs_total_extra:
            return '-'
        return '{}%'.format(round(100 * self.funcs_covered_extra / self.funcs_total_extra))

    @property
    def lines_color_extra(self):
        if not self.lines_total_extra:
            return None
        return self.calculate_color(self.lines_covered_extra / self.lines_total_extra)

    @property
    def funcs_color_extra(self):
        if not self.funcs_total_extra:
            return None
        return self.calculate_color(self.funcs_covered_extra / self.funcs_total_extra)

    @property
    def indentation(self):
        return '    ' * (self.depth - 1)

    @property
    def shown(self):
        if not hasattr(self, '_shown'):
            setattr(self, '_shown', False)
        return getattr(self, '_shown')

    @shown.setter
    def shown(self, value):
        setattr(self, '_shown', bool(value))

    class Meta:
        db_table = 'report_coverage_statistics'


class CoverageDataStatistics(models.Model):
    coverage = models.ForeignKey(CoverageArchive, models.CASCADE)
    name = models.CharField(max_length=255)
    data = JSONField()

    class Meta:
        db_table = 'report_coverage_data_statistics'


class ReportUnsafe(WithFilesMixin, Report):
    trace_id = models.UUIDField(unique=True, db_index=True, default=uuid.uuid4)
    error_trace = models.FileField(upload_to='Unsafes/%Y/%m')
    leaves = GenericRelation(ReportComponentLeaf, related_query_name='unsafes')

    def add_trace(self, fp, save=False):
        self.error_trace.save(REPORT_ARCHIVE['error_trace'], File(fp), save)
        if not os.path.isfile(os.path.join(settings.MEDIA_ROOT, self.error_trace.name)):
            raise CheckArchiveError('ReportUnsafe.error_trace was not saved')

    class Meta:
        db_table = 'report_unsafe'


class ReportSafe(Report):
    leaves = GenericRelation(ReportComponentLeaf, related_query_name='safes')

    class Meta:
        db_table = 'report_safe'


class ReportUnknown(WithFilesMixin, Report):
    component = models.CharField(max_length=MAX_COMPONENT_LEN)
    problem_description = models.FileField(upload_to='Unknowns/%Y/%m')
    leaves = GenericRelation(ReportComponentLeaf, related_query_name='unknowns')

    def add_problem_desc(self, fp, save=False):
        self.problem_description.save(REPORT_ARCHIVE['problem_description'], File(fp), save)
        if not os.path.isfile(os.path.join(settings.MEDIA_ROOT, self.problem_description.name)):
            raise CheckArchiveError('ReportUnknown.problem_description was not saved')

    class Meta:
        db_table = 'report_unknown'


class CompareJobsInfo(models.Model):
    user = models.ForeignKey(User, models.CASCADE)
    root1 = models.ForeignKey(ReportRoot, models.CASCADE, related_name='+')
    root2 = models.ForeignKey(ReportRoot, models.CASCADE, related_name='+')
    names = ArrayField(models.CharField(max_length=64))

    class Meta:
        db_table = 'cache_report_jobs_compare_info'


class ComparisonObject(models.Model):
    info = models.ForeignKey(CompareJobsInfo, models.CASCADE)
    values = ArrayField(models.CharField(max_length=255))
    verdict1 = models.CharField(max_length=1, choices=COMPARE_VERDICT)
    verdict2 = models.CharField(max_length=1, choices=COMPARE_VERDICT)

    class Meta:
        db_table = 'cache_report_comparison_object'
        index_together = ["info", "verdict1", "verdict2"]


class ComparisonLink(models.Model):
    comparison = models.ForeignKey(ComparisonObject, models.CASCADE, related_name='links')
    content_type = models.ForeignKey(ContentType, models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    class Meta:
        db_table = 'cache_report_comparison_link'


post_delete.connect(remove_instance_files, sender=AttrFile)
post_delete.connect(remove_instance_files, sender=OriginalSources)
post_delete.connect(remove_instance_files, sender=AdditionalSources)
post_delete.connect(remove_instance_files, sender=ReportComponent)
post_delete.connect(remove_instance_files, sender=ReportUnsafe)
post_delete.connect(remove_instance_files, sender=ReportUnknown)
post_delete.connect(remove_instance_files, sender=CoverageArchive)
