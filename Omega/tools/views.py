from django.db.models import Q, ProtectedError
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.translation import ugettext as _, activate
from Omega.vars import USER_ROLES
from Omega.utils import unparallel_group
from reports.models import Component
from marks.models import UnknownProblem
from tools.utils import *


@unparallel_group(['report'])
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
            'message': _("The component was successfully deleted")
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


@unparallel_group(['report'])
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
        'message': _("All unused components were deleted, please reload the page")
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
        'message': _("The problem was successfully deleted")
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
        'message': _("All unused problems were deleted, please reload the page")
    })


@login_required
def manager_tools(request):
    activate(request.user.extended.language)
    return render(request, "tools/ManagerPanel.html", {
        'components': Component.objects.all(),
        'problems': UnknownProblem.objects.all()
    })


@unparallel_group(['report', 'job', 'mark', 'task', 'solution'])
@login_required
def clear_system(request):
    activate(request.user.extended.language)
    if request.method != 'POST':
        return JsonResponse({'error': _('Unknown error')})
    if request.user.extended.role != USER_ROLES[2][0]:
        return JsonResponse({'error': _("No access")})
    clear_job_files()
    clear_service_files()
    clear_resorces()
    clear_computers()
    return JsonResponse({'message': _("All unused files and DB rows were deleted")})
