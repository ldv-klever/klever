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
    path('', views.tree_view, name='tree'),
    path('<int:job_id>/', views.show_job, name='job'),
    path('downloadfile/<int:file_id>/', views.download_file, name='download_file'),
    path('prepare_run/<int:job_id>/', views.prepare_decision, name='prepare_run'),
    path('comparison/<int:job1_id>/<int:job2_id>/', views.jobs_files_comparison, name='comparison'),
    path('download_configuration/<int:runhistory_id>/', views.download_configuration),
    path('create/', views.copy_new_job, name='create'),
    path('downloadcompetfile/<int:job_id>/', views.download_files_for_compet, name='download_file_for_compet'),

    # For ajax requests
    path('ajax/save_view/', views.save_view),
    path('ajax/remove_view/', views.remove_view),
    path('ajax/share_view/', views.share_view),
    path('ajax/preferable_view/', views.preferable_view),
    path('ajax/check_view_name/', views.check_view_name),
    path('ajax/removejobs/', views.remove_jobs),
    path('ajax/editjob/', views.edit_job),
    path('ajax/savejob/', views.save_job),
    path('ajax/showjobdata/', views.showjobdata),
    path('ajax/upload_file/', views.upload_file),
    path('ajax/downloadjob/<int:job_id>/', views.download_job),
    path('ajax/downloadjobs/', views.download_jobs),
    path('ajax/downloadtrees/', views.download_trees),
    path('ajax/check_access/', views.check_access),
    path('ajax/upload_job/<parent_id>/', views.upload_job),
    path('ajax/upload_jobs_tree/', views.upload_jobs_tree),
    path('ajax/getfilecontent/', views.getfilecontent),
    path('ajax/getversions/', views.get_job_versions),
    path('ajax/remove_versions/', views.remove_versions),
    path('ajax/stop_decision/', views.stop_decision),
    path('ajax/run_decision/', views.run_decision),
    path('ajax/fast_run_decision/', views.fast_run_decision),
    path('ajax/lastconf_run_decision/', views.lastconf_run_decision),
    path('ajax/get_job_data/', views.get_job_data),
    path('ajax/check_compare_access/', views.check_compare_access),
    path('ajax/get_file_by_checksum/', views.get_file_by_checksum),
    path('ajax/get_def_start_job_val/', views.get_def_start_job_val),
    path('ajax/collapse_reports/', views.collapse_reports),
    path('ajax/do_job_has_children/', views.do_job_has_children),
    path('ajax/enable_safe_marks/', views.enable_safe_marks),
    path('ajax/upload_reports/', views.upload_reports),

    # For Klever Core
    path('decide_job/', views.decide_job),
]
