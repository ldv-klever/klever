import os
import json
from django.db.models import ProtectedError
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import ugettext_lazy as _
from bridge.settings import MEDIA_ROOT
from bridge.utils import print_err
from reports.models import *
from marks.models import *
from marks.utils import ConnectReportWithMarks, update_unknowns_cache


def clear_job_files():
    from jobs.models import File, JOBFILE_DIR
    files_in_the_system = []
    for f in File.objects.all():
        if len(f.etvfiles_set.all()) == 0 \
                and len(f.reportcomponent_set.all()) == 0 \
                and len(f.filesystem_set.all()) == 0 \
                and len(f.reportfiles_set.all()) == 0 \
                and len(f.runhistory_set.all()) == 0:
            f.delete()
        else:
            file_path = os.path.abspath(os.path.join(MEDIA_ROOT, f.file.name))
            files_in_the_system.append(file_path)
            if not(os.path.exists(file_path) and os.path.isfile(file_path)):
                print_err('Deleted from DB (file not exists): %s' % f.file.name)
                f.delete()
    files_directory = os.path.join(MEDIA_ROOT, JOBFILE_DIR)
    if os.path.exists(files_directory):
        for f in [os.path.abspath(os.path.join(files_directory, x)) for x in os.listdir(files_directory)]:
            if f not in files_in_the_system:
                os.remove(f)


def clear_service_files():
    from service.models import FILE_DIR, Solution, Task
    files_in_the_system = []
    for s in Solution.objects.all():
        files_in_the_system.append(os.path.abspath(os.path.join(MEDIA_ROOT, s.archive.name)))
    for s in Task.objects.all():
        files_in_the_system.append(os.path.abspath(os.path.join(MEDIA_ROOT, s.archive.name)))
    files_directory = os.path.join(MEDIA_ROOT, FILE_DIR)
    if os.path.exists(files_directory):
        for f in [os.path.abspath(os.path.join(files_directory, x)) for x in os.listdir(files_directory)]:
            if f not in files_in_the_system:
                os.remove(f)


def clear_computers():
    for c in Computer.objects.all():
        if len(c.reportcomponent_set.all()) == 0:
            c.delete()


class RecalculateLeaves(object):
    def __init__(self, jobs):
        self.jobs = jobs
        self.leaves = LeavesData()
        self.__recalc_all() if self.jobs is None else self.__recalc_for_jobs()

    def __recalc_for_jobs(self):
        ReportComponentLeaf.objects.filter(report__root__job__in=self.jobs).delete()
        for u in ReportComponent.objects.filter(root__job__in=self.jobs).order_by('id'):
            self.leaves.add(u)
        for u in ReportUnsafe.objects.filter(root__job__in=self.jobs):
            self.leaves.add(u)
        for s in ReportSafe.objects.filter(root__job__in=self.jobs):
            self.leaves.add(s)
        for u in ReportUnknown.objects.filter(root__job__in=self.jobs):
            self.leaves.add(u)
        self.leaves.upload()

    def __recalc_all(self):
        ReportComponentLeaf.objects.all().delete()
        for u in ReportComponent.objects.order_by('id'):
            self.leaves.add(u)
        for u in ReportUnsafe.objects.all():
            self.leaves.add(u)
        for s in ReportSafe.objects.all():
            self.leaves.add(s)
        for u in ReportUnknown.objects.all():
            self.leaves.add(u)
        self.leaves.upload()


class RecalculateVerdicts(object):
    def __init__(self, jobs):
        self.jobs = jobs
        self.__recalc_all() if self.jobs is None else self.__recalc_for_jobs()

    def __recalc_for_jobs(self):
        Verdict.objects.filter(report__root__job__in=self.jobs).delete()
        ComponentUnknown.objects.filter(report__root__job__in=self.jobs).delete()
        data = VerdictsData()
        for leaf in ReportComponentLeaf.objects.filter(report__root__job__in=self.jobs):
            data.add(leaf)
        data.upload()

    def __recalc_all(self):
        self.ccc = 0
        Verdict.objects.all().delete()
        ComponentUnknown.objects.all().delete()
        data = VerdictsData()
        for leaf in ReportComponentLeaf.objects.all():
            data.add(leaf)
        data.upload()


class RecalculateUnsafeMarkConnections(object):
    def __init__(self, jobs):
        self.jobs = jobs
        self.__recalc_all() if self.jobs is None else self.__recalc_for_jobs()

    def __recalc_for_jobs(self):
        ReportUnsafeTag.objects.filter(report__root__job__in=self.jobs).delete()
        UnsafeReportTag.objects.filter(report__root__job__in=self.jobs).delete()
        MarkUnsafeReport.objects.filter(report__root__job__in=self.jobs).delete()
        for unsafe in ReportUnsafe.objects.filter(root__job__in=self.jobs):
            ConnectReportWithMarks(unsafe)

    def __recalc_all(self):
        self.ccc = 0
        ReportUnsafeTag.objects.all().delete()
        UnsafeReportTag.objects.all().delete()
        MarkUnsafeReport.objects.all().delete()
        for unsafe in ReportUnsafe.objects.all():
            ConnectReportWithMarks(unsafe)


class RecalculateSafeMarkConnections(object):
    def __init__(self, jobs):
        self.jobs = jobs
        self.__recalc_all() if self.jobs is None else self.__recalc_for_jobs()

    def __recalc_for_jobs(self):
        ReportSafeTag.objects.filter(report__root__job__in=self.jobs).delete()
        SafeReportTag.objects.filter(report__root__job__in=self.jobs).delete()
        MarkSafeReport.objects.filter(report__root__job__in=self.jobs).delete()
        for safe in ReportSafe.objects.filter(root__job__in=self.jobs):
            ConnectReportWithMarks(safe)

    def __recalc_all(self):
        self.ccc = 0
        ReportSafeTag.objects.all().delete()
        SafeReportTag.objects.all().delete()
        MarkSafeReport.objects.all().delete()
        for safe in ReportSafe.objects.all():
            ConnectReportWithMarks(safe)


class RecalculateUnknownMarkConnections(object):
    def __init__(self, jobs):
        self.jobs = jobs
        self.__recalc_all() if self.jobs is None else self.__recalc_for_jobs()
        for problem in UnknownProblem.objects.all():
            try:
                problem.delete()
            except ProtectedError:
                pass

    def __recalc_for_jobs(self):
        MarkUnknownReport.objects.filter(report__root__job__in=self.jobs).delete()
        ComponentMarkUnknownProblem.objects.filter(report__root__job__in=self.jobs).delete()
        for unknown in ReportUnknown.objects.filter(root__job__in=self.jobs):
            ConnectReportWithMarks(unknown, False)
        update_unknowns_cache(ReportUnknown.objects.filter(root__job__in=self.jobs))

    def __recalc_all(self):
        self.ccc = 0
        MarkUnknownReport.objects.all().delete()
        ComponentMarkUnknownProblem.objects.all().delete()
        for unknown in ReportUnknown.objects.all():
            ConnectReportWithMarks(unknown, False)
        update_unknowns_cache(ReportUnknown.objects.all())


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
            return None
        jobs = []
        try:
            job_ids = json.loads(job_ids)
        except ValueError:
            self.error = 'Unknown error'
            return None
        for j_id in job_ids:
            try:
                jobs.append(Job.objects.get(pk=int(j_id)))
            except ObjectDoesNotExist:
                self.error = _('One of the selected jobs was not found')
                return None
            except ValueError:
                self.error = 'Unknown error'
                return None
        if len(jobs) == 0:
            self.error = _('Please select jobs to recalculate caches for them')
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
        elif self.type == 'all':
            RecalculateLeaves(self.jobs)
            RecalculateUnsafeMarkConnections(self.jobs)
            RecalculateSafeMarkConnections(self.jobs)
            RecalculateUnknownMarkConnections(self.jobs)
            RecalculateVerdicts(self.jobs)
            RecalculateResources(self.jobs)
        else:
            self.error = 'Unknown error'


class RecalculateResources(object):
    def __init__(self, jobs):
        self.jobs = jobs
        self.__recalc_all() if self.jobs is None else self.__recalc_for_jobs()

    def __recalc_for_jobs(self):
        ComponentResource.objects.filter(report__root__job__in=self.jobs).delete()
        self.__update_cache({'root__job__in': self.jobs})

    def __recalc_all(self):
        self.ccc = 0
        ComponentResource.objects.all().delete()
        self.__update_cache({})

    def __update_cache(self, filters):
        self.ccc = 0
        rd = ResourceData()
        for rep in ReportComponent.objects.filter(**filters).order_by('id'):
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
                self._data[cache_id][0] += data['ct']
                self._data[cache_id][1] += data['wt']
                self._data[cache_id][2] = max(data['m'], self._data[cache_id][2])
                self._data[cache_id][3] = False

    def add(self, report):
        if not isinstance(report, ReportComponent):
            raise ValueError('Value must be class of ReportComponent')
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
                print_err('ERROR_1')
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
            self._data[report.pk] = {
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
                        self._data[parent_id]['safes'].append(report.pk)
                    elif isinstance(report, ReportUnsafe):
                        self._data[parent_id]['unsafes'].append(report.pk)
                    elif isinstance(report, ReportUnknown):
                        self._data[parent_id]['unknowns'].append(report.pk)
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
