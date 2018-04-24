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
from jobs import views


urlpatterns = [
    # Main pages
    path('', views.JobsTree.as_view(), name='tree'),
    path('<int:pk>/', views.JobPage.as_view(), name='job'),
    path('decision_results/<int:pk>/', views.DecisionResults.as_view()),
    path('progress/<int:pk>/', views.JobProgress.as_view()),
    path('status/<int:pk>/', views.JobStatus.as_view()),
    path('comparison/<int:job1_id>/<int:job2_id>/', views.JobsFilesComparison.as_view(), name='comparison'),

    # Main actions with jobs
    path('remove/', views.RemoveJobsView.as_view()),
    path('save_job_copy/<int:pk>/', views.SaveJobCopyView.as_view()),
    path('decision_results_json/<int:pk>/', views.DecisionResultsJson.as_view()),

    # Job form
    re_path(r'^form/(?P<pk>[0-9]+)/(?P<action>edit|copy)/$', views.JobFormPage.as_view(), name='form'),
    path('get_version_data/<int:job_id>/<int:version>/', views.GetJobHistoryData.as_view()),
    path('get_version_roles/<int:job_id>/<int:version>/', views.GetJobHistoryRoles.as_view()),
    path('get_version_files/<int:job_id>/<int:version>/', views.GetJobHistoryFiles.as_view()),

    # Actions with job files
    path('downloadfile/<slug:hash_sum>/', views.DownloadJobFileView.as_view(), name='download_file'),
    path('upload_file/', views.UploadJobFileView.as_view()),
    path('getfilecontent/<slug:hashsum>/', views.GetFileContentView.as_view()),
    path('get_files_diff/<slug:hashsum1>/<slug:hashsum2>/', views.GetFilesDiffView.as_view()),
    path('replace_job_file/<int:job_id>/', views.ReplaceJobFileView.as_view()),
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
    path('copy_job_version/<int:pk>/', views.CopyJobVersionView.as_view()),

    # Actions with job solving
    path('prepare_run/<int:job_id>/', views.PrepareDecisionView.as_view(), name='prepare_run'),
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
    path('enable_safe_marks/<int:pk>/', views.EnableSafeMarks.as_view()),
]
