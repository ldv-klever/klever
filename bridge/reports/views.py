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
import json
from io import BytesIO
from wsgiref.util import FileWrapper

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponseRedirect
from django.utils.decorators import method_decorator
from django.utils.translation import ugettext as _, override
from django.template.defaulttags import register
from django.views.generic.base import TemplateView
from django.views.generic.detail import SingleObjectMixin, DetailView

import bridge.CustomViews as Bview
from tools.profiling import LoggedCallMixin
from bridge.vars import JOB_STATUS, VIEW_TYPES, LOG_FILE, ERROR_TRACE_FILE, PROOF_FILE, PROBLEM_DESC_FILE
from bridge.utils import logger, ArchiveFileContent, BridgeException, BridgeErrorResponse
from jobs.ViewJobData import ViewJobData
from jobs.utils import JobAccess
from jobs.models import Job
from marks.tables import ReportMarkTable
from service.models import Task
from reports.models import ReportRoot, Report, ReportComponent, ReportSafe, ReportUnknown, ReportUnsafe,\
    AttrName, ReportAttr, CompareJobsInfo, CoverageArchive

import reports.utils
from reports.UploadReport import UploadReport
from reports.etv import GetSource, GetETV
from reports.comparison import CompareTree, ComparisonTableData, ComparisonData, can_compare
from reports.coverage import GetCoverage, GetCoverageSrcHTML


# These filters are used for visualization component specific data. They should not be used for any other purposes.
@register.filter
def get_dict_val(d, key):
    return d.get(key)


@register.filter
def sort_list(l):
    return sorted(l)


@register.filter
def sort_tests_list(l):
    return sorted(l, key=lambda test: test.lstrip('1234567890'))


@register.filter
def sort_bugs_list(l):
    return sorted(l, key=lambda bug: bug[12:].lstrip('~'))


@register.filter
def calculate_test_stats(test_results):
    test_stats = {
        "passed tests": 0,
        "failed tests": 0,
        "missed comments": 0,
        "excessive comments": 0,
        "tests": 0
    }

    for result in test_results.values():
        test_stats["tests"] += 1
        if result["ideal verdict"] == result["verdict"]:
            test_stats["passed tests"] += 1
            if result.get('comment'):
                test_stats["excessive comments"] += 1
        else:
            test_stats["failed tests"] += 1
            if not result.get('comment'):
                test_stats["missed comments"] += 1

    return test_stats


@register.filter
def calculate_validation_stats(validation_results):
    validation_stats = {
        "found bug before fix and safe after fix": 0,
        "found bug before fix and non-safe after fix": 0,
        "found non-bug before fix and safe after fix": 0,
        "found non-bug before fix and non-safe after fix": 0,
        "missed comments": 0,
        "excessive comments": 0,
        "bugs": 0
    }

    for result in validation_results.values():
        validation_stats["bugs"] += 1

        is_found_bug_before_fix = False

        if "before fix" in result:
            if result["before fix"]["verdict"] == "unsafe":
                is_found_bug_before_fix = True
                if result["before fix"]["comment"]:
                    validation_stats["excessive comments"] += 1
            elif 'comment' not in result["before fix"] or not result["before fix"]["comment"]:
                validation_stats["missed comments"] += 1

        is_found_safe_after_fix = False

        if "after fix" in result:
            if result["after fix"]["verdict"] == "safe":
                is_found_safe_after_fix = True
                if result["after fix"]["comment"]:
                    validation_stats["excessive comments"] += 1
            elif 'comment' not in result["after fix"] or not result["after fix"]["comment"]:
                validation_stats["missed comments"] += 1

        if is_found_bug_before_fix:
            if is_found_safe_after_fix:
                validation_stats["found bug before fix and safe after fix"] += 1
            else:
                validation_stats["found bug before fix and non-safe after fix"] += 1
        else:
            if is_found_safe_after_fix:
                validation_stats["found non-bug before fix and safe after fix"] += 1
            else:
                validation_stats["found non-bug before fix and non-safe after fix"] += 1

    return validation_stats


@method_decorator(login_required, name='dispatch')
class ReportComponentView(LoggedCallMixin, Bview.DataViewMixin, DetailView):
    model = ReportComponent
    template_name = 'reports/ReportMain.html'

    def get_context_data(self, **kwargs):
        job = self.object.root.job
        if not JobAccess(self.request.user, job).can_view():
            raise BridgeException(code=400)
        return {
            'report': self.object,
            'status': reports.utils.ReportStatus(self.object),
            'data': reports.utils.ReportData(self.object),
            'resources': reports.utils.report_resources(self.object, self.request.user),
            'computer': reports.utils.computer_description(self.object.computer.description),
            'SelfAttrsData': reports.utils.ReportAttrsTable(self.object).table_data,
            'parents': reports.utils.get_parents(self.object),
            'reportdata': ViewJobData(self.request.user, self.get_view(VIEW_TYPES[2]), self.object),
            'TableData': reports.utils.ReportChildrenTable(self.request.user, self.object, self.get_view(VIEW_TYPES[3]),
                                                           page=self.request.GET.get('page', 1))
        }


@method_decorator(login_required, name='dispatch')
class ComponentLogView(LoggedCallMixin, SingleObjectMixin, Bview.StreamingResponseView):
    model = ReportComponent
    pk_url_kwarg = 'report_id'

    def get_generator(self):
        self.object = self.get_object()
        if not JobAccess(self.request.user, self.object.root.job).can_view():
            return BridgeErrorResponse(400)
        if not self.object.log:
            raise BridgeException(_("The component doesn't have log"))

        content = ArchiveFileContent(self.object, 'log', LOG_FILE).content
        self.file_size = len(content)
        return FileWrapper(BytesIO(content), 8192)

    def get_filename(self):
        return '%s-log.txt' % self.object.component.name


class ComponentLogContent(LoggedCallMixin, Bview.JsonDetailView):
    model = ReportComponent
    pk_url_kwarg = 'report_id'

    def get_context_data(self, **kwargs):
        if not JobAccess(self.request.user, self.object.root.job).can_view():
            raise BridgeException(code=400)
        if not self.object.log:
            raise BridgeException(_("The component doesn't have log"))

        content = ArchiveFileContent(self.object, 'log', LOG_FILE).content
        if len(content) > 10 ** 5:
            content = str(_('The component log is huge and can not be shown but you can download it'))
        else:
            content = content.decode('utf8')
        return {'content': content}


@method_decorator(login_required, name='dispatch')
class AttrDataFileView(LoggedCallMixin, SingleObjectMixin, Bview.StreamingResponseView):
    model = ReportAttr

    def get_generator(self):
        self.object = self.get_object()
        if not JobAccess(self.request.user, self.object.report.root.job).can_view():
            raise BridgeException(code=400)
        if not self.object.data:
            raise BridgeException(_("The attribute doesn't have data"))

        content = self.object.data.file.read()
        self.file_size = len(content)
        return FileWrapper(BytesIO(content), 8192)

    def get_filename(self):
        return 'Attr-Data' + os.path.splitext(self.object.data.file.name)[-1]


class AttrDataContentView(LoggedCallMixin, Bview.JsonDetailView):
    model = ReportAttr

    def get_context_data(self, **kwargs):
        if not JobAccess(self.request.user, self.object.report.root.job).can_view():
            raise BridgeException(code=400)
        if not self.object.data:
            raise BridgeException(_("The attribute doesn't have data"))

        content = self.object.data.file.read()
        if len(content) > 10 ** 5:
            content = str(_('The attribute data is huge and can not be shown but you can download it'))
        else:
            content = content.decode('utf8')
        return {'content': content}


@method_decorator(login_required, name='dispatch')
class DownloadVerifierFiles(LoggedCallMixin, SingleObjectMixin, Bview.StreamingResponseView):
    model = ReportComponent

    def get_generator(self):
        self.object = self.get_object()
        if not self.object.verifier_input:
            raise BridgeException(_("The report doesn't have input files of static verifiers"))
        return FileWrapper(self.object.verifier_input.file, 8192)

    def get_filename(self):
        return '%s files.zip' % self.object.component.name


@method_decorator(login_required, name='dispatch')
class SafesListView(LoggedCallMixin, Bview.DataViewMixin, DetailView):
    model = ReportComponent
    pk_url_kwarg = 'report_id'
    template_name = 'reports/report_list.html'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        context = self.get_context_data(object=self.object)
        values = context['TableData'].table_data['values']

        # If there is only one element in table, and first column of table is link, redirect to this link
        if request.GET.get('view_type') != VIEW_TYPES[5][0] \
                and values.paginator.count == 1 and isinstance(values[0], list) \
                and len(values[0]) > 0 and 'href' in values[0][0] and values[0][0]['href']:
            return HttpResponseRedirect(values[0][0]['href'])
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        if not JobAccess(self.request.user, self.object.root.job).can_view():
            raise BridgeException(code=400)
        getdata = reports.utils.SafesListGetData(self.request.GET)
        return {
            'title': getdata.title, 'report': self.object, 'parents': reports.utils.get_parents(self.object),
            'TableData': reports.utils.SafesTable(self.request.user, self.object, self.get_view(VIEW_TYPES[5]),
                                                  **getdata.args)
        }


@method_decorator(login_required, name='dispatch')
class UnsafesListView(LoggedCallMixin, Bview.DataViewMixin, DetailView):
    model = ReportComponent
    pk_url_kwarg = 'report_id'
    template_name = 'reports/report_list.html'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        context = self.get_context_data(object=self.object)
        values = context['TableData'].table_data['values']

        # If there is only one element in table, and first column of table is link, redirect to this link
        if request.GET.get('view_type') != VIEW_TYPES[4][0] \
                and values.paginator.count == 1 and isinstance(values[0], list) \
                and len(values[0]) > 0 and 'href' in values[0][0] and values[0][0]['href']:
            return HttpResponseRedirect(values[0][0]['href'])
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        if not JobAccess(self.request.user, self.object.root.job).can_view():
            raise BridgeException(code=400)
        getdata = reports.utils.UnsafesListGetData(self.request.GET)
        return {
            'title': getdata.title, 'report': self.object, 'parents': reports.utils.get_parents(self.object),
            'TableData': reports.utils.UnsafesTable(self.request.user, self.object, self.get_view(VIEW_TYPES[4]),
                                                    **getdata.args)
        }


@method_decorator(login_required, name='dispatch')
class UnknownsListView(LoggedCallMixin, Bview.DataViewMixin, DetailView):
    model = ReportComponent
    pk_url_kwarg = 'report_id'
    template_name = 'reports/report_list.html'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        context = self.get_context_data(object=self.object)
        values = context['TableData'].table_data['values']

        # If there is only one element in table, and first column of table is link, redirect to this link
        if request.GET.get('view_type') != VIEW_TYPES[6][0] \
                and values.paginator.count == 1 and isinstance(values[0], list) \
                and len(values[0]) > 0 and 'href' in values[0][0] and values[0][0]['href']:
            return HttpResponseRedirect(values[0][0]['href'])
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        if not JobAccess(self.request.user, self.object.root.job).can_view():
            raise BridgeException(code=400)
        getdata = reports.utils.UnknownsListGetData(self.request.GET)
        return {
            'title': getdata.title, 'report': self.object, 'parents': reports.utils.get_parents(self.object),
            'TableData': reports.utils.UnknownsTable(self.request.user, self.object, self.get_view(VIEW_TYPES[6]),
                                                     **getdata.args)
        }


@method_decorator(login_required, name='dispatch')
class ReportSafeView(LoggedCallMixin, Bview.DataViewMixin, DetailView):
    template_name = 'reports/reportLeaf.html'
    model = ReportSafe

    def get_context_data(self, **kwargs):
        if not JobAccess(self.request.user, self.object.root.job).can_view():
            raise BridgeException(code=400)

        proof_content = None
        if self.object.proof:
            proof_content = ArchiveFileContent(self.object, 'proof', PROOF_FILE).content.decode('utf8')
        return {
            'report': self.object, 'report_type': 'safe',
            'parents': reports.utils.get_parents(self.object),
            'resources': reports.utils.get_leaf_resources(self.request.user, self.object),
            'SelfAttrsData': reports.utils.report_attibutes(self.object),
            'main_content': proof_content,
            'MarkTable': ReportMarkTable(self.request.user, self.object, self.get_view(VIEW_TYPES[11]))
        }


@method_decorator(login_required, name='dispatch')
class ReportUnknownView(LoggedCallMixin, Bview.DataViewMixin, DetailView):
    template_name = 'reports/reportLeaf.html'
    model = ReportUnknown

    def get_context_data(self, **kwargs):
        if not JobAccess(self.request.user, self.object.root.job).can_view():
            raise BridgeException(code=400)

        return {
            'report': self.object, 'report_type': 'unknown',
            'parents': reports.utils.get_parents(self.object),
            'resources': reports.utils.get_leaf_resources(self.request.user, self.object),
            'SelfAttrsData': reports.utils.report_attibutes(self.object),
            'main_content': ArchiveFileContent(
                self.object, 'problem_description', PROBLEM_DESC_FILE).content.decode('utf8'),
            'MarkTable': ReportMarkTable(self.request.user, self.object, self.get_view(VIEW_TYPES[12]))
        }


@method_decorator(login_required, name='dispatch')
class ReportUnsafeView(LoggedCallMixin, Bview.DataViewMixin, DetailView):
    template_name = 'reports/reportLeaf.html'
    model = ReportUnsafe
    slug_url_kwarg = 'trace_id'
    slug_field = 'trace_id'

    def get_context_data(self, **kwargs):
        if not JobAccess(self.request.user, self.object.root.job).can_view():
            raise BridgeException(code=400)
        try:
            etv = GetETV(ArchiveFileContent(self.object, 'error_trace', ERROR_TRACE_FILE).content.decode('utf8'),
                         self.request.user)
        except Exception as e:
            logger.exception(e, stack_info=True)
            etv = None
        return {
            'report': self.object, 'report_type': 'unsafe', 'parents': reports.utils.get_parents(self.object),
            'SelfAttrsData': reports.utils.report_attibutes(self.object),
            'MarkTable': ReportMarkTable(self.request.user, self.object, self.get_view(VIEW_TYPES[10])),
            'etv': etv, 'include_assumptions': self.request.user.extended.assumptions, 'include_jquery_ui': True,
            'resources': reports.utils.get_leaf_resources(self.request.user, self.object)
        }


@method_decorator(login_required, name='dispatch')
class FullscreenReportUnsafe(LoggedCallMixin, DetailView):
    template_name = 'reports/etv_fullscreen.html'
    model = ReportUnsafe
    slug_url_kwarg = 'trace_id'
    slug_field = 'trace_id'

    def get_context_data(self, **kwargs):
        if not JobAccess(self.request.user, self.object.root.job).can_view():
            raise BridgeException(code=400)
        return {
            'report': self.object,
            'include_assumptions': self.request.user.extended.assumptions,
            'etv': GetETV(
                ArchiveFileContent(self.object, 'error_trace', ERROR_TRACE_FILE).content.decode('utf8'),
                self.request.user
            )
        }


class SourceCodeView(LoggedCallMixin, Bview.JsonDetailPostView):
    model = ReportUnsafe
    pk_url_kwarg = 'unsafe_id'

    def get_context_data(self, **kwargs):
        return {
            'name': self.request.POST['file_name'],
            'content': GetSource(self.object, self.request.POST['file_name']).data
        }


@method_decorator(login_required, name='dispatch')
class DownloadErrorTrace(LoggedCallMixin, SingleObjectMixin, Bview.StreamingResponseView):
    model = ReportUnsafe
    pk_url_kwarg = 'unsafe_id'
    file_name = 'error trace.json'

    def get_generator(self):
        self.object = self.get_object()
        content = ArchiveFileContent(self.object, 'error_trace', ERROR_TRACE_FILE).content
        self.file_size = len(content)
        return FileWrapper(BytesIO(content), 8192)


class FillComparisonCacheView(LoggedCallMixin, Bview.JsonView):
    unparallel = ['Job', 'ReportRoot', CompareJobsInfo]

    def get_context_data(self, **kwargs):
        try:
            r1 = ReportRoot.objects.get(job_id=self.kwargs['job1_id'])
            r2 = ReportRoot.objects.get(job_id=self.kwargs['job2_id'])
        except ObjectDoesNotExist:
            raise BridgeException(code=405)
        if not can_compare(self.request.user, r1.job, r2.job):
            raise BridgeException(code=401)
        try:
            CompareJobsInfo.objects.get(user=self.request.user, root1=r1, root2=r2)
        except ObjectDoesNotExist:
            CompareTree(self.request.user, r1, r2)
        return {}


@method_decorator(login_required, name='dispatch')
class ReportsComparisonView(LoggedCallMixin, TemplateView):
    template_name = 'reports/comparison.html'

    def get_context_data(self, **kwargs):
        try:
            root1 = ReportRoot.objects.get(job_id=self.kwargs['job1_id'])
            root2 = ReportRoot.objects.get(job_id=self.kwargs['job2_id'])
        except ObjectDoesNotExist:
            raise BridgeException(code=405)
        if not can_compare(self.request.user, root1.job, root2.job):
            raise BridgeException(code=401)
        res = ComparisonTableData(self.request.user, root1, root2)
        return {
            'job1': root1.job, 'job2': root2.job,
            'tabledata': res.data, 'compare_info': res.info, 'attrs': res.attrs
        }


class ReportsComparisonData(LoggedCallMixin, Bview.DetailPostView):
    template_name = 'reports/comparisonData.html'
    model = CompareJobsInfo
    pk_url_kwarg = 'info_id'

    def get_context_data(self, **kwargs):
        if all(x not in self.request.POST for x in ['verdict', 'attrs']):
            raise BridgeException()
        res = ComparisonData(
            self.object, int(self.request.POST.get('page_num', 1)),
            self.request.POST.get('hide_attrs', 0), self.request.POST.get('hide_attrs', 0),
            self.request.POST.get('verdict'), self.request.POST.get('attrs')
        )
        return {
            'verdict1': res.v1, 'verdict2': res.v2,
            'job1': self.object.root1.job, 'job2': self.object.root2.job,
            'data': res.data, 'pages': res.pages,
            'verdict': self.request.POST.get('verdict'),
            'attrs': self.request.POST.get('attrs')
        }


@method_decorator(login_required, name='dispatch')
class CoverageView(LoggedCallMixin, DetailView):
    template_name = 'reports/coverage/coverage.html'
    model = ReportComponent
    pk_url_kwarg = 'report_id'

    def get_context_data(self, **kwargs):
        return {
            'coverage': GetCoverage(self.object, self.request.GET.get('archive'), False),
            'SelfAttrsData': reports.utils.report_attributes_with_parents(self.object)
        }


@method_decorator(login_required, name='dispatch')
class CoverageLightView(LoggedCallMixin, DetailView):
    template_name = 'reports/coverage/coverage_light.html'
    model = ReportComponent
    pk_url_kwarg = 'report_id'

    def get_context_data(self, **kwargs):
        return {
            'coverage': GetCoverage(self.object, self.request.GET.get('archive'), True),
            'SelfAttrsData': reports.utils.report_attributes_with_parents(self.object)
        }


class CoverageSrcView(LoggedCallMixin, Bview.JsonDetailPostView):
    model = CoverageArchive
    pk_url_kwarg = 'archive_id'

    def get_context_data(self, **kwargs):
        res = GetCoverageSrcHTML(self.object, self.request.POST['filename'], bool(int(self.request.POST['with_data'])))
        return {'content': res.src_html, 'data': res.data_html, 'legend': res.legend}


@method_decorator(login_required, name='dispatch')
class DownloadCoverageView(LoggedCallMixin, SingleObjectMixin, Bview.StreamingResponseView):
    model = CoverageArchive

    def get_generator(self):
        self.object = self.get_object()
        return FileWrapper(self.object.archive.file, 8192)

    def get_filename(self):
        return '%s coverage.zip' % self.object.report.component.name


class UploadReportView(LoggedCallMixin, Bview.JsonDetailPostView):
    model = Job
    unparallel = [ReportRoot, AttrName, Task]

    def dispatch(self, request, *args, **kwargs):
        with override(settings.DEFAULT_LANGUAGE):
            return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        if queryset is None:
            queryset = self.get_queryset()
        try:
            return queryset.get(id=int(self.request.session['job id']))
        except ObjectDoesNotExist:
            raise BridgeException(code=404)

    def get_context_data(self, **kwargs):
        if not JobAccess(self.request.user, self.object).klever_core_access():
            raise BridgeException("User '%s' don't have access to upload report for job '%s'" %
                                  (self.request.user.username, self.object.identifier))
        if self.object.status != JOB_STATUS[2][0]:
            raise BridgeException('Reports can be uploaded only for processing jobs')

        archives = {}
        for f in self.request.FILES.getlist('file'):
            archives[f.name] = f

        if 'report' in self.request.POST:
            data = json.loads(self.request.POST['report'])
            err = UploadReport(self.object, data, archives).error
            if err is not None:
                raise BridgeException(err)
        elif 'reports' in self.request.POST:
            data = json.loads(self.request.POST['reports'])
            if not isinstance(data, list):
                raise BridgeException('Wrong format of reports data')
            for d in data:
                err = UploadReport(self.object, d, archives).error
                if err is not None:
                    raise BridgeException(err)
        else:
            raise BridgeException('Report json data is required')
        return {}


class ClearVerificationFiles(LoggedCallMixin, Bview.JsonDetailPostView):
    model = Job
    pk_url_kwarg = 'job_id'
    unparallel = [Report]

    def get_context_data(self, **kwargs):
        if not JobAccess(self.request.user, self.object).can_clear_verifications():
            raise BridgeException(_("You can't remove verification files of this job"))
        reports.utils.remove_verification_files(self.object)
        return {}
