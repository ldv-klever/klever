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

from django.conf.urls import url
from tools import views


urlpatterns = [
    url(r'^manager/$', views.manager_tools, name='manager'),
    url(r'^view_call_logs/$', views.view_call_logs, name='view_call_logs'),
    url(r'^ajax/rename_component/$', views.rename_component),
    url(r'^ajax/clear_components/$', views.clear_components),
    url(r'^ajax/clear_problems/$', views.clear_problems),
    url(r'^ajax/clear_system/$', views.clear_system),
    url(r'^ajax/recalculation/$', views.recalculation),
    url(r'^ajax/call_list/$', views.call_list),
    url(r'^ajax/call_stat/$', views.call_statistic),
    url(r'^ajax/clear_call_logs/$', views.clear_call_logs),
    url(r'^ajax/clear_tasks/$', views.clear_tasks),
    url(r'^manual_unlock/$', views.manual_unlock)
]
