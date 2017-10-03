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
from reports import views


urlpatterns = [
    url(r'^component/(?P<job_id>[0-9]+)/(?P<report_id>[0-9]+)/$', views.report_component, name='component'),
    url('^log/(?P<report_id>[0-9]+)/$', views.get_component_log, name='log'),
    url('^logcontent/(?P<report_id>[0-9]+)/$', views.get_log_content),

    url(r'^component/(?P<report_id>[0-9]+)/safes/$', views.safes_list, name='safes'),
    url(r'^component/(?P<report_id>[0-9]+)/unsafes/$', views.unsafes_list, name='unsafes'),
    url(r'^component/(?P<report_id>[0-9]+)/unknowns/$', views.unknowns_list, name='unknowns'),

    url(r'^unsafe/(?P<report_id>[0-9]+)/$', views.report_unsafe, name='unsafe'),
    url(r'^safe/(?P<report_id>[0-9]+)/$', views.report_safe, name='safe'),
    url(r'^unknown/(?P<report_id>[0-9]+)/$', views.report_unknown, name='unknown'),
    url(r'^unsafe/(?P<report_id>[0-9]+)/etv/$', views.report_etv_full, name='etv'),

    url(r'^comparison/(?P<job1_id>[0-9]+)/(?P<job2_id>[0-9]+)/$', views.jobs_comparison, name='comparison'),
    url(r'^download-error-trace/(?P<report_id>[0-9]+)/$', views.download_error_trace, name='download_error_trace'),

    url(r'^upload/$', views.upload_report),
    url(r'^ajax/get_source/$', views.get_source_code),
    url(r'^ajax/fill_compare_cache/$', views.fill_compare_cache),
    url(r'^ajax/get_compare_jobs_data/$', views.get_compare_jobs_data),
    url(r'^ajax/clear_verification_files/$', views.clear_verification_files),
    url(r'^component/(?P<report_id>[0-9]+)/download_verifier_input_files/$',
        views.download_verifier_input_files, name='download_verifier_input_files'),
    url(r'^component/(?P<report_id>[0-9]+)/download_coverage/$', views.download_coverage, name='download_coverage'),

    url(r'^coverage/(?P<report_id>[0-9]+)/$', views.coverage_page, name='coverage'),
    url(r'^coverage-light/(?P<report_id>[0-9]+)/$', views.coverage_light_page, name='coverage_light'),
    url(r'^ajax/get-coverage-src/$', views.get_coverage_src),
]
