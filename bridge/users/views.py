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

import json

from django.conf import settings
from django.contrib.auth import authenticate, login, logout, models
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned, ValidationError
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect, JsonResponse, HttpResponse
from django.middleware.csrf import get_token
from django.shortcuts import render, get_object_or_404
from django.utils.translation import ugettext as _, activate
from django.utils.timezone import pytz

from tools.profiling import unparallel_group
from bridge.vars import LANGUAGES, SCHEDULER_TYPE, UNKNOWN_ERROR
from bridge.utils import logger
from bridge.populate import extend_user

from jobs.models import Job

from users.forms import UserExtendedForm, UserForm, EditUserForm
from users.models import Notifications, Extended, User


@unparallel_group(['User'])
def user_signin(request):
    activate(request.LANGUAGE_CODE)
    if not isinstance(request.user, models.AnonymousUser):
        logout(request)
    if request.method != 'POST':
        return render(request, 'users/login.html')
    user = authenticate(username=request.POST.get('username'), password=request.POST.get('password'))
    if user is None:
        return render(request, 'users/login.html', {'login_errors': _("Incorrect username or password")})
    if not user.is_active:
        return render(request, 'users/login.html', {'login_errors': _("Account has been disabled")})
    login(request, user)
    try:
        Extended.objects.get(user=user)
    except ObjectDoesNotExist:
        extend_user(user)
    if Job.objects.count() == 0 and user.is_staff:
        return HttpResponseRedirect(reverse('population'))
    next_url = request.POST.get('next_url')
    if next_url is not None and next_url != '':
        return HttpResponseRedirect(next_url)
    return HttpResponseRedirect(reverse('jobs:tree'))


def user_signout(request):
    logout(request)
    return HttpResponseRedirect(reverse('users:login'))


def register(request):
    activate(request.LANGUAGE_CODE)
    if not isinstance(request.user, models.AnonymousUser):
        logout(request)

    if request.method == 'POST':
        user_form = UserForm(data=request.POST)
        profile_form = UserExtendedForm(data=request.POST)
        user_tz = request.POST.get('timezone')
        if user_form.is_valid() and profile_form.is_valid():
            user = user_form.save()
            user.set_password(user.password)
            profile = profile_form.save(commit=False)
            profile.user = user
            if user_tz:
                profile.timezone = user_tz
            try:
                profile.save()
            except:
                raise ValidationError("Can't save user to the database!")
            user.save()
            return HttpResponseRedirect(reverse('users:login'))
    else:
        user_form = UserForm()
        profile_form = UserExtendedForm()

    return render(request, 'users/register.html', {
        'user_form': user_form,
        'profile_form': profile_form,
        'timezones': pytz.common_timezones,
        'def_timezone': settings.DEF_USER['timezone']
    })


@login_required
@unparallel_group([User])
def edit_profile(request):
    activate(request.user.extended.language)

    if request.method == 'POST':
        user_form = EditUserForm(data=request.POST, request=request, instance=request.user)
        profile_form = UserExtendedForm(data=request.POST, instance=request.user.extended)
        user_tz = request.POST.get('timezone')
        if user_form.is_valid() and profile_form.is_valid():
            user = user_form.save(commit=False)
            new_pass = request.POST.get('new_password')
            do_redirect = False
            if len(new_pass) > 0:
                user.set_password(new_pass)
                do_redirect = True
            user.save()
            profile = profile_form.save(commit=False)
            profile.user = user
            if user_tz:
                profile.timezone = user_tz
            profile.save()
            if 'sch_login' in request.POST and 'sch_password' in request.POST:
                if len(request.POST['sch_login']) > 0 and len(request.POST['sch_password']) > 0:
                    from service.models import SchedulerUser
                    try:
                        sch_user = SchedulerUser.objects.get(user=request.user)
                    except ObjectDoesNotExist:
                        sch_user = SchedulerUser()
                        sch_user.user = request.user
                    sch_user.login = request.POST['sch_login']
                    sch_user.password = request.POST['sch_password']
                    sch_user.save()
                elif len(request.POST['sch_login']) == 0:
                    try:
                        request.user.scheduleruser.delete()
                    except ObjectDoesNotExist:
                        pass

            if do_redirect:
                return HttpResponseRedirect(reverse('users:login'))
            else:
                return HttpResponseRedirect(reverse('users:edit_profile'))
    else:
        user_form = EditUserForm(instance=request.user)
        profile_form = UserExtendedForm(instance=request.user.extended)

    from users.notifications import NotifyData
    return render(
        request,
        'users/edit-profile.html',
        {
            'user_form': user_form,
            'tdata': NotifyData(request.user),
            'profile_form': profile_form,
            'profile_errors': profile_form.errors,
            'user_errors': user_form.errors,
            'timezones': pytz.common_timezones,
            'LANGUAGES': LANGUAGES
        })


@login_required
@unparallel_group([])
def show_profile(request, user_id):
    activate(request.user.extended.language)
    target = get_object_or_404(User, pk=user_id)
    from jobs.models import JobHistory
    from jobs.utils import JobAccess
    from marks.models import MarkSafeHistory, MarkUnsafeHistory, MarkUnknownHistory

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
            'obj_link': act.name
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
            'href': reverse('marks:view_mark', args=['safe', act.mark_id]),
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
            'href': reverse('marks:view_mark', args=['unsafe', act.mark_id])
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
            'href': reverse('marks:view_mark', args=['unknown', act.mark_id])
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


@login_required
@unparallel_group([Notifications])
def save_notifications(request):
    activate(request.user.extended.language)
    if request.method == 'POST':
        try:
            new_ntf = request.user.notifications
        except ObjectDoesNotExist:
            new_ntf = Notifications()
            new_ntf.user = request.user
        try:
            new_ntf.self_ntf = json.loads(request.POST.get('self_ntf', 'false'))
        except Exception as e:
            logger.error("Can't parse json: %s" % e, stack_info=True)
            return JsonResponse({'error': str(UNKNOWN_ERROR)})
        new_ntf.settings = request.POST.get('notifications', '[]')
        new_ntf.save()
        return JsonResponse({'message': _('Saved')})
    return JsonResponse({'error': str(UNKNOWN_ERROR)})
