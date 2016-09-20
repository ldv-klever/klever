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
from users import views


urlpatterns = [
    url(r'^signin/$', views.user_signin, name='login'),
    url(r'^signout/$', views.user_signout, name='logout'),
    url(r'^register/$', views.register, name='register'),
    url(r'^edit/$', views.edit_profile, name='edit_profile'),
    url(r'^profile/(?P<user_id>[0-9]+)$', views.show_profile, name='show_profile'),
    url(r'^service_signin/$', views.service_signin),
    url(r'^service_signout/$', views.service_signout),
    url(r'^ajax/save_notifications/$', views.save_notifications),
]
