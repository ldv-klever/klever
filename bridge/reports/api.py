from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.generics import RetrieveAPIView, get_object_or_404
from rest_framework.exceptions import NotFound, PermissionDenied, APIException
from rest_framework.response import Response

from bridge.utils import BridgeException
from bridge.access import ViewJobPermission
from tools.profiling import LoggedCallMixin

from jobs.utils import JobAccess
from reports.models import ReportRoot, CompareJobsInfo, ReportComponent
from reports.comparison import FillComparisonCache


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
