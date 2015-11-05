import os
import mimetypes
from io import BytesIO
from django.core.urlresolvers import reverse
from django.db.models import ProtectedError
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.utils.translation import ugettext as _, activate
from Omega.vars import USER_ROLES
from reports.models import Component
from marks.models import UnknownProblem
from service.utils import *


# Case 3.2(2) DONE
def get_tasks(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.user.extended.role not in [USER_ROLES[2][0], USER_ROLES[4][0]]:
        return JsonResponse({'error': 'No access'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests are supported'})
    if 'scheduler' not in request.POST or request.POST['scheduler'] not in [x[0][1] for x in SCHEDULER_TYPE]:
        return JsonResponse({'error': 'The scheduler is not specified or is not supported'})
    if 'tasks data' not in request.POST:
        return JsonResponse({'error': 'Tasks data is required'})
    result = GetTasks(request.POST['scheduler'], request.POST['tasks data'])
    if result.error is not None:
        return JsonResponse({'error': result.error + ''})
    return JsonResponse({'tasks data': result.data})


# Case 3.3(2) DONE
def check_schedulers(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.user.extended.role not in [USER_ROLES[2][0], USER_ROLES[4][0]]:
        return JsonResponse({'error': 'No access'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests are supported'})
    if 'statuses' not in request.POST:
        return JsonResponse({'error': 'Statuses were not got'})
    result = CheckSchedulers(request.POST['statuses'])
    if result.error is not None:
        return JsonResponse({'error': result.error + ''})
    return JsonResponse({})


# Case 3.1(3) DONE
def create_task(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.user.extended.role not in [USER_ROLES[2][0], USER_ROLES[4][0]]:
        return JsonResponse({'error': 'No access'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Just POST requests are supported'})
    if 'job id' not in request.POST:
        return JsonResponse({'error': 'Job identifier is not specified'})
    if 'priority' not in request.POST:
        return JsonResponse({'error': 'Task priority is not specified'})
    if 'description' not in request.POST:
        return JsonResponse({'error': 'Task description is not specified'})
    archive = None
    for f in request.FILES.getlist('file'):
        archive = f
    if archive is None:
        return JsonResponse({
            'error': 'The task archive was not got'
        })
    result = CreateTask(request.POST['job id'], request.POST['description'],
                        archive, request.POST['priority'])
    if result.error is not None:
        return JsonResponse({'error': result.error + ''})
    return JsonResponse({'task id': result.task_id})


# Case 3.1(4) DONE
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
    return JsonResponse({'status': result.status})


# Case 3.1(5) DONE
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
    new_file = BytesIO(result.solution.archive.read())
    mimetype = mimetypes.guess_type(os.path.basename(result.solution.archname))[0]
    response = HttpResponse(new_file.read(), content_type=mimetype)
    response['Content-Disposition'] = 'attachment; filename="%s"' % result.solution.archname
    return response


# Case 3.1(6) DONE
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


# Case 3.1(7) DONE
def stop_task(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.user.extended.role not in [USER_ROLES[2][0], USER_ROLES[4][0]]:
        return JsonResponse({'error': 'No access'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Just POST requests are supported'})
    if 'task id' not in request.POST:
        return JsonResponse({'error': 'Task identifier is not specified'})
    result = StopTaskDecision(request.POST['task id'])
    if result.error is not None:
        return JsonResponse({'error': result.error + ''})
    return JsonResponse({})


# Case 3.2(3) DONE
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

    new_file = BytesIO(result.task.archive.read())
    mimetype = mimetypes.guess_type(os.path.basename(result.task.archname))[0]
    response = HttpResponse(new_file.read(), content_type=mimetype)
    response['Content-Disposition'] = 'attachment; filename="%s"' % result.task.archname
    return response


# Case 3.2(4) DONE
def create_solution(request):
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


# Case 3.2(5) DONE
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


# Case 3.2(6) DONE
def update_tools(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.user.extended.role not in [USER_ROLES[2][0], USER_ROLES[4][0]]:
        return JsonResponse({'error': 'No access'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests are supported'})
    if 'tools data' not in request.POST:
        return JsonResponse({'error': 'Tools data is not specified'})
    if 'scheduler' not in request.POST \
            or request.POST['scheduler'] not in [x[0][1] for x in SCHEDULER_TYPE]:
        return JsonResponse({'error': 'Scheduler is not specified or is not supported'})
    result = UpdateTools(request.POST['scheduler'], request.POST['tools data'])
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
    print(UserJobs(user).data)
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
def add_scheduler_user(request):
    activate(request.user.extended.language)
    if request.method != 'POST':
        return JsonResponse({'error': _('Unknown error')})
    new_login = request.POST.get('login', '')
    new_password = request.POST.get('password', '')
    if len(new_login) == 0 or len(new_password) == 0:
        return JsonResponse({'error': _('Unknown error')})
    try:
        sch_u = request.user.scheduleruser
    except ObjectDoesNotExist:
        sch_u = SchedulerUser()
        sch_u.user = request.user
    sch_u.login = new_login
    sch_u.password = new_password
    sch_u.save()
    return JsonResponse({})


@login_required
def remove_scheduler_user(request):
    activate(request.user.extended.language)
    if request.method != 'POST':
        return JsonResponse({'error': _('Unknown error')})
    try:
        sch_u = request.user.scheduleruser
    except ObjectDoesNotExist:
        return JsonResponse({'error': _("Scheduler user doesn't exists")})
    sch_u.delete()
    return JsonResponse({})


@login_required
def test(request):
    return render(request, 'service/test.html', {'priorities': PRIORITY})


@login_required
def change_component(request):
    activate(request.user.extended.language)
    if request.method != 'POST':
        return JsonResponse({'error': _('Unknown error')})
    if request.user.extended.role != USER_ROLES[2][0]:
        return JsonResponse({
            'error': _("No access")
        })
    try:
        component = Component.objects.get(
            pk=int(request.POST.get('component_id', 0)))
    except ObjectDoesNotExist:
        return JsonResponse({
            'error': _("Component was not found")
        })
    action = request.POST.get('action', '')
    if action == 'delete':
        try:
            component.delete()
        except ProtectedError:
            return JsonResponse({
                'error': _("Component is used and can't be deleted")
            })
        return JsonResponse({
            'message': _("Component was successfully deleted")
        })
    elif action == 'rename':
        new_name = request.POST.get('name', '')
        if len(new_name) == 0 or len(new_name) > 255:
            return JsonResponse({
                'error': _("New component name has wrong length")
            })
        try:
            Component.objects.get(Q(name=new_name) & ~Q(pk=component.pk))
            return JsonResponse({
                'error': _("New component name is used already")
            })
        except ObjectDoesNotExist:
            pass
        component.name = new_name
        component.save()
        return JsonResponse({
            'message': _("Component was successfully renamed")
        })
    return JsonResponse({'error': _("Unknown error")})


@login_required
def clear_components_table(request):
    activate(request.user.extended.language)
    if request.method != 'POST':
        return JsonResponse({'error': _('Unknown error')})
    if request.user.extended.role != USER_ROLES[2][0]:
        return JsonResponse({
            'error': _("No access")
        })
    for component in Component.objects.all():
        try:
            component.delete()
        except ProtectedError:
            pass
    return JsonResponse({
        'message': _("Components were cleared, please reload the page")
    })


@login_required
def delete_problem(request):
    activate(request.user.extended.language)
    if request.method != 'POST':
        return JsonResponse({'error': _('Unknown error')})
    if request.user.extended.role != USER_ROLES[2][0]:
        return JsonResponse({
            'error': _("No access")
        })
    try:
        problem = UnknownProblem.objects.get(
            pk=int(request.POST.get('problem_id', 0)))
    except ObjectDoesNotExist:
        return JsonResponse({
            'error': _("Problem was not found")
        })
    try:
        problem.delete()
    except ProtectedError:
        return JsonResponse({
            'error': _("Problem is used and can't be deleted")
        })
    return JsonResponse({
        'message': _("Problem was successfully deleted")
    })


@login_required
def clear_problems(request):
    activate(request.user.extended.language)
    if request.method != 'POST':
        return JsonResponse({'error': _('Unknown error')})
    if request.user.extended.role != USER_ROLES[2][0]:
        return JsonResponse({
            'error': _("No access")
        })
    for problem in UnknownProblem.objects.all():
        try:
            problem.delete()
        except ProtectedError:
            pass
    return JsonResponse({
        'message': _("Problems were cleared, please reload the page")
    })


@login_required
def manager_tools(request):
    return render(request, "service/ManagerPanel.html", {
        'components': Component.objects.all(),
        'problems': UnknownProblem.objects.all()
    })
