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

from django.urls import path
from tools import views, api


urlpatterns = [
    path('manager/', views.ManagerPageView.as_view(), name='manager'),
    path('call-logs/', views.CallLogsView.as_view(), name='call-logs'),
    path('processing-list/', views.ProcessingListView.as_view(), name='processing-list'),
    path('db-statistics/', views.DBLogsStatistics.as_view(), name='db-statistics'),
    path('reports-logging/', views.ReportsLoggingView.as_view(), name='reports-logging'),
    path('logs/', views.FileLogView.as_view(), name='logs'),
    path('error-trace-analizer/', views.ErrorTraceAnalyzerView.as_view(), name='error-trace-analizer'),
    path('secret/', views.SecretPageView.as_view(), name='secret-page'),

    path('api/clear-system/', views.ClearSystemAPIView.as_view(), name='api-clear-system'),
    path('api/clear-comparison/<int:pk>/', views.ClearComparisonAPIView.as_view(), name='api-clear-comparison'),
    path('api/recalculation/', views.RecalculationAPIView.as_view(), name='api-recalc'),
    path('api/recalculation-marks/', views.MarksRecalculationAPIView.as_view(), name='api-recalc-marks'),
    path('api/call-log/', views.CallLogAPIView.as_view(), name='api-call-log'),
    path('api/call-statistic/', views.CallStatisticAPIView.as_view(), name='api-call-statistic'),
    path('api/clear-tasks/', views.ClearTasksAPIView.as_view(), name='api-clear-tasks'),
    path('api/manual-unlock/', views.ManualUnlockAPIView.as_view(), name='api-manual-unlock'),
    path('api/population/', views.PopulationAPIView.as_view(), name='api-populate'),
    path('api/db-statistics/', api.CalculateDBLogStatisticsView.as_view(), name='api-db-statistics'),
    path('api/parse-reports-logs/', api.ParseReportsLogsAPIView.as_view(), name='api-parse-reports-logs'),

    path('api/log-content/', api.LogContentAPIView.as_view(), name='api-log-content'),
    path('api/clear-log/', api.ClearLogAPIView.as_view(), name='api-clear-log'),

    path('api/secret/fix-old-coverage/', api.FixOldCoverageAPIView.as_view(), name='api-secret-fix-old-coverage'),
]
