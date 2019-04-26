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
from io import BytesIO
from wsgiref.util import FileWrapper

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponseRedirect, HttpResponse
from django.utils.decorators import method_decorator
from django.utils.translation import ugettext as _, override
from django.template.defaulttags import register
from django.views.generic.base import TemplateView
from django.views.generic.detail import SingleObjectMixin, DetailView

import bridge.CustomViews as Bview
from tools.profiling import LoggedCallMixin
from bridge.vars import USER_ROLES, VIEW_TYPES, LOG_FILE, ERROR_TRACE_FILE, PROOF_FILE, PROBLEM_DESC_FILE, JOB_WEIGHT
from bridge.utils import logger, ArchiveFileContent, BridgeException, BridgeErrorResponse
from jobs.ViewJobData import ViewReportData
from jobs.utils import JobAccess
from jobs.models import Job
from marks.tables import SafeReportMarksTable, UnsafeReportMarksTable, UnknownReportMarksTable
from service.models import Task
from reports.models import ReportRoot, Report, ReportComponent, ReportSafe, ReportUnknown, ReportUnsafe,\
    ReportAttr, CompareJobsInfo, CoverageArchive

import reports.utils
from reports.UploadReport import UploadReport
from reports.etv import GetSource, GetETV
from reports.comparison import ComparisonTableData, ComparisonData
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


class ReportComponentView(LoginRequiredMixin, LoggedCallMixin, Bview.DataViewMixin, DetailView):
    model = ReportComponent
    template_name = 'reports/ReportMain.html'

    def get_context_data(self, **kwargs):
        job = self.object.root.job
        if not JobAccess(self.request.user, job).can_view():
            raise BridgeException(code=400)
        if job.weight == JOB_WEIGHT[1][0]:
            raise BridgeException(_('Reports pages for lightweight jobs are closed'))
        return {
            'report': self.object,
            'status': reports.utils.ReportStatus(self.object),
            'data': reports.utils.ReportData(self.object),
            'resources': reports.utils.report_resources(self.request.user, self.object),
            'SelfAttrsData': reports.utils.ReportAttrsTable(self.object),
            'parents': reports.utils.get_parents(self.object),
            'reportdata': ViewReportData(self.request.user, self.get_view(VIEW_TYPES[2]), self.object),
            'TableData': reports.utils.ReportChildrenTable(
                self.request.user, self.object, self.get_view(VIEW_TYPES[3]),
                page=self.request.GET.get('page', 1)
            )
        }


class ComponentLogView(LoginRequiredMixin, LoggedCallMixin, SingleObjectMixin, Bview.StreamingResponseView):
    model = ReportComponent
    pk_url_kwarg = 'report_id'

    def get_generator(self):
        instance = self.get_object()
        if not JobAccess(self.request.user, instance.root.job).can_view():
            return BridgeErrorResponse(400)
        return reports.utils.ComponentLogGenerator(instance)


class ComponentLogContentView(LoggedCallMixin, Bview.JSONResponseMixin, DetailView):
    model = ReportComponent
    pk_url_kwarg = 'report_id'

    def get(self, *args, **kwargs):
        report = self.get_object()
        if not JobAccess(self.request.user, report.root.job).can_view():
            raise BridgeException(code=400)
        if not report.log:
            raise BridgeException(_("The component doesn't have log"))

        content = ArchiveFileContent(report, 'log', LOG_FILE).content
        if len(content) > 10 ** 5:
            content = str(_('The component log is huge and can not be shown but you can download it'))
        else:
            content = content.decode('utf8')
        return HttpResponse(content)


class AttrDataFileView(LoginRequiredMixin, LoggedCallMixin, SingleObjectMixin, Bview.StreamingResponseView):
    model = ReportAttr

    def get_generator(self):
        instance = self.get_object()
        if not JobAccess(self.request.user, instance.report.root.job).can_view():
            return BridgeErrorResponse(400)
        return reports.utils.AttrDataGenerator(instance)


class AttrDataContentView(LoggedCallMixin, Bview.JSONResponseMixin, DetailView):
    model = ReportAttr

    def get(self, *args, **kwargs):
        instance = self.get_object()
        if not JobAccess(self.request.user, instance.report.root.job).can_view():
            raise BridgeException(code=400)
        if not instance.data:
            raise BridgeException(_("The attribute doesn't have data"))

        content = instance.data.file.read()
        if len(content) > 10 ** 5:
            content = str(_('The attribute data is huge and can not be shown but you can download it'))
        else:
            content = content.decode('utf8')
        return HttpResponse(content)


class DownloadVerifierFiles(LoginRequiredMixin, LoggedCallMixin, SingleObjectMixin, Bview.StreamingResponseView):
    model = ReportComponent

    def get_generator(self):
        instance = self.get_object()
        if not JobAccess(self.request.user, instance.report.root.job).can_view():
            return BridgeErrorResponse(400)
        return reports.utils.VerifierFilesGenerator(instance)


class SafesListView(LoginRequiredMixin, LoggedCallMixin, Bview.DataViewMixin, DetailView):
    model = ReportComponent
    pk_url_kwarg = 'report_id'
    template_name = 'reports/report_list.html'

    def __init__(self, *args, **kwargs):
        self.object = None
        super().__init__(*args, **kwargs)

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()

        # Check job access
        if not JobAccess(self.request.user, self.object.root.job).can_view():
            raise BridgeException(code=400)

        # Get safes data
        safes_data = reports.utils.SafesTable(
            self.request.user, self.object, self.get_view(VIEW_TYPES[5]), self.request.GET
        )

        # Get context
        context = self.get_context_data(report=self.object)

        # Redirect if needed
        if hasattr(safes_data, 'redirect'):
            return HttpResponseRedirect(safes_data.redirect)

        context['TableData'] = safes_data
        return self.render_to_response(context)


class UnsafesListView(LoginRequiredMixin, LoggedCallMixin, Bview.DataViewMixin, DetailView):
    model = ReportComponent
    pk_url_kwarg = 'report_id'
    template_name = 'reports/report_list.html'

    def __init__(self, *args, **kwargs):
        self.object = None
        super().__init__(*args, **kwargs)

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()

        # Check job access
        if not JobAccess(self.request.user, self.object.root.job).can_view():
            raise BridgeException(code=400)

        # Get unsafes data
        unsafes_data = reports.utils.UnsafesTable(
            self.request.user, self.object, self.get_view(VIEW_TYPES[4]), self.request.GET
        )

        # Get context
        context = self.get_context_data(report=self.object)

        # Redirect if needed
        if hasattr(unsafes_data, 'redirect'):
            return HttpResponseRedirect(unsafes_data.redirect)

        context['TableData'] = unsafes_data
        return self.render_to_response(context)


class UnknownsListView(LoginRequiredMixin, LoggedCallMixin, Bview.DataViewMixin, DetailView):
    model = ReportComponent
    pk_url_kwarg = 'report_id'
    template_name = 'reports/report_list.html'

    def __init__(self, *args, **kwargs):
        self.object = None
        super().__init__(*args, **kwargs)

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()

        # Check job access
        if not JobAccess(self.request.user, self.object.root.job).can_view():
            raise BridgeException(code=400)

        # Get unknowns data
        unknowns_data = reports.utils.UnknownsTable(
            self.request.user, self.object, self.get_view(VIEW_TYPES[6]), self.request.GET
        )

        # Get context
        context = self.get_context_data(report=self.object)

        # Redirect if needed
        if hasattr(unknowns_data, 'redirect'):
            return HttpResponseRedirect(unknowns_data.redirect)

        context['TableData'] = unknowns_data
        return self.render_to_response(context)


class ReportSafeView(LoggedCallMixin, Bview.DataViewMixin, DetailView):
    template_name = 'reports/ReportSafe.html'
    model = ReportSafe

    def get_context_data(self, **kwargs):
        if not JobAccess(self.request.user, self.object.root.job).can_view():
            raise BridgeException(code=400)

        proof_content = None
        if self.object.proof:
            proof_content = ArchiveFileContent(self.object, 'proof', PROOF_FILE).content.decode('utf8')
        context = super().get_context_data(**kwargs)
        if self.object.root.job.weight == JOB_WEIGHT[0][0]:
            context['parents'] = reports.utils.get_parents(self.object)
        context.update({
            'report': self.object, 'report_type': 'safe',
            'resources': reports.utils.report_resources(self.request.user, self.object),
            'SelfAttrsData': self.object.attrs.order_by('id').values_list('id', 'name', 'value', 'data'),
            'main_content': proof_content,
            'MarkTable': SafeReportMarksTable(self.request.user, self.object, self.get_view(VIEW_TYPES[11]))
        })
        return context


class ReportUnsafeView(LoginRequiredMixin, LoggedCallMixin, Bview.DataViewMixin, DetailView):
    template_name = 'reports/ReportUnsafe.html'
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
        context = super().get_context_data(**kwargs)
        if self.object.root.job.weight == JOB_WEIGHT[0][0]:
            context['parents'] = reports.utils.get_parents(self.object)
        context.update({
            'report': self.object, 'report_type': 'unsafe',
            'SelfAttrsData': self.object.attrs.order_by('id').values_list('id', 'name', 'value', 'data'),
            'MarkTable': UnsafeReportMarksTable(self.request.user, self.object, self.get_view(VIEW_TYPES[10])),
            'etv': etv, 'include_assumptions': self.request.user.assumptions, 'include_jquery_ui': True,
            'resources': reports.utils.report_resources(self.request.user, self.object)
        })
        return context


class ReportUnknownView(LoginRequiredMixin, LoggedCallMixin, Bview.DataViewMixin, DetailView):
    template_name = 'reports/ReportUnknown.html'
    model = ReportUnknown

    def get_context_data(self, **kwargs):
        if not JobAccess(self.request.user, self.object.root.job).can_view():
            raise BridgeException(code=400)
        context = super().get_context_data(**kwargs)
        context.update({
            'report': self.object, 'report_type': 'unknown',
            'resources': reports.utils.report_resources(self.request.user, self.object),
            'SelfAttrsData': self.object.attrs.order_by('id').values_list('id', 'name', 'value', 'data'),
            'main_content': ArchiveFileContent(
                self.object, 'problem_description', PROBLEM_DESC_FILE).content.decode('utf8'),
            'MarkTable': UnknownReportMarksTable(self.request.user, self.object, self.get_view(VIEW_TYPES[12]))
        })
        if self.object.root.job.weight == JOB_WEIGHT[0][0]:
            context['parents'] = reports.utils.get_parents(self.object)
        return context


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
            'include_assumptions': self.request.user.assumptions,
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


class ReportsComparisonView(LoginRequiredMixin, LoggedCallMixin, TemplateView):
    template_name = 'reports/comparison.html'

    def get_context_data(self, **kwargs):
        try:
            root1 = ReportRoot.objects.get(job_id=self.kwargs['job1_id'])
            root2 = ReportRoot.objects.get(job_id=self.kwargs['job2_id'])
        except ObjectDoesNotExist:
            raise BridgeException(code=406)
        if not JobAccess(self.request.user, job=root1.job) or not JobAccess(self.request.user, job=root2.job):
            raise BridgeException(code=401)
        return {
            'job1': root1.job, 'job2': root2.job,
            'data': ComparisonTableData(self.request.user, root1, root2)
        }


class ReportsComparisonDataView(LoginRequiredMixin, LoggedCallMixin, Bview.JSONResponseMixin, DetailView):
    template_name = 'reports/comparisonData.html'
    model = CompareJobsInfo
    pk_url_kwarg = 'info_id'

    def get_context_data(self, **kwargs):
        return {
            'data': ComparisonData(
                self.object, int(self.request.GET.get('page', 1)),
                self.request.GET.get('hide_attrs', 0), self.request.GET.get('hide_components', 0),
                self.request.GET.get('verdict'), self.request.GET.get('attrs')
            )
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


class ClearVerificationFiles(LoggedCallMixin, Bview.JsonDetailPostView):
    model = Job
    pk_url_kwarg = 'job_id'
    unparallel = [Report]

    def get_context_data(self, **kwargs):
        if not JobAccess(self.request.user, self.object).can_clear_verifications():
            raise BridgeException(_("You can't remove verification files of this job"))
        reports.utils.remove_verification_files(self.object)
        return {}
