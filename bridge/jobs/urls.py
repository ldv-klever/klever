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

from django.conf.urls import url
from jobs import views


urlpatterns = [
    url(r'^$', views.tree_view, name='tree'),
    url(r'^(?P<job_id>[0-9]+)/$', views.show_job, name='job'),
    url(r'^downloadfile/(?P<file_id>[0-9]+)/$', views.download_file, name='download_file'),
    url(r'^prepare_run/(?P<job_id>[0-9]+)/$', views.prepare_decision, name='prepare_run'),
    url(r'^comparison/(?P<job1_id>[0-9]+)/(?P<job2_id>[0-9]+)/$', views.jobs_files_comparison, name='comparison'),
    url(r'^download_configuration/(?P<runhistory_id>[0-9]+)/$', views.download_configuration),
    url(r'^create/$', views.copy_new_job, name='create'),
    url(r'^downloadcompetfile/(?P<job_id>[0-9]+)/$', views.download_files_for_compet, name='download_file_for_compet'),

    # For ajax requests
    url(r'^ajax/save_view/$', views.save_view),
    url(r'^ajax/remove_view/$', views.remove_view),
    url(r'^ajax/share_view/$', views.share_view),
    url(r'^ajax/preferable_view/$', views.preferable_view),
    url(r'^ajax/check_view_name/$', views.check_view_name),
    url(r'^ajax/removejobs/$', views.remove_jobs),
    url(r'^ajax/editjob/$', views.edit_job),
    url(r'^ajax/savejob/$', views.save_job),
    url(r'^ajax/showjobdata/$', views.showjobdata),
    url(r'^ajax/upload_file/$', views.upload_file),
    url(r'^ajax/downloadjob/(?P<job_id>[0-9]+)/$', views.download_job),
    url(r'^ajax/downloadjobs/$', views.download_jobs),
    url(r'^ajax/downloadtrees/$', views.download_trees),
    url(r'^ajax/check_access/$', views.check_access),
    url(r'^ajax/upload_job/(?P<parent_id>.*)/$', views.upload_job),
    url(r'^ajax/upload_jobs_tree/$', views.upload_jobs_tree),
    url(r'^ajax/getfilecontent/$', views.getfilecontent),
    url(r'^ajax/getversions/$', views.get_job_versions),
    url(r'^ajax/remove_versions/$', views.remove_versions),
    url(r'^ajax/stop_decision/$', views.stop_decision),
    url(r'^ajax/run_decision/$', views.run_decision),
    url(r'^ajax/fast_run_decision/$', views.fast_run_decision),
    url(r'^ajax/lastconf_run_decision/$', views.lastconf_run_decision),
    url(r'^ajax/get_job_data/$', views.get_job_data),
    url(r'^ajax/check_compare_access/$', views.check_compare_access),
    url(r'^ajax/get_file_by_checksum/$', views.get_file_by_checksum),
    url(r'^ajax/get_def_start_job_val/$', views.get_def_start_job_val),
    url(r'^ajax/collapse_reports/$', views.collapse_reports),
    url(r'^ajax/do_job_has_children/$', views.do_job_has_children),
    url(r'^ajax/enable_safe_marks/$', views.enable_safe_marks),
    url(r'^ajax/upload_reports/$', views.upload_reports),

    # For Klever Core
    url(r'^decide_job/$', views.decide_job),
]
