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

from django.urls import path
from tools import views


urlpatterns = [
    path('manager/', views.manager_tools, name='manager'),
    path('view_call_logs/', views.view_call_logs, name='view_call_logs'),
    path('processing_list/', views.processing_list, name='processing_list'),
    path('ajax/rename_component/', views.rename_component),
    path('ajax/clear_components/', views.clear_components),
    path('ajax/clear_problems/', views.clear_problems),
    path('ajax/clear_system/', views.clear_system),
    path('ajax/recalculation/', views.recalculation),
    path('ajax/call_list/', views.call_list),
    path('ajax/call_stat/', views.call_statistic),
    path('ajax/clear_call_logs/', views.clear_call_logs),
    path('ajax/clear_tasks/', views.clear_tasks),
    path('manual_unlock/', views.manual_unlock)
]
