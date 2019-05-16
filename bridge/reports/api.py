import json

from django.http import HttpResponse
from django.template import loader
from django.urls import reverse
from django.utils.translation import ugettext as _

from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.generics import RetrieveAPIView, get_object_or_404, CreateAPIView, DestroyAPIView
from rest_framework.exceptions import PermissionDenied, APIException
from rest_framework.response import Response
from rest_framework.status import HTTP_403_FORBIDDEN

from bridge.vars import JOB_STATUS
from bridge.utils import BridgeException
from bridge.access import ServicePermission
from tools.profiling import LoggedCallMixin

from jobs.models import Job
from jobs.utils import JobAccess
from reports.models import Report, ReportRoot, CompareJobsInfo, OriginalSources, ReportUnsafe
from reports.comparison import FillComparisonCache, ComparisonData
from reports.UploadReport import UploadReport, CheckArchiveError
from reports.serializers import OriginalSourcesSerializer
from reports.etv import GetSource
from reports.utils import remove_verification_files


class FillComparisonView(LoggedCallMixin, APIView):
    unparallel = ['Job', 'ReportRoot', CompareJobsInfo]
    permission_classes = (IsAuthenticated,)

    def post(self, request, job1_id, job2_id):
        r1 = get_object_or_404(ReportRoot, job_id=job1_id)
        r2 = get_object_or_404(ReportRoot, job_id=job2_id)
        if not JobAccess(self.request.user, job=r1.job).can_view() \
                or not JobAccess(self.request.user, job=r2.job).can_view():
            raise PermissionDenied(_("You don't have an access to one of the selected jobs"))
        try:
            CompareJobsInfo.objects.get(user=self.request.user, root1=r1, root2=r2)
        except CompareJobsInfo.DoesNotExist:
            try:
                FillComparisonCache(self.request.user, r1, r2)
            except BridgeException as e:
                raise APIException(e.message)
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
            raise APIException(e.message)
        template = loader.get_template('reports/comparisonData.html')
        return HttpResponse(template.render({'data': res}, request))


class HasOriginalSources(LoggedCallMixin, APIView):
    permission_classes = (ServicePermission,)

    def get(self, request):
        if 'identifier' not in request.GET:
            raise APIException('Provide sources identifier in query parameters')
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
            raise APIException('Reports can be uploaded only for processing jobs')
        archives = dict((f.name, f) for f in request.FILES.getlist('file'))

        if 'report' in request.POST:
            data = [json.loads(request.POST['report'])]
        elif 'reports' in request.POST:
            data = json.loads(request.POST['reports'])
        else:
            raise APIException('Report json data is required')
        try:
            UploadReport(job, archives).upload_all(data)
        except CheckArchiveError as e:
            return Response({'ZIP error': str(e)}, status=HTTP_403_FORBIDDEN)
        return Response({})


class GetSourceCodeView(LoggedCallMixin, APIView):
    def get(self, request, unsafe_id):
        unsafe = get_object_or_404(ReportUnsafe.objects.only('id'), id=unsafe_id)
        if 'file_name' not in request.GET:
            raise APIException('File name was not provided')
        try:
            return HttpResponse(GetSource(unsafe, request.GET['file_name']).data)
        except BridgeException as e:
            raise APIException(str(e))


class ClearVerificationFilesView(LoggedCallMixin, DestroyAPIView):
    unparallel = [Report]
    permission_classes = (IsAuthenticated,)
    queryset = Job.objects.all()
    lookup_url_kwarg = 'job_id'

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if not JobAccess(request.user, obj).can_clear_verifications():
            self.permission_denied(request, message=_("You can't remove verification files of this job"))

    def perform_destroy(self, instance):
        remove_verification_files(instance)
