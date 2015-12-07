import os
import json
from django.db.models import Q, ProtectedError
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import ugettext_lazy as _
from Omega.settings import MEDIA_ROOT
from Omega.utils import print_err
from reports.models import *
from marks.models import ReportUnsafeTag, UnsafeReportTag, MarkUnsafeReport,\
    ReportSafeTag, SafeReportTag, MarkSafeReport, MarkUnknownReport, ComponentMarkUnknownProblem, UnknownProblem
from marks.utils import ConnectReportWithMarks


def clear_job_files():
    from jobs.models import File, JOBFILE_DIR
    files_in_the_system = []
    for f in File.objects.all():
        if len(f.etvfiles_set.all()) == 0 \
                and len(f.reportcomponent_set.all()) == 0 \
                and len(f.filesystem_set.all()) == 0:
            f.delete()
        else:
            file_path = os.path.abspath(os.path.join(MEDIA_ROOT, f.file.name))
            files_in_the_system.append(file_path)
            if not(os.path.isfile(file_path) and os.path.exists(file_path)):
                print_err('Deleted from DB (file not exists): %s' % f.file.name)
                f.delete()
    files_directory = os.path.join(MEDIA_ROOT, JOBFILE_DIR)
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
    for f in [os.path.abspath(os.path.join(files_directory, x)) for x in os.listdir(files_directory)]:
        if f not in files_in_the_system:
            os.remove(f)


def clear_resources():
    for r in Resource.objects.all():
        if len(r.reportcomponent_set.all()) == 0 and len(r.componentresource_set.all()) == 0:
            r.delete()


def clear_computers():
    for c in Computer.objects.all():
        if len(c.reportcomponent_set.all()) == 0:
            c.delete()


class RecalculateVerdicts(object):
    def __init__(self, jobs=None):
        self.error = None
        self.jobs = jobs
        self.__recalc_all() if self.jobs is None else self.__recalc_for_jobs()

    def __recalc_for_jobs(self):
        ReportComponentLeaf.objects.filter(report__root__job__in=self.jobs).delete()
        Verdict.objects.filter(report__root__job__in=self.jobs).delete()
        ComponentUnknown.objects.filter(report__root__job__in=self.jobs).delete()
        for u in ReportUnsafe.objects.filter(root__job__in=self.jobs):
            self.__update_unsafe(u)
        for s in ReportSafe.objects.filter(root__job__in=self.jobs):
            self.__update_safe(s)
        for u in ReportUnknown.objects.filter(root__job__in=self.jobs):
            self.__update_unknown(u)

    def __recalc_all(self):
        ReportComponentLeaf.objects.all().delete()
        Verdict.objects.all().delete()
        ComponentUnknown.objects.all().delete()
        for u in ReportUnsafe.objects.all():
            self.__update_unsafe(u)
        for s in ReportSafe.objects.all():
            self.__update_safe(s)
        for u in ReportUnknown.objects.all():
            self.__update_unknown(u)

    def __update_unsafe(self, u):
        self.ccc = 0
        try:
            parent = ReportComponent.objects.get(pk=u.parent_id)
        except ObjectDoesNotExist:
            u.delete()
            return
        while parent is not None:
            verdict = Verdict.objects.get_or_create(report=parent)[0]
            verdict.unsafe += 1
            if u.verdict == UNSAFE_VERDICTS[0][0]:
                verdict.unsafe_unknown += 1
            elif u.verdict == UNSAFE_VERDICTS[1][0]:
                verdict.unsafe_bug += 1
            elif u.verdict == UNSAFE_VERDICTS[2][0]:
                verdict.unsafe_target_bug += 1
            elif u.verdict == UNSAFE_VERDICTS[3][0]:
                verdict.unsafe_false_positive += 1
            elif u.verdict == UNSAFE_VERDICTS[4][0]:
                verdict.unsafe_inconclusive += 1
            elif u.verdict == UNSAFE_VERDICTS[5][0]:
                verdict.unsafe_unassociated += 1
            verdict.save()
            ReportComponentLeaf.objects.create(report=parent, unsafe=u)
            if parent.parent_id is None:
                return
            try:
                parent = ReportComponent.objects.get(pk=parent.parent_id)
            except ObjectDoesNotExist:
                return

    def __update_safe(self, s):
        self.ccc = 0
        try:
            parent = ReportComponent.objects.get(pk=s.parent_id)
        except ObjectDoesNotExist:
            s.delete()
            return
        while parent is not None:
            verdict = Verdict.objects.get_or_create(report=parent)[0]
            verdict.safe += 1
            if s.verdict == SAFE_VERDICTS[0][0]:
                verdict.safe_unknown += 1
            elif s.verdict == SAFE_VERDICTS[1][0]:
                verdict.safe_incorrect_proof += 1
            elif s.verdict == SAFE_VERDICTS[2][0]:
                verdict.safe_missed_bug += 1
            elif s.verdict == SAFE_VERDICTS[3][0]:
                verdict.safe_inconclusive += 1
            elif s.verdict == SAFE_VERDICTS[4][0]:
                verdict.safe_unassociated += 1
            verdict.save()
            ReportComponentLeaf.objects.create(report=parent, safe=s)
            if parent.parent_id is None:
                return
            try:
                parent = ReportComponent.objects.get(pk=parent.parent_id)
            except ObjectDoesNotExist:
                return

    def __update_unknown(self, u):
        self.ccc = 0
        component = u.component
        try:
            parent = ReportComponent.objects.get(pk=u.parent_id)
        except ObjectDoesNotExist:
            u.delete()
            return
        while parent is not None:
            verdict = Verdict.objects.get_or_create(report=parent)[0]
            verdict.unknown += 1
            verdict.save()
            ReportComponentLeaf.objects.create(report=parent, unknown=u)
            comp_unknown = ComponentUnknown.objects.get_or_create(report=parent, component=component)[0]
            comp_unknown.number += 1
            comp_unknown.save()
            if parent.parent_id is None:
                return
            try:
                parent = ReportComponent.objects.get(pk=parent.parent_id)
            except ObjectDoesNotExist:
                return


class RecalculateResources(object):
    def __init__(self, jobs=None):
        self.error = None
        self.jobs = jobs
        self.__recalc_all() if self.jobs is None else self.__recalc_for_jobs()
        clear_resources()

    def __recalc_for_jobs(self):
        ComponentResource.objects.filter(report__root__job__in=self.jobs).delete()
        for rep in ReportComponent.objects.filter(root__job__in=self.jobs):
            self.__update_cache(rep)

    def __recalc_all(self):
        self.ccc = 0
        ComponentResource.objects.all().delete()
        for rep in ReportComponent.objects.all():
            self.__update_cache(rep)

    def __update_cache(self, report):
        self.ccc = 0

        def update_total_resources(rep):
            res_set = rep.resources_cache.filter(~Q(component=None))
            if len(res_set) > 0:
                nres = Resource()
                nres.wall_time = 0
                nres.cpu_time = 0
                nres.memory = 0
                for comp_res in res_set:
                    nres.wall_time += comp_res.resource.wall_time
                    nres.cpu_time += comp_res.resource.cpu_time
                    nres.memory = max(comp_res.resource.memory, nres.memory)
                nres.save()
                try:
                    total_compres = rep.resources_cache.get(component=None)
                    total_compres.resource.delete()
                except ObjectDoesNotExist:
                    total_compres = ComponentResource()
                    total_compres.report = rep
                total_compres.resource = nres
                total_compres.save()

        update_total_resources(report)
        try:
            report.resources_cache.get(component=report.component)
        except ObjectDoesNotExist:
            report.resources_cache.create(component=report.component, resource=report.resource)

        try:
            parent = ReportComponent.objects.get(pk=report.parent_id)
        except ObjectDoesNotExist:
            parent = None
        while parent is not None:
            new_res = Resource()
            new_res.wall_time = report.resource.wall_time
            new_res.cpu_time = report.resource.cpu_time
            new_res.memory = report.resource.memory
            try:
                compres = parent.resources_cache.get(component=report.component)
                new_res.wall_time += compres.resource.wall_time
                new_res.cpu_time += compres.resource.cpu_time
                new_res.memory = max(compres.resource.memory, new_res.memory)
                compres.resource.delete()
            except ObjectDoesNotExist:
                compres = ComponentResource()
                compres.component = report.component
                compres.report = parent
            new_res.save()
            compres.resource = new_res
            compres.save()
            update_total_resources(parent)
            try:
                parent = ReportComponent.objects.get(pk=parent.parent_id)
            except ObjectDoesNotExist:
                parent = None


class RecalculateUnsafeMarkConnections(object):
    def __init__(self, jobs=None):
        self.error = None
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
    def __init__(self, jobs=None):
        self.error = None
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
    def __init__(self, jobs=None):
        self.error = None
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
            ConnectReportWithMarks(unknown)

    def __recalc_all(self):
        self.ccc = 0
        MarkUnknownReport.objects.all().delete()
        ComponentMarkUnknownProblem.objects.all().delete()
        for unknown in ReportUnknown.objects.all():
            ConnectReportWithMarks(unknown)


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
            return
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
            self.error = _('There are no jobs to recalculate')
        return jobs

    def __recalc(self):
        args = {}
        if self.jobs is not None:
            args['jobs'] = self.jobs
        if self.type == 'verdicts':
            res = RecalculateVerdicts(**args)
            self.error = res.error
        elif self.type == 'unsafe':
            res = RecalculateUnsafeMarkConnections(**args)
            self.error = res.error
        elif self.type == 'safe':
            res = RecalculateSafeMarkConnections(**args)
            self.error = res.error
        elif self.type == 'unknown':
            res = RecalculateUnknownMarkConnections(**args)
            self.error = res.error
        elif self.type == 'resources':
            res = RecalculateResources(**args)
            self.error = res.error
        elif self.type == 'all':
            res = RecalculateUnsafeMarkConnections(**args)
            self.error = res.error
            if self.error is not None:
                return
            res = RecalculateSafeMarkConnections(**args)
            self.error = res.error
            if self.error is not None:
                return
            res = RecalculateUnknownMarkConnections(**args)
            self.error = res.error
            if self.error is not None:
                return
            res = RecalculateVerdicts(**args)
            self.error = res.error
            if self.error is not None:
                return
            res = RecalculateResources(**args)
            self.error = res.error
            if self.error is not None:
                return
        else:
            self.error = 'Unknown error'
