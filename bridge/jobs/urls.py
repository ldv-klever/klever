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
    path('decision_results/<int:pk>/', views.DecisionResults.as_view()),
    path('progress/<int:pk>/', views.JobProgress.as_view()),
    path('api/job-status/<int:pk>/', api.JobStatusView.as_view()),
    path('comparison/<int:job1_id>/<int:job2_id>/', views.JobsFilesComparison.as_view(), name='comparison'),

    # Main actions with jobs
    path('remove/', views.RemoveJobsView.as_view()),
    path('api/duplicate/', api.DuplicateJobAPIView.as_view(), name='api-duplicate-job'),
    path('api/duplicate/<int:pk>/', api.DuplicateJobAPIView.as_view(), name='api-duplicate-version'),

    path('api/decision-results/<int:pk>/', api.DecisionResultsAPIView.as_view(), name='api-decision-results'),

    # Job form
    re_path(r'^form/(?P<pk>[0-9]+)/(?P<action>edit|copy)/$', views.JobFormPage.as_view(), name='form'),
    path('api/save-job/<int:pk>/', api.SaveJobView.as_view(), name='api-save-job'),
    path('api/job-version/<int:job_id>/<int:version>/', api.JobVersionView.as_view(), name='api-job-version'),

    # Actions with job files
    path('downloadfile/<slug:hash_sum>/', views.DownloadJobFileView.as_view(), name='download_file'),
    path('api/file/', api.CreateFileView.as_view()),
    path('api/file/<slug:hashsum>/', api.FileContentView.as_view(), name='file-content'),

    path('get_files_diff/<slug:hashsum1>/<slug:hashsum2>/', api.GetFilesDiffView.as_view(), name='files-diff'),
    path('api/replace-job-file/', api.ReplaceJobFileView.as_view()),
    path('downloadcompetfile/<int:pk>/', views.DownloadFilesForCompetition.as_view(), name='download_file_for_compet'),

    # Download/upload actions
    path('downloadjob/<int:pk>/', views.DownloadJobView.as_view(), name='download'),
    path('downloadjobs/', views.DownloadJobsListView.as_view()),
    path('downloadtrees/', views.DownloadJobsTreeView.as_view()),
    path('upload_jobs/<slug:parent_id>/', views.UploadJobsView.as_view()),
    path('upload_jobs_tree/', views.UploadJobsTreeView.as_view()),

    # Actions with job versions
    path('remove_versions/<int:pk>/', views.RemoveJobVersions.as_view()),
    path('compare_versions/<int:pk>/', views.CompareJobVersionsView.as_view()),

    # Actions with job solving
    path('prepare_run/<int:pk>/', views.PrepareDecisionView.as_view(), name='prepare_run'),
    path('download_configuration/<int:pk>/', views.DownloadRunConfigurationView.as_view()),
    path('get_def_start_job_val/', views.GetDefStartJobValue.as_view()),
    path('run_decision/<int:job_id>/', views.StartDecision.as_view()),
    path('stop_decision/<int:pk>/', views.StopDecisionView.as_view()),
    path('decide_job/', views.DecideJobServiceView.as_view()),

    # "Utils"
    path('get_job_field/', views.GetJobFieldView.as_view()),
    path('do_job_has_children/<int:pk>/', views.DoJobHasChildrenView.as_view()),
    path('check_download_access/', views.CheckDownloadAccessView.as_view()),
    path('check_compare_access/', views.CheckCompareAccessView.as_view()),
    path('get_job_progress_json/<int:pk>/', views.JobProgressJson.as_view()),

    # Actions with reports
    path('upload_reports/<int:pk>/', views.UploadReportsView.as_view()),
    path('collapse_reports/<int:pk>/', views.CollapseReportsView.as_view()),
]
