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

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from users import views, api

router = DefaultRouter()
router.register('views', api.DataViewAPIViewSet, 'views')

urlpatterns = [
    path('signin/', views.BridgeLoginView.as_view(), name='login'),
    path('signout/', views.BridgeLogoutView.as_view(), name='logout'),

    path('register/', views.UserRegisterView.as_view(), name='register'),
    path('edit/', views.EditProfileView.as_view(), name='edit-profile'),
    path('profile/<int:user_id>/', views.UserProfileView.as_view(), name='show-profile'),

    # Views
    path('', include(router.urls)),
    path('views/<int:view_id>/prefer/', api.PreferViewAPIView.as_view()),
    path('views/prefer-default/<slug:view_type>/', api.PreferViewAPIView.as_view()),
]
