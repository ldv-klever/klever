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

from django.urls import path
from jobs import views


urlpatterns = [
    # Main pages
    path('', views.JobsTree.as_view(), name='tree'),
    # path('<int:job_id>/', views.show_job, name='job'),
    path('<int:pk>/', views.JobPage.as_view(), name='job'),
    path('data/<int:pk>/', views.JobData.as_view()),
    path('progress/<int:pk>/', views.JobProgress.as_view()),
    path('status/<int:pk>/', views.JobStatus.as_view()),
    path('create/', views.copy_new_job, name='create'),
    path('comparison/<int:job1_id>/<int:job2_id>/', views.jobs_files_comparison, name='comparison'),

    # Main actions with jobs
    path('ajax/removejobs/', views.remove_jobs),
    path('ajax/editjob/', views.edit_job),
    path('ajax/savejob/', views.save_job),
    path('ajax/save_job_copy/<int:job_id>/', views.save_job_copy),

    # Actions with job results
    path('ajax/showjobdata/', views.showjobdata),
    path('ajax/get_job_data/', views.get_job_data),
    path('ajax/get_job_decision_results/<int:job_id>/', views.get_job_decision_results),

    # Download/upload actions
    path('ajax/downloadjob/<int:job_id>/', views.download_job),
    path('ajax/downloadjobs/', views.download_jobs),
    path('ajax/downloadtrees/', views.download_trees),
    path('ajax/upload_job/<parent_id>/', views.upload_job),
    path('ajax/upload_jobs_tree/', views.upload_jobs_tree),

    # Actions with job files
    path('downloadfile/<int:file_id>/', views.download_file, name='download_file'),
    path('downloadcompetfile/<int:job_id>/', views.download_files_for_compet, name='download_file_for_compet'),
    path('ajax/upload_file/', views.upload_file),
    path('ajax/getfilecontent/', views.getfilecontent),
    path('ajax/get_files_diff/', views.get_files_diff),
    path('ajax/get_file_by_checksum/', views.get_file_by_checksum),
    path('ajax/replace_job_file/<int:job_id>/', views.replace_job_file),

    # Actions with job versions
    path('ajax/getversions/', views.get_job_versions),
    path('ajax/remove_versions/', views.remove_versions),
    path('ajax/compare_versions/', views.compare_versions),
    path('ajax/copy_job_version/<int:job_id>/', views.copy_job_version),

    # Actions with job solving
    path('download_configuration/<int:runhistory_id>/', views.download_configuration),
    path('prepare_run/<int:job_id>/', views.prepare_decision, name='prepare_run'),
    path('ajax/get_def_start_job_val/', views.get_def_start_job_val),
    path('ajax/stop_decision/', views.stop_decision),
    path('ajax/run_decision/', views.run_decision),
    path('ajax/fast_run_decision/', views.fast_run_decision),
    path('ajax/lastconf_run_decision/', views.lastconf_run_decision),
    path('decide_job/', views.decide_job),

    # "Utils"
    path('ajax/get_job_id/', views.get_job_id),
    path('ajax/get_job_identifier/', views.get_job_identifier),
    path('ajax/do_job_has_children/', views.do_job_has_children),
    path('ajax/check_access/', views.check_access),
    path('ajax/check_compare_access/', views.check_compare_access),
    path('ajax/get_job_progress_json/<int:job_id>/', views.get_job_progress_json),

    # Actions with reports
    path('ajax/collapse_reports/', views.collapse_reports),
    path('ajax/enable_safe_marks/', views.enable_safe_marks),
    path('ajax/upload_reports/', views.upload_reports),

    path('ajax/test/', views.Testing.as_view()),
]
