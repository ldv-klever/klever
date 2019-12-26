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

from celery import shared_task

from bridge.vars import PROBLEM_DESC_FILE
from bridge.utils import BridgeException, ArchiveFileContent

from reports.models import ReportSafe, ReportUnsafe, ReportUnknown
from marks.models import MarkSafe, MarkSafeReport, MarkUnsafe, MarkUnsafeReport, MarkUnknown, MarkUnknownReport

from marks.UnsafeUtils import CompareReport
from marks.UnknownUtils import MatchUnknown
from caches.utils import RecalculateSafeCache, RecalculateUnsafeCache, RecalculateUnknownCache


@shared_task()
def connect_safe_report(report_id):
    report = ReportSafe.objects.select_related('cache').get(pk=report_id)
    marks_qs = MarkSafe.objects.filter(cache_attrs__contained_by=report.cache.attrs)
    MarkSafeReport.objects.bulk_create(list(
        MarkSafeReport(mark_id=m_id, report=report, associated=True)
        for m_id in marks_qs.values_list('id', flat=True)
    ))
    RecalculateSafeCache(reports=[report.id])


@shared_task
def connect_unsafe_report(report_id):
    report = ReportUnsafe.objects.select_related('cache').get(pk=report_id)
    marks_qs = MarkUnsafe.objects.filter(cache_attrs__contained_by=report.cache.attrs).select_related('error_trace')
    compare_results = CompareReport(report).compare(marks_qs)

    MarkUnsafeReport.objects.bulk_create(list(MarkUnsafeReport(
        mark_id=mark.id, report=report, **compare_results[mark.id]
    ) for mark in marks_qs))
    RecalculateUnsafeCache(reports=[report.id])


@shared_task
def connect_unknown_report(report_id):
    report = ReportUnknown.objects.select_related('cache').get(pk=report_id)
    try:
        problem_desc = ArchiveFileContent(report, 'problem_description', PROBLEM_DESC_FILE).content.decode('utf8')
    except Exception as e:
        raise BridgeException("Can't read problem description for unknown '{}': {}".format(report.id, e))
    new_markreports = []
    for mark in MarkUnknown.objects.filter(component=report.component, cache_attrs__contained_by=report.cache.attrs):
        problem = MatchUnknown(problem_desc, mark.function, mark.problem_pattern, mark.is_regexp).problem
        if not problem:
            continue
        new_markreports.append(MarkUnknownReport(mark_id=mark.id, report=report, problem=problem, associated=True))
    MarkUnknownReport.objects.bulk_create(new_markreports)
    RecalculateUnknownCache(reports=[report.id])
