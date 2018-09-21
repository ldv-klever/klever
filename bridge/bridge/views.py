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

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import ugettext as _, activate

from tools.profiling import unparallel_group
from bridge.vars import USER_ROLES, UNKNOWN_ERROR
from bridge.utils import logger, BridgeErrorResponse, BridgeException
from bridge.populate import Population

from users.models import Extended
from marks.models import MarkSafe, MarkUnsafe, MarkUnknown
from reports.models import AttrName


def index_page(request):
    if request.user.is_authenticated:
        return HttpResponseRedirect(reverse('jobs:tree'))
    return HttpResponseRedirect(reverse('users:login'))


@unparallel_group(['Job', 'Scheduler', 'MarkUnsafeCompare', 'MarkUnsafeConvert',
                   MarkSafe, MarkUnsafe, MarkUnknown, AttrName])
@login_required
def population(request):
    try:
        activate(request.user.extended.language)
    except ObjectDoesNotExist:
        activate(request.LANGUAGE_CODE)
    if not request.user.extended or request.user.extended.role != USER_ROLES[2][0]:
        return BridgeErrorResponse(_("You don't have an access to this page"))
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
            return BridgeErrorResponse(_("Can't populate without Manager and service user"))
        try:
            changes = Population(
                request.user,
                (manager_username, request.POST.get('manager_password')),
                (service_username, request.POST.get('service_password'))
            ).changes
        except BridgeException as e:
            return render(request, 'Population.html', {'error': str(e)})
        except Exception as e:
            logger.exception(e)
            return render(request, 'Population.html', {'error': str(UNKNOWN_ERROR)})
        return render(request, 'Population.html', {'changes': changes})
    return render(request, 'Population.html', {'need_manager': need_manager, 'need_service': need_service})
