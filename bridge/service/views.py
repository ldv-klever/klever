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

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic.base import TemplateView
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render

from tools.profiling import unparallel_group, LoggedCallMixin
from bridge.vars import USER_ROLES, PRIORITY
from bridge.utils import logger

from jobs.models import Job
from service.models import Scheduler, Node

import service.utils
from service.test import TEST_NODES_DATA, TEST_TOOLS_DATA, TEST_JSON


class SchedulersInfoView(LoginRequiredMixin, LoggedCallMixin, TemplateView):
    template_name = 'service/scheduler.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['schedulers'] = Scheduler.objects.prefetch_related('verificationtool_set').all()
        context['data'] = service.utils.NodesData()
        context['nodes'] = Node.objects.select_related('workload', 'config')
        return context


@unparallel_group([Job])
def get_jobs_and_tasks(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'You are not signing in'})
    if request.user.role not in [USER_ROLES[2][0], USER_ROLES[4][0]]:
        return JsonResponse({'error': 'No access'})
    if 'scheduler' not in request.session:
        return JsonResponse({'error': 'The scheduler was not found in session'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests are supported'})
    if 'jobs and tasks status' not in request.POST:
        return JsonResponse({'error': 'Tasks data is required'})
    try:
        jobs_and_tasks = service.utils.GetTasks(
            request.session['scheduler'], request.POST['jobs and tasks status']).newtasks
    except service.utils.ServiceError as e:
        # TODO: email notification
        return JsonResponse({'error': str(e)})
    except Exception as e:
        logger.exception(e)
        return JsonResponse({'error': 'Unknown error'})
    return JsonResponse({'jobs and tasks status': jobs_and_tasks})


@login_required
def test(request):
    return render(request, 'service/test.html', {
        'priorities': PRIORITY,
        'jobs': Job.objects.filter(~Q(solvingprogress=None)),
        'schedulers': Scheduler.objects.all(),
        'defvals': {
            'task_description': '{"priority": "LOW"}',
            'sch_json': json.dumps(TEST_JSON),
            'solution_description': '{"resources": {"wall time": 10000}}',
            'nodes_data': json.dumps(TEST_NODES_DATA),
            'tools_data': json.dumps(TEST_TOOLS_DATA),
        },
        'curr_scheduler': request.session.get('scheduler', None),
        'curr_job_id': request.session.get('job id', None)
    })
