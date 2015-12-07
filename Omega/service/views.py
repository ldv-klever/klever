import os
import mimetypes
from urllib.parse import quote
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.utils.translation import activate
from Omega.vars import USER_ROLES
from Omega.utils import unparallel_group, unparallel
from service.utils import *
from service.test import *


# Case 3.1(3)
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
    result = ScheduleTask(request.session['job id'], request.POST['description'], archive)
    if result.error is not None:
        return JsonResponse({'error': result.error + ''})
    return JsonResponse({'task id': result.task_id})


# Case 3.1(4)
def get_task_status(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.user.extended.role not in [USER_ROLES[2][0], USER_ROLES[4][0]]:
        return JsonResponse({'error': 'No access'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Just POST requests are supported'})
    if 'task id' not in request.POST:
        return JsonResponse({'error': 'Task identifier is not specified'})
    result = GetTaskStatus(request.POST['task id'])
    if result.error is not None:
        return JsonResponse({'error': result.error + ''})
    return JsonResponse({'task status': result.status})


# Case 3.1(5)
@unparallel_group(['solution'])
def download_solution(request, task_id):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.user.extended.role not in [USER_ROLES[2][0], USER_ROLES[4][0]]:
        return JsonResponse({'error': 'No access'})
    if request.method != 'GET':
        return JsonResponse({'error': 'Just GET requests are supported'})

    result = GetSolution(task_id)
    if result.error is not None:
        return JsonResponse({'error': result.error + ''})
    if result.task.status == TASK_STATUS[3][0]:
        return JsonResponse({'task error': result.task.error})
    mimetype = mimetypes.guess_type(os.path.basename(result.solution.archname))[0]
    response = HttpResponse(result.solution.archive.read(), content_type=mimetype)
    response['Content-Disposition'] = 'attachment; filename="%s"' % quote(result.solution.archname)
    return response


# Case 3.1(6)
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

    result = RemoveTask(request.POST['task id'])
    if result.error is not None:
        return JsonResponse({'error': result.error + ''})
    return JsonResponse({})


# Case 3.1(7)
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
    result = CancelTask(request.POST['task id'])
    if result.error is not None:
        return JsonResponse({'error': result.error + ''})
    return JsonResponse({})


# Case 3.2(2)
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
    result = GetTasks(request.session['scheduler'], request.POST['jobs and tasks status'])
    if result.error is not None:
        return JsonResponse({'error': result.error + ''})
    return JsonResponse({'jobs and tasks status': result.data})


# Case 3.2(3)
@unparallel_group(['service'])
def download_task(request, task_id):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.user.extended.role not in [USER_ROLES[2][0], USER_ROLES[4][0]]:
        return JsonResponse({'error': 'No access'})
    if request.method != 'GET':
        return JsonResponse({'error': 'Just GET requests are supported'})
    result = GetTaskData(task_id)
    if result.error is not None:
        return JsonResponse({'error': result.error + ''})

    mimetype = mimetypes.guess_type(os.path.basename(result.task.archname))[0]
    response = HttpResponse(result.task.archive.read(), content_type=mimetype)
    response['Content-Disposition'] = 'attachment; filename="%s"' % quote(result.task.archname)
    return response


# Case 3.2(4)
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
    result = SaveSolution(request.POST['task id'], archive, request.POST['description'])
    if result.error is not None:
        return JsonResponse({'error': result.error + ''})
    return JsonResponse({})


# Case 3.2(5)
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

    result = SetNodes(request.POST['nodes data'])
    if result.error is not None:
        return JsonResponse({'error': result.error + ''})
    return JsonResponse({})


# Case 3.2(6)
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
    result = UpdateTools(request.session['scheduler'], request.POST['tools data'])
    if result.error is not None:
        return JsonResponse({'error': result.error + ''})
    return JsonResponse({})


# Case 3.3(2)
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
    result = SetSchedulersStatus(request.POST['statuses'])
    if result.error is not None:
        return JsonResponse({'error': result.error + ''})
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
        return JsonResponse({'error': 'Job identifier is not specified'})
    try:
        job = Job.objects.get(pk=int(request.POST['job id']))
        request.session['job id'] = job.pk
    except ObjectDoesNotExist:
        return JsonResponse({'error': 'Job was not found'})
    except ValueError:
        return JsonResponse({'error': 'Unknown error'})

    if job.status != JOB_STATUS[1][0]:
        return JsonResponse({'error': 'Job is not PENDING'})
    job.status = JOB_STATUS[2][0]
    job.save()
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
