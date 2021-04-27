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

from rest_framework import exceptions
from rest_framework.generics import (
    get_object_or_404, RetrieveAPIView, CreateAPIView, RetrieveDestroyAPIView, RetrieveUpdateAPIView
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from bridge.vars import TASK_STATUS, DECISION_STATUS
from bridge.access import ServicePermission
from bridge.CustomViews import StreamingResponseAPIView
from tools.profiling import LoggedCallMixin

from users.models import SchedulerUser
from jobs.models import Decision, Scheduler
from service.models import Task, Solution, VerificationTool, NodesConfiguration

from jobs.serializers import decision_status_changed
from service.serializers import (
    TaskSerializer, SolutionSerializer, SchedulerUserSerializer, DecisionSerializer,
    UpdateToolsSerializer, SchedulerSerializer, NodeConfSerializer
)
from service.utils import FinishDecision, TaskArchiveGenerator, SolutionArchiveGenerator, ReadDecisionConfiguration


class TaskAPIViewset(LoggedCallMixin, ModelViewSet):
    queryset = Task.objects.select_related('decision').all()
    serializer_class = TaskSerializer
    permission_classes = (ServicePermission,)

    def get_unparallel(self, request):
        if request.method != 'GET':
            return [Decision]
        return []

    def get_serializer(self, *args, **kwargs):
        fields = None
        if self.request.method == 'GET':
            fields = self.request.query_params.getlist('fields')
        elif self.request.method == 'POST':
            fields = {'id', 'job', 'archive', 'description'}
        elif self.request.method in {'PUT', 'PATCH'}:
            fields = {'id', 'status', 'error'}
        return super().get_serializer(*args, fields=fields, **kwargs)

    def filter_queryset(self, queryset):
        if 'job' in self.request.query_params:
            return queryset.filter(decision__identifier=self.request.query_params['job'])
        return super().filter_queryset(queryset)

    def perform_destroy(self, instance):
        if instance.status not in {TASK_STATUS[2][0], TASK_STATUS[3][0], TASK_STATUS[4][0]}:
            raise exceptions.ValidationError({'status': 'The task is not finished'})
        if instance.status == TASK_STATUS[2][0]:
            if not Solution.objects.filter(task=instance).exists():
                raise exceptions.ValidationError({'solution': 'The task solution was not uploaded'})
        instance.delete()


class DownloadTaskArchiveView(StreamingResponseAPIView):
    permission_classes = (ServicePermission,)

    def get_generator(self):
        task = get_object_or_404(Task, pk=self.kwargs['pk'])
        if Decision.objects.only('status').get(id=task.decision_id).status != DECISION_STATUS[2][0]:
            raise exceptions.APIException('The decision is not processing')
        if task.status not in {TASK_STATUS[0][0], TASK_STATUS[1][0]}:
            raise exceptions.APIException('The task status is {}'.format(task.status))
        return TaskArchiveGenerator(task)


class SolutionCreateView(LoggedCallMixin, CreateAPIView):
    serializer_class = SolutionSerializer
    permission_classes = (ServicePermission,)


class SolutionDetailView(LoggedCallMixin, RetrieveDestroyAPIView):
    serializer_class = SolutionSerializer
    permission_classes = (ServicePermission,)
    queryset = Solution.objects.all()
    lookup_field = 'task_id'

    def get_serializer(self, *args, **kwargs):
        return super().get_serializer(*args, fields=self.request.query_params.getlist('fields'), **kwargs)


class SolutionDownloadView(LoggedCallMixin, StreamingResponseAPIView):
    permission_classes = (ServicePermission,)

    def get_generator(self):
        solution = get_object_or_404(Solution.objects.select_related('task'), task_id=self.kwargs['task_id'])
        if Decision.objects.only('status').get(id=solution.decision_id).status != DECISION_STATUS[2][0]:
            raise exceptions.ValidationError('The decision is not processing')
        if solution.task.status != TASK_STATUS[2][0]:
            raise exceptions.ValidationError('The task is not finished')
        return SolutionArchiveGenerator(solution)


class AddSchedulerUserView(LoggedCallMixin, CreateAPIView):
    serializer_class = SchedulerUserSerializer
    permission_classes = (IsAuthenticated,)


class SchedulerUserView(LoggedCallMixin, RetrieveAPIView):
    serializer_class = SchedulerUserSerializer
    permission_classes = (ServicePermission,)

    def get_object(self):
        return SchedulerUser.objects.filter(user__decisions__identifier=self.kwargs['decision_uuid']).first()


class DecisionStatusAPIView(LoggedCallMixin, APIView):
    permission_classes = (ServicePermission,)

    def get(self, request, **kwargs):
        decision = get_object_or_404(Decision.objects.only('status'), **kwargs)
        return Response({'status': decision.status})

    def patch(self, request, **kwargs):
        decision = get_object_or_404(Decision, **kwargs)
        if 'status' not in request.data:
            raise exceptions.ValidationError('Status is required')
        if request.data['status'] == DECISION_STATUS[7][0]:
            if decision.status != DECISION_STATUS[6][0]:
                raise exceptions.ValidationError("The decision status is not cancelling")
            decision.status = DECISION_STATUS[7][0]
            decision.save()
            decision_status_changed(decision)
        elif request.data['status'] == DECISION_STATUS[3][0]:
            res = FinishDecision(decision, DECISION_STATUS[3][0])
            if res.error:
                raise exceptions.ValidationError({'job': res.error})
            return Response({})
        elif request.data['status'] == DECISION_STATUS[4][0]:
            FinishDecision(decision, DECISION_STATUS[4][0], request.data.get('error'))
            return Response({})
        else:
            raise exceptions.APIException('Unsupported decision status: {}'.format(request.data['status']))
        return Response({})


class DecisionProgressAPIView(LoggedCallMixin, RetrieveUpdateAPIView):
    unparallel = [Decision]
    permission_classes = (ServicePermission,)
    serializer_class = DecisionSerializer
    queryset = Decision.objects
    lookup_field = 'identifier'

    def perform_update(self, serializer):
        if serializer.instance.status != DECISION_STATUS[2][0]:
            raise exceptions.ValidationError('The decision is not solving')
        serializer.save()


class DecisionConfigurationAPIView(LoggedCallMixin, APIView):
    permission_classes = (ServicePermission,)

    def get(self, request, identifier):
        decision = get_object_or_404(
            Decision.objects.select_related('scheduler', 'configuration'), identifier=identifier
        )
        res = ReadDecisionConfiguration(decision)
        return Response(res.data)


class UpdateToolsAPIView(LoggedCallMixin, CreateAPIView):
    unparallel = [VerificationTool]
    serializer_class = UpdateToolsSerializer
    permission_classes = (ServicePermission,)


class SchedulerAPIView(LoggedCallMixin, RetrieveUpdateAPIView):
    unparallel = [Scheduler, Decision]
    permission_classes = (ServicePermission,)
    serializer_class = SchedulerSerializer
    queryset = Scheduler.objects.all()
    lookup_url_kwarg = 'type'
    lookup_field = 'type'


class UpdateNodes(LoggedCallMixin, APIView):
    permission_classes = (ServicePermission,)

    def post(self, request):
        serializer = NodeConfSerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        NodesConfiguration.objects.all().delete()
        serializer.save()
        return Response({})
