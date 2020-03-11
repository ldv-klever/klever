#
# Copyright (c) 2019 ISP RAS (http://www.ispras.ru)
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

from django.http import HttpResponseRedirect
from django.urls import reverse
from django.views.defaults import bad_request, permission_denied, page_not_found, server_error


def index_page(request):
    if request.user.is_authenticated:
        return HttpResponseRedirect(reverse('jobs:tree'))
    return HttpResponseRedirect(reverse('users:login'))


def error_400_view(request, exception):
    return bad_request(request, exception, template_name='bridge/400.html')


def error_403_view(request, exception):
    return permission_denied(request, exception, template_name='bridge/403.html')


def error_404_view(request, exception):
    return page_not_found(request, exception, template_name='bridge/404.html')


def error_500_view(request):
    return server_error(request, template_name='bridge/500.html')
