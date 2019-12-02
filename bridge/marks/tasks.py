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
from __future__ import absolute_import
from celery import shared_task

from reports.models import ReportUnsafe
from marks.models import MarkUnsafe, MarkUnsafeReport
from marks.UnsafeUtils import CompareReport
from caches.utils import RecalculateUnsafeCache


@shared_task
def connect_unsafe_report(report_id):
    report = ReportUnsafe.objects.get(pk=report_id)
    marks_qs = MarkUnsafe.objects.filter(cache_attrs__contained_by=report.cache.attrs).select_related('error_trace')
    compare_results = CompareReport(report).compare(marks_qs)

    MarkUnsafeReport.objects.bulk_create(list(MarkUnsafeReport(
        mark_id=mark.id, report=report, **compare_results[mark.id]
    ) for mark in marks_qs))
    RecalculateUnsafeCache(reports=[report.id])
