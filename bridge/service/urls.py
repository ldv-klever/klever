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

from django.urls import path, include
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter

from service import views

router = DefaultRouter()
router.register('task', views.TaskAPIViewset, 'task')

urlpatterns = [
    path('', include(router.urls)),
    path('signin/', obtain_auth_token),

    # TESTS
    path('test/', views.test, name='test'),
    path('ajax/fill_session/', views.fill_session),
    path('ajax/process_job/', views.process_job),

    path('set_schedulers_status/', views.set_schedulers_status),
    path('get_jobs_and_tasks/', views.get_jobs_and_tasks),
    path('schedule_task/', views.schedule_task),

    path('update_tools/', views.UpdateToolsAPIView.as_view()),


    path('get_tasks_statuses/', views.get_tasks_statuses),
    path('remove_task/', views.remove_task),
    path('cancel_task/', views.cancel_task),
    path('upload_solution/', views.upload_solution),
    path('download_solution/', views.download_solution),
    path('download_task/', views.download_task),
    path('update_nodes/', views.update_nodes),
    path('update_progress/', views.update_progress),
    path('schedulers/', views.schedulers_info, name='schedulers'),
    path('ajax/add_scheduler_user/', views.add_scheduler_user)
]
