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

from django.urls import path
from reports import views, api


urlpatterns = [
    # ReportComponent page
    path('component/<int:pk>/', views.ReportComponentView.as_view(), name='component'),
    path('log/<int:report_id>/', views.ComponentLogView.as_view(), name='log'),
    path('logcontent/<int:report_id>/', views.ComponentLogContentView.as_view(), name='log-content'),
    path('attrdata/<int:pk>/', views.AttrDataFileView.as_view(), name='attr-data'),
    path('attrdata-content/<int:pk>/', views.AttrDataContentView.as_view(), name='attr-data-content'),
    path('component/<int:pk>/download_files/', views.DownloadVerifierFiles.as_view(), name='download_files'),

    # List of verdicts
    path('component/<int:report_id>/safes/', views.SafesListView.as_view(), name='safes'),
    path('component/<int:report_id>/unsafes/', views.UnsafesListView.as_view(), name='unsafes'),
    path('component/<int:report_id>/unknowns/', views.UnknownsListView.as_view(), name='unknowns'),

    # Pages of verdicts
    path('safe/<int:pk>/', views.ReportSafeView.as_view(), name='safe'),
    path('unknown/<int:pk>/', views.ReportUnknownView.as_view(), name='unknown'),
    path('unsafe/<slug:trace_id>/', views.ReportUnsafeView.as_view(), name='unsafe'),
    path('unsafe/<slug:trace_id>/fullscreen/', views.FullscreenReportUnsafe.as_view(), name='unsafe_fullscreen'),
    path('unsafe/<int:unsafe_id>/download/', views.DownloadErrorTraceView.as_view(), name='unsafe-download'),
    path('unsafe/<int:unsafe_id>/source/', api.GetSourceCodeView.as_view(), name='api-get-source'),

    # Reports comparison
    path('api/fill-comparison/<int:job1_id>/<int:job2_id>/',
         api.FillComparisonView.as_view(), name='api-fill-comparison'),
    path('comparison/<int:job1_id>/<int:job2_id>/', views.ReportsComparisonView.as_view(), name='comparison'),
    path('api/comparison-data/<int:info_id>/', api.ReportsComparisonDataView.as_view(), name='api-comparison-data'),

    # Coverage
    path('coverage/<int:report_id>/', views.CoverageView.as_view(), name='coverage'),
    path('coverage-light/<int:report_id>/', views.CoverageLightView.as_view(), name='coverage_light'),
    path('get-coverage-src/<int:archive_id>/', views.CoverageSrcView.as_view()),
    path('download_coverage/<int:pk>/', views.DownloadCoverageView.as_view(), name='download_coverage'),

    # Utils
    path('api/has-sources/', api.HasOriginalSources.as_view()),
    path('api/upload-sources/', api.UploadOriginalSourcesView.as_view()),
    path('api/upload/<uuid:job_uuid>/', api.UploadReportView.as_view()),
    path('api/clear-verification-files/<int:job_id>/', api.ClearVerificationFilesView.as_view(),
         name='clear-verification-files')
]
