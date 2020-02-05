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

import json
import mimetypes

from difflib import unified_diff

from django.db import transaction
from django.http.response import HttpResponse, StreamingHttpResponse
from django.urls import reverse
from django.utils.translation import ugettext as _

from rest_framework import exceptions
from rest_framework.authentication import SessionAuthentication
from rest_framework.generics import (
    get_object_or_404, GenericAPIView, RetrieveAPIView, ListAPIView, CreateAPIView, UpdateAPIView, DestroyAPIView
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from bridge.access import (
    ViewJobPermission, DestroyJobPermission, ServicePermission, CreateJobPermission, UpdateJobPermission
)
from bridge.vars import PRESET_JOB_TYPE, DECISION_STATUS
from bridge.CustomViews import TemplateAPIRetrieveView, TemplateAPIListView, StreamingResponseAPIView
from tools.profiling import LoggedCallMixin

from jobs.models import Job, JobFile, FileSystem, UploadedJobArchive, PresetJob, PresetFile, Decision
from jobs.serializers import (
    decision_status_changed, PresetJobDirSerializer, JobFileSerializer,
    CreateJobSerializer, UpdateJobSerializer, DecisionStatusSerializerRO
)
from jobs.configuration import get_configuration_value, GetConfiguration
from jobs.Download import KleverCoreArchiveGen, UploadJobsScheduler, JobArchiveGenerator, get_jobs_to_download
from jobs.utils import JobAccess, DecisionAccess, get_unique_name, copy_files_with_replace
from reports.serializers import DecisionResultsSerializerRO
from reports.coverage import DecisionCoverageStatistics
from reports.UploadReport import collapse_reports
from service.utils import StartJobDecision, RestartJobDecision, cancel_decision


class PresetJobAPIViewset(LoggedCallMixin, ModelViewSet):
    permission_classes = (IsAuthenticated,)
    authentication_classes = (SessionAuthentication,)
    queryset = PresetJob.objects.filter(type=PRESET_JOB_TYPE[2][0])
    serializer_class = PresetJobDirSerializer

    def get_serializer(self, *args, **kwargs):
        fields = None
        if self.request.method == 'GET':
            fields = self.request.query_params.getlist('fields')
        elif self.request.method == 'POST':
            fields = {'parent', 'name'}
        elif self.request.method in {'PUT', 'PATCH'}:
            fields = {'name'}
        return super().get_serializer(*args, fields=fields, **kwargs)


class CreateJobView(LoggedCallMixin, CreateAPIView):
    unparallel = [Job]
    queryset = Job.objects.all()
    serializer_class = CreateJobSerializer
    permission_classes = (CreateJobPermission,)


class UpdateJobView(LoggedCallMixin, UpdateAPIView):
    unparallel = [Job]
    queryset = Job.objects.all()
    serializer_class = UpdateJobSerializer
    permission_classes = (UpdateJobPermission,)


class GetConfigurationView(LoggedCallMixin, APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        conf_kwargs = {}
        if 'file_conf' in self.request.FILES:
            conf_kwargs = {'file_conf': request.FILES['file_conf']}
        elif 'decision' in self.request.data:
            decision = get_object_or_404(
                Decision.objects.select_related('configuration'),
                pk=self.request.data['decision']
            )
            conf_kwargs = {'file_conf': decision.configuration.file}
        elif 'conf_name' in self.request.data:
            conf_kwargs = {'conf_name': request.data['conf_name']}
        return Response(GetConfiguration(**conf_kwargs).configuration)


class StartJobDefValueView(LoggedCallMixin, APIView):
    def post(self, request):
        return Response(get_configuration_value(request.data['name'], request.data['value']))


class StartDecisionView(LoggedCallMixin, APIView):
    permission_classes = (IsAuthenticated,)

    def get_job(self, **kwargs):
        job = get_object_or_404(Job, **kwargs)
        if not JobAccess(self.request.user, job).can_decide:
            raise exceptions.PermissionDenied(_("You don't have an access to start decision of this job"))
        return job

    def get_configuration(self):
        if 'file_conf' in self.request.FILES:
            return GetConfiguration(file_conf=self.request.FILES['file_conf']).for_json()
        elif 'data' in self.request.data:
            return GetConfiguration(user_conf=json.loads(self.request.data['data'])).for_json()
        return GetConfiguration().for_json()

    def post(self, request, **kwargs):
        job = self.get_job(**kwargs)
        res = StartJobDecision(request.user, job, self.get_configuration(), self.request.data.get('name'))
        return Response({'url': reverse('jobs:decision', args=[res.decision.id])})


class DecisionStatusListView(ListAPIView):
    queryset = Decision.objects.select_related('scheduler')
    serializer_class = DecisionStatusSerializerRO
    permission_classes = (IsAuthenticated,)


class DecisionStatusView(RetrieveAPIView):
    queryset = Decision.objects.select_related('scheduler')
    serializer_class = DecisionStatusSerializerRO
    permission_classes = (IsAuthenticated,)


class CreatePresetJobView(LoggedCallMixin, CreateAPIView):
    permission_classes = (CreateJobPermission,)
    queryset = PresetJob.objects
    lookup_field = 'identifier'
    lookup_url_kwarg = 'identifier'

    def create(self, request, *args, **kwargs):
        preset_job = self.get_object()
        job = Job.objects.create(preset=preset_job, author=request.user, name=get_unique_name(preset_job.name))

        # Copy files from preset job
        preset_files_qs = PresetFile.objects.filter(preset=preset_job).values_list('file_id', 'name')
        copy_files_with_replace(request, job.id, preset_files_qs)

        return Response({'id': job.id, 'identifier': str(job.identifier)})


class DuplicateJobView(LoggedCallMixin, GenericAPIView):
    permission_classes = (CreateJobPermission, ViewJobPermission)
    queryset = Job.objects
    lookup_field = 'identifier'
    lookup_url_kwarg = 'identifier'

    def post(self, request, *args, **kwargs):
        base_job = self.get_object()

        # Create new job
        job = Job.objects.create(preset_id=base_job.preset_id, author=request.user, name=get_unique_name(base_job.name))

        # Copy files from base job
        base_files_qs = FileSystem.objects.filter(job=base_job).values_list('file_id', 'name')
        copy_files_with_replace(request, job.id, base_files_qs)

        return Response({'id': job.id, 'identifier': str(job.identifier)})


class CreateFileView(LoggedCallMixin, CreateAPIView):
    serializer_class = JobFileSerializer
    permission_classes = (CreateJobPermission,)


class FileContentView(LoggedCallMixin, RetrieveAPIView):
    lookup_field = 'hash_sum'
    queryset = JobFile.objects.all()
    permission_classes = (IsAuthenticated,)

    def retrieve(self, request, *args, **kwargs):
        return HttpResponse(self.get_object().file.read().decode('utf8'))


class GetFilesDiffView(LoggedCallMixin, APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, hashsum1, hashsum2):
        try:
            f1 = JobFile.objects.get(hash_sum=hashsum1)
            f2 = JobFile.objects.get(hash_sum=hashsum2)
        except JobFile.DoesNotExist:
            raise exceptions.ValidationError("The file was not found")
        with f1.file as fp1, f2.file as fp2:
            return HttpResponse(
                '\n'.join(list(unified_diff(
                    fp1.read().decode('utf8').split('\n'),
                    fp2.read().decode('utf8').split('\n'),
                    fromfile=request.query_params.get('name1', 'Old'),
                    tofile=request.query_params.get('name2', 'New')
                )))
            )


class RemoveJobView(LoggedCallMixin, DestroyAPIView):
    permission_classes = (DestroyJobPermission,)
    queryset = Job.objects.all()


class RemoveDecisionView(LoggedCallMixin, DestroyAPIView):
    permission_classes = (DestroyJobPermission,)
    queryset = Decision.objects.all()

    def perform_destroy(self, instance):
        if not DecisionAccess(self.request.user, instance).can_delete:
            self.permission_denied(self.request, message=_("You can't remove this decision"))
        super().perform_destroy(instance)


class CheckDownloadAccessView(LoggedCallMixin, APIView):
    def post(self, request):
        get_jobs_to_download(
            self.request.user,
            json.loads(request.data.get('jobs', '[]')),
            json.loads(request.data.get('decisions', '[]'))
        )
        return Response({})


class StopDecisionView(LoggedCallMixin, APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, **kwargs):
        with transaction.atomic():
            decision = get_object_or_404(Decision.objects.select_for_update(), **kwargs)
            if not DecisionAccess(request.user, decision).can_stop:
                raise exceptions.PermissionDenied(_("You don't have an access to stop this decision"))
            cancel_decision(decision)
        decision_status_changed(decision)
        # If there are a lot of tasks that are not still deleted it could be too long
        # as there is request to DB for each task here (pre_delete signal)
        decision.tasks.all().delete()
        return Response({})


class RestartDecisionView(LoggedCallMixin, APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, **kwargs):
        decision = get_object_or_404(Decision.objects.select_related('job', 'configuration'), **kwargs)
        if not DecisionAccess(self.request.user, decision).can_restart:
            raise exceptions.PermissionDenied(_("You don't have an access to restart this decision"))
        RestartJobDecision(request.user, decision)
        return Response({})


class CollapseReportsView(LoggedCallMixin, APIView):
    unparallel = [Decision]

    def post(self, request, **kwargs):
        decision = get_object_or_404(Decision, **kwargs)
        if not DecisionAccess(request.user, decision).can_collapse:
            raise exceptions.PermissionDenied(_("You don't have an access to collapse reports"))
        collapse_reports(decision)
        return Response({})


class UploadStatusAPIView(LoggedCallMixin, TemplateAPIListView):
    permission_classes = (IsAuthenticated,)
    authentication_classes = (SessionAuthentication,)
    template_name = 'jobs/UploadStatusTableBody.html'

    def get_queryset(self):
        return UploadedJobArchive.objects.filter(author=self.request.user).select_related('job').order_by('-start_date')


class CoreDecisionArchiveView(LoggedCallMixin, RetrieveAPIView):
    permission_classes = (ServicePermission,)
    queryset = Decision.objects.all()
    lookup_field = 'identifier'
    lookup_url_kwarg = 'identifier'

    def get_queryset(self):
        return Decision.objects.select_for_update().all()

    def retrieve(self, request, *args, **kwargs):
        with transaction.atomic():
            instance = self.get_object()
            if instance.status == DECISION_STATUS[1][0]:
                # Update pending decision
                instance.status = DECISION_STATUS[2][0]
                instance.save()
                decision_status_changed(instance)
            elif instance.status != DECISION_STATUS[2][0]:
                raise exceptions.APIException('The job is not solving')

        generator = KleverCoreArchiveGen(instance)
        mimetype = mimetypes.guess_type(generator.arcname)[0]
        response = StreamingHttpResponse(generator, content_type=mimetype)
        response['Content-Disposition'] = 'attachment; filename="%s"' % generator.arcname
        return response


class DecisionResultsAPIView(LoggedCallMixin, RetrieveAPIView):
    serializer_class = DecisionResultsSerializerRO
    permission_classes = (ViewJobPermission,)
    queryset = Decision.objects.all()
    lookup_url_kwarg = 'identifier'
    lookup_field = 'identifier'

    def get_object(self):
        obj = super().get_object()
        if not obj.is_finished:
            # Not finished decisions can be without results
            raise exceptions.ValidationError(detail='The decision is not finished yet')
        return obj


class DownloadJobByUUIDView(LoggedCallMixin, StreamingResponseAPIView):
    permission_classes = (ServicePermission,)

    def get_generator(self):
        job = get_object_or_404(Job, identifier=self.kwargs['identifier'])
        return JobArchiveGenerator(job)


class UploadJobsAPIView(LoggedCallMixin, APIView):
    unparallel = [Job]
    permission_classes = (CreateJobPermission,)

    def post(self, request):
        for f in request.FILES.getlist('file'):
            upload_scheduler = UploadJobsScheduler(request.user, f)
            upload_scheduler.upload_all()
        return Response({})


class GetJobCoverageTableView(LoggedCallMixin, TemplateAPIRetrieveView):
    permission_classes = (ViewJobPermission,)
    queryset = Decision.objects.all()
    template_name = 'jobs/viewDecision/coverageTable.html'

    def get_context_data(self, instance, **kwargs):
        if 'coverage_id' not in self.request.query_params:
            raise exceptions.APIException('Query parameter coverage_id was not provided')
        context = super().get_context_data(instance, **kwargs)
        context['statistics'] = DecisionCoverageStatistics(
            instance, self.request.query_params['coverage_id']
        ).statistics
        return context
