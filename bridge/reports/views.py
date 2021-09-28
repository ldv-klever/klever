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

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseRedirect
from django.template.defaulttags import register
from django.utils.translation import ugettext as _
from django.views.generic.base import TemplateView
from django.views.generic.detail import SingleObjectMixin, DetailView

from bridge.vars import VIEW_TYPES, ERROR_TRACE_FILE, PROBLEM_DESC_FILE, DECISION_WEIGHT
from bridge.utils import logger, ArchiveFileContent, BridgeException, BridgeErrorResponse
from bridge.CustomViews import DataViewMixin, StreamingResponseView
from tools.profiling import LoggedCallMixin

from jobs.models import Decision
from reports.models import (
    ReportComponent, ReportSafe, ReportUnknown, ReportUnsafe, ReportAttr, CoverageArchive, CompareDecisionsInfo,
    ReportImage
)

from jobs.utils import JobAccess
from jobs.ViewJobData import ViewReportData

from reports.comparison import ComparisonTableData, FillComparisonCache
from reports.coverage import (
    GetCoverageStatistics, LeafCoverageStatistics, CoverageGenerator,
    ReportCoverageStatistics, VerificationCoverageStatistics
)
from reports.etv import GetETV
from reports.utils import (
    report_resources, get_parents, report_attributes_with_parents, leaf_verifier_files_url,
    ReportStatus, ReportData, ReportAttrsTable, ReportChildrenTable, SafesTable, UnsafesTable, UnknownsTable,
    ComponentLogGenerator, AttrDataGenerator, VerifierFilesGenerator, ErrorTraceFileGenerator, ReportPNGGenerator
)

from marks.tables import SafeReportMarksTable, UnsafeReportMarksTable, UnknownReportMarksTable


@register.filter
def get_file_path(value, ind):
    if ind is None:
        return value[-1][1]
    return value[ind][1] if ind < len(value) else None


# These filters are used for visualization component specific data. They should not be used for any other purposes.
@register.filter
def get_dict_val(d, key):
    return d.get(key)


@register.filter
def sort_list(value):
    return sorted(value)


@register.filter
def sort_tests_list(value):
    return sorted(value, key=lambda test_result: test_result['test'].lstrip('1234567890'))


@register.filter
def sort_bugs_list(value):
    return sorted(value, key=lambda validation_result: validation_result['bug'][12:].lstrip('~'))


class ReportComponentView(LoginRequiredMixin, LoggedCallMixin, DataViewMixin, DetailView):
    template_name = 'reports/ReportMain.html'
    slug_field = 'identifier'
    slug_url_kwarg = 'identifier'

    def get_queryset(self):
        return ReportComponent.objects.select_related('decision', 'decision__operator')\
            .filter(decision__identifier=self.kwargs['decision'])

    def get_context_data(self, **kwargs):
        if not JobAccess(self.request.user, self.object.decision.job).can_view:
            raise BridgeException(code=400)
        if self.object.decision.weight == DECISION_WEIGHT[1][0]:
            raise BridgeException(_('Report pages for lightweight decisions are not available'))

        context = super().get_context_data(**kwargs)
        context.update({
            'report': self.object,
            'status': ReportStatus(self.object),
            'data': ReportData(self.object),
            'resources': report_resources(self.request.user, self.object),
            'SelfAttrsData': ReportAttrsTable(self.object),
            'parents': get_parents(self.object),
            'reportdata': ViewReportData(self.request.user, self.get_view(VIEW_TYPES[2]), self.object),
            'images': ReportImage.objects.filter(report_id=self.object.pk).only('id', 'title'),
            'TableData': ReportChildrenTable(
                self.request.user, self.object, self.get_view(VIEW_TYPES[3]),
                page=self.request.GET.get('page', 1)
            )
        })
        if self.object.verification:
            context['VerificationCoverage'] = VerificationCoverageStatistics(self.object)
        else:
            context['Coverage'] = ReportCoverageStatistics(self.object)
        return context


class ComponentLogView(LoginRequiredMixin, LoggedCallMixin, SingleObjectMixin, StreamingResponseView):
    model = ReportComponent
    pk_url_kwarg = 'report_id'

    def get_generator(self):
        instance = self.get_object()
        if not JobAccess(self.request.user, instance.decision.job).can_view:
            return BridgeErrorResponse(400)
        return ComponentLogGenerator(instance)


class AttrDataFileView(LoginRequiredMixin, LoggedCallMixin, SingleObjectMixin, StreamingResponseView):
    model = ReportAttr

    def get_generator(self):
        instance = self.get_object()
        if not JobAccess(self.request.user, instance.report.decision.job).can_view:
            return BridgeErrorResponse(400)
        return AttrDataGenerator(instance)


class DownloadVerifierFiles(LoginRequiredMixin, LoggedCallMixin, SingleObjectMixin, StreamingResponseView):
    model = ReportComponent

    def get_generator(self):
        instance = self.get_object()
        if not JobAccess(self.request.user, instance.decision.job).can_view:
            return BridgeErrorResponse(400)
        return VerifierFilesGenerator(instance)


class SafesListView(LoginRequiredMixin, LoggedCallMixin, DataViewMixin, DetailView):
    pk_url_kwarg = 'report_id'
    template_name = 'reports/report_list.html'

    def __init__(self, *args, **kwargs):
        self.object = None
        super().__init__(*args, **kwargs)

    def get_queryset(self):
        return ReportComponent.objects.select_related('decision', 'decision__operator')

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()

        # Check job access
        if not JobAccess(self.request.user, self.object.decision.job).can_view:
            raise BridgeException(code=400)

        # Get safes data
        safes_data = SafesTable(self.request.user, self.object, self.get_view(VIEW_TYPES[5]), self.request.GET)

        # Get context
        context = self.get_context_data(report=self.object)

        # Redirect if needed
        if hasattr(safes_data, 'redirect'):
            return HttpResponseRedirect(safes_data.redirect)

        context['TableData'] = safes_data
        return self.render_to_response(context)


class UnsafesListView(LoginRequiredMixin, LoggedCallMixin, DataViewMixin, DetailView):
    pk_url_kwarg = 'report_id'
    template_name = 'reports/report_list.html'

    def __init__(self, *args, **kwargs):
        self.object = None
        super().__init__(*args, **kwargs)

    def get_queryset(self):
        return ReportComponent.objects.select_related('decision', 'decision__operator')

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()

        # Check job access
        if not JobAccess(self.request.user, self.object.decision.job).can_view:
            raise BridgeException(code=400)

        # Get unsafes data
        unsafes_data = UnsafesTable(self.request.user, self.object, self.get_view(VIEW_TYPES[4]), self.request.GET)

        # Get context
        context = self.get_context_data(report=self.object)

        # Redirect if needed
        if hasattr(unsafes_data, 'redirect'):
            return HttpResponseRedirect(unsafes_data.redirect)

        context['TableData'] = unsafes_data
        return self.render_to_response(context)


class UnknownsListView(LoginRequiredMixin, LoggedCallMixin, DataViewMixin, DetailView):
    pk_url_kwarg = 'report_id'
    template_name = 'reports/report_list.html'

    def __init__(self, *args, **kwargs):
        self.object = None
        super().__init__(*args, **kwargs)

    def get_queryset(self):
        return ReportComponent.objects.select_related('decision', 'decision__operator')

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()

        # Check job access
        if not JobAccess(self.request.user, self.object.decision.job).can_view:
            raise BridgeException(code=400)

        # Get unknowns data
        unknowns_data = UnknownsTable(self.request.user, self.object, self.get_view(VIEW_TYPES[6]), self.request.GET)

        # Get context
        context = self.get_context_data(report=self.object)

        # Redirect if needed
        if hasattr(unknowns_data, 'redirect'):
            return HttpResponseRedirect(unknowns_data.redirect)

        context['TableData'] = unknowns_data
        return self.render_to_response(context)


class ReportSafeView(LoginRequiredMixin, LoggedCallMixin, DataViewMixin, DetailView):
    template_name = 'reports/ReportSafe.html'
    slug_field = 'identifier'
    slug_url_kwarg = 'identifier'

    def get_queryset(self):
        return ReportSafe.objects.select_related('decision', 'decision__operator')\
            .filter(decision__identifier=self.kwargs['decision'])

    def get_context_data(self, **kwargs):
        if not JobAccess(self.request.user, self.object.decision.job).can_view:
            raise BridgeException(code=400)

        context = super().get_context_data(**kwargs)
        if self.object.decision.weight == DECISION_WEIGHT[0][0]:
            context['parents'] = get_parents(self.object)
        context['verifier_files_url'] = leaf_verifier_files_url(self.object)
        context.update({
            'report': self.object, 'resources': report_resources(self.request.user, self.object),
            'SelfAttrsData': self.object.attrs.order_by('id'),
            'MarkTable': SafeReportMarksTable(self.request.user, self.object, self.get_view(VIEW_TYPES[11]))
        })

        # Get parent coverage if exists
        cov_obj = CoverageArchive.objects.filter(report_id=self.object.parent_id).first()
        if cov_obj:
            context['coverage'] = LeafCoverageStatistics(cov_obj)

        return context


class ReportUnsafeView(LoginRequiredMixin, LoggedCallMixin, DataViewMixin, DetailView):
    template_name = 'reports/ReportUnsafe.html'
    slug_url_kwarg = 'identifier'
    slug_field = 'identifier'

    def get_queryset(self):
        return ReportUnsafe.objects.select_related('decision', 'decision__operator')\
            .filter(decision__identifier=self.kwargs['decision'])

    def get_context_data(self, **kwargs):
        if not JobAccess(self.request.user, self.object.decision.job).can_view:
            raise BridgeException(code=400)
        try:
            etv = GetETV(ArchiveFileContent(self.object, 'error_trace', ERROR_TRACE_FILE).content.decode('utf8'),
                         self.request.user)
        except Exception as e:
            logger.exception(e)
            etv = None
        context = super().get_context_data(**kwargs)
        if self.object.decision.weight == DECISION_WEIGHT[0][0]:
            context['parents'] = get_parents(self.object)
        context['verifier_files_url'] = leaf_verifier_files_url(self.object)
        context.update({
            'include_jquery_ui': True, 'report': self.object, 'etv': etv,
            'SelfAttrsData': self.object.attrs.order_by('id'),
            'MarkTable': UnsafeReportMarksTable(self.request.user, self.object, self.get_view(VIEW_TYPES[10])),
            'resources': report_resources(self.request.user, self.object)
        })

        # Get parent coverage if exists and parent is verification report
        cov_obj = CoverageArchive.objects.filter(
            report_id=self.object.parent_id, report__verification=True
        ).first()
        if cov_obj:
            context['coverage'] = LeafCoverageStatistics(cov_obj)

        return context


class ReportUnknownView(LoginRequiredMixin, LoggedCallMixin, DataViewMixin, DetailView):
    template_name = 'reports/ReportUnknown.html'
    slug_url_kwarg = 'identifier'
    slug_field = 'identifier'

    def get_queryset(self):
        return ReportUnknown.objects.select_related('decision', 'decision__operator')\
            .filter(decision__identifier=self.kwargs['decision'])

    def get_context_data(self, **kwargs):
        if not JobAccess(self.request.user, self.object.decision.job).can_view:
            raise BridgeException(code=400)
        context = super().get_context_data(**kwargs)
        context.update({
            'report': self.object, 'resources': report_resources(self.request.user, self.object),
            'SelfAttrsData': self.object.attrs.order_by('id'),
            'main_content': ArchiveFileContent(
                self.object, 'problem_description', PROBLEM_DESC_FILE).content.decode('utf8'),
            'MarkTable': UnknownReportMarksTable(self.request.user, self.object, self.get_view(VIEW_TYPES[12]))
        })

        # Get parent coverage if exists and parent is verification report
        cov_obj = CoverageArchive.objects.filter(
            report_id=self.object.parent_id, report__verification=True
        ).first()
        if cov_obj:
            context['coverage'] = LeafCoverageStatistics(cov_obj)

        if self.object.decision.weight == DECISION_WEIGHT[0][0]:
            context['parents'] = get_parents(self.object)
        context['verifier_files_url'] = leaf_verifier_files_url(self.object)
        return context


class FullscreenReportUnsafe(LoginRequiredMixin, LoggedCallMixin, DetailView):
    template_name = 'reports/etv_fullscreen.html'
    slug_url_kwarg = 'identifier'
    slug_field = 'identifier'

    def get_queryset(self):
        return ReportUnsafe.objects.filter(decision__identifier=self.kwargs['decision']).select_related('decision')

    def get_context_data(self, **kwargs):
        if not JobAccess(self.request.user, self.object.decision.job).can_view:
            raise BridgeException(code=400)
        return {'report': self.object, 'include_jquery_ui': True, 'etv': GetETV(
            ArchiveFileContent(self.object, 'error_trace', ERROR_TRACE_FILE).content.decode('utf8'),
            self.request.user
        )}


class DownloadErrorTraceView(LoginRequiredMixin, LoggedCallMixin, SingleObjectMixin, StreamingResponseView):
    model = ReportUnsafe
    pk_url_kwarg = 'unsafe_id'

    def get_generator(self):
        return ErrorTraceFileGenerator(self.get_object())


class ReportsComparisonView(LoginRequiredMixin, LoggedCallMixin, TemplateView):
    template_name = 'reports/comparison.html'

    def get_context_data(self, **kwargs):
        try:
            decision1 = Decision.objects.select_related('job').get(id=self.kwargs['decision1'])
            decision2 = Decision.objects.select_related('job').get(id=self.kwargs['decision2'])
        except Decision.DoesNotExist:
            raise BridgeException(_("One of the selected decisions wasn't found"))
        if not JobAccess(self.request.user, job=decision1.job).can_view\
                or not JobAccess(self.request.user, job=decision2.job).can_view:
            raise BridgeException(code=401)
        return {
            'decision1': decision1, 'decision2': decision2,
            'data': ComparisonTableData(decision1, decision2)
        }


class ReportsComparisonUUIDView(LoginRequiredMixin, LoggedCallMixin, TemplateView):
    unparallel = ['Decision', CompareDecisionsInfo]
    template_name = 'reports/comparison.html'

    def get_context_data(self, **kwargs):
        # Get decisions
        try:
            decision1 = Decision.objects.select_related('job').get(identifier=self.kwargs['decision1'])
            decision2 = Decision.objects.select_related('job').get(identifier=self.kwargs['decision2'])
        except Decision.DoesNotExist:
            raise BridgeException(_("One of the selected decisions wasn't found"))

        # Check jobs access
        if not JobAccess(self.request.user, job=decision1.job).can_view\
                or not JobAccess(self.request.user, job=decision2.job).can_view:
            raise BridgeException(code=401)

        # Get or create comparison cache
        try:
            comparison_info = CompareDecisionsInfo.objects.get(decision1=decision1, decision2=decision2)
        except CompareDecisionsInfo.DoesNotExist:
            obj = FillComparisonCache(self.request.user, decision1, decision2)
            comparison_info = obj.info

        return {
            'decision1': decision1, 'decision2': decision2,
            'data': ComparisonTableData(decision1, decision2, comparison_info=comparison_info)
        }


class CoverageView(LoginRequiredMixin, LoggedCallMixin, DetailView):
    template_name = 'reports/coverage/coverage.html'
    model = ReportComponent
    pk_url_kwarg = 'report_id'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['coverage_id'] = self.request.GET.get('coverage_id')
        context['SelfAttrsData'] = report_attributes_with_parents(self.object)
        context['decision'] = Decision.objects.only('id', 'start_date', 'title', 'weight')\
            .get(id=self.object.decision_id)
        if context['decision'].weight == DECISION_WEIGHT[0][0]:
            context['parents'] = get_parents(self.object, include_self=True)
        context['statistics'] = GetCoverageStatistics(self.object, context['coverage_id'])
        return context


class DownloadCoverageView(LoginRequiredMixin, LoggedCallMixin, SingleObjectMixin, StreamingResponseView):
    model = CoverageArchive

    def get_generator(self):
        return CoverageGenerator(self.get_object())


class TestD3(TemplateView):
    template_name = 'reports/d3test.html'


class DownloadReportPNGView(LoginRequiredMixin, LoggedCallMixin, SingleObjectMixin, StreamingResponseView):
    model = ReportImage

    def get_generator(self):
        return ReportPNGGenerator(self.get_object())
