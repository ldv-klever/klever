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
from reports import views


urlpatterns = [
    path('component/<int:job_id>/<int:report_id>/', views.report_component, name='component'),
    path('log/<int:report_id>/', views.get_component_log, name='log'),
    path('logcontent/<int:report_id>/', views.get_log_content),
    path('attrdata/<int:attr_id>/', views.get_attr_data_file, name='attr_data'),
    path('attrdata-content/<int:attr_id>/', views.get_attr_data_content),

    path('component/<int:report_id>/safes/', views.safes_list, name='safes'),
    path('component/<int:report_id>/unsafes/', views.unsafes_list, name='unsafes'),
    path('component/<int:report_id>/unknowns/', views.unknowns_list, name='unknowns'),

    path('unsafe/<slug:trace_id>/', views.report_unsafe, name='unsafe'),
    path('safe/<int:report_id>/', views.report_safe, name='safe'),
    path('unknown/<int:report_id>/', views.report_unknown, name='unknown'),
    path('unsafe/<slug:trace_id>/fullscreen/', views.report_etv_full, name='unsafe_fullscreen'),

    path('comparison/<int:job1_id>/<int:job2_id>/', views.jobs_comparison, name='comparison'),
    path('download-error-trace/<int:report_id>/', views.download_error_trace, name='download_error_trace'),

    path('upload/', views.upload_report),
    path('ajax/get_source/', views.get_source_code),
    path('ajax/fill_compare_cache/', views.fill_compare_cache),
    path('ajax/get_compare_jobs_data/', views.get_compare_jobs_data),
    path('clear_verification_files/', views.clear_verification_files),
    path('component/<int:report_id>/download_verifier_input_files/',
         views.download_verifier_input_files, name='download_verifier_input_files'),
    path('component/<int:archive_id>/download_coverage/', views.download_coverage, name='download_coverage'),

    path('coverage/<int:report_id>/', views.coverage_page, name='coverage'),
    path('coverage-light/<int:report_id>/', views.coverage_light_page, name='coverage_light'),
    path('ajax/get-coverage-src/', views.get_coverage_src),
]
