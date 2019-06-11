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
import mimetypes

from difflib import unified_diff

from django.db.models import F
from django.http.response import HttpResponse, StreamingHttpResponse
from django.urls import reverse
from django.utils.translation import ugettext as _

from rest_framework import exceptions
from rest_framework.views import APIView
from rest_framework.generics import (
    RetrieveAPIView, get_object_or_404, GenericAPIView, CreateAPIView, UpdateAPIView, DestroyAPIView
)
from rest_framework.mixins import UpdateModelMixin, CreateModelMixin
from rest_framework.response import Response
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated

from bridge.access import WriteJobPermission, ViewJobPermission, DestroyJobPermission, ServicePermission
from bridge.vars import JOB_STATUS
from bridge.utils import logger, BridgeException, extract_archive
from tools.profiling import LoggedCallMixin

from jobs.models import Job, JobHistory, JobFile, FileSystem, RunHistory
from jobs.serializers import (
    JobFilesField, CreateJobSerializer, JVformSerializerRO, JobFileSerializer, JobStatusSerializer,
    DuplicateJobSerializer, change_job_status
)
from jobs.configuration import get_configuration_value, GetConfiguration
from jobs.Download import KleverCoreArchiveGen, UploadReportsWithoutDecision
from jobs.utils import JobAccess
from reports.serializers import DecisionResultsSerializerRO
from reports.UploadReport import collapse_reports
from service.utils import StartJobDecision, CancelDecision


class JobStatusView(RetrieveAPIView):
    queryset = Job.objects.all()
    serializer_class = JobStatusSerializer
    permission_classes = (IsAuthenticated,)


class SaveJobView(LoggedCallMixin, UpdateModelMixin, CreateModelMixin, GenericAPIView):
    unparallel = [Job]
    queryset = Job.objects.all()
    serializer_class = CreateJobSerializer
    permission_classes = (WriteJobPermission,)

    def post(self, request, *args, **kwargs):
        return self.create(request, *args, **kwargs)

    def put(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)


class JobVersionView(LoggedCallMixin, RetrieveAPIView):
    authentication_classes = (SessionAuthentication,)
    queryset = JobHistory
    serializer_class = JVformSerializerRO
    permission_classes = (ViewJobPermission,)

    def get_object(self):
        queryset = self.filter_queryset(self.get_queryset())
        obj = get_object_or_404(queryset, **self.kwargs)
        self.check_object_permissions(self.request, obj)
        return obj


class JobHistoryFiles(RetrieveAPIView):
    queryset = JobHistory.objects.all()
    permission_classes = (IsAuthenticated,)

    def retrieve(self, request, *args, **kwargs):
        return Response(data=JobFilesField().to_representation(
            get_object_or_404(self.get_queryset(), **self.kwargs))
        )


class CreateFileView(LoggedCallMixin, CreateAPIView):
    unparallel = [JobFile]
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


class ReplaceJobFileView(LoggedCallMixin, UpdateAPIView):
    queryset = FileSystem.objects.all()
    permission_classes = (WriteJobPermission,)

    def get_object(self):
        # Check request data
        for field in ['job', 'name']:
            if field not in self.request.data:
                raise exceptions.ValidationError(_('Field {field} is required').format(field=field))

        # Get last job version
        job_version = get_object_or_404(
            JobHistory.objects.select_related('job'),
            job_id=self.request.data['job'], version=F('job__version')
        )

        # Check job permission
        self.check_object_permissions(self.request, job_version.job)

        # Get queryset
        queryset = self.filter_queryset(self.get_queryset())

        # Get Job file
        return get_object_or_404(queryset, name=self.request.data['name'], job_version=job_version)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()

        # Save the file
        file_serializer = JobFileSerializer(data=request.data)
        file_serializer.is_valid(raise_exception=True)
        instance.file = file_serializer.save()
        instance.save()

        return Response({})


class DuplicateJobView(LoggedCallMixin, UpdateModelMixin, CreateModelMixin, GenericAPIView):
    unparallel = [Job]
    serializer_class = DuplicateJobSerializer
    permission_classes = (WriteJobPermission,)

    def post(self, request, *args, **kwargs):
        return self.create(request, *args, **kwargs)

    def patch(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)


class DecisionResultsView(LoggedCallMixin, RetrieveAPIView):
    serializer_class = DecisionResultsSerializerRO
    permission_classes = (ViewJobPermission,)
    queryset = Job.objects.all()

    def get_object(self):
        obj = super().get_object()

        # Not finished jobs don't have results
        if obj.status in {JOB_STATUS[0][0], JOB_STATUS[1][0], JOB_STATUS[2][0]}:
            raise exceptions.ValidationError(detail='The job is not decided yet')
        return obj


class RemoveJobView(LoggedCallMixin, DestroyAPIView):
    permission_classes = (DestroyJobPermission,)
    queryset = Job.objects.all()


# TODO
class UploadJobsAPIView(LoggedCallMixin, APIView):
    unparallel = [Job, 'AttrName']
    permission_classes = (WriteJobPermission,)


class CoreJobArchiveView(LoggedCallMixin, RetrieveAPIView):
    unparallel = ['Job']
    permission_classes = (ServicePermission,)
    queryset = Job.objects.all()
    lookup_field = 'identifier'
    lookup_url_kwarg = 'identifier'

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()

        if instance.status == JOB_STATUS[1][0]:
            # Update pending job
            change_job_status(instance, JOB_STATUS[2][0])
        elif instance.status != JOB_STATUS[2][0]:
            raise exceptions.APIException('The job is not solving')

        generator = KleverCoreArchiveGen(instance)
        mimetype = mimetypes.guess_type(generator.arcname)[0]
        response = StreamingHttpResponse(generator, content_type=mimetype)
        response['Content-Disposition'] = 'attachment; filename="%s"' % generator.arcname
        return response


class StartJobDefValueView(LoggedCallMixin, APIView):
    def post(self, request):
        return Response(get_configuration_value(request.data['name'], request.data['value']))


class CheckDownloadAccessView(LoggedCallMixin, APIView):
    def post(self, request):
        job_ids = json.loads(request.POST.get('jobs', '[]'))
        jobs_qs = Job.objects.filter(id__in=job_ids)
        if len(jobs_qs) != len(job_ids):
            raise exceptions.APIException(_('One of the selected jobs was not found'))
        if not JobAccess(self.request.user).can_download_jobs(jobs_qs):
            raise exceptions.APIException(_("You don't have an access to one of the selected jobs"))
        return Response({})


class RemoveJobVersions(LoggedCallMixin, APIView):
    unparallel = ['Job', JobHistory]

    def delete(self, request, job_id):
        job = get_object_or_404(Job, pk=job_id)
        if not JobAccess(request.user, job).can_edit():
            raise exceptions.PermissionDenied(_("You don't have an access to remove job versions"))
        versions = list(int(v) for v in json.loads(request.data.get('versions', '[]')))
        if job.version in versions:
            raise exceptions.PermissionDenied(_("You don't have an access to remove one of the selected version"))
        job.versions.filter(version__in=versions).delete()
        return Response({'message': _('Selected versions were successfully deleted')})


class GetConfigurationView(LoggedCallMixin, APIView):
    def post(self, request):
        if 'name' not in request.data:
            raise exceptions.APIException('Configuration name was not provided')

        if request.data['name'] == 'file':
            conf_args = {'file_conf': request.FILES['file']}
        else:
            conf_args = {'conf_name': request.data['name']}
        return Response(GetConfiguration(**conf_args).configuration)


class StartDecisionView(LoggedCallMixin, APIView):
    def post(self, request, job_id):
        getconf_kwargs = {}
        job = get_object_or_404(Job, id=job_id)
        if not JobAccess(request.user, job).can_decide():
            raise exceptions.PermissionDenied(_("You don't have an access to start decision of this job"))

        # If self.request.POST['mode'] == 'fast' or any other then default configuration is used
        if request.data['mode'] == 'data':
            getconf_kwargs['user_conf'] = json.loads(request.data['data'])
        elif request.data['mode'] == 'file_conf':
            getconf_kwargs['file_conf'] = request.FILES['file_conf']
        elif request.data['mode'] == 'lastconf':
            last_run = RunHistory.objects.filter(job_id=job.id).order_by('-date').first()
            if last_run is None:
                raise exceptions.APIException(_('The job was not decided before'))
            getconf_kwargs['last_run'] = last_run
        elif request.data['mode'] == 'default':
            getconf_kwargs['conf_name'] = request.data['conf_name']

        try:
            StartJobDecision(request.user, job, GetConfiguration(**getconf_kwargs).for_json())
        except BridgeException as e:
            raise exceptions.APIException(str(e))
        return Response({'url': reverse('jobs:job', args=[job.id])})


class StopDecisionView(LoggedCallMixin, APIView):
    model = Job
    unparallel = [Job]

    def post(self, request, job_id):
        job = get_object_or_404(Job, pk=job_id)
        if not JobAccess(request.user, job).can_stop():
            raise exceptions.PermissionDenied(_("You don't have an access to stop decision of this job"))
        try:
            CancelDecision(job)
        except BridgeException as e:
            raise exceptions.APIException(str(e))
        return Response({})


class GetJobFieldView(LoggedCallMixin, APIView):
    def post(self, request):
        if 'job' not in request.data:
            raise exceptions.APIException(_('The job was not provided'))
        if 'field' not in request.data:
            raise exceptions.APIException(_('The job field name was not provided'))
        name_or_id = request.data['job']
        try:
            job = Job.objects.only('id').get(name=name_or_id)
        except Job.DoesNotExist:
            found_jobs = Job.objects.only('id').filter(identifier__startswith=name_or_id)
            if len(found_jobs) == 0:
                raise exceptions.ValidationError(_('The job with specified identifier or name was not found'))
            elif len(found_jobs) > 1:
                raise exceptions.ValidationError(
                    _('Several jobs match the specified identifier, please increase the length of the job identifier')
                )
            job = found_jobs[0]
        if not hasattr(job, request.data['field']):
            raise exceptions.ValidationError(_('The job does not have attribute %(field)s') % {
                'field': request.data['field']
            })
        return {request.data['field']: getattr(job, request.data['field'])}


class DoJobHasChildrenView(LoggedCallMixin, RetrieveAPIView):
    def get_queryset(self):
        return Job.objects.only('id')

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return Response({'children': (instance.children.count() > 0)})


class UploadReportsView(LoggedCallMixin, APIView):
    model = Job
    unparallel = [Job]

    def post(self, request, pk):
        instance = get_object_or_404(Job, pk=pk)
        if not JobAccess(request.user, instance).can_decide():
            raise exceptions.ValidationError(_("You don't have an access to upload reports for this job"))

        # try:
        #     reports_dir = extract_archive(request.FILES['archive'])
        # except Exception as e:
        #     logger.exception(e)
        #     raise BridgeException(_('Extraction of the archive has failed'))
        #
        # UploadReportsWithoutDecision(instance, request.user, reports_dir.name)
        # TODO: implement
        logger.error('Manual reports uploading is not implemented yet')
        return Response({})


class CollapseReportsView(LoggedCallMixin, APIView):
    model = Job
    unparallel = [Job]

    def post(self, request, pk):
        job = get_object_or_404(Job, pk=pk)
        if not JobAccess(self.request.user, job).can_collapse():
            raise exceptions.PermissionDenied(_("You don't have an access to collapse reports"))
        collapse_reports(job)
        return Response({})
