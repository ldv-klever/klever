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

from django.conf import settings
from django.contrib.auth import authenticate, login, logout, models
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned, ValidationError
from django.db.models import Q
from django.http import HttpResponseRedirect, JsonResponse, HttpResponse
from django.middleware.csrf import get_token
from django.shortcuts import render, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.utils.translation import ugettext as _, activate
from django.utils.timezone import pytz
from django.views.generic import CreateView, UpdateView

from rest_framework.generics import ListAPIView

from tools.profiling import unparallel_group
from bridge.vars import LANGUAGES, SCHEDULER_TYPE, UNKNOWN_ERROR, VIEW_TYPES
from bridge.utils import logger

from jobs.models import Job
from jobs.models import JobHistory
from jobs.utils import JobAccess
from marks.models import MarkSafeHistory, MarkUnsafeHistory, MarkUnknownHistory

from users.forms import BridgeAuthForm, RegisterForm, EditProfileForm, SchedulerUserForm
from users.models import User, DataView, PreferableView, SchedulerUser


class BridgeLoginView(LoginView):
    template_name = 'users/login.html'
    success_url = reverse_lazy('jobs:tree')
    authentication_form = BridgeAuthForm


class BridgeLogoutView(LogoutView):
    next_page = 'users:login'


class UserRegisterView(CreateView):
    form_class = RegisterForm
    success_url = reverse_lazy('users:login')
    template_name = 'users/register.html'


class EditProfileView(LoginRequiredMixin, UpdateView):
    form_class = EditProfileForm
    template_name = 'users/edit-profile.html'
    success_url = reverse_lazy('users:edit_profile')

    def get_object(self, queryset=None):
        return self.request.user

    def get_sch_form(self):
        sch_kwargs = {'initial': {}, 'prefix': 'sch'}
        if self.request.method in ('POST', 'PUT'):
            sch_kwargs.update({'data': self.request.POST})
        if hasattr(self, 'object'):
            try:
                sch_inst = SchedulerUser.objects.get(user=self.object)
            except SchedulerUser.DoesNotExist:
                sch_inst = SchedulerUser(user=self.object)
            sch_kwargs.update({'instance': sch_inst})
        return SchedulerUserForm(**sch_kwargs)

    def get_context_data(self, **kwargs):
        if 'sch_form' not in kwargs:
            kwargs['sch_form'] = self.get_sch_form()
        return super().get_context_data(**kwargs)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        sch_form = self.get_sch_form()
        if form.is_valid() and sch_form.is_valid():
            self.object = form.save()
            sch_form.save()
            return HttpResponseRedirect(self.get_success_url())
        else:
            return self.render_to_response(self.get_context_data(form=form, sch_form=sch_form))


class JobChangesView(ListAPIView):
    def get_queryset(self):
        return JobHistory.objects.filter(change_author_id=self.kwargs['user_id']).select_related('job')


@login_required
@unparallel_group([])
def show_profile(request, user_id):
    activate(request.user.language)
    target = get_object_or_404(User, pk=user_id)

    activity = []
    for act in JobHistory.objects.filter(change_author=target).order_by('-change_date')[:30]:
        act_comment = act.comment
        small_comment = act_comment
        if len(act_comment) > 50:
            small_comment = act_comment[:47] + '...'
        if act.version == 1:
            act_type = _('Creation')
            act_color = '#58bd2a'
        else:
            act_type = _('Modification')
            act_color = '#31e6ff'
        new_act = {
            'date': act.change_date,
            'comment': act_comment,
            'small_comment': small_comment,
            'act_type': act_type,
            'act_color': act_color,
            'obj_type': _('Job'),
            'obj_link': act.job.name
        }
        if JobAccess(request.user, act.job).can_view():
            new_act['href'] = reverse('jobs:job', args=[act.job_id])
        activity.append(new_act)
    for act in MarkSafeHistory.objects.filter(author=target).order_by('-change_date')[:30]:
        act_comment = act.comment
        small_comment = act_comment
        if len(act_comment) > 50:
            small_comment = act_comment[:47] + '...'
        if act.version == 1:
            act_type = _('Creation')
            act_color = '#58bd2a'
        else:
            act_type = _('Modification')
            act_color = '#31e6ff'
        activity.append({
            'date': act.change_date,
            'comment': act_comment,
            'small_comment': small_comment,
            'act_type': act_type,
            'act_color': act_color,
            'obj_type': _('Safes mark'),
            'obj_link': act.mark.identifier,
            'href': reverse('marks:mark', args=['safe', act.mark_id]),
        })
    for act in MarkUnsafeHistory.objects.filter(author=target).order_by('-change_date')[:30]:
        act_comment = act.comment
        small_comment = act_comment
        if len(act_comment) > 47:
            small_comment = act_comment[:50] + '...'
        if act.version == 1:
            act_type = _('Creation')
            act_color = '#58bd2a'
        else:
            act_type = _('Modification')
            act_color = '#31e6ff'
        activity.append({
            'date': act.change_date,
            'comment': act_comment,
            'small_comment': small_comment,
            'act_type': act_type,
            'act_color': act_color,
            'obj_type': _('Unsafes mark'),
            'obj_link': act.mark.identifier,
            'href': reverse('marks:mark', args=['unsafe', act.mark_id])
        })
    for act in MarkUnknownHistory.objects.filter(author=target).order_by('-change_date')[:30]:
        act_comment = act.comment
        small_comment = act_comment
        if len(act_comment) > 50:
            small_comment = act_comment[:47] + '...'
        if act.version == 1:
            act_type = _('Creation')
            act_color = '#58bd2a'
        else:
            act_type = _('Modification')
            act_color = '#31e6ff'
        activity.append({
            'date': act.change_date,
            'comment': act_comment,
            'small_comment': small_comment,
            'act_type': act_type,
            'act_color': act_color,
            'obj_type': _('Unknowns mark'),
            'obj_link': act.mark.identifier,
            'href': reverse('marks:mark', args=['unknown', act.mark_id])
        })
    return render(request, 'users/showProfile.html', {
        'target': target,
        'activity': list(reversed(sorted(activity, key=lambda x: x['date'])))[:50],
    })


@unparallel_group(['User'])
def service_signin(request):
    if request.method != 'POST':
        get_token(request)
        return HttpResponse('')
    username = request.POST.get('username')
    password = request.POST.get('password')
    for p in request.POST:
        if p == 'job identifier':
            try:
                request.session['job id'] = Job.objects.get(identifier__startswith=request.POST[p]).pk
            except ObjectDoesNotExist:
                return JsonResponse({
                    'error': 'The job with specified identifier "%s" was not found' % request.POST[p]
                })
            except MultipleObjectsReturned:
                return JsonResponse({'error': 'The specified job identifier is not unique'})
        elif p == 'scheduler':
            for s in SCHEDULER_TYPE:
                if s[1] == request.POST[p]:
                    request.session['scheduler'] = s[0]
                    break
            else:
                return JsonResponse({
                    'error': 'The specified scheduler "%s" is not supported' % request.POST[p]
                })

    user = authenticate(username=username, password=password)
    if user is None:
        return JsonResponse({'error': 'Incorrect username or password'})
    if not user.is_active:
        return JsonResponse({'error': 'Account has been disabled'})
    try:
        Extended.objects.get(user=user)
    except ObjectDoesNotExist:
        return JsonResponse({'error': 'User does not have extended data'})
    login(request, user)
    return HttpResponse('')


@unparallel_group([])
def service_signout(request):
    logout(request)
    return HttpResponse('')


@unparallel_group([PreferableView, 'View'])
def preferable_view(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': _('You are not signing in')})
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': str(UNKNOWN_ERROR)})

    view_id = request.POST.get('view_id', None)
    view_type = request.POST.get('view_type', None)
    if view_id is None or view_type is None or view_type not in set(x[0] for x in VIEW_TYPES):
        return JsonResponse({'error': str(UNKNOWN_ERROR)})

    if view_id == 'default':
        pref_views = request.user.preferableview_set.filter(view__type=view_type)
        if len(pref_views):
            pref_views.delete()
            return JsonResponse({'message': _("The default view was made preferred")})
        return JsonResponse({'error': _("The default view is already preferred")})

    try:
        user_view = View.objects.get(Q(id=view_id, type=view_type) & (Q(author=request.user) | Q(shared=True)))
    except ObjectDoesNotExist:
        return JsonResponse({'error': _("The view was not found")})
    request.user.preferableview_set.filter(view__type=view_type).delete()
    PreferableView.objects.create(user=request.user, view=user_view)
    return JsonResponse({'message': _("The preferred view was successfully changed")})


@unparallel_group(['View'])
def check_view_name(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': _('You are not signing in')})
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': str(UNKNOWN_ERROR)})

    view_name = request.POST.get('view_title', None)
    view_type = request.POST.get('view_type', None)
    if view_name is None or view_type is None:
        return JsonResponse({'error': str(UNKNOWN_ERROR)})

    if view_name == '':
        return JsonResponse({'error': _("The view name is required")})

    if view_name == str(_('Default')) or request.user.view_set.filter(type=view_type, name=view_name).count():
        return JsonResponse({'error': _("Please choose another view name")})
    return JsonResponse({})


@unparallel_group([DataView])
def save_view(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': _('You are not signing in')})
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': str(UNKNOWN_ERROR)})

    view_data = request.POST.get('view', None)
    view_name = request.POST.get('title', '')
    view_id = request.POST.get('view_id', None)
    view_type = request.POST.get('view_type', None)
    if view_data is None or view_type is None or view_type not in list(x[0] for x in VIEW_TYPES):
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    if view_id == 'default':
        return JsonResponse({'error': _("You can't edit the default view")})
    elif view_id is not None:
        try:
            new_view = request.user.view_set.get(pk=int(view_id))
        except ObjectDoesNotExist:
            return JsonResponse({'error': _("The view was not found or you don't have an access to it")})
    elif len(view_name) > 0:
        new_view = View(name=view_name, type=view_type, author=request.user)
    else:
        return JsonResponse({'error': _('The view name is required')})
    new_view.view = view_data
    new_view.save()
    return JsonResponse({
        'view_id': new_view.id, 'view_name': new_view.name,
        'message': _("The view was successfully saved")
    })


@unparallel_group([DataView])
def remove_view(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': _('You are not signing in')})
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': str(UNKNOWN_ERROR)})

    v_id = request.POST.get('view_id', 0)
    view_type = request.POST.get('view_type', None)
    if view_type is None:
        return JsonResponse({'error': str(UNKNOWN_ERROR)})
    if v_id == 'default':
        return JsonResponse({'error': _("You can't remove the default view")})
    try:
        View.objects.get(id=v_id, author=request.user, type=view_type).delete()
    except ObjectDoesNotExist:
        return JsonResponse({'error': _("The view was not found or you don't have an access to it")})
    return JsonResponse({'message': _("The view was successfully removed")})


@unparallel_group([DataView])
def share_view(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': _('You are not signing in')})
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'error': 'Unknown error'})

    v_id = request.POST.get('view_id', 0)
    view_type = request.POST.get('view_type', None)
    if view_type is None:
        return JsonResponse({'error': 'Unknown error'})
    if v_id == 'default':
        return JsonResponse({'error': _("You can't share the default view")})
    try:
        view = View.objects.get(author=request.user, pk=v_id, type=view_type)
    except ObjectDoesNotExist:
        return JsonResponse({'error': _("The view was not found or you don't have an access to it")})
    view.shared = not view.shared
    view.save()
    if view.shared:
        return JsonResponse({'message': _("The view was successfully shared")})
    PreferableView.objects.filter(view=view).exclude(user=request.user).delete()
    return JsonResponse({'message': _("The view was hidden from other users")})
