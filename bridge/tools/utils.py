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
import json

from django.conf import settings
from django.db import transaction
from django.utils.translation import ugettext_lazy as _

from bridge.vars import JOB_WEIGHT
from bridge.utils import BridgeException, logger

import marks.SafeUtils as SafeUtils
import marks.UnsafeUtils as UnsafeUtils
import marks.UnknownUtils as UnknownUtils

from jobs.models import JOBFILE_DIR, JobFile
from service.models import SERVICE_DIR, Solution, Task
from marks.models import CONVERTED_DIR
from reports.models import ReportRoot, ReportComponent, ReportSafe, ReportUnsafe, ReportUnknown, ReportComponentLeaf,\
    CoverageFile, CoverageDataStatistics

from reports.coverage import FillCoverageCache


def objects_without_relations(table):
    filters = {}
    for rel in [f for f in getattr(table, '_meta').get_fields()
                if (f.one_to_one or f.one_to_many) and f.auto_created and not f.concrete]:
        accessor_name = rel.get_accessor_name()
        if not rel.related_name and accessor_name.endswith('_set'):
            accessor_name = accessor_name[:-4]
        filters[accessor_name] = None
    return table.objects.filter(**filters)


class ClearFiles:
    def __init__(self):
        self.__clear_files_with_ref(JobFile, JOBFILE_DIR)
        self.__clear_files_with_ref(ConvertedTraces, CONVERTED_DIR)
        self.__clear_service_files()

    def __clear_files_with_ref(self, table, files_dir):
        self.__is_not_used()
        objects_without_relations(table).delete()

        files_in_the_system = set()
        files_to_delete = set()
        for f in table.objects.all():
            file_path = os.path.abspath(os.path.join(settings.MEDIA_ROOT, f.file.name))
            files_in_the_system.add(file_path)
            if not (os.path.exists(file_path) and os.path.isfile(file_path)):
                logger.error('Deleted from DB (file not exists): %s' % f.file.name, stack_info=True)
                files_to_delete.add(f.pk)
        table.objects.filter(id__in=files_to_delete).delete()
        files_directory = os.path.join(settings.MEDIA_ROOT, files_dir)
        if os.path.exists(files_directory):
            files_on_disk = set(os.path.abspath(os.path.join(files_directory, x)) for x in os.listdir(files_directory))
            for f in files_on_disk - files_in_the_system:
                os.remove(f)

    def __clear_service_files(self):
        self.__is_not_used()
        files_in_the_system = set()
        for s in Solution.objects.values_list('archive'):
            files_in_the_system.add(os.path.abspath(os.path.join(settings.MEDIA_ROOT, s[0])))
        for s in Task.objects.values_list('archive'):
            files_in_the_system.add(os.path.abspath(os.path.join(settings.MEDIA_ROOT, s[0])))
        files_directory = os.path.join(settings.MEDIA_ROOT, SERVICE_DIR)
        if os.path.exists(files_directory):
            files_on_disk = set(os.path.abspath(os.path.join(files_directory, x)) for x in os.listdir(files_directory))
            for f in files_on_disk - files_in_the_system:
                os.remove(f)

    def __is_not_used(self):
        pass


class RecalculateLeaves:
    def __init__(self, roots):
        self._roots = roots
        self._leaves = LeavesData()
        self.__recalc()

    def __recalc(self):
        ReportComponentLeaf.objects.filter(report__root__in=self._roots).delete()
        for rc in ReportComponent.objects.filter(root__in=self._roots).order_by('id').only('id', 'parent_id'):
            self._leaves.add(rc)
        for u in ReportUnsafe.objects.filter(root__in=self._roots).only('id', 'parent_id'):
            self._leaves.add(u)
        for s in ReportSafe.objects.filter(root__in=self._roots).only('id', 'parent_id'):
            self._leaves.add(s)
        for f in ReportUnknown.objects.filter(root__in=self._roots).only('id', 'parent_id'):
            self._leaves.add(f)
        self._leaves.upload()


class RecalculateComponentInstances:
    def __init__(self, roots):
        self._roots = list(root for root in roots if root.job.weight == JOB_WEIGHT[0][0])
        self.__recalc()

    def __recalc(self):
        inst_cache = {}
        for report in ReportComponent.objects.filter(root__in=self._roots)\
                .order_by('id').only('component', 'finish_date'):
            if report.root_id not in inst_cache:
                inst_cache[report.root_id] = {}
            if report.component not in inst_cache[report.root_id]:
                inst_cache[report.root_id][report.component] = {'finished': 0, 'total': 0}

            inst_cache[report.root_id][report.component]['total'] += 1
            if report.finish_date:
                inst_cache[report.root_id][report.component]['finished'] += 1

        with transaction.atomic():
            for root in self._roots:
                root.instances = inst_cache.get(root.id, {})
                root.save()


class RecalculateCoverageCache:
    def __init__(self, roots):
        self.roots = roots
        self.__recalc()

    def __recalc(self):
        CoverageFile.objects.filter(archive__report__root__in=self.roots).delete()
        CoverageDataStatistics.objects.filter(archive__report__root__in=self.roots).delete()
        # TODO: ensure that each report is unique in queryset
        for report in ReportComponent.objects.filter(root__in=self.roots).exclude(coverages=None):
            FillCoverageCache(report)


class Recalculation:
    def __init__(self, rec_type, jobs=None):
        self.type = rec_type
        self._roots = self.__get_roots(jobs)
        self.__recalc()

    def __get_roots(self, job_ids):
        self.__is_not_used()
        if job_ids is None:
            return ReportRoot.objects.all().select_related('job')
        job_ids = json.loads(job_ids)
        roots = ReportRoot.objects.filter(job_id__in=job_ids).select_related('job')
        if roots.count() < len(job_ids):
            raise BridgeException(_('One of the selected jobs was not found'))
        if roots.count() == 0:
            raise BridgeException(_('Please select jobs to recalculate caches for them'))
        return roots

    def __recalc(self):
        if self.type == 'leaves':
            RecalculateLeaves(self._roots)
        elif self.type == 'unsafe':
            UnsafeUtils.RecalculateConnections(self._roots)
        elif self.type == 'safe':
            SafeUtils.RecalculateConnections(self._roots)
        elif self.type == 'unknown':
            UnknownUtils.RecalculateConnections(self._roots)
        elif self.type == 'resources':
            RecalculateResources(self._roots)
        elif self.type == 'compinst':
            RecalculateComponentInstances(self._roots)
        elif self.type == 'coverage':
            RecalculateCoverageCache(self._roots)
        elif self.type == 'all':
            RecalculateLeaves(self._roots)
            UnsafeUtils.RecalculateConnections(self._roots)
            SafeUtils.RecalculateConnections(self._roots)
            UnknownUtils.RecalculateConnections(self._roots)
            RecalculateResources(self._roots)
            RecalculateComponentInstances(self._roots)
            RecalculateCoverageCache(self._roots)
        elif self.type == 'for_uploaded':
            RecalculateLeaves(self._roots)
            UnsafeUtils.RecalculateConnections(self._roots)
            SafeUtils.RecalculateConnections(self._roots)
            UnknownUtils.RecalculateConnections(self._roots)
            RecalculateComponentInstances(self._roots)
            RecalculateCoverageCache(self._roots)
        else:
            logger.error('Wrong type of recalculation')
            raise BridgeException()

    def __is_not_used(self):
        pass


class RecalculateResources:
    def __init__(self, roots):
        self._roots = list(root for root in roots if root.job.weight == JOB_WEIGHT[0][0])
        self.__recalc()

    def __recalc(self):
        data = {}
        for report in ReportComponent.objects.filter(root__in=self._roots):
            data.setdefault(report.root_id, {'cpu_time': 0, 'wall_time': 0, 'memory': 0})
            data[report.root_id]['cpu_time'] += report.cpu_time
            data[report.root_id]['wall_time'] += report.wall_time
            data[report.root_id]['memory'] = max(report.cpu_time, data[report.root_id]['memory'])

        with transaction.atomic():
            for root in self._roots:
                root.resources = data.get(root.id, {})
                root.save()


class LeavesData(object):
    def __init__(self):
        self._data = {}

    def add(self, report):
        if isinstance(report, ReportComponent):
            self._data[report.id] = {
                'parent': report.parent_id,
                'unsafes': [],
                'safes': [],
                'unknowns': []
            }
        else:
            parent_id = report.parent_id
            while parent_id is not None:
                if parent_id in self._data:
                    if isinstance(report, ReportSafe):
                        self._data[parent_id]['safes'].append(report.id)
                    elif isinstance(report, ReportUnsafe):
                        self._data[parent_id]['unsafes'].append(report.id)
                    elif isinstance(report, ReportUnknown):
                        self._data[parent_id]['unknowns'].append(report.id)
                parent_id = self._data[parent_id]['parent']

    def upload(self):
        new_leaves = []
        for rep_id in self._data:
            for unsafe in self._data[rep_id]['unsafes']:
                new_leaves.append(ReportComponentLeaf(report_id=rep_id, unsafe_id=unsafe))
            for safe in self._data[rep_id]['safes']:
                new_leaves.append(ReportComponentLeaf(report_id=rep_id, safe_id=safe))
            for unknown in self._data[rep_id]['unknowns']:
                new_leaves.append(ReportComponentLeaf(report_id=rep_id, unknown_id=unknown))
        ReportComponentLeaf.objects.bulk_create(new_leaves)
        self.__init__()
