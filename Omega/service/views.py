# from django.shortcuts import render
from django.http import JsonResponse
from jobs.utils import JobAccess
from service.utils import *


def init_session(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Just POST requests are supported'})
    if 'session id' not in request.POST:
        return JsonResponse({'error': 'Session identifier is not specified'})
    if 'job id' not in request.POST:
        return JsonResponse({'error': 'Job identifier is not specified'})
    if 'planners' not in request.POST:
        return JsonResponse({'error': 'Planners are not specified'})
    if 'max priority' not in request.POST:
        return JsonResponse({'error': 'Max priority is not specified'})

    try:
        planners = list(json.loads(request.POST['planners']))
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
    InitSession(request.user, job, request.POST['max priority'], planners)
    return JsonResponse('OK')


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
        if f.content_type == 'application/x-tar-gz':
            archive = f
        elif f.content_type == 'application/json':
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
        return JsonResponse({'error': 'Task priority is not specified'})
    return JsonResponse({'task id': task_creation.task_id})
