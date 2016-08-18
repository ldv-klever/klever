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
    url(r'^ajax/change_component/$', views.change_component),
    url(r'^ajax/clear_components_table/$', views.clear_components_table),
    url(r'^ajax/delete_problem/$', views.delete_problem),
    url(r'^ajax/clear_problems/$', views.clear_problems),
    url(r'^ajax/clear_system/$', views.clear_system),
    url(r'^ajax/recalculation/$', views.recalculation),
]
