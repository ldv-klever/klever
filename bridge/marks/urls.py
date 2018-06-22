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

from django.urls import path, re_path
from marks import views


urlpatterns = [
    # Main marks pages
    re_path(r'^(?P<type>unsafe|safe|unknown)/(?P<pk>[0-9]+)/$', views.MarkPage.as_view(), name='mark'),
    re_path(r'^(?P<type>unsafe|safe|unknown)/association_changes/(?P<association_id>.*)/$',
            views.AssociationChangesView.as_view()),
    re_path(r'^(?P<type>unsafe|safe|unknown)/$', views.MarksListView.as_view(), name='list'),

    # Mark form
    re_path(r'^(?P<type>unsafe|safe|unknown)/(?P<pk>[0-9]+)/(?P<action>create|edit)/$',
            views.MarkFormView.as_view(), name='mark_form'),
    re_path(r'^(?P<type>unsafe|safe|unknown)/(?P<pk>[0-9]+)/(?P<action>create|edit)/inline/$',
            views.InlineMarkForm.as_view()),

    # Mark versions views
    re_path(r'^(?P<type>unsafe|safe|unknown)/(?P<pk>[0-9]+)/remove_versions/$', views.RemoveVersionsView.as_view()),
    re_path(r'^(?P<type>unsafe|safe|unknown)/(?P<pk>[0-9]+)/compare_versions/$', views.CompareVersionsView.as_view()),

    # Download/Upload marks
    re_path(r'^download/(?P<type>unsafe|safe|unknown)/(?P<pk>[0-9]+)/$',
            views.DownloadMarkView.as_view(), name='download_mark'),
    re_path(r'^download-preset/(?P<type>unsafe|safe|unknown)/(?P<pk>[0-9]+)/$',
            views.DownloadPresetMarkView.as_view(), name='download_preset_mark'),
    path('upload/', views.UploadMarksView.as_view()),
    path('download-all/', views.DownloadAllMarksView.as_view(), name='download_all'),
    path('upload-all/', views.UploadAllMarksView.as_view()),

    # Tags
    path('tags/save_tag/', views.SaveTagView.as_view()),
    re_path(r'^tags/(?P<type>unsafe|safe)/$', views.TagsTreeView.as_view(), name='tags'),
    re_path(r'^tags/(?P<type>unsafe|safe)/download/$', views.DownloadTagsView.as_view(), name='download_tags'),
    re_path(r'^tags/(?P<type>unsafe|safe)/upload/$', views.UploadTagsView.as_view()),
    re_path(r'^tags/(?P<type>unsafe|safe)/get_tag_data/$', views.TagDataView.as_view()),
    re_path(r'^tags/(?P<type>unsafe|safe)/delete/(?P<pk>[0-9]+)/$', views.RemoveTagView.as_view()),
    re_path(r'^(?P<type>unsafe|safe)/tags_data/$', views.MarkTagsView.as_view()),

    # Action with associations
    re_path(r'^association/(?P<type>unsafe|safe|unknown)/(?P<rid>[0-9]+)/(?P<mid>[0-9]+)/(?P<act>confirm|unconfirm)/$',
            views.ChangeAssociationView.as_view()),
    re_path(r'^association/(?P<type>unsafe|safe|unknown)/(?P<rid>[0-9]+)/(?P<mid>[0-9]+)/(?P<act>like|dislike)/$',
            views.LikeAssociation.as_view()),

    # Utils
    path('delete/', views.DeleteMarksView.as_view()),
    path('get_func_description/<int:pk>/', views.GetFuncDescription.as_view()),
    path('check-unknown-mark/<int:pk>/', views.CheckUnknownMarkView.as_view()),
]
