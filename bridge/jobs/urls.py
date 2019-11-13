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
from jobs import views, api


urlpatterns = [
    # Main pages
    path('', views.JobsTree.as_view(), name='tree'),
    path('<int:pk>/', views.JobPage.as_view(), name='job'),
    path('decision-results/<int:pk>/', views.DecisionResults.as_view(), name='decision-results'),
    path('progress/<int:pk>/', views.JobProgress.as_view(), name='progress'),
    path('api/job-status/', api.JobStatusListView.as_view(), name='api-jobs-statuses'),
    path('api/job-status/<int:pk>/', api.JobStatusView.as_view(), name='api-job-status'),
    path('comparison/<int:job1_id>/<int:job2_id>/', views.JobsFilesComparison.as_view(), name='comparison'),

    # Main actions with jobs
    path('api/<int:pk>/remove/', api.RemoveJobView.as_view(), name='api-remove-job'),
    path('api/duplicate/', api.DuplicateJobView.as_view(), name='api-duplicate-job'),
    path('api/duplicate/<int:pk>/', api.DuplicateJobView.as_view(), name='api-duplicate-version'),

    path('api/decision-results/<int:pk>/', api.DecisionResultsView.as_view(), name='api-decision-results'),

    # Job form
    re_path(r'^form/(?P<pk>[0-9]+)/(?P<action>edit|copy)/$', views.JobFormPage.as_view(), name='form'),
    path('form/preset/<uuid:preset_uuid>/', views.PresetFormPage.as_view(), name='preset-form'),
    path('api/create/', api.CreateJobView.as_view(), name='api-create-job'),
    path('api/update/<int:pk>/', api.UpdateJobView.as_view(), name='api-update-job'),
    path('api/job-version/<int:job_id>/<int:version>/', api.JobVersionView.as_view(), name='api-job-version'),
    path('api/preset-data/<uuid:preset_uuid>/', api.PresetFormDataView.as_view(), name='api-preset-data'),

    # Actions with job files
    path('downloadfile/<slug:hash_sum>/', views.DownloadJobFileView.as_view(), name='download_file'),
    path('api/file/', api.CreateFileView.as_view()),
    path('api/file/<slug:hash_sum>/', api.FileContentView.as_view(), name='file-content'),

    path('get_files_diff/<slug:hashsum1>/<slug:hashsum2>/', api.GetFilesDiffView.as_view(), name='files-diff'),
    path('api/replace-job-file/', api.ReplaceJobFileView.as_view()),
    path('svcomp-files/<int:pk>/', views.DownloadFilesForCompetition.as_view(), name='svcomp-files'),

    # Download/upload actions
    path('downloadjob/<int:pk>/', views.DownloadJobView.as_view(), name='download'),
    path('downloadjobs/', views.DownloadJobsListView.as_view(), name='download-jobs'),
    path('downloadtrees/', views.DownloadJobsTreeView.as_view(), name='download-trees'),
    path('api/upload_jobs/', api.UploadJobsAPIView.as_view(), name='api-upload-jobs'),
    path('api/upload_jobs_tree/', api.UploadJobsTreeAPIView.as_view(), name='api-upload-tree'),

    # Actions with job versions
    path('api/remove-versions/<int:job_id>/', api.RemoveJobVersions.as_view(), name='api-remove-versions'),
    path('api/compare-versions/<int:pk>/<int:version1>/<int:version2>/', api.CompareJobVersionsView.as_view()),

    # Actions with job solving
    path('prepare-decision/<int:pk>/', views.PrepareDecisionView.as_view(), name='prepare-decision'),
    path('download-configuration/<int:pk>/', views.DownloadRunConfigurationView.as_view(), name='download-conf'),
    path('api/configuration/', api.GetConfigurationView.as_view(), name='api-configuration'),
    path('api/conf-def-value/', api.StartJobDefValueView.as_view(), name='api-def-start-value'),
    path('api/decide/<int:job_id>/', api.StartDecisionView.as_view(), name='api-decide'),
    path('api/stop/<int:job_id>/', api.StopDecisionView.as_view(), name='api-cancel-decision'),
    path('api/download-files/<uuid:identifier>/', api.CoreJobArchiveView.as_view()),

    # "Utils"
    path('get_job_field/', api.GetJobFieldView.as_view()),
    path('api/has-children/<int:pk>/', api.DoJobHasChildrenView.as_view(), name='api-has-children'),
    path('api/can-download/', api.CheckDownloadAccessView.as_view(), name='api-can-download'),
    path('api/collapse/<int:pk>/', api.CollapseReportsView.as_view(), name='api-collapse-reports'),
    path('api/coverage/<int:pk>/', api.GetJobCoverageTableView.as_view(), name='api-get-coverage'),
]
