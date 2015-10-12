from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from jobs.utils import JobAccess
from service.utils import *


def init_session(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Just POST requests are supported'})
    if 'job id' not in request.POST:
        return JsonResponse({'error': 'Job identifier is not specified'})
    if 'schedulers' not in request.POST:
        return JsonResponse({'error': 'Schedulers are not specified'})
    if 'max priority' not in request.POST:
        return JsonResponse({'error': 'Max priority is not specified'})
    if 'verifier name' not in request.POST:
        return JsonResponse({'error': 'Verifier name is not specified'})
    if 'verifier version' not in request.POST:
        return JsonResponse({'error': 'Verifier version is not specified'})

    try:
        schedulers = list(json.loads(request.POST['schedulers']))
    except Exception as e:
        return JsonResponse({'error': e})

    try:
        job = Job.objects.get(identifier__startswith=request.POST['job id'])
    except ObjectDoesNotExist:
        return JsonResponse({
            'error': 'Job with the specified identifier "{0}" was not found'
            .format(request.POST['job id'])})
    except MultipleObjectsReturned:
        return JsonResponse({
            'error': 'Specified identifier "{0}" is not unique'
            .format(request.POST['job id'])})

    if job.status != '1':
        return JsonResponse({'error': 'The specified job is not solving yet'})
    if not JobAccess(request.user, job).service_access():
        return JsonResponse({
            'error': 'User "{0}" has not access to job "{1}"'.format(
                request.user, job.identifier
            )
        })
    result = InitSession(job, request.POST['max priority'], schedulers,
                         request.POST['verifier name'],
                         request.POST['verifier version'])
    if result.error is not None:
        return JsonResponse({'error': result.error})
    return JsonResponse({'session id': result.jobsession.pk})


def close_session(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Just POST requests are supported'})
    if 'session id' not in request.POST:
        return JsonResponse({'error': 'Session identifier is not specified'})
    result = CloseSession(session_id=request.POST.get('session id', '0'))
    if result.error is not None:
        return JsonResponse({'error': result.error})
    return JsonResponse({})


def create_task(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Just POST requests are supported'})
    if 'session id' not in request.POST:
        return JsonResponse({'error': 'Session identifier is not specified'})
    if 'priority' not in request.POST:
        return JsonResponse({'error': 'Task priority is not specified'})
    archive = None
    description = None
    for f in request.FILES.getlist('file'):
        if f.content_type == 'application/gzip':
            archive = f
        else:
            description = f
    if archive is None:
        return JsonResponse({
            'error': 'The task archive was not got or has incorrect type'
        })
    if description is None:
        return JsonResponse({
            'error': 'The task description was not got or has incorrect type'
        })
    task_creation = CreateTask(request.POST['session id'], description, archive,
                               request.POST['priority'])
    if task_creation.error is not None:
        return JsonResponse({'error': task_creation.error})
    return JsonResponse({'task id': task_creation.task_id})


def add_scheduler(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests are supported'})
    scheduler_name = request.POST.get('scheduler name', '')
    scheduler_key = request.POST.get('scheduler key', '')
    need_auth = request.POST.get('need auth', None)
    if need_auth is None:
        return JsonResponse({'error': 'Wrong argument - need auth'})
    try:
        need_auth = bool(int(need_auth))
    except ValueError:
        return JsonResponse({'error': 'Wrong argument - need auth'})
    result = AddScheduler(scheduler_name, scheduler_key, need_auth)
    if result.error is not None:
        return JsonResponse({'error': result.error})
    return JsonResponse({})


def get_scheduler_login_data(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests are supported'})
    try:
        scheduler = Scheduler.objects.get(pk=int(request.POST.get('sch_id', 0)))
    except ObjectDoesNotExist:
        return JsonResponse({'error': 'Scheduler was not found'})
    if not scheduler.need_auth:
        return JsonResponse({
            'error': 'This scheduler does not need authentification'
        })
    if len(scheduler.scheduleruser_set.filter(user=request.user)) > 0:
        login_data = scheduler.scheduleruser_set.filter(user=request.user)[0]
        return JsonResponse({
            'login': login_data.login,
            'password': login_data.password,
            'max_priority': login_data.get_max_priority_display()
        })
    return JsonResponse({})


def add_scheduler_login_data(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests are supported'})
    new_login = request.POST.get('login', '')
    new_password = request.POST.get('password', '')
    max_priority = request.POST.get('max_priority', None)
    if len(new_login) == 0 or len(new_password) == 0 \
            or all(x[0] != max_priority for x in PRIORITY):
        return JsonResponse({
            'error': 'Login, password or max priority was not got'
        })
    try:
        scheduler = Scheduler.objects.get(pk=int(request.POST.get('sch_id', 0)))
    except ObjectDoesNotExist:
        return JsonResponse({'error': 'Scheduler was not found'})
    if not scheduler.need_auth:
        return JsonResponse({
            'error': 'This scheduler does not need authentification'
        })
    if len(scheduler.scheduleruser_set.filter(user=request.user)) > 0:
        login_data = scheduler.scheduleruser_set.filter(user=request.user)[0]
        login_data.login = new_login
        login_data.password = new_password
        login_data.max_priority = max_priority
        login_data.save()
        return JsonResponse({
            'login': login_data.login,
            'password': login_data.password
        })
    login_data = SchedulerUser.objects.create(
        login=new_login, password=new_password,
        max_priority=max_priority, scheduler=scheduler, user=request.user
    )
    return JsonResponse({
        'login': login_data.login,
        'password': login_data.password
    })


@login_required
def remove_sch_logindata(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests are supported'})
    try:
        scheduler = Scheduler.objects.get(pk=int(request.POST.get('sch_id', 0)))
    except ObjectDoesNotExist:
        return JsonResponse({'error': 'Scheduler was not found'})
    if not scheduler.need_auth:
        return JsonResponse({
            'error': 'This scheduler does not need authentification'
        })
    scheduler.scheduleruser_set.filter(user=request.user).delete()
    return JsonResponse({})


def get_tasks(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests are supported'})
    sch_key = request.POST.get('scheduler key', '')
    if len(sch_key) == 0 or len(sch_key) > 12:
        return JsonResponse({
            'error': 'Scheduler key is required or has wrong length'
        })
    try:
        scheduler = Scheduler.objects.get(pkey=sch_key)
    except ObjectDoesNotExist:
        return JsonResponse({'error': 'Scheduler was not found'})
    result = GetTasks(scheduler, request.POST.get('tasks list', '{}'))
    if result.error is not None:
        print(result.error)
        return JsonResponse({'error': result.error})
    return JsonResponse({'tasks list': result.data})


def clear_sessions(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests are supported'})
    try:
        num_of_hours = float(request.POST.get('hours', ''))
    except ValueError:
        return JsonResponse({'error': 'Wrong parameter'})
    delete_old_sessions(num_of_hours)
    return JsonResponse({})


def check_schedulers(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests are supported'})
    change_schedulers_status()
    return JsonResponse({})


def close_sessions(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests are supported'})
    try:
        num_of_minutes = float(request.POST.get('minutes', ''))
    except ValueError:
        return JsonResponse({'error': 'Wrong parameter'})
    close_old_active_sessions(num_of_minutes)
    return JsonResponse({})


@login_required
def test(request):
    return render(request, 'service/test.html', {'priorities': PRIORITY})
