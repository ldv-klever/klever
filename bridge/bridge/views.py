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

from urllib.parse import unquote
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.utils.translation import ugettext as _, activate
from bridge.populate import Population
from bridge.vars import ERRORS, USER_ROLES
from bridge.utils import logger
from tools.profiling import unparallel_group
from users.models import Extended


def index_page(request):
    if request.user.is_authenticated():
        return HttpResponseRedirect(reverse('jobs:tree'))
    return HttpResponseRedirect(reverse('users:login'))


def klever_bridge_error(request, err_code=0, user_message=None):
    if request.user.is_authenticated():
        activate(request.user.extended.language)
    else:
        activate(request.LANGUAGE_CODE)

    err_code = int(err_code)

    back = None
    if request.method == 'GET':
        back = request.GET.get('back', None)
        if back is not None:
            back = unquote(back)

    if isinstance(user_message, str):
        message = user_message
    else:
        if err_code in ERRORS:
            message = ERRORS[err_code]
        else:
            message = _('Unknown error')

    return render(request, 'error.html', {'message': message, 'back': back})


@unparallel_group(['Job', 'MarkUnknown', 'TaskStatistic', 'Scheduler', 'Component'])
@login_required
def population(request):
    try:
        activate(request.user.extended.language)
    except ObjectDoesNotExist:
        activate(request.LANGUAGE_CODE)
    if not request.user.is_staff:
        return HttpResponseRedirect(reverse('error', args=[300]))
    need_manager = (len(Extended.objects.filter(role=USER_ROLES[2][0])) == 0)
    need_service = (len(Extended.objects.filter(role=USER_ROLES[4][0])) == 0)
    if request.method == 'POST':
        manager_username = request.POST.get('manager_username', '')
        if len(manager_username) == 0:
            manager_username = None
        service_username = request.POST.get('service_username', '')
        if len(service_username) == 0:
            service_username = None
        if need_manager and need_service and (manager_username is None or service_username is None):
            return HttpResponseRedirect(reverse('error', args=[305]))
        try:
            changes = Population(request.user, manager_username, service_username).changes
        except Exception as e:
            logger.exception(e)
            return render(request, 'Population.html', {'error': str(e)})
        else:
            return render(request, 'Population.html', {'changes': changes})
    return render(request, 'Population.html', {
        'need_manager': need_manager,
        'need_service': need_service,
    })
