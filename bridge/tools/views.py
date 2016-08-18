#
# Copyright (c) 2014-2015 ISPRAS (http://www.ispras.ru)
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

from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.translation import ugettext as _, activate
from bridge.vars import USER_ROLES
from bridge.utils import unparallel_group
from tools.utils import *


@login_required
def manager_tools(request):
    activate(request.user.extended.language)
    return render(request, "tools/ManagerPanel.html", {
        'components': Component.objects.all(),
        'problems': UnknownProblem.objects.all(),
        'jobs': Job.objects.all()
    })


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


@unparallel_group(['report', 'job', 'mark', 'task', 'solution'])
@login_required
def clear_system(request):
    activate(request.user.extended.language)
    if request.method != 'POST':
        return JsonResponse({'error': _('Unknown error')})
    if request.user.extended.role != USER_ROLES[2][0]:
        return JsonResponse({'error': _("No access")})
    clear_files()
    clear_service_files()
    clear_computers()
    return JsonResponse({'message': _("All unused files and DB rows were deleted")})


@unparallel_group(['report', 'job', 'mark'])
@login_required
def recalculation(request):
    activate(request.user.extended.language)
    if request.method != 'POST':
        return JsonResponse({'error': 'Unknown error'})
    if request.user.extended.role != USER_ROLES[2][0]:
        return JsonResponse({'error': _("No access")})
    if 'type' not in request.POST:
        return JsonResponse({'error': 'Unknown error'})
    res = Recalculation(request.POST['type'], request.POST.get('jobs', None))
    if res.error is not None:
        return JsonResponse({'error': res.error + ''})
    return JsonResponse({'message': _("Caches were successfully recalculated")})
