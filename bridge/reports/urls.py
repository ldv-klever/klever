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

from django.urls import path, re_path
from reports import views, api


urlpatterns = [
    # ReportComponent page
    path('log/<int:report_id>/', views.ComponentLogView.as_view(), name='log'),
    path('logcontent/<int:report_id>/', api.ComponentLogContentView.as_view(), name='log-content'),
    path('attrdata/<int:pk>/', views.AttrDataFileView.as_view(), name='attr-data'),
    path('attrdata-content/<int:pk>/', api.AttrDataContentView.as_view(), name='attr-data-content'),
    path('component/<int:pk>/download_files/', views.DownloadVerifierFiles.as_view(), name='download_files'),

    # List of verdicts
    path('component/<int:report_id>/safes/', views.SafesListView.as_view(), name='safes'),
    path('component/<int:report_id>/unsafes/', views.UnsafesListView.as_view(), name='unsafes'),
    path('component/<int:report_id>/unknowns/', views.UnknownsListView.as_view(), name='unknowns'),

    path('unsafe/<int:unsafe_id>/download/', views.DownloadErrorTraceView.as_view(), name='unsafe-download'),
    path('report/<int:report_id>/source/', api.GetSourceCodeView.as_view(), name='api-get-source'),

    # Reports comparison
    path('api/fill-comparison/<int:decision1>/<int:decision2>/',
         api.FillComparisonView.as_view(), name='api-fill-comparison'),
    path('comparison/<int:decision1>/<int:decision2>/', views.ReportsComparisonView.as_view(), name='comparison'),
    path('comparison/<uuid:decision1>/<uuid:decision2>/',
         views.ReportsComparisonUUIDView.as_view(), name='comparison-uuid'),
    path('api/comparison-data/<int:info_id>/', api.ReportsComparisonDataView.as_view(), name='api-comparison-data'),

    # Coverage
    path('<int:report_id>/coverage/', views.CoverageView.as_view(), name='coverage'),
    path('coverage/<int:pk>/download/', views.DownloadCoverageView.as_view(), name='coverage-download'),
    path('api/coverage/data/<int:cov_id>/', api.GetCoverageDataAPIView.as_view(), name='api-coverage-data'),
    path('api/coverage/table/<int:report_id>/', api.GetReportCoverageTableView.as_view(), name='api-coverage-table'),

    # Utils
    path('api/has-sources/', api.HasOriginalSources.as_view()),
    path('api/upload-sources/', api.UploadOriginalSourcesView.as_view()),
    path('api/upload/<uuid:decision_uuid>/', api.UploadReportView.as_view()),
    path('api/report-attr/<uuid:decision>/', api.UpdateReportAttrView.as_view()),
    path('api/clear-verification-files/<int:decision_id>/', api.ClearVerificationFilesView.as_view(),
         name='clear-verification-files'),

    # Report images
    path('component/images-download/<int:pk>/', views.DownloadReportPNGView.as_view(), name='download-report-png'),
    path('api/component/images-create/', api.ReportImageCreate.as_view(), name='api-add-report-image'),
    path('api/component/images-get/<int:pk>/', api.ReportImageGetDataView.as_view(), name='api-get-report-image'),

    # Pages of reports by identifier
    re_path(r'^(?P<decision>[0-9A-Fa-f-]+)/safe(?P<identifier>.*)$',
            views.ReportSafeView.as_view(), name='safe'),
    re_path(r'^(?P<decision>[0-9A-Fa-f-]+)/unsafe-fullscreen(?P<identifier>.*)$',
            views.FullscreenReportUnsafe.as_view(), name='unsafe-fullscreen'),
    re_path(r'^(?P<decision>[0-9A-Fa-f-]+)/unsafe(?P<identifier>.*)$',
            views.ReportUnsafeView.as_view(), name='unsafe'),
    re_path(r'^(?P<decision>[0-9A-Fa-f-]+)/unknown(?P<identifier>.*)$',
            views.ReportUnknownView.as_view(), name='unknown'),
    re_path(r'^(?P<decision>[0-9A-Fa-f-]+)/component(?P<identifier>.*)$',
            views.ReportComponentView.as_view(), name='component'),

    path('d3/', views.TestD3.as_view()),
]
