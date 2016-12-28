#
# Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
# Institute for System Programming of the Russian Academy of Sciences
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
import mimetypes
from wsgiref.util import FileWrapper
from urllib.parse import quote
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse, StreamingHttpResponse
from django.shortcuts import render
from django.utils.translation import activate
from bridge.vars import USER_ROLES
from bridge.utils import unparallel_group, unparallel
from service.test import TEST_NODES_DATA, TEST_TOOLS_DATA, TEST_JSON
from service.utils import *


@unparallel_group(['service', 'task'])
def schedule_task(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.user.extended.role not in [USER_ROLES[2][0], USER_ROLES[4][0]]:
        return JsonResponse({'error': 'No access'})
    if 'job id' not in request.session:
        return JsonResponse({'error': 'Session does not have job id'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Just POST requests are supported'})
    if 'description' not in request.POST:
        return JsonResponse({'error': 'Task description is not specified'})
    archive = None
    for f in request.FILES.getlist('file'):
        archive = f
    if archive is None:
        return JsonResponse({'error': 'The task archive was not got'})
    try:
        res = ScheduleTask(request.session['job id'], request.POST['description'], archive)
    except Exception as e:
        logger.exception(e)
        return JsonResponse({'error': str(e)})
    return JsonResponse({'task id': res.task_id})


def get_task_status(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.user.extended.role not in [USER_ROLES[2][0], USER_ROLES[4][0]]:
        return JsonResponse({'error': 'No access'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Just POST requests are supported'})
    if 'task id' not in request.POST:
        return JsonResponse({'error': 'Task identifier is not specified'})
    try:
        res = GetTaskStatus(request.POST['task id'])
    except Exception as e:
        return JsonResponse({'error': str(e)})
    return JsonResponse({'task status': res.status})


@unparallel_group(['solution'])
def download_solution(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.user.extended.role not in [USER_ROLES[2][0], USER_ROLES[4][0]]:
        return JsonResponse({'error': 'No access'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Just POST requests are supported'})
    if 'task id' not in request.POST:
        return JsonResponse({'error': 'Task identifier is not specified'})

    try:
        res = GetSolution(request.POST['task id'])
    except Exception as e:
        logger.exception(e)
        return JsonResponse({'error': str(e)})
    if res.task.status == TASK_STATUS[3][0]:
        return JsonResponse({'task error': res.task.error})
    mimetype = mimetypes.guess_type(os.path.basename(res.solution.archname))[0]
    response = StreamingHttpResponse(FileWrapper(res.solution.archive, 8192), content_type=mimetype)
    response['Content-Length'] = len(res.solution.archive)
    response['Content-Disposition'] = "attachment; filename=%s" % quote(res.solution.archname)
    return response


@unparallel_group(['service'])
def remove_task(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.user.extended.role not in [USER_ROLES[2][0], USER_ROLES[4][0]]:
        return JsonResponse({'error': 'No access'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Just POST requests are supported'})
    if 'task id' not in request.POST:
        return JsonResponse({'error': 'Task identifier is not specified'})

    try:
        RemoveTask(request.POST['task id'])
    except Exception as e:
        logger.exception(e)
        return JsonResponse({'error': str(e)})
    return JsonResponse({})


@unparallel_group(['service'])
def cancel_task(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.user.extended.role not in [USER_ROLES[2][0], USER_ROLES[4][0]]:
        return JsonResponse({'error': 'No access'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Just POST requests are supported'})
    if 'task id' not in request.POST:
        return JsonResponse({'error': 'Task identifier is not specified'})
    try:
        CancelTask(request.POST['task id'])
    except Exception as e:
        return JsonResponse({'error': str(e)})
    return JsonResponse({})


@unparallel_group(['service', 'job'])
def get_jobs_and_tasks(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.user.extended.role not in [USER_ROLES[2][0], USER_ROLES[4][0]]:
        return JsonResponse({'error': 'No access'})
    if 'scheduler' not in request.session:
        return JsonResponse({'error': 'The scheduler was not found in session'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests are supported'})
    if 'jobs and tasks status' not in request.POST:
        return JsonResponse({'error': 'Tasks data is required'})
    try:
        jobs_and_tasks = GetTasks(request.session['scheduler'], request.POST['jobs and tasks status']).newtasks
    except Exception as e:
        # TODO: email notification
        logger.exception(e)
        return JsonResponse({'error': str(e)})
    return JsonResponse({'jobs and tasks status': jobs_and_tasks})


@unparallel_group(['service'])
def download_task(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.user.extended.role not in [USER_ROLES[2][0], USER_ROLES[4][0]]:
        return JsonResponse({'error': 'No access'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Just POST requests are supported'})
    if 'task id' not in request.POST:
        return JsonResponse({'error': 'Task identifier is not specified'})

    try:
        res = GetTaskData(request.POST['task id'])
    except Exception as e:
        logger.exception(e)
        return JsonResponse({'error': str(e)})

    mimetype = mimetypes.guess_type(os.path.basename(res.task.archname))[0]
    with res.task.archive as fp:
        response = HttpResponse(fp.read(), content_type=mimetype)
    response['Content-Disposition'] = 'attachment; filename="%s"' % quote(res.task.archname)
    return response


@unparallel_group(['task', 'solution'])
def upload_solution(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.user.extended.role not in [USER_ROLES[2][0], USER_ROLES[4][0]]:
        return JsonResponse({'error': 'No access'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Just POST requests are supported'})
    if 'task id' not in request.POST:
        return JsonResponse({'error': 'Task identifier is not specified'})
    if 'description' not in request.POST:
        return JsonResponse({'error': 'Description is not specified'})

    archive = None
    for f in request.FILES.getlist('file'):
        archive = f
    if archive is None:
        return JsonResponse({'error': 'The solution archive was not got'})
    try:
        SaveSolution(request.POST['task id'], archive, request.POST['description'])
    except Exception as e:
        logger.exception(e)
        return JsonResponse({'error': str(e)})
    return JsonResponse({})


@unparallel
def update_nodes(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.user.extended.role not in [USER_ROLES[2][0], USER_ROLES[4][0]]:
        return JsonResponse({'error': 'No access'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Just POST requests are supported'})
    if 'nodes data' not in request.POST:
        return JsonResponse({'error': 'Nodes data is not specified'})

    try:
        SetNodes(request.POST['nodes data'])
    except Exception as e:
        logger.exception(e)
        return JsonResponse({'error': str(e)})
    return JsonResponse({})


@unparallel
def update_tools(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.user.extended.role not in [USER_ROLES[2][0], USER_ROLES[4][0]]:
        return JsonResponse({'error': 'No access'})
    if 'scheduler' not in request.session:
        return JsonResponse({'error': 'The scheduler was not found in session'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests are supported'})
    if 'tools data' not in request.POST:
        return JsonResponse({'error': 'Tools data is not specified'})
    try:
        UpdateTools(request.session['scheduler'], request.POST['tools data'])
    except Exception as e:
        logger.exception(e)
        return JsonResponse({'error': str(e)})
    return JsonResponse({})


@unparallel_group(['service'])
def set_schedulers_status(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.user.extended.role not in [USER_ROLES[2][0], USER_ROLES[4][0]]:
        return JsonResponse({'error': 'No access'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests are supported'})
    if 'statuses' not in request.POST:
        return JsonResponse({'error': 'Statuses were not got'})
    try:
        SetSchedulersStatus(request.POST['statuses'])
    except Exception as e:
        logger.exception(e)
        return JsonResponse({'error': str(e)})
    return JsonResponse({})


@login_required
def schedulers_info(request):
    activate(request.user.extended.language)
    return render(request, 'service/scheduler.html', {
        'schedulers': Scheduler.objects.all(),
        'data': NodesData()
    })


@login_required
def test(request):
    return render(request, 'service/test.html', {
        'priorities': PRIORITY,
        'jobs': Job.objects.filter(~Q(solvingprogress=None)),
        'schedulers': Scheduler.objects.all(),
        'defvals': {
            'task_description': '{"priority": "LOW"}',
            'sch_json': json.dumps(TEST_JSON),
            'solution_description': "{}",
            'nodes_data': json.dumps(TEST_NODES_DATA),
            'tools_data': json.dumps(TEST_TOOLS_DATA),
        },
        'curr_scheduler': request.session.get('scheduler', None),
        'curr_job_id': request.session.get('job id', None)
    })


@login_required
def fill_session(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests are supported'})
    for v in request.POST:
        request.session[v] = request.POST[v]
    return JsonResponse({})


@login_required
def process_job(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests are supported'})
    if 'job id' not in request.POST:
        return JsonResponse({'error': 'Job id is not specified'})
    try:
        job = Job.objects.get(pk=int(request.POST['job id']))
        request.session['job id'] = job.pk
    except ObjectDoesNotExist:
        return JsonResponse({'error': 'Job was not found'})
    except ValueError:
        return JsonResponse({'error': 'Unknown error'})

    if job.status != JOB_STATUS[1][0]:
        return JsonResponse({'error': 'Job is not PENDING'})
    change_job_status(job, JOB_STATUS[2][0])
    return JsonResponse({})


@login_required
def add_scheduler_user(request):
    activate(request.user.extended.language)
    if request.method != 'POST':
        return JsonResponse({'error': 'Unknown error'})
    if 'login' not in request.POST or len(request.POST['login']) == 0:
        return JsonResponse({'error': 'Unknown error'})
    if 'password' not in request.POST or len(request.POST['password']) == 0:
        return JsonResponse({'error': 'Unknown error'})
    try:
        sch_u = request.user.scheduleruser
    except ObjectDoesNotExist:
        sch_u = SchedulerUser()
        sch_u.user = request.user
    sch_u.login = request.POST['login']
    sch_u.password = request.POST['password']
    sch_u.save()
    return JsonResponse({})
