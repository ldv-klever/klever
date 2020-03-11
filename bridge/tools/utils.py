#
# Copyright (c) 2019 ISP RAS (http://www.ispras.ru)
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

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import F, FileField
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _

from bridge.vars import JOB_WEIGHT
from bridge.utils import BridgeException, logger

from jobs.models import JOBFILE_DIR, JobFile
from service.models import SERVICE_DIR, Solution, Task
from marks.models import (
    CONVERTED_DIR, ConvertedTrace, MarkSafe, MarkSafeReport, MarkSafeAttr, MarkSafeTag,
    MarkUnsafe, MarkUnsafeReport, MarkUnsafeAttr, MarkUnsafeTag,
    MarkUnknown, MarkUnknownReport, MarkUnknownAttr
)
from reports.models import (
    ReportRoot, ReportComponent, ReportSafe, ReportUnsafe, ReportUnknown, ReportComponentLeaf,
    CoverageArchive, OriginalSources, RootCache, ORIGINAL_SOURCES_DIR
)
from marks.tasks import connect_safe_report, connect_unsafe_report, connect_unknown_report

from caches.utils import RecalculateSafeCache, RecalculateUnsafeCache, RecalculateUnknownCache
from reports.coverage import FillCoverageStatistics


def objects_without_relations(table):
    filters = {}
    for rel in [f for f in getattr(table, '_meta').get_fields()
                if (f.one_to_one or f.one_to_many) and f.auto_created and not f.concrete]:
        accessor_name = rel.get_accessor_name()
        if not rel.related_name and accessor_name.endswith('_set'):
            accessor_name = accessor_name[:-4]
        filters[accessor_name] = None
    return table.objects.filter(**filters)


def recalculate_safe_links(roots):
    MarkSafeReport.objects.filter(report__root__in=roots).delete()
    # It could be long
    for report_id in ReportSafe.objects.filter(root__in=roots).values_list('id', flat=True):
        connect_safe_report.delay(report_id)


def recalculate_unsafe_links(roots):
    MarkUnsafeReport.objects.filter(report__root__in=roots).delete()
    for report_id in ReportUnsafe.objects.filter(root__in=roots).values_list('id', flat=True):
        connect_unsafe_report.delay(report_id)


def recalculate_unknown_links(roots):
    MarkUnknownReport.objects.filter(report__root__in=roots).delete()
    for report_id in ReportUnknown.objects.filter(root__in=roots).values_list('id', flat=True):
        connect_unknown_report.delay(report_id)


class ClearFiles:
    def __init__(self):
        self.__clear_files_with_ref(JobFile, JOBFILE_DIR)
        self.__clear_files_with_ref(OriginalSources, ORIGINAL_SOURCES_DIR)
        self.__clear_files_with_ref(ConvertedTrace, CONVERTED_DIR)
        self.__clear_service_files()

    def __clear_files_with_ref(self, model, files_dir):
        objects_without_relations(model).delete()

        files_in_the_system = set()
        to_delete = set()
        for instance in model.objects.all():
            # file_path = os.path.abspath(os.path.join(settings.MEDIA_ROOT, f.file.name))
            for file_path in self.__files_paths(instance):
                files_in_the_system.add(file_path)
                if not (os.path.exists(file_path) and os.path.isfile(file_path)):
                    logger.error('Deleted from DB (file not exists): {}'.format(
                        os.path.relpath(file_path, settings.MEDIA_ROOT)
                    ), stack_info=True)
                    to_delete.add(instance.pk)
        model.objects.filter(id__in=to_delete).delete()

        self.__clear_unused_files(files_dir, files_in_the_system)

    def __files_paths(self, instance):
        paths_list = []
        for field in getattr(instance, '_meta').fields:
            if isinstance(field, FileField):
                paths_list.append(getattr(instance, field.name).path)
        return paths_list

    def __clear_service_files(self):
        files_in_the_system = set()
        for s in Solution.objects.values_list('archive', flat=True):
            files_in_the_system.add(os.path.abspath(os.path.join(settings.MEDIA_ROOT, s)))
        for s in Task.objects.values_list('archive', flat=True):
            files_in_the_system.add(os.path.abspath(os.path.join(settings.MEDIA_ROOT, s)))
        self.__clear_unused_files(SERVICE_DIR, files_in_the_system)

    def __clear_unused_files(self, files_dir, excluded: set):
        files_directory = os.path.join(settings.MEDIA_ROOT, files_dir)
        if os.path.exists(files_directory):
            files_on_disk = set(os.path.abspath(os.path.join(files_directory, x)) for x in os.listdir(files_directory))
            for f in files_on_disk - excluded:
                os.remove(f)


class RecalculateLeaves:
    def __init__(self, roots):
        self._roots = roots
        self._leaves = LeavesData()
        self.__recalc()

    def __recalc(self):
        ReportComponentLeaf.objects.filter(report__root__in=self._roots).delete()
        for report in ReportComponent.objects.filter(root__in=self._roots).order_by('id').only('id', 'parent_id'):
            self._leaves.add_component(report)
        for report in ReportUnsafe.objects.filter(root__in=self._roots).only('id', 'parent_id'):
            self._leaves.add_leaf(report)
        for report in ReportSafe.objects.filter(root__in=self._roots).only('id', 'parent_id'):
            self._leaves.add_leaf(report)
        for report in ReportUnknown.objects.filter(root__in=self._roots).only('id', 'parent_id'):
            self._leaves.add_leaf(report)
        self._leaves.upload()


class RecalculateRootCache:
    def __init__(self, roots):
        self._roots = list(root for root in roots if root.job.weight == JOB_WEIGHT[0][0])
        self.__recalc()

    def __recalc(self):
        cache_data = {}
        for report in ReportComponent.objects.filter(root__in=self._roots):
            if (report.root_id, report.component) not in cache_data:
                cache_data[(report.root_id, report.component)] = {
                    'total': 0, 'finished': 0, 'cpu_time': 0, 'wall_time': 0, 'memory': 0
                }
            cache_data[(report.root_id, report.component)]['total'] += 1
            if report.finish_date:
                cache_data[(report.root_id, report.component)]['finished'] += 1
            if report.cpu_time:
                cache_data[(report.root_id, report.component)]['cpu_time'] += report.cpu_time
            if report.wall_time:
                cache_data[(report.root_id, report.component)]['wall_time'] += report.wall_time
            if report.memory:
                cache_data[(report.root_id, report.component)]['memory'] += max(
                    cache_data[(report.root_id, report.component)]['memory'], report.memory
                )
        RootCache.objects.filter(root_id__in=self._roots).delete()
        RootCache.objects.bulk_create(list(
            RootCache(root_id=r_id, component=component, **obj_kwargs)
            for (r_id, component), obj_kwargs in cache_data.items()
        ))


class Recalculation:
    def __init__(self, rec_type, jobs):
        self.type = rec_type
        self._roots = self.__get_roots(jobs)
        self.__recalc()

    def __get_roots(self, job_ids):
        roots = ReportRoot.objects.filter(job_id__in=job_ids).select_related('job')
        if len(roots) < len(job_ids):
            raise BridgeException(_('One of the selected jobs was not found'))
        if len(roots) == 0:
            raise BridgeException(_('Please select jobs to recalculate caches for them'))
        return roots

    @cached_property
    def _root_ids(self):
        return set(r.id for r in self._roots)

    def __recalc(self):
        if self.type == 'leaves':
            RecalculateLeaves(self._roots)
        elif self.type == 'safe_links':
            recalculate_safe_links(self._roots)
        elif self.type == 'unsafe_links':
            recalculate_unsafe_links(self._roots)
        elif self.type == 'unknown_links':
            recalculate_unknown_links(self._roots)
        elif self.type == 'safe_reports':
            reports_ids = list(ReportSafe.objects.filter(root_id__in=self._root_ids).values_list('id', flat=True))
            RecalculateSafeCache(reports_ids)
        elif self.type == 'unsafe_reports':
            reports_ids = list(ReportUnsafe.objects.filter(root_id__in=self._root_ids).values_list('id', flat=True))
            RecalculateUnsafeCache(reports_ids)
        elif self.type == 'unknown_reports':
            reports_ids = list(ReportUnknown.objects.filter(root_id__in=self._root_ids).values_list('id', flat=True))
            RecalculateUnknownCache(reports_ids)
        elif self.type == 'root_cache':
            RecalculateRootCache(self._roots)
        elif self.type == 'coverage':
            RecalculateCoverage(self._roots)
        elif self.type == 'all':
            RecalculateLeaves(self._roots)
            recalculate_safe_links(self._roots)
            recalculate_unsafe_links(self._roots)
            recalculate_unknown_links(self._roots)
            RecalculateRootCache(self._roots)
            RecalculateCoverage(self._roots)
        else:
            logger.error('Wrong type of recalculation')
            raise BridgeException()


class RecalculateMarksCache:
    def __init__(self, marks_type):
        if marks_type == 'safe':
            self.__recalculate_safes()
        elif marks_type == 'unsafe':
            self.__recalculate_unsafes()
        elif marks_type == 'unknown':
            self.__recalculate_unknowns()

    def __recalculate_safes(self):
        cache_data = {}

        # Collect attrs cache
        attrs_qs = MarkSafeAttr.objects\
            .filter(is_compare=True, mark_version__mark__version=F('mark_version__version'))\
            .select_related('mark_version').only('name', 'value', 'mark_version__mark_id')
        for ma in attrs_qs:
            cache_data.setdefault(ma.mark_version.mark_id, {'cache_attrs': {}})
            cache_data[ma.mark_version.mark_id]['cache_attrs'][ma.name] = ma.value

        # Collect tags cache
        tags_qs = MarkSafeTag.objects \
            .filter(mark_version__mark__version=F('mark_version__version')) \
            .select_related('mark_version', 'tag').order_by('tag__name')\
            .only('tag__name', 'mark_version__mark_id')
        for mt in tags_qs:
            cache_data.setdefault(mt.mark_version.mark_id, {'cache_tags': []})
            cache_data[mt.mark_version.mark_id].setdefault('cache_tags', [])
            cache_data[mt.mark_version.mark_id]['cache_tags'].append(mt.tag.name)

        with transaction.atomic():
            for mark in MarkSafe.objects.all():
                if mark.id not in cache_data:
                    continue
                for field_name, field_value in cache_data[mark.id].items():
                    setattr(mark, field_name, field_value)
                mark.save()

    def __recalculate_unsafes(self):
        cache_data = {}

        # Collect attrs cache
        attrs_qs = MarkUnsafeAttr.objects \
            .filter(is_compare=True, mark_version__mark__version=F('mark_version__version')) \
            .select_related('mark_version').only('name', 'value', 'mark_version__mark_id')
        for ma in attrs_qs:
            cache_data.setdefault(ma.mark_version.mark_id, {'cache_attrs': {}})
            cache_data[ma.mark_version.mark_id]['cache_attrs'][ma.name] = ma.value

        # Collect tags cache
        tags_qs = MarkUnsafeTag.objects \
            .filter(mark_version__mark__version=F('mark_version__version')) \
            .select_related('mark_version', 'tag').order_by('tag__name') \
            .only('tag__name', 'mark_version__mark_id')
        for mt in tags_qs:
            cache_data.setdefault(mt.mark_version.mark_id, {'cache_tags': []})
            cache_data[mt.mark_version.mark_id].setdefault('cache_tags', [])
            cache_data[mt.mark_version.mark_id]['cache_tags'].append(mt.tag.name)

        with transaction.atomic():
            for mark in MarkUnsafe.objects.all():
                if mark.id not in cache_data:
                    continue
                for field_name, field_value in cache_data[mark.id].items():
                    setattr(mark, field_name, field_value)
                mark.save()

    def __recalculate_unknowns(self):
        cache_data = {}

        # Collect attrs cache
        attrs_qs = MarkUnknownAttr.objects \
            .filter(is_compare=True, mark_version__mark__version=F('mark_version__version')) \
            .select_related('mark_version').only('name', 'value', 'mark_version__mark_id')
        for ma in attrs_qs:
            cache_data.setdefault(ma.mark_version.mark_id, {'cache_attrs': {}})
            cache_data[ma.mark_version.mark_id]['cache_attrs'][ma.name] = ma.value

        with transaction.atomic():
            for mark in MarkUnknown.objects.all():
                if mark.id not in cache_data:
                    continue
                for field_name, field_value in cache_data[mark.id].items():
                    setattr(mark, field_name, field_value)
                mark.save()


class LeavesData:
    def __init__(self):
        self._ctypes = {}
        self._tree = {}
        self._leaves_cache = []

    def __content_type(self, report):
        model_name = report.__class__.__name__
        if model_name not in self._ctypes:
            self._ctypes[model_name] = ContentType.objects.get_for_model(report.__class__)
        return self._ctypes[model_name]

    def add_component(self, report):
        self._tree[report.id] = report.parent_id

    def add_leaf(self, report):
        parent_id = report.parent_id
        while parent_id is not None:
            self._leaves_cache.append(ReportComponentLeaf(
                report_id=parent_id, object_id=report.id,
                content_type=self.__content_type(report)
            ))
            parent_id = self._tree[parent_id]

    def upload(self):
        ReportComponentLeaf.objects.bulk_create(self._leaves_cache)
        self.__init__()


class RecalculateCoverage:
    def __init__(self, roots):
        self._roots = roots
        self.__recalc()

    def __recalc(self):
        for root in self._roots:
            for cov_obj in CoverageArchive.objects.filter(report__root=root):
                res = FillCoverageStatistics(cov_obj)
                cov_obj.total = res.total_coverage
                cov_obj.has_extra = res.has_extra
                cov_obj.save()
