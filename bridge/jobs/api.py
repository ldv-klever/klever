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
from django.template import loader
from django.urls import reverse
from django.utils.translation import gettext as _

from rest_framework import exceptions, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.generics import (
    get_object_or_404, RetrieveAPIView, ListAPIView, CreateAPIView, UpdateAPIView, DestroyAPIView
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from bridge.access import (
    ViewJobPermission, DestroyJobPermission, ServicePermission,
    CreateJobPermission, UpdateJobPermission, CLIPermission
)
from bridge.vars import PRESET_JOB_TYPE, DECISION_STATUS
from bridge.utils import logger
from bridge.CustomViews import TemplateAPIRetrieveView, TemplateAPIListView, StreamingResponseAPIView
from tools.profiling import LoggedCallMixin

from jobs.models import Job, JobFile, UploadedJobArchive, PresetJob, Decision, DefaultDecisionConfiguration
from jobs.serializers import (
    decision_status_changed, create_default_decision,
    PresetJobDirSerializer, JobFileSerializer, CreateJobSerializer, UpdateJobSerializer,
    DecisionStatusSerializerRO, CreateDecisionSerializer, UpdateDecisionSerializer, RestartDecisionSerializer,
    DefaultDecisionConfigurationSerializer
)
from jobs.configuration import get_configuration_value, get_default_configuration, GetConfiguration
from jobs.Download import KleverCoreArchiveGen, UploadJobsScheduler, JobArchiveGenerator, get_jobs_to_download
from jobs.utils import get_unique_job_name, JobAccess, DecisionAccess
from reports.coverage import DecisionCoverageStatistics
from reports.serializers import DecisionResultsSerializerRO
from reports.utils import collapse_reports
from service.utils import cancel_decision


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


class CreateDecisionView(LoggedCallMixin, CreateAPIView):
    unparallel = [Decision]
    queryset = Decision.objects.all()
    serializer_class = CreateDecisionSerializer
    permission_classes = (IsAuthenticated,)

    def create(self, request, *args, **kwargs):
        job = get_object_or_404(Job, pk=self.kwargs['job_id'])
        if not JobAccess(request.user, job).can_decide:
            raise exceptions.PermissionDenied(_("You don't have an access to decide the job"))
        return super(CreateDecisionView, self).create(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(job_id=self.kwargs['job_id'])


class RenameDecisionView(LoggedCallMixin, UpdateAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = UpdateDecisionSerializer
    queryset = Decision.objects

    def check_object_permissions(self, request, obj):
        super(RenameDecisionView, self).check_object_permissions(request, obj)
        if not DecisionAccess(request.user, obj).can_rename:
            self.permission_denied(request, _("You don't have an access to rename the decision"))


class RestartDecisionView(LoggedCallMixin, UpdateAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = RestartDecisionSerializer

    def get_queryset(self):
        return Decision.objects.select_related('job', 'configuration')

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if not DecisionAccess(request.user, obj).can_restart:
            self.permission_denied(request, _("You don't have an access to restart the decision"))


class GetConfigurationView(LoggedCallMixin, APIView):
    permission_classes = (IsAuthenticated,)

    def __get_configuration(self, **kwargs):
        try:
            return GetConfiguration(**kwargs).configuration
        except Exception as e:
            logger.exception(e)
            raise exceptions.APIException(_('Wrong configuration format'))

    def post(self, request):
        if 'file_conf' in self.request.FILES:
            return Response(self.__get_configuration(file_conf=request.FILES['file_conf']))
        if 'decision' in self.request.data:
            decision = get_object_or_404(
                Decision.objects.select_related('configuration').filter(pk=self.request.data['decision'])
            )
            return Response(GetConfiguration(file_conf=decision.configuration.file).configuration)
        if self.request.data.get('conf_name', 'default') == 'default':
            return Response(get_default_configuration(self.request.user).configuration)
        return Response(self.__get_configuration(conf_name=request.data['conf_name']))


class StartJobDefValueView(LoggedCallMixin, APIView):
    def post(self, request):
        return Response(get_configuration_value(request.data['name'], request.data['value']))


class StartDefaultDecisionView(LoggedCallMixin, APIView):
    permission_classes = (IsAuthenticated,)

    def get_job(self, **kwargs):
        job = get_object_or_404(Job, **kwargs)
        if not JobAccess(self.request.user, job).can_decide:
            raise exceptions.PermissionDenied(_("You don't have an access to start decision of this job"))
        return job

    def post(self, request, **kwargs):
        try:
            job = self.get_job(**kwargs)

            if 'file_conf' in self.request.FILES:
                configuration = GetConfiguration(file_conf=self.request.FILES['file_conf']).for_json()
            else:
                configuration = get_default_configuration(self.request.user).for_json()

            decision = create_default_decision(request, job, configuration)
            decision_status_changed(decision)
        except Exception as e:
            logger.exception(e)
            raise exceptions.APIException('Error occured for starting default decision')
        return Response({
            'id': decision.id, 'identifier': str(decision.identifier),
            'url': reverse('jobs:decision', args=[decision.id])
        })


class DecisionStatusListView(ListAPIView):
    queryset = Decision.objects.select_related('scheduler')
    serializer_class = DecisionStatusSerializerRO
    permission_classes = (IsAuthenticated,)


class DecisionStatusView(RetrieveAPIView):
    queryset = Decision.objects.select_related('scheduler')
    serializer_class = DecisionStatusSerializerRO
    permission_classes = (IsAuthenticated,)


class DecisionResultsAPIView(LoggedCallMixin, RetrieveAPIView):
    serializer_class = DecisionResultsSerializerRO
    permission_classes = (CLIPermission,)
    queryset = Decision.objects.all()
    lookup_url_kwarg = 'identifier'
    lookup_field = 'identifier'

    def get_object(self):
        obj = super().get_object()
        if not obj.is_finished:
            # Not finished decisions can be without results
            raise exceptions.ValidationError(detail='The decision is not finished yet')
        return obj


class CreateDefaultJobView(LoggedCallMixin, CreateAPIView):
    permission_classes = (CreateJobPermission,)
    queryset = PresetJob.objects.exclude(type=PRESET_JOB_TYPE[0][0])
    lookup_field = 'identifier'

    def create(self, request, *args, **kwargs):
        preset_job = self.get_object()
        job = Job.objects.create(preset=preset_job, author=request.user, name=get_unique_job_name(preset_job))
        return Response({'id': job.id, 'identifier': str(job.identifier)})


class CreateFileView(LoggedCallMixin, CreateAPIView):
    serializer_class = JobFileSerializer
    permission_classes = (IsAuthenticated,)


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


class CollapseReportsView(LoggedCallMixin, APIView):
    unparallel = [Decision]

    def post(self, request, **kwargs):
        decision = get_object_or_404(Decision, **kwargs)
        if not DecisionAccess(request.user, decision).can_collapse:
            raise exceptions.PermissionDenied(_("You don't have an access to collapse the reports tree"))
        collapse_reports(decision)
        return Response({})


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


class CheckDownloadAccessView(LoggedCallMixin, APIView):
    def post(self, request):
        get_jobs_to_download(
            self.request.user,
            json.loads(request.data.get('jobs', '[]')),
            json.loads(request.data.get('decisions', '[]'))
        )
        return Response({})


class DownloadJobByUUIDView(LoggedCallMixin, StreamingResponseAPIView):
    permission_classes = (CLIPermission,)

    def get_generator(self):
        job = get_object_or_404(Job, identifier=self.kwargs['identifier'])
        self.check_object_permissions(self.request, job)
        return JobArchiveGenerator(job)


class UploadStatusAPIView(LoggedCallMixin, TemplateAPIListView):
    permission_classes = (IsAuthenticated,)
    authentication_classes = (SessionAuthentication,)
    template_name = 'jobs/UploadStatusTableBody.html'

    def get_queryset(self):
        return UploadedJobArchive.objects.filter(author=self.request.user).select_related('job').order_by('-start_date')


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


class CreateDefConfAPIView(LoggedCallMixin, CreateAPIView):
    serializer_class = DefaultDecisionConfigurationSerializer
    permission_classes = (IsAuthenticated,)
    unparallel = [DefaultDecisionConfiguration]

    def create(self, request, *args, **kwargs):
        try:
            def_conf = DefaultDecisionConfiguration.objects.get(user=self.request.user)
            serializer = self.get_serializer(def_conf, data=request.data)
            success_status = status.HTTP_200_OK
        except DefaultDecisionConfiguration.DoesNotExist:
            serializer = self.get_serializer(data=request.data)
            success_status = status.HTTP_201_CREATED
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=success_status)


class GetConfHtmlAPIView(LoggedCallMixin, RetrieveAPIView):
    # TODO: Decision view permission
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return Decision.objects.select_related('configuration', 'scheduler')

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        conf_data = GetConfiguration(file_conf=instance.configuration.file).for_html()
        template = loader.get_template('jobs/viewDecision/configuration.html')
        return HttpResponse(template.render({'conf': conf_data, 'object': instance}, request))
