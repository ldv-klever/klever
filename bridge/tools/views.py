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

import os
import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.utils.translation import ugettext as _
from django.views.generic import TemplateView

from rest_framework import exceptions
from rest_framework.generics import DestroyAPIView
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.renderers import TemplateHTMLRenderer

from bridge.vars import USER_ROLES, JOB_STATUS, UNKNOWN_ERROR
from bridge.utils import BridgeException, logger
from bridge.access import ManagerPermission

from jobs.models import Job, JobFile
from reports.models import Computer, OriginalSources, CompareJobsInfo
from marks.models import ConvertedTrace
from service.models import Task
from tools.models import LockTable

from tools.utils import objects_without_relations, ClearFiles, Recalculation, RecalculateMarksCache
from tools.profiling import ProfileData, ExecLocker, LoggedCallMixin

from marks.population import (
    PopulateSafeTags, PopulateUnsafeTags, PopulateSafeMarks, PopulateUnsafeMarks, PopulateUnknownMarks
)
from service.population import populuate_schedulers


class ManagerPageView(LoginRequiredMixin, TemplateView):
    template_name = 'tools/ManagerPanel.html'

    def get_context_data(self, **kwargs):
        if self.request.user.role != USER_ROLES[2][0]:
            raise PermissionDenied("You don't have an acces to this page")
        context = super().get_context_data(**kwargs)
        context['jobs'] = Job.objects.exclude(reportroot=None).exclude(
            status__in=[JOB_STATUS[0][0], JOB_STATUS[1][0], JOB_STATUS[2][0], JOB_STATUS[6][0]]
        )
        context['original_sources'] = OriginalSources.objects.annotate(
            links_num=Count('reportcomponent__root', distinct=True)
        ).all()
        context['comparison'] = CompareJobsInfo.objects.select_related('user', 'root1__job', 'root2__job')
        return context


class ClearSystemAPIView(LoggedCallMixin, APIView):
    unparallel = [JobFile, OriginalSources, ConvertedTrace, Computer]
    permission_classes = (ManagerPermission,)

    def post(self, request):
        assert request.user.role == USER_ROLES[2][0]
        ClearFiles()
        objects_without_relations(Computer).delete()
        return Response({'message': _("All unused files and DB rows were deleted")})


class ClearComparisonAPIView(LoggedCallMixin, DestroyAPIView):
    queryset = CompareJobsInfo.objects.all()
    permission_classes = (ManagerPermission,)


class RecalculationAPIView(LoggedCallMixin, APIView):
    permission_classes = (ManagerPermission,)
    unparallel = [Job]

    def post(self, request):
        try:
            Recalculation(request.data['type'], request.data['jobs'])
        except BridgeException as e:
            raise exceptions.ValidationError({'error': str(e)})
        except Exception as e:
            logger.exception(e)
            raise exceptions.APIException({'error': str(UNKNOWN_ERROR)})
        return Response({})


class MarksRecalculationAPIView(LoggedCallMixin, APIView):
    permission_classes = (ManagerPermission,)
    unparallel = ['MarkSafe', 'MarkUnsafe', 'MarkUnknown']

    def post(self, request):
        try:
            RecalculateMarksCache(request.data['type'])
        except BridgeException as e:
            raise exceptions.ValidationError({'error': str(e)})
        except Exception as e:
            logger.exception(e)
            raise exceptions.APIException({'error': str(UNKNOWN_ERROR)})
        return Response({})


class CallLogsView(LoginRequiredMixin, TemplateView):
    template_name = 'tools/CallLogs.html'


class CallLogAPIView(APIView):
    renderer_classes = (TemplateHTMLRenderer,)
    permission_classes = (ManagerPermission,)

    def post(self, request):
        action = request.data.get('action')

        if action == 'between':
            data = ProfileData().get_log(
                float(request.data['date1']) if request.data.get('date1') else None,
                float(request.data['date2']) if request.data.get('date2') else None,
                request.data.get('name')
            )
        elif action == 'around' and 'date' in request.POST:
            data = ProfileData().get_log_around(
                float(request.data['date']),
                int(request.data['interval']) if request.data.get('interval') else None
            )
        else:
            raise exceptions.APIException(str(UNKNOWN_ERROR))
        return Response({'data': data}, template_name='tools/LogList.html')


class CallStatisticAPIView(APIView):
    renderer_classes = (TemplateHTMLRenderer,)
    permission_classes = (ManagerPermission,)

    def post(self, request):
        action = request.data.get('action')

        if action == 'between':
            data = ProfileData().get_statistic(
                float(request.data['date1']) if request.data.get('date1') else None,
                float(request.data['date2']) if request.data.get('date2') else None,
                request.data.get('name')
            )
        elif action == 'around' and 'date' in request.POST:
            data = ProfileData().get_statistic_around(
                float(request.data['date']),
                int(request.data['interval']) if request.data.get('interval') else None
            )
        else:
            raise exceptions.APIException(str(UNKNOWN_ERROR))
        return Response({'data': data}, template_name='tools/CallStatistic.html')


class ProcessingListView(LoginRequiredMixin, TemplateView):
    template_name = 'tools/ProcessingRequests.html'

    def get_context_data(self, **kwargs):
        if self.request.user.role != USER_ROLES[2][0]:
            raise PermissionDenied("You don't have an acces to this page")
        context = super(ProcessingListView, self).get_context_data(**kwargs)
        context['data'] = ProfileData().processing()
        context['locked'] = LockTable.objects.filter(locked=True)
        return context


class ClearTasksAPIView(LoggedCallMixin, APIView):
    permission_classes = (ManagerPermission,)

    def delete(self, request):
        assert request.user.role == USER_ROLES[2][0]
        Task.objects.exclude(decision__job__status=JOB_STATUS[2][0]).delete()
        return Response({'message': _('Tasks were successfully deleted')})


class ManualUnlockAPIView(LoggedCallMixin, APIView):
    permission_classes = (ManagerPermission,)

    def delete(self, request):
        assert request.user.role == USER_ROLES[2][0]
        LockTable.objects.all().delete()
        try:
            os.remove(ExecLocker.lockfile)
        except FileNotFoundError:
            pass
        return Response({'message': 'Success!'})


class PopulationAPIView(LoggedCallMixin, APIView):
    permission_classes = (ManagerPermission,)
    unparallel = [Job, 'MarkSafe', 'MarkUnsafe', 'MarkUnknown', 'SafeTag', 'UnsafeTag', 'Scheduler']

    def post(self, request):
        data = json.loads(request.data['data'])
        messages = []
        if 'schedulers' in data:
            populuate_schedulers()
            messages.append('Schedulers were populated!')
        if 'safe-tags' in data:
            res = PopulateSafeTags()
            messages.append("{} of {} safe tags were populated".format(res.created, res.total))
        if 'unsafe-tags' in data:
            res = PopulateUnsafeTags()
            messages.append("{} of {} unsafe tags were populated".format(res.created, res.total))
        if 'safe-marks' in data:
            res = PopulateSafeMarks()
            messages.append("{} of {} safe marks were populated".format(res.created, res.total))
        if 'unsafe-marks' in data:
            res = PopulateUnsafeMarks()
            messages.append("{} of {} unsafe marks were populated".format(res.created, res.total))
        if 'unknown-marks' in data:
            res = PopulateUnknownMarks()
            messages.append("{} of {} unknown marks were populated".format(res.created, res.total))
        return Response({'messages': messages})
