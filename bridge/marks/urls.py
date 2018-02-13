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

from django.urls import path, re_path
from marks import views


urlpatterns = [
    re_path(r'^(?P<mark_type>unsafe|safe|unknown)/create/(?P<report_id>[0-9]+)/$', views.create_mark, name='create_mark'),
    re_path(r'^(?P<mark_type>unsafe|safe|unknown)/edit/(?P<mark_id>[0-9]+)/$', views.edit_mark, name='edit_mark'),
    re_path(r'^(?P<mark_type>unsafe|safe|unknown)/view/(?P<mark_id>[0-9]+)/$', views.view_mark, name='view_mark'),
    re_path(r'^(?P<marks_type>unsafe|safe|unknown)/$', views.mark_list, name='mark_list'),
    re_path(r'^download/(?P<mark_type>unsafe|safe|unknown)/(?P<mark_id>[0-9]+)/$',
            views.download_mark, name='download_mark'),
    path('association_changes/<slug:association_id>/', views.association_changes),
    re_path(r'^tags/(?P<tags_type>unsafe|safe)/$', views.show_tags, name='tags'),
    re_path(r'^tags/download/(?P<tags_type>unsafe|safe)/$', views.download_tags, name='download_tags'),

    # For ajax requests
    path('ajax/delete/', views.delete_marks),
    path('ajax/save_mark/', views.save_mark),
    path('ajax/upload_marks/', views.upload_marks),
    path('ajax/get_func_description/', views.get_func_description),
    path('ajax/inline_mark_form/', views.get_inline_mark_form),
    path('ajax/check-unknown-mark/', views.check_unknown_mark),

    path('ajax/get_mark_version_data/', views.get_mark_version_data),
    path('ajax/getversions/', views.get_mark_versions),
    path('ajax/remove_versions/', views.remove_versions),

    path('ajax/get_tag_data/', views.get_tag_data),
    path('ajax/save_tag/', views.save_tag),
    path('ajax/remove_tag/', views.remove_tag),
    path('ajax/get_tags_data/', views.get_tags_data),
    path('ajax/upload_tags/', views.upload_tags),

    path('ajax/confirm-association/', views.confirm_association),
    path('ajax/unconfirm-association/', views.unconfirm_association),
    path('ajax/like-association/', views.like_association),

    # For service requests
    path('download-all/', views.download_all, name='download_all'),
    path('upload-all/', views.upload_all, name='upload_all'),
]
