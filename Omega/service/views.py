import os
import mimetypes
from io import BytesIO
from urllib.parse import unquote
from django.core.urlresolvers import reverse
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.utils.translation import ugettext as _, activate
from service.utils import *


# Case 3.1.2 (7)
def update_tools(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests are supported'})
    try:
        tools_data = json.loads(request.POST.get('tools data', ''))
    except ValueError:
        return JsonResponse({'error': 'Tools data was not got or incorrect'})
    sch_key = request.POST.get('scheduler key', '')
    if len(sch_key) == 0 or len(sch_key) > 12:
        return JsonResponse({
            'error': 'Scheduler key is required or has wrong length'
        })
    result = UpdateTools(sch_key, tools_data)
    if result.error is not None:
        return JsonResponse({'error': result.error + ''})
    return JsonResponse({})


# Case 3.1.1 (8)
def close_session(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Just POST requests are supported'})
    if 'job id' not in request.POST:
        return JsonResponse({'error': 'Job identifier is not specified'})
    try:
        job = Job.objects.get(identifier=request.POST['job id'])
    except ObjectDoesNotExist:
        return JsonResponse({'error': 'Job was not found'})
    if not JobAccess(request.user, job).service_access():
        return JsonResponse({
            'error': 'User "{0}" has not access to job "{1}"'.format(
                request.user, job.identifier
            )
        })
    result = CloseSession(job)
    if result.error is not None:
        return JsonResponse({'error': result.error + ''})
    return JsonResponse({})


# Case 3.1.2 (2)
def add_scheduler(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests are supported'})
    scheduler_name = request.POST.get('scheduler name', '')
    scheduler_key = request.POST.get('scheduler key', '')
    need_auth = request.POST.get('need auth', None)
    for_jobs = request.POST.get('for jobs', None)
    if need_auth is None:
        return JsonResponse({'error': '"need auth" is required'})
    if for_jobs is None:
        return JsonResponse({'error': '"for jobs" is required'})
    try:
        need_auth = bool(int(need_auth))
    except ValueError:
        return JsonResponse({'error': 'Wrong argument - "need auth"'})
    try:
        for_jobs = bool(int(for_jobs))
    except ValueError:
        return JsonResponse({'error': 'Wrong argument - "for jobs"'})
    result = AddScheduler(scheduler_name, scheduler_key, need_auth, for_jobs)
    if result.error is not None:
        return JsonResponse({'error': result.error + ''})
    return JsonResponse({})


# Case 3.1.2 (3)
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
        return JsonResponse({'error': result.error + ''})
    return JsonResponse({'tasks list': result.data})


# Case 3.1,3 (2)
def clear_sessions(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests are supported'})
    try:
        num_of_hours = float(request.POST.get('hours', ''))
    except ValueError:
        return JsonResponse({'error': 'Wrong parameter - "hours"'})
    delete_old_sessions(num_of_hours)
    return JsonResponse({})


# Case 3.1.3 (1)
def check_schedulers(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests are supported'})
    try:
        minutes = float(request.POST.get('waiting time', ''))
    except ValueError:
        return JsonResponse({'error': 'Wrong argument: "waiting time"'})
    try:
        statuses = json.loads(request.POST.get('statuses', ''))
    except ValueError:
        return JsonResponse({'error': 'Wrong argument: "statuses"'})
    CheckSchedulers(minutes, statuses)
    return JsonResponse({})


# Case 3.1.3 (3)
def close_sessions(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests are supported'})
    try:
        num_of_minutes = float(request.POST.get('minutes', ''))
    except ValueError:
        return JsonResponse({'error': 'Wrong parameter - "minutes"'})
    close_old_active_sessions(num_of_minutes)
    return JsonResponse({})


# Case 3.1.1 (3)
def create_task(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Just POST requests are supported'})
    if 'job id' not in request.POST:
        return JsonResponse({'error': 'Job identifier is not specified'})
    if 'priority' not in request.POST:
        return JsonResponse({'error': 'Task priority is not specified'})
    if 'description' not in request.POST:
        return JsonResponse({'error': 'Description is not specified'})
    try:
        job = Job.objects.get(identifier=request.POST['job id'])
    except ObjectDoesNotExist:
        return JsonResponse({'error': 'Job was not found'})
    try:
        jobsession = job.jobsession
    except ObjectDoesNotExist:
        return JsonResponse({'error': 'Job session was not found'})
    if not JobAccess(request.user, job).service_access():
        return JsonResponse({
            'error': 'User "{0}" has not access to job "{1}"'.format(
                request.user, job.identifier
            )
        })
    archive = None
    for f in request.FILES.getlist('file'):
        archive = f
    if archive is None:
        return JsonResponse({
            'error': 'The task archive was not got'
        })
    result = CreateTask(jobsession, request.POST['description'],
                        archive, request.POST['priority'])
    if result.error is not None:
        return JsonResponse({'error': result.error + ''})
    return JsonResponse({'task id': result.task_id})


# Case 3.1.1 (4)
def get_task_status(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Just POST requests are supported'})
    if 'task id' not in request.POST:
        return JsonResponse({'error': 'Task identifier is not specified'})
    try:
        task = Task.objects.get(pk=int(request.POST['task id']))
    except ObjectDoesNotExist:
        return JsonResponse({'error': 'Task was not found'})
    except ValueError:
        return JsonResponse({'error': 'Task identifier is not integer'})
    if not JobAccess(request.user, task.job_session.job).service_access():
        return JsonResponse({
            'error': 'User "{0}" has not access to job "{1}"'.format(
                request.user, task.job_session.job.identifier
            )
        })
    result = GetTaskStatus(task)
    if result.error is not None:
        return JsonResponse({'error': result.error + ''})
    return JsonResponse({'status': result.status})


# Case 3.1.1 (5)
def download_solution(request, task_id):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.method != 'GET':
        return JsonResponse({'error': 'Just GET requests are supported'})
    try:
        task = Task.objects.get(pk=int(task_id))
    except ObjectDoesNotExist:
        return JsonResponse({'error': 'Task was not found'})

    if not JobAccess(request.user, task.job_session.job).service_access():
        return JsonResponse({
            'error': 'User "{0}" has not access to job "{1}"'.format(
                request.user, task.job_session.job.identifier
            )
        })

    result = GetSolution(task)
    if result.error is not None:
        return JsonResponse({'error': result.error + ''})

    new_file = BytesIO(result.files.source.read())
    mimetype = mimetypes.guess_type(os.path.basename(result.files.name))[0]
    response = HttpResponse(new_file.read(), content_type=mimetype)
    response['Content-Disposition'] = 'attachment; filename="%s"' \
                                      % result.files.name
    return response


# Case 3.1.1 (6)
def remove_task(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Just POST requests are supported'})
    if 'task id' not in request.POST:
        return JsonResponse({'error': 'Task identifier is not specified'})

    try:
        task = Task.objects.get(pk=int(request.POST['task id']))
    except ObjectDoesNotExist:
        return JsonResponse({'error': 'Task was not found'})
    except ValueError:
        return JsonResponse({'error': 'Task identifier is not integer'})
    if not JobAccess(request.user, task.job_session.job).service_access():
        return JsonResponse({
            'error': 'User "{0}" has not access to job "{1}"'.format(
                request.user, task.job_session.job.identifier
            )
        })
    result = RemoveTask(task)
    if result.error is not None:
        return JsonResponse({'error': result.error + ''})
    return JsonResponse({})


# Case 3.1.1 (7)
def stop_task(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Just POST requests are supported'})
    if 'task id' not in request.POST:
        return JsonResponse({'error': 'Task identifier is not specified'})

    try:
        task = Task.objects.get(pk=int(request.POST['task id']))
    except ObjectDoesNotExist:
        return JsonResponse({'error': 'Task was not found'})
    except ValueError:
        return JsonResponse({'error': 'Task identifier is not integer'})
    if not JobAccess(request.user, task.job_session.job).service_access():
        return JsonResponse({
            'error': 'User "{0}" has not access to job "{1}"'.format(
                request.user, task.job_session.job.identifier
            )
        })

    result = StopTaskDecision(task)
    if result.error is not None:
        return JsonResponse({'error': result.error + ''})
    return JsonResponse({})


# Case 3.1.2 (4)
def download_task(request, task_id):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.method != 'GET':
        return JsonResponse({'error': 'Just GET requests are supported'})
    sch_key = unquote(request.GET.get('key', ''))
    if not (0 < len(sch_key) <= 12):
        return JsonResponse({'error': 'Wrong length of key'})
    result = GetTaskData(task_id, sch_key)
    if result.error is not None:
        return JsonResponse({'error': result.error + ''})

    new_file = BytesIO(result.task.files.source.read())
    mimetype = mimetypes.guess_type(os.path.basename(result.task.files.name))[0]
    response = HttpResponse(new_file.read(), content_type=mimetype)
    response['Content-Disposition'] = 'attachment; filename="%s"' \
                                      % result.task.files.name
    return response


# Case 3.1.2 (5)
def create_solution(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Just POST requests are supported'})
    if 'task id' not in request.POST:
        return JsonResponse({'error': 'Task identifier is not specified'})
    if 'scheduler key' not in request.POST:
        return JsonResponse({'error': 'Scheduler key is not specified'})
    try:
        task_id = int(request.POST['task id'])
    except ValueError:
        return JsonResponse({'error': 'Task id is wrong'})
    archive = None
    for f in request.FILES.getlist('file'):
        archive = f
    if archive is None:
        return JsonResponse({
            'error': 'The solution archive was not got'
        })
    result = SaveSolution(task_id, request.POST['scheduler key'], archive,
                          request.POST.get('description', None))
    if result.error is not None:
        return JsonResponse({'error': result.error + ''})
    return JsonResponse({})


# Case 3.1.2 (6)
def update_nodes(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Just POST requests are supported'})
    if 'scheduler key' not in request.POST:
        return JsonResponse({'error': 'Task identifier is not specified'})
    if 'nodes data' not in request.POST:
        return JsonResponse({'error': 'Nodes data is not specified'})
    result = SetNodes(request.POST['scheduler key'], request.POST['nodes data'])
    if result.error is not None:
        return JsonResponse({'error': result.error + ''})
    return JsonResponse({})


@login_required
def user_jobs(request, user_id):
    activate(request.user.extended.language)
    try:
        user = User.objects.get(pk=int(user_id))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('error', args=[904]))
    except Exception as e:
        print(e)
        return HttpResponseRedirect(reverse('error', args=[500]))
    return render(request, 'service/jobs.html', {
        'data': UserJobs(user).data,
        'target': user
    })


@login_required
def update_user_jobs(request, user_id):
    activate(request.user.extended.language)
    try:
        user = User.objects.get(pk=int(user_id))
    except ObjectDoesNotExist:
        return JsonResponse({'error': "User was not found"})
    except Exception as e:
        print(e)
        return JsonResponse({'error': "Unknown error"})
    return render(request, 'service/jobs_table.html',
                  {'data': UserJobs(user).data})


@login_required
def scheduler_table(request, scheduler_id):
    activate(request.user.extended.language)
    try:
        scheduler = Scheduler.objects.get(pk=int(scheduler_id))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('error', args=[905]))
    except Exception as e:
        print(e)
        return HttpResponseRedirect(reverse('error', args=[500]))
    return render(request, 'service/scheduler.html', {
        'data': SchedulerTable(scheduler)
    })


@login_required
def sessions_page(request):
    activate(request.user.extended.language)
    return render(request, 'service/sessions.html', {
        'data': SessionsTable().data
    })


@login_required
def scheduler_sessions(request):
    activate(request.user.extended.language)
    if request.method != 'POST':
        return JsonResponse({'error': _('Unknown error')})
    try:
        jobsession = JobSession.objects.get(
            pk=int(request.POST.get('session_id', 0)))
    except ObjectDoesNotExist:
        return JsonResponse({'error': _('The job session was not found')})
    return render(request, 'service/schedulerSessions.html', {
        'data': SchedulerSessionsTable(jobsession)
    })


@login_required
def scheduler_job_sessions(request):
    activate(request.user.extended.language)
    if request.method != 'POST':
        return JsonResponse({'error': _('Unknown error')})
    try:
        scheduler = Scheduler.objects.get(
            pk=int(request.POST.get('scheduler_id', 0)))
    except ObjectDoesNotExist:
        return JsonResponse({'error': _('The job session was not found')})
    return render(request, 'service/schedulerJobSessions.html', {
        'data': SchedulerJobSessionsTable(scheduler)
    })


@login_required
def get_scheduler_login_data(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': _('Unknown error')})
    try:
        scheduler = Scheduler.objects.get(pk=int(request.POST.get('sch_id', 0)))
    except ObjectDoesNotExist:
        return JsonResponse({'error': _('Scheduler was not found')})
    if not scheduler.need_auth:
        return JsonResponse({
            'error': _('This scheduler does not need authentification')
        })
    if len(scheduler.scheduleruser_set.filter(user=request.user)) > 0:
        login_data = scheduler.scheduleruser_set.filter(user=request.user)[0]
        return JsonResponse({
            'login': login_data.login,
            'password': login_data.password,
            'max_priority': login_data.get_max_priority_display()
        })
    return JsonResponse({})


@login_required
def add_scheduler_login_data(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': _('Unknown error')})
    new_login = request.POST.get('login', '')
    new_password = request.POST.get('password', '')
    max_priority = request.POST.get('max_priority', None)
    if len(new_login) == 0 or len(new_password) == 0 \
            or all(x[0] != max_priority for x in PRIORITY):
        return JsonResponse({
            'error': _('Login, password or max priority was not got')
        })
    try:
        scheduler = Scheduler.objects.get(pk=int(request.POST.get('sch_id', 0)))
    except ObjectDoesNotExist:
        return JsonResponse({'error': _('Scheduler was not found')})
    if not scheduler.need_auth:
        return JsonResponse({
            'error': _('This scheduler does not need authentification')
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
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': _('Unknown error')})
    try:
        scheduler = Scheduler.objects.get(pk=int(request.POST.get('sch_id', 0)))
    except ObjectDoesNotExist:
        return JsonResponse({'error': _('Scheduler was not found')})
    if not scheduler.need_auth:
        return JsonResponse({
            'error': _('This scheduler does not need authentification')
        })
    scheduler.scheduleruser_set.filter(user=request.user).delete()
    return JsonResponse({})


@login_required
def test(request):
    return render(request, 'service/test.html', {'priorities': PRIORITY})
