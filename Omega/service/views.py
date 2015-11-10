import os
import mimetypes
from io import BytesIO
from django.db.models import ProtectedError, Q
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.utils.translation import ugettext as _, activate
from Omega.vars import USER_ROLES
from reports.models import Component
from marks.models import UnknownProblem
from service.utils import *
from service.test import *


# Case 3.1(3) DONE
def schedule_task(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.user.extended.role not in [USER_ROLES[2][0], USER_ROLES[4][0]]:
        return JsonResponse({'error': 'No access'})
    if 'job_id' not in request.session:
        return JsonResponse({'error': 'Session does not have job identifier'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Just POST requests are supported'})
    if 'description' not in request.POST:
        return JsonResponse({'error': 'Task description is not specified'})
    archive = None
    for f in request.FILES.getlist('file'):
        archive = f
    if archive is None:
        return JsonResponse({
            'error': 'The task archive was not got'
        })
    result = ScheduleTask(request.session['job_id'], request.POST['description'], archive)
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
    return JsonResponse({'task status': result.status})


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


# Case 3.2(2) DONE
def get_jobs_and_tasks(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.user.extended.role not in [USER_ROLES[2][0], USER_ROLES[4][0]]:
        return JsonResponse({'error': 'No access'})
    if 'scheduler' not in request.session:
        return JsonResponse({'error': 'The scheduler was not found in session'})
    if request.session['scheduler'] not in [x[1] for x in SCHEDULER_TYPE]:
        return JsonResponse({
            'error': "The scheduler '%s' is not supported" % request.session['scheduler']
        })
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests are supported'})
    if 'jobs and tasks status' not in request.POST:
        return JsonResponse({'error': 'Tasks data is required'})
    result = GetTasks(request.session['scheduler'], request.POST['jobs and tasks status'])
    if result.error is not None:
        return JsonResponse({'error': result.error + ''})
    return JsonResponse({'jobs and tasks status': result.data})


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
    if 'scheduler' not in request.session:
        return JsonResponse({'error': 'The scheduler was not found in session'})
    if request.session['scheduler'] not in [x[1] for x in SCHEDULER_TYPE]:
        return JsonResponse({
            'error': "The scheduler '%s' is not supported" % request.session['scheduler']
        })
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests are supported'})
    if 'tools data' not in request.POST:
        return JsonResponse({'error': 'Tools data is not specified'})
    result = UpdateTools(request.session['scheduler'], request.POST['tools data'])
    if result.error is not None:
        return JsonResponse({'error': result.error + ''})
    return JsonResponse({})


# Case 3.3(2) DONE
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
    return render(request, 'service/scheduler.html', {
        'schedulers': Scheduler.objects.all(),
        'data': NodesData()
    })

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
            'error': _("The component was not found")
        })
    action = request.POST.get('action', '')
    if action == 'delete':
        try:
            component.delete()
        except ProtectedError:
            return JsonResponse({
                'error': _("The component is used and can't be deleted")
            })
        return JsonResponse({
            'message': _("The component was successfully deleted, please, reload the page")
        })
    elif action == 'rename':
        new_name = request.POST.get('name', '')
        if len(new_name) == 0 or len(new_name) > 15:
            return JsonResponse({
                'error': _("The component name should be greater than 0 and less than 16 symbols")
            })
        try:
            Component.objects.get(Q(name=new_name) & ~Q(pk=component.pk))
            return JsonResponse({
                'error': _("The specified component name is used already")
            })
        except ObjectDoesNotExist:
            pass
        component.name = new_name
        component.save()
        return JsonResponse({
            'message': _("The component was successfully renamed")
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
        'message': _("All unused components were deleted, please, reload the page")
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
            'error': _("The problem was not found")
        })
    try:
        problem.delete()
    except ProtectedError:
        return JsonResponse({
            'error': _("The problem is used and can't be deleted")
        })
    return JsonResponse({
        'message': _("The problem was successfully deleted, please, reload the page")
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
        'message': _("All unused problems were deleted, please, reload the page")
    })


@login_required
def manager_tools(request):
    return render(request, "service/ManagerPanel.html", {
        'components': Component.objects.all(),
        'problems': UnknownProblem.objects.all()
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
        'curr_job_id': request.session.get('job_id', None)
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
    for v in request.POST:
        request.session[v] = request.POST[v]
    if 'job_id' not in request.POST:
        return JsonResponse({'error': 'Job identifier is not specified'})
    try:
        job = Job.objects.get(identifier=request.session.get('job_id', 'null'))
    except ObjectDoesNotExist:
        return JsonResponse({'error': 'Job was not found'})

    if job.status != JOB_STATUS[1][0]:
        return JsonResponse({'error': 'Job is not PENDING'})
    job.status = JOB_STATUS[2][0]
    job.save()
    return JsonResponse({})
