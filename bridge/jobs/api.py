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
from bridge.utils import logger
from tools.profiling import LoggedCallMixin

from jobs.models import Job, JobHistory, JobFile, FileSystem
from jobs.serializers import (
    JobFilesField, CreateJobSerializer, JVformSerializerRO, JobFileSerializer, JobStatusSerializer,
    DuplicateJobSerializer
)
from jobs.configuration import get_configuration_value
from jobs.Download import KleverCoreArchiveGen
from jobs.utils import JobAccess
from reports.serializers import DecisionResultsSerializerRO


class JobStatusView(LoggedCallMixin, RetrieveAPIView):
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

    def get(self, request, hashsum1=None, hashsum2=None):
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
            serializer = JobStatusSerializer(instance=instance, data={'status': JOB_STATUS[2][0]})
            serializer.is_valid(raise_exception=True)
            instance = serializer.save()
        elif instance.status != JOB_STATUS[2][0]:
            raise exceptions.APIException('The job is not solving')

        generator = KleverCoreArchiveGen(instance)
        mimetype = mimetypes.guess_type(generator.arcname)[0]
        response = StreamingHttpResponse(generator, content_type=mimetype)
        response['Content-Disposition'] = 'attachment; filename="%s"' % generator.arcname
        return response


class StartJobDefValue(LoggedCallMixin, APIView):
    def post(self, request):
        try:
            return get_configuration_value(request.data['name'], request.data['value'])
        except Exception as e:
            logger.exception(e)
            raise exceptions.APIException()


class CheckDownloadAccessView(LoggedCallMixin, APIView):
    def post(self, request):
        job_ids = json.loads(request.POST.get('jobs', '[]'))
        jobs_qs = Job.objects.filter(id__in=job_ids)
        if len(jobs_qs) != len(job_ids):
            raise exceptions.APIException(_('One of the selected jobs was not found'))
        if not JobAccess(self.request.user).can_download_jobs(jobs_qs):
            raise exceptions.APIException(_("You don't have an access to one of the selected jobs"))
        # TODO: check if None data is allowed
        return Response()


class CheckCompareAccessView(LoggedCallMixin, APIView):
    def post(self, request):
        try:
            j1 = Job.objects.get(id=self.kwargs['job1'])
            j2 = Job.objects.get(id=self.kwargs['job2'])
        except Job.DoesNotExist:
            raise exceptions.APIException(_('One of the selected jobs was not found'))
        if not JobAccess(self.request.user, job=j1).can_view() or not JobAccess(self.request.user, job=j2).can_view():
            raise exceptions.APIException(_("You don't have an access to one of the selected jobs"))
        return Response({})
