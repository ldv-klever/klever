import mimetypes

from rest_framework.views import APIView
from rest_framework.generics import (
    CreateAPIView, UpdateAPIView, RetrieveAPIView, DestroyAPIView,
    RetrieveDestroyAPIView, RetrieveUpdateAPIView,
    get_object_or_404
)
from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import exceptions

from bridge.vars import JOB_STATUS, TASK_STATUS
from bridge.access import ServicePermission
from bridge.CustomViews import StreamingResponseAPIView
from users.models import SchedulerUser
from jobs.models import Job
from jobs.serializers import change_job_status
from jobs.utils import JobAccess
from tools.profiling import LoggedCallMixin
from service.models import Decision, Task, Solution, VerificationTool, Scheduler, NodesConfiguration
from service.serializers import (
    TaskSerializer, SolutionSerializer, SchedulerUserSerializer, DecisionSerializer,
    UpdateToolsSerializer, SchedulerSerializer, NodeConfSerializer
)
from service.utils import FinishJobDecision, TaskArchiveGenerator, SolutionArchiveGenerator


class TaskAPIViewset(LoggedCallMixin, ModelViewSet):
    queryset = Task.objects.select_related('decision').all()
    serializer_class = TaskSerializer
    permission_classes = (ServicePermission,)

    def get_unparallel(self, request):
        if request.method != 'GET':
            return [Decision]
        return []

    def create(self, request, *args, **kwargs):
        response = super(TaskAPIViewset, self).create(request, *args, **kwargs)
        # Return only id
        response.data = {'id': response.data['id']}
        return response

    def perform_update(self, serializer):
        instance = serializer.save()
        if instance.status == TASK_STATUS[4][0]:
            instance.delete()

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        response.data = {}
        return response

    def filter_queryset(self, queryset):
        if 'job' in self.request.query_params:
            return queryset.filter(decision__job__identifier=self.request.query_params['job'])
        return super().filter_queryset(queryset)

    def perform_destroy(self, instance):
        assert isinstance(instance, Task)
        job = Job.objects.only('status').get(decision=instance.decision)
        if job.status != JOB_STATUS[2][0]:
            raise exceptions.ValidationError({'job': 'The job is not processing'})
        if instance.status not in {TASK_STATUS[2][0], TASK_STATUS[3][0]}:
            raise exceptions.ValidationError({'status': 'The task is not finished'})
        if instance.status == TASK_STATUS[2][0]:
            if not Solution.objects.filter(task=instance).exists():
                raise exceptions.ValidationError({'solution': 'The task solution was not uplaoded'})
        instance.delete()


class DownloadTaskArchiveView(StreamingResponseAPIView):
    permission_classes = (ServicePermission,)

    def get_generator(self):
        task = get_object_or_404(Task, pk=self.kwargs['pk'])
        if Job.objects.only('status').get(decision=task.decision).status != JOB_STATUS[2][0]:
            raise exceptions.ValidationError('The job is not processing')
        if task.status not in {TASK_STATUS[0][0], TASK_STATUS[1][0]}:
            raise exceptions.ValidationError('The task status is {}'.format(task.status))
        return TaskArchiveGenerator(task)


class SolutionCreateView(LoggedCallMixin, CreateAPIView):
    unparallel = [Decision]
    serializer_class = SolutionSerializer
    permission_classes = (ServicePermission,)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        response.data = {}
        return response


class SolutionDetailView(LoggedCallMixin, RetrieveDestroyAPIView):
    serializer_class = SolutionSerializer
    permission_classes = (ServicePermission,)
    queryset = Solution.objects.all()
    lookup_url_kwarg = 'task_id'
    lookup_field = 'task_id'


class SolutionDownloadView(LoggedCallMixin, StreamingResponseAPIView):
    def get_generator(self):
        solution = get_object_or_404(Solution.objects.select_related('task'), task_id=self.kwargs['task_id'])
        if Job.objects.only('status').get(decision=solution.decision).status != JOB_STATUS[2][0]:
            raise exceptions.ValidationError('The job is not processing')
        if solution.task.status != TASK_STATUS[2][0]:
            raise exceptions.ValidationError('The task is not finished')
        return SolutionArchiveGenerator(solution)


class AddSchedulerUserView(LoggedCallMixin, CreateAPIView):
    # queryset = SchedulerUser.objects.all()
    serializer_class = SchedulerUserSerializer
    permission_classes = (IsAuthenticated,)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class ChangeJobStatusView(LoggedCallMixin, APIView):
    permission_classes = (ServicePermission,)

    def get(self, request, job_uuid):
        job = get_object_or_404(Job.objects.only('status'), identifier=job_uuid)
        return Response({'status': job.status})

    def patch(self, request, job_uuid):
        job = get_object_or_404(Job, identifier=job_uuid)
        if 'status' not in request.data:
            raise exceptions.ValidationError('Status is required')
        if request.data['status'] == JOB_STATUS[7][0]:
            if job.status != JOB_STATUS[6][0]:
                raise exceptions.ValidationError("The job status is not cancelling")
            change_job_status(job, JOB_STATUS[7][0])
        elif request.data['status'] == JOB_STATUS[3][0]:
            res = FinishJobDecision(job, JOB_STATUS[3][0])
            if res.error:
                raise exceptions.ValidationError({'job': res.error})
            return Response({})
        elif request.data['status'] == JOB_STATUS[4][0]:
            res = FinishJobDecision(job, JOB_STATUS[4][0], request.data.get('error'))
            if res.error:
                raise exceptions.ValidationError({'job': res.error})
            return Response({})
        else:
            raise exceptions.APIException('Unsupported job status: {}'.format(request.data['status']))
        return Response({})


class JobProgressAPIView(LoggedCallMixin, RetrieveUpdateAPIView):
    unparallel = [Job]
    permission_classes = (ServicePermission,)
    serializer_class = DecisionSerializer
    queryset = Decision.objects.select_related('job')
    lookup_url_kwarg = 'job_uuid'
    lookup_field = 'job__identifier'

    def perform_update(self, serializer):
        if serializer.instance.job.status != JOB_STATUS[2][0]:
            raise exceptions.ValidationError('The job is not solving')
        serializer.save()

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()

        return Response({
            'status': instance.job.status,
            'subjobs': {
                'total': instance.total_sj, 'failed': instance.failed_sj, 'solved': instance.solved_sj,
                'expected_time': instance.expected_time_sj, 'gag_text': instance.gag_text_sj,
                'start': instance.start_sj.timestamp() if instance.start_sj else None,
                'finish': instance.finish_sj.timestamp() if instance.finish_sj else None
            },
            'tasks': {
                'total': instance.total_ts, 'failed': instance.failed_ts, 'solved': instance.solved_ts,
                'expected_time': instance.expected_time_ts, 'gag_text': instance.gag_text_ts,
                'start': instance.start_ts.timestamp() if instance.start_ts else None,
                'finish': instance.finish_ts.timestamp() if instance.finish_ts else None
            },
            'start_date': instance.start_date.timestamp() if instance.start_date else None,
            'finish_date': instance.finish_date.timestamp() if instance.finish_date else None
        })


class UpdateToolsAPIView(LoggedCallMixin, CreateAPIView):
    unparallel = [VerificationTool]
    serializer_class = UpdateToolsSerializer
    permission_classes = (ServicePermission,)


class SchedulerAPIView(LoggedCallMixin, RetrieveUpdateAPIView):
    unparallel = [Scheduler, Job]
    permission_classes = (ServicePermission,)
    serializer_class = SchedulerSerializer
    queryset = Scheduler.objects.all()
    lookup_url_kwarg = 'type'
    lookup_field = 'type'


class UpdateNodes(LoggedCallMixin, APIView):
    def post(self, request):
        serializer = NodeConfSerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        NodesConfiguration.objects.all().delete()
        serializer.save()
        return Response({})
