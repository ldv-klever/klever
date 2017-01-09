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

import json
from django.db.models import ProtectedError
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import ugettext_lazy as _
from bridge.settings import MEDIA_ROOT
from bridge.vars import ATTR_STATISTIC
from jobs.models import JOBFILE_DIR, JobFile
from service.models import FILE_DIR, Solution, Task
from reports.models import *
from marks.models import *
from marks.utils import ConnectReportWithMarks, update_unknowns_cache


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
            file_path = os.path.abspath(os.path.join(MEDIA_ROOT, f.file.name))
            files_in_the_system.add(file_path)
            if not (os.path.exists(file_path) and os.path.isfile(file_path)):
                logger.error('Deleted from DB (file not exists): %s' % f.file.name, stack_info=True)
                files_to_delete.add(f.pk)
        table.objects.filter(id__in=files_to_delete).delete()
        files_directory = os.path.join(MEDIA_ROOT, files_dir)
        if os.path.exists(files_directory):
            files_on_disk = set(os.path.abspath(os.path.join(files_directory, x)) for x in os.listdir(files_directory))
            for f in files_on_disk - files_in_the_system:
                os.remove(f)

    def __clear_service_files(self):
        self.__is_not_used()
        files_in_the_system = set()
        for s in Solution.objects.values_list('archive'):
            files_in_the_system.add(os.path.abspath(os.path.join(MEDIA_ROOT, s[0])))
        for s in Task.objects.values_list('archive'):
            files_in_the_system.add(os.path.abspath(os.path.join(MEDIA_ROOT, s[0])))
        files_directory = os.path.join(MEDIA_ROOT, FILE_DIR)
        if os.path.exists(files_directory):
            files_on_disk = set(os.path.abspath(os.path.join(files_directory, x)) for x in os.listdir(files_directory))
            for f in files_on_disk - files_in_the_system:
                os.remove(f)

    def __is_not_used(self):
        pass


class RecalculateLeaves(object):
    def __init__(self, jobs):
        self._jobs = jobs
        self._leaves = LeavesData()
        self.__recalc()

    def __recalc(self):
        ReportComponentLeaf.objects.filter(report__root__job__in=self._jobs).delete()
        for rc in ReportComponent.objects.filter(root__job__in=self._jobs).order_by('id').only('id', 'parent_id'):
            self._leaves.add(rc)
        for u in ReportUnsafe.objects.filter(root__job__in=self._jobs).only('id', 'parent_id'):
            self._leaves.add(u)
        for s in ReportSafe.objects.filter(root__job__in=self._jobs).only('id', 'parent_id'):
            self._leaves.add(s)
        for f in ReportUnknown.objects.filter(root__job__in=self._jobs).only('id', 'parent_id'):
            self._leaves.add(f)
        self._leaves.upload()


class RecalculateVerdicts(object):
    def __init__(self, jobs):
        self.jobs = jobs
        self.__recalc()

    def __recalc(self):
        Verdict.objects.filter(report__root__job__in=self.jobs).delete()
        ComponentUnknown.objects.filter(report__root__job__in=self.jobs).delete()
        data = VerdictsData()
        for leaf in ReportComponentLeaf.objects.filter(report__root__job__in=self.jobs)\
                .select_related('safe', 'unsafe', 'unknown'):
            data.add(leaf)
        data.upload()


class RecalculateUnsafeMarkConnections(object):
    def __init__(self, jobs):
        self.jobs = jobs
        self.__recalc()

    def __recalc(self):
        ReportUnsafeTag.objects.filter(report__root__job__in=self.jobs).delete()
        UnsafeReportTag.objects.filter(report__root__job__in=self.jobs).delete()
        MarkUnsafeReport.objects.filter(report__root__job__in=self.jobs).delete()
        for unsafe in ReportUnsafe.objects.filter(root__job__in=self.jobs):
            ConnectReportWithMarks(unsafe)


class RecalculateSafeMarkConnections(object):
    def __init__(self, jobs):
        self.jobs = jobs
        self.__recalc()

    def __recalc(self):
        ReportSafeTag.objects.filter(report__root__job__in=self.jobs).delete()
        SafeReportTag.objects.filter(report__root__job__in=self.jobs).delete()
        MarkSafeReport.objects.filter(report__root__job__in=self.jobs).delete()
        for safe in ReportSafe.objects.filter(root__job__in=self.jobs):
            ConnectReportWithMarks(safe)


class RecalculateUnknownMarkConnections(object):
    def __init__(self, jobs):
        self.jobs = jobs
        self.__recalc()
        for problem in UnknownProblem.objects.all():
            try:
                problem.delete()
            except ProtectedError:
                pass

    def __recalc(self):
        MarkUnknownReport.objects.filter(report__root__job__in=self.jobs).delete()
        ComponentMarkUnknownProblem.objects.filter(report__root__job__in=self.jobs).delete()
        for unknown in ReportUnknown.objects.filter(root__job__in=self.jobs):
            ConnectReportWithMarks(unknown, False)
        update_unknowns_cache(ReportUnknown.objects.filter(root__job__in=self.jobs))


class RecalculateAttrStatistic(object):
    def __init__(self, jobs):
        self.jobs = jobs
        self.__recalc()

    def __recalc(self):
        AttrStatistic.objects.filter(report__root__job__in=self.jobs).delete()
        attrs_data = []
        for j_type in ATTR_STATISTIC:
            attr_names = set(a['id'] for a in AttrName.objects.filter(name__in=ATTR_STATISTIC[j_type]).values('id'))
            reports = set()
            for report in ReportComponent.objects.filter(root__job__in=[j.id for j in self.jobs if j.type == j_type]):
                reports.add(report.id)

            safes = {}
            unsafes = {}
            unknowns = {}
            for leaf in ReportComponentLeaf.objects.filter(report_id__in=reports):
                if leaf.safe_id is not None:
                    if leaf.safe_id not in safes:
                        safes[leaf.safe_id] = set()
                    safes[leaf.safe_id].add(leaf.report_id)
                elif leaf.unsafe_id is not None:
                    if leaf.unsafe_id not in unsafes:
                        unsafes[leaf.unsafe_id] = set()
                    unsafes[leaf.unsafe_id].add(leaf.report_id)
                elif leaf.unknown_id is not None:
                    if leaf.unknown_id not in unknowns:
                        unknowns[leaf.unknown_id] = set()
                    unknowns[leaf.unknown_id].add(leaf.report_id)

            report_attrs = {}
            for ra in ReportAttr.objects.filter(report_id__in=safes, attr__name__name__in=ATTR_STATISTIC[j_type]) \
                    .values_list('report_id', 'attr__name_id', 'attr_id'):
                report_attrs[('s', ra[0], ra[1])] = ra[2]
            for ra in ReportAttr.objects.filter(report_id__in=unsafes, attr__name__name__in=ATTR_STATISTIC[j_type]) \
                    .values_list('report_id', 'attr__name_id', 'attr_id'):
                report_attrs[('u', ra[0], ra[1])] = ra[2]
            for ra in ReportAttr.objects.filter(report_id__in=unknowns, attr__name__name__in=ATTR_STATISTIC[j_type]) \
                    .values_list('report_id', 'attr__name_id', 'attr_id'):
                report_attrs[('f', ra[0], ra[1])] = ra[2]

            for r_id in reports:
                for n_id in attr_names:
                    safes_num = {}
                    unsafes_num = {}
                    unknowns_num = {}
                    for s_id in safes:
                        if r_id not in safes[s_id]:
                            continue
                        a_id = report_attrs.get(('s', s_id, n_id), None)
                        if a_id not in safes_num:
                            safes_num[a_id] = 0
                        safes_num[a_id] += 1
                    for u_id in unsafes:
                        if r_id not in unsafes[u_id]:
                            continue
                        a_id = report_attrs.get(('u', u_id, n_id), None)
                        if a_id not in unsafes_num:
                            unsafes_num[a_id] = 0
                        unsafes_num[a_id] += 1
                    for f_id in unknowns:
                        if r_id not in unknowns[f_id]:
                            continue
                        a_id = report_attrs.get(('f', f_id, n_id), None)
                        if a_id not in unknowns_num:
                            unknowns_num[a_id] = 0
                        unknowns_num[a_id] += 1
                    for a_id in set(safes_num) | set(unsafes_num) | set(unknowns_num):
                        attrs_data.append(AttrStatistic(
                            report_id=r_id, attr_id=a_id, name_id=n_id,
                            safes=safes_num.get(a_id, 0),
                            unsafes=unsafes_num.get(a_id, 0),
                            unknowns=unknowns_num.get(a_id, 0)
                        ))
        AttrStatistic.objects.bulk_create(attrs_data)


class Recalculation(object):
    def __init__(self, rec_type, jobs=None):
        self.error = None
        self.type = rec_type
        self.jobs = self.__get_jobs(jobs)
        if self.error is not None:
            return
        self.__recalc()

    def __get_jobs(self, job_ids):
        if job_ids is None:
            return Job.objects.filter(light=False)
        jobs = []
        try:
            job_ids = json.loads(job_ids)
        except ValueError:
            self.error = 'Unknown error'
            return None
        for j_id in job_ids:
            try:
                job = Job.objects.get(pk=int(j_id))
                if not job.light:
                    jobs.append(job)
            except ObjectDoesNotExist:
                self.error = _('One of the selected jobs was not found')
                return None
            except ValueError:
                self.error = 'Unknown error'
                return None
        if len(jobs) == 0:
            self.error = _('Please select jobs to recalculate caches for them')
            return None
        return jobs

    def __recalc(self):
        if self.type == 'verdicts':
            RecalculateVerdicts(self.jobs)
        elif self.type == 'leaves':
            RecalculateLeaves(self.jobs)
        elif self.type == 'unsafe':
            RecalculateUnsafeMarkConnections(self.jobs)
        elif self.type == 'safe':
            RecalculateSafeMarkConnections(self.jobs)
        elif self.type == 'unknown':
            RecalculateUnknownMarkConnections(self.jobs)
        elif self.type == 'resources':
            RecalculateResources(self.jobs)
        elif self.type == 'attrs_stat':
            RecalculateAttrStatistic(self.jobs)
        elif self.type == 'all':
            RecalculateLeaves(self.jobs)
            RecalculateUnsafeMarkConnections(self.jobs)
            RecalculateSafeMarkConnections(self.jobs)
            RecalculateUnknownMarkConnections(self.jobs)
            RecalculateVerdicts(self.jobs)
            RecalculateResources(self.jobs)
            RecalculateAttrStatistic(self.jobs)
        else:
            self.error = 'Unknown error'


class RecalculateResources(object):
    def __init__(self, jobs):
        self.jobs = jobs
        self.__recalc()

    def __recalc(self):
        ComponentResource.objects.filter(report__root__job__in=self.jobs).delete()
        rd = ResourceData()
        for rep in ReportComponent.objects.filter(root__job__in=self.jobs).order_by('id'):
            rd.add(rep)
        ComponentResource.objects.bulk_create(rd.cache_for_db())


class ResourceData(object):
    def __init__(self):
        self._data = {}
        self._resources = self.ResourceCache()

    class ResourceCache(object):
        def __init__(self):
            self._data = {}

        def update(self, report_id, data):
            if any(data[x] is None for x in ['ct', 'wt', 'm']):
                return
            self.__recalculate((report_id, data['component']), data)
            self.__recalculate((report_id, 't'), data)

        def get_all(self):
            all_data = []
            for d in self._data:
                if d[1] == 't' and self._data[d][3]:
                    continue
                all_data.append({
                    'report_id': d[0],
                    'component_id': d[1] if d[1] != 't' else None,
                    'cpu_time': self._data[d][0],
                    'wall_time': self._data[d][1],
                    'memory': self._data[d][2]
                })
            return all_data

        def __recalculate(self, cache_id, data):
            if cache_id not in self._data:
                self._data[cache_id] = [data['ct'], data['wt'], data['m'], True]
            else:
                if self._data[cache_id][0] is None:
                    self._data[cache_id][0] = data['ct']
                else:
                    self._data[cache_id][0] += data['ct'] if data['ct'] is not None else 0
                if self._data[cache_id][1] is None:
                    self._data[cache_id][1] = data['wt']
                else:
                    self._data[cache_id][1] += data['wt'] if data['wt'] is not None else 0
                if data['m'] is not None:
                    if self._data[cache_id][2] is not None:
                        self._data[cache_id][2] = max(data['m'], self._data[cache_id][2])
                    else:
                        self._data[cache_id][2] = data['m']
                self._data[cache_id][3] = False

    def add(self, report):
        if not isinstance(report, ReportComponent):
            raise ValueError('Value must be ReportComponent object')
        self._data[report.pk] = {'id': report.pk, 'parent': report.parent_id}
        self.__update_resources({
            'id': report.pk,
            'parent': report.parent_id,
            'component': report.component_id,
            'wt': report.wall_time,
            'ct': report.cpu_time,
            'm': report.memory
        })

    def __update_resources(self, newdata):
        d = newdata
        while d is not None:
            if d['parent'] is not None and d['parent'] not in self._data:
                logger.error('Updating resources failed', stack_info=True)
                return
            self._resources.update(d['id'], newdata)
            if d['parent'] is not None:
                d = self._data[d['parent']]
            else:
                d = None

    def cache_for_db(self):
        return list(ComponentResource(**d) for d in self._resources.get_all())


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


class VerdictsData(object):
    def __init__(self):
        self._verdicts = {}
        self._unknowns = {}

    def add(self, leaf):
        if not isinstance(leaf, ReportComponentLeaf):
            return
        if leaf.report_id not in self._verdicts:
            self._verdicts[leaf.report_id] = Verdict(report_id=leaf.report_id)
        if leaf.safe is not None:
            self._verdicts[leaf.report_id].safe += 1
            if leaf.safe.verdict == SAFE_VERDICTS[0][0]:
                self._verdicts[leaf.report_id].safe_unknown += 1
            elif leaf.safe.verdict == SAFE_VERDICTS[1][0]:
                self._verdicts[leaf.report_id].safe_incorrect_proof += 1
            elif leaf.safe.verdict == SAFE_VERDICTS[2][0]:
                self._verdicts[leaf.report_id].safe_missed_bug += 1
            elif leaf.safe.verdict == SAFE_VERDICTS[3][0]:
                self._verdicts[leaf.report_id].safe_inconclusive += 1
            elif leaf.safe.verdict == SAFE_VERDICTS[4][0]:
                self._verdicts[leaf.report_id].safe_unassociated += 1
        elif leaf.unsafe is not None:
            self._verdicts[leaf.report_id].unsafe += 1
            if leaf.unsafe.verdict == UNSAFE_VERDICTS[0][0]:
                self._verdicts[leaf.report_id].unsafe_unknown += 1
            elif leaf.unsafe.verdict == UNSAFE_VERDICTS[1][0]:
                self._verdicts[leaf.report_id].unsafe_bug += 1
            elif leaf.unsafe.verdict == UNSAFE_VERDICTS[2][0]:
                self._verdicts[leaf.report_id].unsafe_target_bug += 1
            elif leaf.unsafe.verdict == UNSAFE_VERDICTS[3][0]:
                self._verdicts[leaf.report_id].unsafe_false_positive += 1
            elif leaf.unsafe.verdict == UNSAFE_VERDICTS[4][0]:
                self._verdicts[leaf.report_id].unsafe_inconclusive += 1
            elif leaf.unsafe.verdict == UNSAFE_VERDICTS[5][0]:
                self._verdicts[leaf.report_id].unsafe_unassociated += 1
        elif leaf.unknown is not None:
            self._verdicts[leaf.report_id].unknown += 1
            if (leaf.report_id, leaf.unknown.component_id) not in self._unknowns:
                self._unknowns[(leaf.report_id, leaf.unknown.component_id)] = 0
            self._unknowns[(leaf.report_id, leaf.unknown.component_id)] += 1

    def upload(self):
        Verdict.objects.bulk_create(list(self._verdicts.values()))
        unknowns_cache = []
        for u in self._unknowns:
            unknowns_cache.append(
                ComponentUnknown(report_id=u[0], component_id=u[1], number=self._unknowns[u])
            )
        ComponentUnknown.objects.bulk_create(unknowns_cache)
        self.__init__()
