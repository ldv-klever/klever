import json
import hashlib
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import ugettext_lazy as _
from reports.models import *


class CompareTree(object):
    def __init__(self, job1, job2):
        self.error = None
        self.__get_jobs(job1, job2)
        if self.error is not None:
            return
        self.nodes = {}
        self.tree = self.__get_tree()

    def __get_jobs(self, job1, job2):
        try:
            self.job1 = Job.objects.get(pk=int(job1))
            self.job2 = Job.objects.get(pk=int(job2))
        except ObjectDoesNotExist:
            self.error = _('One of jobs was not found')

    def __get_tree(self):
        children = ReportComponent.objects.get(parent=None, root__job=self.job1)
        while len(children) > 0:
            children_ids = []
            for child in children:
                try:
                    self.nodes[child.pk] = ReportData(child, ReportUnknown.objects.get(parent_id=child.pk))
                except ObjectDoesNotExist:
                    self.nodes[child.pk] = ReportData(child)
                children_ids.append(child.pk)
            children = ReportComponent.objects.get(id__in=children_ids)
        for safe in ReportSafe.objects.filter(root__job=self.job1):
            self.nodes[safe.pk] = SafeData(safe)
        return None


class UnknownData(object):
    def __init__(self, unknown):
        self.pk = unknown.pk
        self.type = 'unknown'
        self.attr = get_attr_hash(unknown)
        self.problem = self.__get_problem(unknown)

    def __get_problem(self, unknown):
        self.ccc = 0
        data = []
        for mrep in unknown.markreport_set.order_by('problem__name'):
            data.append(mrep.problem.name)
        if len(data) == 0:
            return hashlib.md5(unknown.problem_description).hexdigest()
        else:
            return hashlib.md5(json.dumps(data).encode('utf8')).hexdigest()


class ReportData(object):
    def __init__(self, report, unknown=None):
        self.pk = report.pk
        self.type = 'report'
        self.attr = get_attr_hash(report)
        self.component = report.component.name
        self.unknown = self.__get_unknown_data(unknown)
        self.parent = report.parent_id

    def __get_unknown_data(self, unknown):
        self.ccc = 0
        if isinstance(unknown, ReportUnknown):
            return UnknownData(unknown)
        return None


class SafeData(object):
    def __init__(self, safe):
        self.pk = safe.pk
        self.type = 'safe'
        self.attr = get_attr_hash(safe)
        self.verdict = safe.verdict
        self.proof = hashlib.md5(safe.proof).hexdigest()
        self.parent = safe.parent_id


class UnsafeData(object):
    def __init__(self, unsafe):
        self.pk = unsafe.pk
        self.type = 'unsafe'
        self.attr = get_attr_hash(unsafe)
        self.verdict = unsafe.verdict
        self.error_trace = hashlib.md5(unsafe.error_trace).hexdigest()
        self.parent = unsafe.parent_id


def get_attr_hash(report):
    attr_data = []
    for a in report.attrs.order_by('attr__name__name'):
        attr_data.append("%s#%s" % (a.attr.name.name, a.attr.value))
    return hashlib.md5(json.dumps(attr_data).encode('utf8')).hexdigest()


class TreeNode(object):
    def __init__(self, parent=None):
        self.a = 0
        self.parent = parent
