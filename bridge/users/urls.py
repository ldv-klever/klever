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

from django.urls import path
from users import views


urlpatterns = [
    path('signin/', views.user_signin, name='login'),
    path('signout/', views.user_signout, name='logout'),
    path('register/', views.register, name='register'),
    path('edit/', views.edit_profile, name='edit_profile'),
    path('profile/<int:user_id>', views.show_profile, name='show_profile'),
    path('service_signin/', views.service_signin),
    path('service_signout/', views.service_signout),
    path('ajax/save_notifications/', views.save_notifications),

    # View actions
    path('ajax/save_view/', views.save_view),
    path('ajax/remove_view/', views.remove_view),
    path('ajax/share_view/', views.share_view),
    path('ajax/preferable_view/', views.preferable_view),
    path('ajax/check_view_name/', views.check_view_name),
]
