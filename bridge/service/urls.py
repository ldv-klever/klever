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
from service import views


urlpatterns = [
    # TESTS
    url(r'^test/$', views.test, name='test'),
    url(r'^ajax/fill_session/$', views.fill_session),
    url(r'^ajax/process_job/$', views.process_job),

    url(r'^set_schedulers_status/$', views.set_schedulers_status),
    url(r'^get_jobs_and_tasks/$', views.get_jobs_and_tasks),
    url(r'^schedule_task/$', views.schedule_task),
    url(r'^update_tools/$', views.update_tools),
    url(r'^get_tasks_statuses/$', views.get_tasks_statuses),
    url(r'^remove_task/$', views.remove_task),
    url(r'^cancel_task/$', views.cancel_task),
    url(r'^upload_solution/$', views.upload_solution),
    url(r'^download_solution/$', views.download_solution),
    url(r'^download_task/$', views.download_task),
    url(r'^update_nodes/$', views.update_nodes),
    url(r'^update_progresses/$', views.update_progresses),
    url(r'^schedulers/$', views.schedulers_info, name='schedulers'),
    url(r'^ajax/add_scheduler_user/$', views.add_scheduler_user)
]
