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

from django.urls import path, re_path, include
from rest_framework import routers
from marks import views, api

router = routers.DefaultRouter()
router.register('safe', api.MarkSafeViewSet, 'api-safe')
router.register('unsafe', api.MarkUnsafeViewSet, 'api-unsafe')
router.register('unknown', api.MarkUnknownViewSet, 'api-unknown')
router.register('tags/safe', api.SafeTagViewSet, 'api-tags-safe')
router.register('tags/unsafe', api.UnsafeTagViewSet, 'api-tags-unsafe')


urlpatterns = [
    path('api/', include(router.urls)),

    # Safe marks
    path('safe/', views.SafeMarksListView.as_view(), name='safe-list'),
    path('safe/<int:pk>/', views.SafeMarkPage.as_view(), name='safe'),
    path('safe/<int:pk>/edit/', views.SafeMarkEditView.as_view(), name='safe-edit'),
    path('safe/<int:pk>/create/', views.SafeMarkCreateView.as_view(), name='safe-create'),
    path('safe/<int:mark_id>/edit/inl/', api.InlineEditForm.as_view(mtype='safe'), name="safe-edit-inl"),
    path('safe/<int:r_id>/create/inl/', api.InlineCreateForm.as_view(mtype='safe'), name="safe-create-inl"),
    path('safe/association-changes/<uuid:cache_id>/', views.SafeAssChangesView.as_view(),
         name='safe-ass-changes'),
    path('api/remove-safe-marks/', api.RemoveSafeMarksView.as_view(), name='api-remove-marks-safe'),

    # Unsafe marks
    path('unsafe/', views.UnsafeMarksListView.as_view(), name='unsafe-list'),
    path('unsafe/<int:pk>/', views.UnsafeMarkPage.as_view(), name='unsafe'),
    path('unsafe/<int:pk>/edit/', views.UnsafeMarkEditView.as_view(), name='unsafe-edit'),
    path('unsafe/<int:pk>/create/', views.UnsafeMarkCreateView.as_view(), name='unsafe-create'),
    path('unsafe/<int:mark_id>/edit/inl/', api.InlineEditForm.as_view(mtype='unsafe'), name="unsafe-edit-inl"),
    path('unsafe/<int:r_id>/create/inl/', api.InlineCreateForm.as_view(mtype='unsafe'), name="unsafe-create-inl"),
    path('unsafe/association-changes/<uuid:cache_id>/', views.UnsafeAssChangesView.as_view(),
         name='unsafe-ass-changes'),
    path('api/remove-unsafe-marks/', api.RemoveUnsafeMarksView.as_view(), name='api-remove-marks-unsafe'),

    path('api/get-updated-preset/<uuid:identifier>/', api.GetUpdatedPresetView.as_view(),
         name='api-updated-unsafe-preset'),

    # Unknown marks
    path('unknown/', views.UnknownMarksListView.as_view(), name='unknown-list'),
    path('unknown/<int:pk>/', views.UnknownMarkPage.as_view(), name='unknown'),
    path('unknown/<int:pk>/edit/', views.UnknownMarkEditView.as_view(), name='unknown-edit'),
    path('unknown/<int:pk>/create/', views.UnknownMarkCreateView.as_view(), name='unknown-create'),
    path('unknown/<int:mark_id>/edit/inl/', api.InlineEditForm.as_view(mtype='unknown'), name="unknown-edit-inl"),
    path('unknown/<int:r_id>/create/inl/', api.InlineCreateForm.as_view(mtype='unknown'), name="unknown-create-inl"),
    path('unknown/association-changes/<uuid:cache_id>/', views.UnknownAssChangesView.as_view(),
         name='unknown-ass-changes'),
    path('api/remove-unknown-marks/', api.RemoveUnknownMarksView.as_view(), name='api-remove-marks-unknown'),
    path('api/check-unknown-function/<int:report_id>/', api.CheckUnknownFuncView.as_view(), name='api-check-problem'),

    # Tags
    re_path(r'^api/tags-access/(?P<tag_type>safe|unsafe)/(?P<tag_id>[0-9]+)/$', api.TagAccessView.as_view()),
    re_path(r'^api/tags-upload/(?P<tag_type>safe|unsafe)/$', api.UploadTagsView.as_view(), name='tags-upload'),
    re_path(r'^api/tags-data/(?P<tag_type>unsafe|safe)/$', views.MarkTagsView.as_view(), name='api-tags-data'),
    re_path(r'^tags-download/(?P<tag_type>unsafe|safe)/$', views.DownloadTagsView.as_view(), name='tags-download'),

    # Mark versions views
    path('safe/<int:pk>/compare-versions/<int:v1>/<int:v2>/', views.SafeCompareVersionsView.as_view()),
    path('unsafe/<int:pk>/compare-versions/<int:v1>/<int:v2>/', views.UnsafeCompareVersionsView.as_view()),
    path('unknown/<int:pk>/compare-versions/<int:v1>/<int:v2>/', views.UnknownCompareVersionsView.as_view()),
    path('api/safe/<int:pk>/remove-versions/', api.SafeRmVersionsView.as_view(), name='api-rm-vers-safe'),
    path('api/unsafe/<int:pk>/remove-versions/', api.UnsafeRmVersionsView.as_view(), name='api-rm-vers-unsafe'),
    path('api/unknown/<int:pk>/remove-versions/', api.UnknownRmVersionsView.as_view(), name='api-rm-vers-unknown'),

    # Download/Upload marks
    path('safe/<int:pk>/download/', views.DownloadSafeMarkView.as_view(), name='safe-download'),
    path('unsafe/<int:pk>/download/', views.DownloadUnsafeMarkView.as_view(), name='unsafe-download'),
    path('unknown/<int:pk>/download/', views.DownloadUnknownMarkView.as_view(), name='unknown-download'),
    path('download-marks-list/', views.DownloadSeveralMarksView.as_view(), name='download-marks-list'),

    path('safe/<int:pk>/download-preset/', views.PresetSafeMarkView.as_view(), name='safe-download-preset'),
    path('unsafe/<int:pk>/download-preset/', views.PresetUnsafeMarkView.as_view(), name='unsafe-download-preset'),
    path('unknown/<int:pk>/download-preset/', views.PresetUnknownMarkView.as_view(), name='unknown-download-preset'),
    path('api/download-all/', api.DownloadAllMarksView.as_view(), name='api-download-all'),
    path('upload/', api.UploadMarksView.as_view(), name='upload'),
    path('upload-all/', api.UploadAllMarksView.as_view(), name='upload-all'),

    # Tags
    re_path(r'^tags/(?P<type>unsafe|safe)/$', views.TagsTreeView.as_view(), name='tags'),

    # Actions with associations
    path('api/ass-confirmation/safe/<int:pk>/', api.ConfirmSafeMarkView.as_view(), name='api-confirm-safe'),
    path('api/ass-confirmation/unsafe/<int:pk>/', api.ConfirmUnsafeMarkView.as_view(), name='api-confirm-unsafe'),
    path('api/ass-confirmation/unknown/<int:pk>/', api.ConfirmUnknownMarkView.as_view(), name='api-confirm-unknown'),
    path('api/ass-like/safe/<int:pk>/', api.LikeSafeMark.as_view(), name='api-like-safe'),
    path('api/ass-like/unsafe/<int:pk>/', api.LikeUnsafeMark.as_view(), name='api-like-unsafe'),
    path('api/ass-like/unknown/<int:pk>/', api.LikeUnknownMark.as_view(), name='api-like-unknown'),
]
