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
from jobs import views, api

router = DefaultRouter()
router.register('api-preset-job-dir', api.PresetJobAPIViewset, 'api-preset-job-dir')

urlpatterns = [
    path('api/', include(router.urls)),

    # Main pages
    path('', views.JobsTree.as_view(), name='tree'),
    path('<int:pk>/', views.JobPage.as_view(), name='job'),
    path('preset/<int:pk>/', views.PresetJobPage.as_view(), name='preset'),
    path('decision/latest/<int:job_id>/', views.LatestDecisionPage.as_view(), name='decision-latest'),
    path('decision/<int:pk>/', views.DecisionPage.as_view(), name='decision'),
    path('decision-create/<int:job_id>/', views.DecisionFormPage.as_view(), name='decision-create'),
    path('decision-copy/<int:pk>/', views.DecisionCopyFormPage.as_view(), name='decision-copy'),
    path('decision-restart/<int:pk>/', views.DecisionRestartPage.as_view(), name='decision-restart'),

    path('decision-results/<int:pk>/', views.DecisionResults.as_view(), name='decision-results'),
    path('api/decision-results/<uuid:identifier>/', api.DecisionResultsAPIView.as_view(), name='api-decision-results'),
    path('progress/<int:pk>/', views.DecisionProgress.as_view(), name='progress'),
    path('api/decision-status/', api.DecisionStatusListView.as_view(), name='api-decisions-statuses'),
    path('api/decision-status/<int:pk>/', api.DecisionStatusView.as_view(), name='api-decision-status'),
    path('comparison/<int:decision1_id>/<int:decision2_id>/', views.DecisionsFilesComparison.as_view()),

    # Main actions with jobs
    path('api/<int:pk>/remove/', api.RemoveJobView.as_view(), name='api-remove-job'),
    path('api/<int:job_id>/create-decision/', api.CreateDecisionView.as_view(), name='api-create-decision'),
    path('api/decision/<int:pk>/rename/', api.RenameDecisionView.as_view(), name='api-rename-decision'),
    path('api/decision/<int:pk>/remove/', api.RemoveDecisionView.as_view(), name='api-remove-decision'),

    # Job form
    path('form/create/<int:preset_id>/', views.CreateJobFormPage.as_view(), name='job-create-form'),
    path('form/edit/<int:pk>/', views.EditJobFormPage.as_view(), name='job-edit-form'),
    path('api/create/', api.CreateJobView.as_view(), name='api-create-job'),
    path('api/update/<int:pk>/', api.UpdateJobView.as_view(), name='api-update-job'),
    path('api/create-default-job/<uuid:identifier>/', api.CreateDefaultJobView.as_view()),

    # Actions with job files
    path('downloadfile/<slug:hash_sum>/', views.DownloadJobFileView.as_view(), name='download_file'),
    path('api/file/', api.CreateFileView.as_view()),
    path('api/file/<slug:hash_sum>/', api.FileContentView.as_view(), name='file-content'),
    path('files-diff/<slug:hashsum1>/<slug:hashsum2>/', api.GetFilesDiffView.as_view(), name='files-diff'),

    # Download/upload actions
    path('downloadjob/<int:pk>/', views.DownloadJobView.as_view(), name='download'),
    path('api/downloadjob/<uuid:identifier>/', api.DownloadJobByUUIDView.as_view(), name='api-download'),
    path('downloadjobs/', views.DownloadJobsListView.as_view(), name='download-jobs'),
    path('api/upload_jobs/', api.UploadJobsAPIView.as_view(), name='api-upload-jobs'),
    path('uploading-status/', views.JobsUploadingStatus.as_view(), name='uploading-status'),
    path('api/uploading-status/', api.UploadStatusAPIView.as_view(), name='api-uploading-status'),

    # Actions with job solving
    path('download-configuration/<int:pk>/', views.DownloadConfigurationView.as_view(), name='download-decision-conf'),
    path('api/configuration/', api.GetConfigurationView.as_view(), name='api-configuration'),
    path('api/conf-def-value/', api.StartJobDefValueView.as_view(), name='api-def-start-value'),

    path('api/decide/<int:pk>/', api.StartDefaultDecisionView.as_view(), name='api-decide'),
    path('api/decide-uuid/<uuid:identifier>/', api.StartDefaultDecisionView.as_view(), name='api-decide-uuid'),

    path('api/restart-decision/<int:pk>/', api.RestartDecisionView.as_view(), name='api-restart-decision'),
    path('api/decision/stop/<int:pk>/', api.StopDecisionView.as_view(), name='api-cancel-decision'),
    path('api/download-files/<uuid:identifier>/', api.CoreDecisionArchiveView.as_view()),

    # "Utils"
    path('decision/svcomp-files/<int:pk>/', views.DownloadFilesForCompetition.as_view(), name='svcomp-files'),
    path('api/can-download/', api.CheckDownloadAccessView.as_view(), name='api-can-download'),
    path('api/collapse/<int:pk>/', api.CollapseReportsView.as_view(), name='api-collapse-reports'),
    path('api/coverage/<int:pk>/', api.GetJobCoverageTableView.as_view(), name='api-get-coverage'),
]
