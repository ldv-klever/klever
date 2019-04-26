import json

from django.http import HttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.generics import RetrieveAPIView, get_object_or_404, CreateAPIView
from rest_framework.exceptions import NotFound, PermissionDenied, APIException
from rest_framework.response import Response
from rest_framework.status import HTTP_403_FORBIDDEN

from bridge.vars import JOB_STATUS
from bridge.utils import BridgeException
from bridge.access import ViewJobPermission, ServicePermission
from tools.profiling import LoggedCallMixin

from jobs.models import Job
from jobs.utils import JobAccess
from reports.models import ReportRoot, CompareJobsInfo, ReportComponent, OriginalSources, ReportUnsafe
from reports.comparison import FillComparisonCache
from reports.UploadReport import UploadReport, CheckArchiveError
from reports.serializers import OriginalSourcesSerializer
from reports.etv import GetSource


class FillComparisonView(LoggedCallMixin, APIView):
    unparallel = ['Job', 'ReportRoot', CompareJobsInfo]
    permission_classes = (IsAuthenticated,)

    def post(self, *args, **kwargs):
        r1 = get_object_or_404(ReportRoot, job_id=self.kwargs['job1_id'])
        r2 = get_object_or_404(ReportRoot, job_id=self.kwargs['job2_id'])
        if not JobAccess(self.request.user, job=r1.job) or not JobAccess(self.request.user, job=r2.job):
            raise PermissionDenied()
        try:
            CompareJobsInfo.objects.get(user=self.request.user, root1=r1, root2=r2)
        except CompareJobsInfo.DoesNotExist:
            try:
                FillComparisonCache(self.request.user, r1, r2)
            except BridgeException as e:
                raise APIException(e.message)
        return Response({})


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

    # def dispatch(self, request, *args, **kwargs):
    #     with override(settings.DEFAULT_LANGUAGE):
    #         return super().dispatch(request, *args, **kwargs)

    def post(self, request, job_uuid):
        job = get_object_or_404(Job, identifier=job_uuid)
        if job.status != JOB_STATUS[2][0]:
            print(job.get_status_display())
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
