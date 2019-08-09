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
from rest_framework.generics import RetrieveAPIView, get_object_or_404, CreateAPIView, DestroyAPIView
from rest_framework.renderers import TemplateHTMLRenderer
from rest_framework.response import Response
from rest_framework.status import HTTP_403_FORBIDDEN
from rest_framework.views import APIView

from bridge.vars import JOB_STATUS
from bridge.utils import BridgeException, logger
from bridge.access import ServicePermission
from tools.profiling import LoggedCallMixin

from jobs.models import Job
from jobs.utils import JobAccess
from reports.models import Report, ReportRoot, CompareJobsInfo, OriginalSources, CoverageArchive
from reports.comparison import FillComparisonCache, ComparisonData
from reports.UploadReport import UploadReport, CheckArchiveError
from reports.serializers import OriginalSourcesSerializer
from reports.source import GetSource
from reports.utils import remove_verification_files
from reports.coverage import GetCoverageData


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
            try:
                FillComparisonCache(self.request.user, r1, r2)
            except BridgeException as e:
                raise exceptions.APIException(e.message)
        return Response({'url': reverse('reports:comparison', args=[r1.job_id, r2.job_id])})


class ReportsComparisonDataView(LoggedCallMixin, RetrieveAPIView):
    permission_classes = (IsAuthenticated,)
    queryset = CompareJobsInfo.objects.all()
    lookup_url_kwarg = 'info_id'

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            res = ComparisonData(
                instance, int(self.request.GET.get('page', 1)),
                self.request.GET.get('hide_attrs', 0), self.request.GET.get('hide_components', 0),
                self.request.GET.get('verdict'), self.request.GET.get('attrs')
            )
        except BridgeException as e:
            raise exceptions.APIException(e.message)
        template = loader.get_template('reports/comparisonData.html')
        return HttpResponse(template.render({'data': res}, request))


class HasOriginalSources(LoggedCallMixin, APIView):
    permission_classes = (ServicePermission,)

    def get(self, request):
        if 'identifier' not in request.GET:
            raise exceptions.APIException('Provide sources identifier in query parameters')
        return Response({
            'exists': OriginalSources.objects.filter(identifier=request.GET['identifier']).exists()
        })


class UploadOriginalSourcesView(LoggedCallMixin, CreateAPIView):
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


class GetSourceCodeView(LoggedCallMixin, APIView):
    renderer_classes = (TemplateHTMLRenderer,)
    permission_classes = (IsAuthenticated,)

    def get(self, request, report_id):
        report = get_object_or_404(Report.objects.only('id'), id=report_id)
        if 'file_name' not in request.GET:
            raise exceptions.APIException('File name was not provided')
        try:
            return Response({
                'data': GetSource(
                    request.user, report, request.GET['file_name'],
                    request.GET.get('coverage_id'), request.GET.get('with_legend')
                )
            }, template_name='reports/SourceCode.html')
        except BridgeException as e:
            logger.error(e)
            raise exceptions.APIException(str(e))


class ClearVerificationFilesView(LoggedCallMixin, DestroyAPIView):
    unparallel = [Report]
    permission_classes = (IsAuthenticated,)
    queryset = Job.objects.all()
    lookup_url_kwarg = 'job_id'

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if not JobAccess(request.user, obj).can_clear_verifications:
            self.permission_denied(request, message=_("You can't remove verification files of this job"))

    def perform_destroy(self, instance):
        remove_verification_files(instance)


class GetCoverageDataAPIView(LoggedCallMixin, APIView):
    renderer_classes = (TemplateHTMLRenderer,)
    permission_classes = (IsAuthenticated,)

    def get(self, request, cov_id):
        coverage = get_object_or_404(CoverageArchive.objects.only('id'), id=cov_id)
        if 'line' not in request.GET:
            raise exceptions.APIException('File line was not provided')
        if 'file_name' not in request.GET:
            raise exceptions.APIException('File name was not provided')
        try:
            res = GetCoverageData(coverage, request.GET['line'], request.GET['file_name'])
        except Exception as e:
            logger.eception(e)
            raise exceptions.APIException(str(e))
        if not res.data:
            logger.error('Coverage data was not found')
            raise exceptions.APIException('Coverage data was not found')
        return Response({'data': res.data}, template_name='reports/coverage/CoverageData.html')
