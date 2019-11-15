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

import json

from django.http import HttpResponse
from django.template import loader
from django.urls import reverse
from django.utils.translation import ugettext as _

from rest_framework.permissions import IsAuthenticated

from rest_framework import exceptions
from rest_framework.generics import RetrieveAPIView, get_object_or_404, CreateAPIView, DestroyAPIView, GenericAPIView
from rest_framework.response import Response
from rest_framework.status import HTTP_403_FORBIDDEN
from rest_framework.views import APIView

from bridge.vars import JOB_STATUS, LOG_FILE
from bridge.utils import logger, BridgeException, ArchiveFileContent
from bridge.access import ServicePermission, ViewJobPermission
from bridge.CustomViews import TemplateAPIRetrieveView
from tools.profiling import LoggedCallMixin

from jobs.models import Job
from jobs.utils import JobAccess
from reports.models import (
    Report, ReportRoot, ReportComponent, CompareJobsInfo, OriginalSources, CoverageArchive, ReportAttr
)
from reports.comparison import FillComparisonCache, ComparisonData
from reports.UploadReport import UploadReport, CheckArchiveError
from reports.serializers import OriginalSourcesSerializer
from reports.source import GetSource
from reports.utils import remove_verifier_files
from reports.coverage import GetCoverageData, ReportCoverageStatistics


class FillComparisonView(LoggedCallMixin, APIView):
    unparallel = ['Job', 'ReportRoot', CompareJobsInfo]
    permission_classes = (IsAuthenticated,)

    def post(self, request, job1_id, job2_id):
        r1 = ReportRoot.objects.filter(job_id=job1_id).first()
        r2 = ReportRoot.objects.filter(job_id=job2_id).first()
        if not r1 or not r2:
            raise exceptions.APIException(_('One of the jobs is not decided yet'))
        if not JobAccess(self.request.user, job=r1.job).can_view \
                or not JobAccess(self.request.user, job=r2.job).can_view:
            raise exceptions.PermissionDenied(_("You don't have an access to one of the selected jobs"))
        try:
            CompareJobsInfo.objects.get(user=self.request.user, root1=r1, root2=r2)
        except CompareJobsInfo.DoesNotExist:
            FillComparisonCache(self.request.user, r1, r2)
        return Response({'url': reverse('reports:comparison', args=[r1.job_id, r2.job_id])})


class ReportsComparisonDataView(LoggedCallMixin, RetrieveAPIView):
    permission_classes = (IsAuthenticated,)
    queryset = CompareJobsInfo.objects.all()
    lookup_url_kwarg = 'info_id'

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        res = ComparisonData(
            instance, int(self.request.GET.get('page', 1)),
            self.request.GET.get('hide_attrs', 0), self.request.GET.get('hide_components', 0),
            self.request.GET.get('verdict'), self.request.GET.get('attrs')
        )
        template = loader.get_template('reports/comparisonData.html')
        return HttpResponse(template.render({'data': res}, request))


class HasOriginalSources(LoggedCallMixin, APIView):
    unparallel = ['OriginalSources']
    permission_classes = (ServicePermission,)

    def get(self, request):
        if 'identifier' not in request.GET:
            raise exceptions.APIException('Provide sources identifier in query parameters')
        return Response({
            'exists': OriginalSources.objects.filter(identifier=request.GET['identifier']).exists()
        })


class UploadOriginalSourcesView(LoggedCallMixin, CreateAPIView):
    unparallel = ['OriginalSources']
    queryset = OriginalSources
    serializer_class = OriginalSourcesSerializer
    permission_classes = (ServicePermission,)


class UploadReportView(LoggedCallMixin, APIView):
    unparallel = [ReportRoot]
    permission_classes = (ServicePermission,)

    def post(self, request, job_uuid):
        job = get_object_or_404(Job, identifier=job_uuid)
        if job.status != JOB_STATUS[2][0]:
            raise exceptions.APIException('Reports can be uploaded only for processing jobs')

        if 'report' in request.POST:
            data = [json.loads(request.POST['report'])]
        elif 'reports' in request.POST:
            data = json.loads(request.POST['reports'])
        else:
            raise exceptions.APIException('Report json data is required')
        try:
            UploadReport(job, request.FILES).upload_all(data)
        except CheckArchiveError as e:
            return Response({'ZIP error': str(e)}, status=HTTP_403_FORBIDDEN)
        return Response({})


class GetSourceCodeView(LoggedCallMixin, TemplateAPIRetrieveView):
    template_name = 'reports/SourceCode.html'
    permission_classes = (IsAuthenticated,)
    queryset = Report.objects.only('id')
    lookup_url_kwarg = 'report_id'

    def get_context_data(self, instance, **kwargs):
        if 'file_name' not in self.request.query_params:
            raise exceptions.APIException('File name was not provided')
        context = super().get_context_data(instance, **kwargs)
        context['data'] = GetSource(
            self.request.user, instance, self.request.query_params['file_name'],
            self.request.query_params.get('coverage_id'), self.request.query_params.get('with_legend')
        )
        return context


class ClearVerificationFilesView(LoggedCallMixin, DestroyAPIView):
    unparallel = [Report]
    permission_classes = (IsAuthenticated,)
    queryset = Job.objects.all()
    lookup_url_kwarg = 'job_id'

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if not JobAccess(request.user, obj).can_clear_verifier_files:
            self.permission_denied(request, message=_("You can't clear verifier input files of this job"))

    def perform_destroy(self, instance):
        remove_verifier_files(instance)


class GetCoverageDataAPIView(LoggedCallMixin, TemplateAPIRetrieveView):
    template_name = 'reports/coverage/CoverageData.html'
    permission_classes = (IsAuthenticated,)
    queryset = CoverageArchive.objects.only('id')
    lookup_url_kwarg = 'cov_id'

    def get_context_data(self, instance, **kwargs):
        if 'line' not in self.request.GET:
            raise exceptions.APIException('File line was not provided')
        if 'file_name' not in self.request.GET:
            raise exceptions.APIException('File name was not provided')

        context = super().get_context_data(instance, **kwargs)
        context['data'] = GetCoverageData(
            instance, self.request.query_params['line'], self.request.query_params['file_name']
        ).data
        if not context['data']:
            logger.error('Coverage data was not found')
            raise exceptions.APIException('Coverage data was not found')
        return context


class GetReportCoverageTableView(LoggedCallMixin, TemplateAPIRetrieveView):
    permission_classes = (ViewJobPermission,)
    queryset = ReportComponent.objects.select_related('root', 'root__job')
    template_name = 'jobs/viewJob/coverageTable.html'
    lookup_url_kwarg = 'report_id'

    def get_context_data(self, instance, **kwargs):
        context = super().get_context_data(instance, **kwargs)
        context['statistics'] = ReportCoverageStatistics(
            instance, self.request.query_params.get('coverage_id')
        ).statistics
        return context


class AttrDataContentView(LoggedCallMixin, GenericAPIView):
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return ReportAttr.objects.select_related('data', 'report', 'report__root', 'report__root__job')

    def get(self, request, pk):
        assert pk
        instance = self.get_object()
        if not JobAccess(self.request.user, instance.report.root.job).can_view:
            raise exceptions.PermissionDenied(_("You don't have an access to the job"))
        if not instance.data:
            raise BridgeException(_("The attribute doesn't have data"))

        content = instance.data.file.read()
        if len(content) > 10 ** 5:
            content = str(_('The attribute data is huge and can not be shown but you can download it'))
        else:
            content = content.decode('utf8')
        return HttpResponse(content)


class ComponentLogContentView(LoggedCallMixin, GenericAPIView):
    permission_classes = (ViewJobPermission,)
    lookup_url_kwarg = 'report_id'

    def get_queryset(self):
        return ReportComponent.objects.select_related('root', 'root__job')

    def get(self, request, report_id):
        assert report_id
        report = self.get_object()
        if not report.log:
            raise BridgeException(_("The component doesn't have log"))

        content = ArchiveFileContent(report, 'log', LOG_FILE).content
        if len(content) > 10 ** 5:
            content = str(_('The component log is huge and can not be shown but you can download it'))
        else:
            content = content.decode('utf8')
        return HttpResponse(content)
