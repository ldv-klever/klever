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

import os
import json

from urllib.parse import unquote

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.utils.translation import gettext as _
from django.views.generic import TemplateView

from rest_framework import exceptions
from rest_framework.generics import DestroyAPIView
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.renderers import TemplateHTMLRenderer

from bridge.vars import USER_ROLES, UNKNOWN_ERROR, DECISION_STATUS
from bridge.utils import logger, BridgeException
from bridge.access import ManagerPermission

from jobs.models import JobFile, Decision
from reports.models import Computer, OriginalSources, CompareDecisionsInfo
from marks.models import ConvertedTrace
from service.models import Task
from tools.models import LockTable

from tools.utils import (
    objects_without_relations, ClearFiles, Recalculation, RecalculateMarksCache, RemoveDuplicates, ErrorTraceAnanlizer
)
from tools.profiling import ProfileData, ExecLocker, LoggedCallMixin, DBLogsAnalizer

from jobs.preset import PopulatePresets
from reports.etv import GetETV
from marks.population import PopulateSafeMarks, PopulateUnsafeMarks, PopulateUnknownMarks, populate_tags
from service.population import populuate_schedulers


class ManagerPageView(LoginRequiredMixin, TemplateView):
    template_name = 'tools/ManagerPanel.html'

    def get_context_data(self, **kwargs):
        if not self.request.user.is_manager:
            raise PermissionDenied("You don't have an access to this page")
        context = super().get_context_data(**kwargs)
        context['decisions'] = Decision.objects.exclude(
            status__in=[DECISION_STATUS[0][0], DECISION_STATUS[1][0], DECISION_STATUS[2][0], DECISION_STATUS[6][0]]
        ).select_related('job')
        context['original_sources'] = OriginalSources.objects.annotate(
            links_num=Count('reportcomponent__decision', distinct=True)
        ).all()
        context['comparison'] = CompareDecisionsInfo.objects.select_related('user', 'decision1', 'decision2')
        return context


class ClearSystemAPIView(LoggedCallMixin, APIView):
    unparallel = [JobFile, OriginalSources, ConvertedTrace, Computer]
    permission_classes = (ManagerPermission,)

    def post(self, request):
        assert request.user.role == USER_ROLES[2][0]
        ClearFiles()
        objects_without_relations(Computer).delete()
        RemoveDuplicates()
        return Response({'message': _("All unused files and DB rows were deleted")})


class ClearComparisonAPIView(LoggedCallMixin, DestroyAPIView):
    queryset = CompareDecisionsInfo.objects.all()
    permission_classes = (ManagerPermission,)


class RecalculationAPIView(LoggedCallMixin, APIView):
    permission_classes = (ManagerPermission,)
    unparallel = [Decision]

    def post(self, request):
        try:
            Recalculation(request.data['type'], request.data['decisions'])
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
        Task.objects.exclude(decision__status=DECISION_STATUS[2][0]).delete()
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
    unparallel = ['PresetJob', 'MarkSafe', 'MarkUnsafe', 'MarkUnknown', 'Tag', 'Scheduler']

    def post(self, request):
        data = json.loads(request.data['data'])
        messages = []
        if 'preset-jobs' in data:
            PopulatePresets().populate()
            messages.append('Preset jobs were populated!')
        if 'schedulers' in data:
            populuate_schedulers()
            messages.append('Schedulers were populated!')
        if 'tags' in data:
            created, total = populate_tags()
            messages.append("{} of {} tags were populated".format(created, total))
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


class DBLogsStatistics(TemplateView):
    template_name = 'tools/DBLogsStatistics.html'

    def get_context_data(self, **kwargs):
        context = super(DBLogsStatistics, self).get_context_data(**kwargs)
        results_file = os.path.join('logs', DBLogsAnalizer.results_file)
        if os.path.isfile(results_file):
            with open(results_file, mode='r', encoding='utf-8') as fp:
                data = json.load(fp)
                context['data'] = list({
                    'name': k,
                    'numbers': data[k][:6],
                    'percents': list(int(x / data[k][5] * 100) for x in data[k][:5]),
                    'average': data[k][6] / data[k][5],
                    'total': data[k][6]
                } for k in sorted(data) if data[k][0] != data[k][5] > 10)
        return context


class ReportsLogggingView(TemplateView):
    template_name = 'tools/ReportsLogging.html'


class FileLogView(LoginRequiredMixin, TemplateView):
    template_name = 'tools/Logs.html'

    def get_context_data(self, **kwargs):
        context = super(FileLogView, self).get_context_data(**kwargs)

        context['logs'] = list(sorted(name for name in os.listdir(settings.LOGS_DIR) if name.endswith('.log')))
        selected_log = None
        if self.request.GET.get('name'):
            log_name = unquote(self.request.GET['name'])
            if log_name in context['logs']:
                selected_log = log_name

        if not selected_log and len(context['logs']):
            selected_log = context['logs'][0]

        context['selected_log'] = selected_log
        return context


class ErrorTraceAnalizerView(LoginRequiredMixin, TemplateView):
    template_name = 'tools/ErrorTraceAnalizer.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['include_jquery_ui'] = True
        context['etv'] = context['json'] = None

        et_index = 0
        if 'index' in self.request.GET:
            et_index = int(self.request.GET['index'])
        context['index'] = et_index

        et_dir = os.path.join(settings.BASE_DIR, 'tools', 'error-traces')
        error_traces = os.listdir(et_dir)
        context['error_traces'] = list((i, error_traces[i]) for i in range(len(error_traces)))
        if len(error_traces) > et_index:
            with open(os.path.join(et_dir, error_traces[0]), mode='r', encoding='utf-8') as fp:
                error_trace = fp.read()
            try:
                context['etv'] = GetETV(error_trace, self.request.user)
            except Exception as e:
                logger.exception(e)
            context['json'] = ErrorTraceAnanlizer(error_trace).get_trace().replace('\\"', '\\\\"')
        return context


class SecretPageView(TemplateView):
    template_name = 'tools/secret.html'
