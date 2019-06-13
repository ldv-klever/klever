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

import copy
from collections import Counter
import uuid

from django.db import transaction
from django.db.models import F
from django.utils.functional import cached_property

from bridge.vars import SAFE_VERDICTS, UNSAFE_VERDICTS, ASSOCIATION_TYPE

from reports.models import ReportSafe, ReportUnsafe
from marks.models import (
    MarkSafe, MarkSafeHistory, MarkUnsafe, MarkUnsafeHistory, MarkUnknown,
    MarkSafeReport, MarkUnsafeReport, MarkUnknownReport,
    MarkSafeTag, MarkUnsafeTag, SafeTag, UnsafeTag
)
from caches.models import (
    ASSOCIATION_CHANGE_KIND, ReportSafeCache, ReportUnsafeCache, ReportUnknownCache,
    SafeMarkAssociationChanges, UnsafeMarkAssociationChanges, UnknownMarkAssociationChanges
)


@transaction.atomic
def update_cache_atomic(queryset, data):
    for rep_cache in queryset:
        if rep_cache.report_id not in data:
            continue
        for field, value in data[rep_cache.report_id].items():
            setattr(rep_cache, field, value)
        rep_cache.save()


class UpdateSafeCachesOnMarkChange:
    def __init__(self, mark, old_links, new_links):
        self._mark = mark
        self._old_links = old_links
        self._new_links = new_links

        self._affected_reports = self._old_links | self._new_links
        self._cache_queryset = ReportSafeCache.objects.filter(report_id__in=self._affected_reports)
        self._markreport_qs = MarkSafeReport.objects\
            .filter(report_id__in=self._affected_reports)\
            .exclude(type=ASSOCIATION_TYPE[2][0]).select_related('mark')

        self._collected = set()
        self._old_data = self.__collect_old_data()
        self._new_data = self.__init_new_data()

    def save(self):
        update_cache_atomic(self._cache_queryset, self._new_data)
        return self.__create_changes_cache()

    def __collect_old_data(self):
        old_data = {}
        for cache_obj in self._cache_queryset:
            old_data[cache_obj.report_id] = {
                'job_id': cache_obj.job_id,
                'verdict': cache_obj.verdict,
                'tags': cache_obj.tags
            }
        return old_data

    def __init_new_data(self):
        return dict((cache_obj.report_id, {}) for cache_obj in self._cache_queryset)

    def update_all(self):
        for cache_obj in self._cache_queryset:
            self._new_data[cache_obj.report_id]['verdict'] = SAFE_VERDICTS[4][0]
            self._new_data[cache_obj.report_id]['tags'] = {}
            self._new_data[cache_obj.report_id]['marks_total'] = 0
            self._new_data[cache_obj.report_id]['marks_confirmed'] = 0

        for mr in self._markreport_qs:
            self.__add_verdict(mr.report_id, mr.mark.verdict)
            self.__add_tags(mr.report_id, mr.mark.cache_tags)
            self._new_data[mr.report_id]['marks_total'] += 1
            self._new_data[mr.report_id]['marks_confirmed'] += int(mr.type == ASSOCIATION_TYPE[1][0])

        self._collected.add('verdicts')
        self._collected.add('tags')

    def update_verdicts(self):
        if 'verdicts' in self._collected:
            return

        for cache_obj in self._cache_queryset:
            self._new_data[cache_obj.report_id]['verdict'] = SAFE_VERDICTS[4][0]

        for mr in self._markreport_qs:
            self.__add_verdict(mr.report_id, mr.mark.verdict)

        self._collected.add('verdicts')

    def update_tags(self):
        if 'tags' in self._collected:
            return

        for cache_obj in self._cache_queryset:
            self._new_data[cache_obj.report_id]['tags'] = {}

        for mr in self._markreport_qs:
            self.__add_tags(mr.report_id, mr.mark.cache_tags)

        self._collected.add('tags')

    def __get_change_kind(self, report_id):
        if report_id in self._old_links:
            if report_id in self._new_links:
                return ASSOCIATION_CHANGE_KIND[0][0]
            return ASSOCIATION_CHANGE_KIND[2][0]
        # Report is always in new links as method called with needed report id
        return ASSOCIATION_CHANGE_KIND[1][0]

    @cached_property
    def _change_kinds(self):
        return dict((report_id, self.__get_change_kind(report_id)) for report_id in self._affected_reports)

    def __add_verdict(self, report_id, verdict):
        old_verdict = self._new_data[report_id]['verdict']
        if old_verdict == SAFE_VERDICTS[4][0]:
            # No marks + V = V
            self._new_data[report_id]['verdict'] = verdict
        elif old_verdict == SAFE_VERDICTS[3][0]:
            # Incompatible + V = Incompatible
            return
        elif old_verdict != verdict:
            # V1 + V2 = Incompatible
            self._new_data[report_id]['verdict'] = SAFE_VERDICTS[3][0]
        else:
            # V + V = V
            return

    def __add_tags(self, report_id, tags_list):
        for tag in tags_list:
            self._new_data[report_id]['tags'].setdefault(tag, 0)
            self._new_data[report_id]['tags'][tag] += 1

    def __create_changes_cache(self):
        # Remove old association changes cache
        SafeMarkAssociationChanges.objects.filter(mark=self._mark).delete()

        # Create new association changes
        identifier = uuid.uuid4()
        changes_objects = []
        for report_id in self._affected_reports:
            verdict_old = self._old_data[report_id]['verdict']
            verdict_new = self._new_data[report_id].get('verdict', verdict_old)
            tags_old = self._old_data[report_id]['tags']
            tags_new = self._new_data[report_id].get('tags', tags_old)
            changes_objects.append(SafeMarkAssociationChanges(
                identifier=identifier, mark=self._mark,
                job_id=self._old_data[report_id]['job_id'], report_id=report_id,
                kind=self._change_kinds[report_id],
                verdict_old=verdict_old, verdict_new=verdict_new,
                tags_old=tags_old, tags_new=tags_new
            ))
        SafeMarkAssociationChanges.objects.bulk_create(changes_objects)
        return str(identifier)


class UpdateUnsafeCachesOnMarkChange:
    def __init__(self, mark, old_links, new_links):
        self._mark = mark
        self._old_links = old_links
        self._new_links = new_links

        self._affected_reports = self._old_links | self._new_links
        self._cache_queryset = ReportUnsafeCache.objects.filter(report_id__in=self._affected_reports)
        self._markreport_qs = MarkUnsafeReport.objects\
            .filter(report_id__in=self._affected_reports, result__gt=0)\
            .exclude(type=ASSOCIATION_TYPE[2][0]).select_related('mark')

        self._collected = set()
        self._old_data = self.__collect_old_data()
        self._new_data = self.__init_new_data()

    def save(self):
        update_cache_atomic(self._cache_queryset, self._new_data)
        return self.__create_changes_cache()

    def __collect_old_data(self):
        old_data = {}
        for cache_obj in self._cache_queryset:
            old_data[cache_obj.report_id] = {
                'job_id': cache_obj.job_id,
                'verdict': cache_obj.verdict,
                'tags': cache_obj.tags,
                'total_similarity': cache_obj.total_similarity
            }
        return old_data

    def __init_new_data(self):
        return dict((cache_obj.report_id, {}) for cache_obj in self._cache_queryset)

    def update_all(self):
        for cache_obj in self._cache_queryset:
            self._new_data[cache_obj.report_id]['verdict'] = UNSAFE_VERDICTS[5][0]
            self._new_data[cache_obj.report_id]['tags'] = {}
            self._new_data[cache_obj.report_id]['marks_total'] = 0
            self._new_data[cache_obj.report_id]['marks_confirmed'] = 0
            self._new_data[cache_obj.report_id]['total_similarity'] = 0

        result_sum = {}
        for mr in self._markreport_qs:
            result_sum.setdefault(mr.report_id, 0)
            result_sum[mr.report_id] += mr.result

            self.__add_verdict(mr.report_id, mr.mark.verdict)
            self.__add_tags(mr.report_id, mr.mark.cache_tags)
            self._new_data[mr.report_id]['marks_total'] += 1
            self._new_data[mr.report_id]['marks_confirmed'] += int(mr.type == ASSOCIATION_TYPE[1][0])

        for r_id in result_sum:
            self._new_data[r_id]['total_similarity'] = result_sum[r_id] / self._new_data[r_id]['marks_total']

        self._collected.add('verdicts')
        self._collected.add('tags')

    def update_verdicts(self):
        if 'verdicts' in self._collected:
            return

        for cache_obj in self._cache_queryset:
            self._new_data[cache_obj.report_id]['verdict'] = UNSAFE_VERDICTS[5][0]

        for mr in self._markreport_qs:
            self.__add_verdict(mr.report_id, mr.mark.verdict)

        self._collected.add('verdicts')

    def update_tags(self):
        if 'tags' in self._collected:
            return

        for cache_obj in self._cache_queryset:
            self._new_data[cache_obj.report_id]['tags'] = {}

        for mr in self._markreport_qs:
            self.__add_tags(mr.report_id, mr.mark.cache_tags)

        self._collected.add('tags')

    def __get_change_kind(self, report_id):
        if report_id in self._old_links:
            if report_id in self._new_links:
                return ASSOCIATION_CHANGE_KIND[0][0]
            return ASSOCIATION_CHANGE_KIND[2][0]
        # Report is always in new links as method called with needed report id
        return ASSOCIATION_CHANGE_KIND[1][0]

    @cached_property
    def _change_kinds(self):
        return dict((report_id, self.__get_change_kind(report_id)) for report_id in self._affected_reports)

    def __add_verdict(self, report_id, verdict):
        old_verdict = self._new_data[report_id]['verdict']
        if old_verdict == UNSAFE_VERDICTS[5][0]:
            # No marks + V = V
            self._new_data[report_id]['verdict'] = verdict
        elif old_verdict == UNSAFE_VERDICTS[4][0]:
            # Incompatible + V = Incompatible
            return
        elif old_verdict != verdict:
            # V1 + V2 = Incompatible
            self._new_data[report_id]['verdict'] = UNSAFE_VERDICTS[4][0]
        else:
            # V + V = V
            return

    def __add_tags(self, report_id, tags_list):
        for tag in tags_list:
            self._new_data[report_id]['tags'].setdefault(tag, 0)
            self._new_data[report_id]['tags'][tag] += 1

    def __create_changes_cache(self):
        # Remove old association changes cache
        UnsafeMarkAssociationChanges.objects.filter(mark=self._mark).delete()

        # Create new association changes
        identifier = uuid.uuid4()
        changes_objects = []
        for report_id in self._affected_reports:
            verdict_old = self._old_data[report_id]['verdict']
            verdict_new = self._new_data[report_id].get('verdict', verdict_old)
            tags_old = self._old_data[report_id]['tags']
            tags_new = self._new_data[report_id].get('tags', tags_old)
            sim_old = self._old_data[report_id]['total_similarity']
            sim_new = self._new_data[report_id].get('total_similarity', sim_old)
            changes_objects.append(UnsafeMarkAssociationChanges(
                identifier=identifier, mark=self._mark,
                job_id=self._old_data[report_id]['job_id'], report_id=report_id,
                kind=self._change_kinds[report_id],
                verdict_old=verdict_old, verdict_new=verdict_new,
                tags_old=tags_old, tags_new=tags_new,
                total_similarity_old=sim_old, total_similarity_new=sim_new
            ))
        UnsafeMarkAssociationChanges.objects.bulk_create(changes_objects)
        return str(identifier)


class UpdateUnknownCachesOnMarkChange:
    def __init__(self, mark, old_links, new_links):
        self._mark = mark
        self._old_links = old_links
        self._new_links = new_links

        self._affected_reports = self._old_links | self._new_links
        self._cache_queryset = ReportUnknownCache.objects.filter(report_id__in=self._affected_reports)
        self._markreport_qs = MarkUnknownReport.objects.filter(report_id__in=self._affected_reports)\
            .exclude(type=ASSOCIATION_TYPE[2][0])

        self._collected = False
        self._old_data = self.__collect_old_data()
        self._new_data = self.__init_new_data()

    def save(self):
        if self._collected:
            update_cache_atomic(self._cache_queryset, self._new_data)
            self._collected = False
        return self.__create_changes_cache()

    def __collect_old_data(self):
        old_data = {}
        for cache_obj in self._cache_queryset:
            old_data[cache_obj.report_id] = {
                'job_id': cache_obj.job_id,
                'problems': cache_obj.problems
            }
        return old_data

    def __init_new_data(self):
        return dict((cache_obj.report_id, {}) for cache_obj in self._cache_queryset)

    def update_all(self):
        for cache_obj in self._cache_queryset:
            self._new_data[cache_obj.report_id]['marks_total'] = 0
            self._new_data[cache_obj.report_id]['marks_confirmed'] = 0
            self._new_data[cache_obj.report_id]['problems'] = {}

        for mr in self._markreport_qs:
            self._new_data[mr.report_id]['problems'].setdefault(mr.problem, 0)
            self._new_data[mr.report_id]['problems'][mr.problem] += 1

            self._new_data[mr.report_id]['marks_total'] += 1
            self._new_data[mr.report_id]['marks_confirmed'] += int(mr.type == ASSOCIATION_TYPE[1][0])

        self._collected = True

    def __get_change_kind(self, report_id):
        if report_id in self._old_links:
            if report_id in self._new_links:
                return ASSOCIATION_CHANGE_KIND[0][0]
            return ASSOCIATION_CHANGE_KIND[2][0]
        # Report is always in new links as method called with needed report id
        return ASSOCIATION_CHANGE_KIND[1][0]

    @cached_property
    def _change_kinds(self):
        return dict((report_id, self.__get_change_kind(report_id)) for report_id in self._affected_reports)

    def __create_changes_cache(self):
        # Remove old association changes cache
        UnknownMarkAssociationChanges.objects.filter(mark=self._mark).delete()

        # Create new association changes
        identifier = uuid.uuid4()
        changes_objects = []
        for report_id in self._affected_reports:
            problems_old = self._old_data[report_id]['problems']
            problems_new = self._new_data[report_id].get('problems', problems_old)
            changes_objects.append(UnknownMarkAssociationChanges(
                identifier=identifier, mark=self._mark,
                job_id=self._old_data[report_id]['job_id'], report_id=report_id,
                kind=self._change_kinds[report_id],
                problems_old=problems_old, problems_new=problems_new
            ))
        UnknownMarkAssociationChanges.objects.bulk_create(changes_objects)
        return str(identifier)


class UpdateCachesOnMarkPopulate:
    def __init__(self, mark, new_links):
        self._mark = mark
        self._new_links = new_links

    def update(self):
        if not self._new_links:
            # Nothing changed
            return
        if isinstance(self._mark, MarkSafe):
            self.__update_safes()
        elif isinstance(self._mark, MarkUnsafe):
            self.__update_unsafes()
        elif isinstance(self._mark, MarkUnknown):
            self.__update_unknowns()

    @transaction.atomic
    def __update_safes(self):
        for cache_obj in ReportSafeCache.objects.filter(report_id__in=self._new_links):
            # Populated mark can't be confirmed, so we don't need to update confirmed number
            cache_obj.marks_total += 1
            cache_obj.verdict = self.__sum_unsafe_verdict(cache_obj.verdict)
            cache_obj.tags = self.__sum_tags(cache_obj.tags)
            cache_obj.save()

    @transaction.atomic
    def __update_unsafes(self):
        new_results = dict(MarkUnsafeReport.objects.filter(mark=self._mark).values_list('report_id', 'result'))

        for cache_obj in ReportUnsafeCache.objects.filter(report_id__in=self._new_links):
            new_sim_sum = cache_obj.total_similarity * cache_obj.marks_total + new_results[cache_obj.report_id]
            new_marks_total = cache_obj.marks_total + 1
            total_similarity = new_sim_sum / new_marks_total

            # Populated mark can't be confirmed, so we don't need to update confirmed number
            cache_obj.marks_total = new_marks_total
            cache_obj.total_similarity = total_similarity
            cache_obj.verdict = self.__sum_unsafe_verdict(cache_obj.verdict)
            cache_obj.tags = self.__sum_tags(cache_obj.tags)
            cache_obj.save()

    @transaction.atomic
    def __update_unknowns(self):
        new_problems = dict(MarkUnknownReport.objects.filter(mark=self._mark).values_list('report_id', 'problem'))

        for cache_obj in ReportUnknownCache.objects.filter(report_id__in=self._new_links):
            cache_obj.marks_total += 1
            if cache_obj.report_id in new_problems:
                problem = new_problems[cache_obj.report_id]
                cache_obj.problems.setdefault(problem, 0)
                cache_obj.problems[problem] += 1
            cache_obj.save()

    def __sum_safe_verdict(self, old_verdict):
        if self._mark.verdict == old_verdict:
            # V + V = V
            return old_verdict
        elif old_verdict == SAFE_VERDICTS[4][0]:
            # Without marks + V = V
            return self._mark.verdict
        elif old_verdict == SAFE_VERDICTS[3][0]:
            # Incompatible + V = Incompatible
            return SAFE_VERDICTS[3][0]
        # V1 + V2 = Incompatible
        return SAFE_VERDICTS[3][0]

    def __sum_unsafe_verdict(self, old_verdict):
        if self._mark.verdict == old_verdict:
            # V + V = V
            return old_verdict
        elif old_verdict == UNSAFE_VERDICTS[5][0]:
            # Without marks + V = V
            return self._mark.verdict
        elif old_verdict == UNSAFE_VERDICTS[4][0]:
            # Incompatible + V = Incompatible
            return UNSAFE_VERDICTS[4][0]
        # V1 + V2 = Incompatible
        return UNSAFE_VERDICTS[4][0]

    def __sum_tags(self, old_tags):
        old_tags = copy.deepcopy(old_tags)
        for tag_name in self._mark.cache_tags:
            old_tags.setdefault(tag_name, 0)
            old_tags[tag_name] += 1
        return old_tags


class UpdateCachesOnMarksDelete:
    def __init__(self, affected_reports):
        self._affected_reports = affected_reports

    def update_safes_cache(self):
        cache_queryset = ReportSafeCache.objects.filter(report_id__in=self._affected_reports)
        markreport_qs = MarkSafeReport.objects.filter(report_id__in=self._affected_reports)\
            .exclude(type=ASSOCIATION_TYPE[2][0]).select_related('mark')

        new_data = {}
        for cache_obj in cache_queryset:
            new_data[cache_obj.report_id] = {
                'marks_total': 0,
                'marks_confirmed': 0,
                'tags': {},
                'verdict': SAFE_VERDICTS[4][0]
            }

        reports_data = {}
        for mark_report in markreport_qs:
            reports_data.setdefault(mark_report.report_id, {'tags': [], 'verdicts': set()})
            reports_data[mark_report.report_id]['tags'] += mark_report.mark.cache_tags
            reports_data[mark_report.report_id]['verdicts'].add(mark_report.mark.verdict)

            new_data[mark_report.report_id]['marks_total'] += 1
            if mark_report.type == ASSOCIATION_TYPE[1][0]:
                new_data[mark_report.report_id]['marks_confirmed'] += 1

        # Calculate total verdict and tags cache
        for r_id in reports_data:
            if len(reports_data[r_id]['verdicts']) == 1:
                new_data[r_id]['verdict'] = reports_data[r_id]['verdicts'].pop()
            else:
                new_data[r_id]['verdict'] = SAFE_VERDICTS[3][0]

            new_data[r_id]['tags'] = dict(Counter(reports_data[r_id]['tags']))

        update_cache_atomic(cache_queryset, new_data)

    def update_unsafes_cache(self):
        cache_queryset = ReportUnsafeCache.objects.filter(report_id__in=self._affected_reports)
        markreport_qs = MarkUnsafeReport.objects.filter(report_id__in=self._affected_reports)\
            .exclude(type=ASSOCIATION_TYPE[2][0]).select_related('mark')

        new_data = {}
        for cache_obj in cache_queryset:
            new_data[cache_obj.report_id] = {
                'marks_total': 0,
                'marks_confirmed': 0,
                'total_similarity': 0,
                'tags': {},
                'verdict': UNSAFE_VERDICTS[5][0]
            }

        reports_data = {}
        for mark_report in markreport_qs:
            reports_data.setdefault(mark_report.report_id, {
                'tags': [], 'verdicts': set(), 'res_sum': 0
            })
            reports_data[mark_report.report_id]['tags'] += mark_report.mark.cache_tags
            reports_data[mark_report.report_id]['verdicts'].add(mark_report.mark.verdict)
            reports_data[mark_report.report_id]['res_sum'] += mark_report.result

            new_data[mark_report.report_id]['marks_total'] += 1
            if mark_report.type == ASSOCIATION_TYPE[1][0]:
                new_data[mark_report.report_id]['marks_confirmed'] += 1

        # Calculate total verdict, tags cache and total similarity
        for r_id in reports_data:
            if len(reports_data[r_id]['verdicts']) == 1:
                new_data[r_id]['verdict'] = reports_data[r_id]['verdicts'].pop()
            else:
                new_data[r_id]['verdict'] = UNSAFE_VERDICTS[4][0]

            new_data[r_id]['tags'] = dict(Counter(reports_data[r_id]['tags']))

            # If r_id in reports data then there is at least one mark association, so marks_total > 0
            new_data[r_id]['total_similarity'] = reports_data[r_id]['res_sum'] / new_data[r_id]['marks_total']

        update_cache_atomic(cache_queryset, new_data)


class UpdateReportCache:
    def __init__(self, report):
        self._report = report

    def update(self):
        if isinstance(self._report, ReportSafe):
            self.__update_safe_cache()
        elif isinstance(self._report, ReportUnsafe):
            self.__update_unsafe_cache()

    def __update_safe_cache(self):
        cache_obj = ReportSafeCache.objects.get(report=self._report)
        cache_obj.marks_total = 0
        cache_obj.marks_confirmed = 0

        verdicts = set()
        tags_list = []
        for verdict, ass_type, cache_tags in MarkSafeReport.objects\
                .filter(report=self._report).exclude(type=ASSOCIATION_TYPE[2][0]) \
                .values_list('mark__verdict', 'type', 'mark__cache_tags'):
            verdicts.add(verdict)
            tags_list += cache_tags

            cache_obj.marks_total += 1
            cache_obj.marks_confirmed += int(ass_type == ASSOCIATION_TYPE[1][0])

        # Calculate tags
        cache_obj.tags = dict(Counter(tags_list))

        # Set total verdict
        if len(verdicts) == 0:
            cache_obj.verdict = SAFE_VERDICTS[4][0]
        elif len(verdicts) == 1:
            cache_obj.verdict = verdicts.pop()
        else:
            cache_obj.verdict = SAFE_VERDICTS[3][0]

        cache_obj.save()

    def __update_unsafe_cache(self):
        cache_obj = ReportUnsafeCache.objects.get(report=self._report)
        cache_obj.marks_total = 0
        cache_obj.marks_confirmed = 0
        cache_obj.total_similarity = 0

        verdicts = set()
        tags_list = []
        similarity_sum = 0
        for verdict, ass_type, cache_tags, result in MarkUnsafeReport.objects\
                .filter(report=self._report, result__gt=0).exclude(type=ASSOCIATION_TYPE[2][0])\
                .values_list('mark__verdict', 'type', 'mark__cache_tags', 'result'):
            verdicts.add(verdict)
            tags_list += cache_tags
            similarity_sum += result

            cache_obj.marks_total += 1
            cache_obj.marks_confirmed += int(ass_type == ASSOCIATION_TYPE[1][0])

        # Calculate tags
        cache_obj.tags = dict(Counter(tags_list))

        # Calculate total similarity
        if cache_obj.marks_total > 0:
            cache_obj = similarity_sum / cache_obj.marks_total

        # Set total verdict
        if len(verdicts) == 0:
            cache_obj.verdict = UNSAFE_VERDICTS[5][0]
        elif len(verdicts) == 1:
            cache_obj.verdict = verdicts.pop()
        else:
            cache_obj.verdict = UNSAFE_VERDICTS[3][0]

        cache_obj.save()


class RecalculateSafeCache:
    def __init__(self, roots=None, reports=None):
        self._cache_queryset = self.__get_cache_queryset(roots=roots, reports=reports)
        self._markreport_qs = self.__get_markreport_qs(roots=roots, reports=reports)
        self._new_data = self.__initialize_cache()
        self.__update_cache()

    def __get_cache_queryset(self, roots=None, reports=None):
        if isinstance(roots, list):
            return ReportSafeCache.objects.filter(report__root_id__in=roots)
        elif isinstance(reports, (set, list)):
            return ReportSafeCache.objects.filter(report_id__in=reports)
        return ReportSafeCache.objects.all()

    def __get_markreport_qs(self, roots=None, reports=None):
        qs_filters = {}
        if isinstance(roots, list):
            qs_filters['report__root_id__in'] = roots
        elif isinstance(reports, (set, list)):
            qs_filters['report_id__in'] = reports
        return MarkSafeReport.objects.filter(**qs_filters).exclude(type=ASSOCIATION_TYPE[2][0]).select_related('mark')

    def __initialize_cache(self):
        new_data = {}
        for cache_obj in self._cache_queryset:
            new_data[cache_obj.report_id] = {
                'marks_total': 0,
                'marks_confirmed': 0,
                'tags': {},
                'verdict': SAFE_VERDICTS[4][0]
            }
        return new_data

    def __update_cache(self):
        for mr in self._markreport_qs:
            self.__add_verdict(mr.report_id, mr.mark.verdict)
            self.__add_tags(mr.report_id, mr.mark.cache_tags)
            self._new_data[mr.report_id]['marks_total'] += 1
            self._new_data[mr.report_id]['marks_confirmed'] += int(mr.type == ASSOCIATION_TYPE[1][0])
        update_cache_atomic(self._cache_queryset, self._new_data)

    def __add_verdict(self, report_id, verdict):
        old_verdict = self._new_data[report_id]['verdict']
        if old_verdict == SAFE_VERDICTS[4][0]:
            # No marks + V = V
            self._new_data[report_id]['verdict'] = verdict
        elif old_verdict == SAFE_VERDICTS[3][0]:
            # Incompatible + V = Incompatible
            return
        elif old_verdict != verdict:
            # V1 + V2 = Incompatible
            self._new_data[report_id]['verdict'] = SAFE_VERDICTS[3][0]
        else:
            # V + V = V
            return

    def __add_tags(self, report_id, tags_list):
        for tag in tags_list:
            self._new_data[report_id]['tags'].setdefault(tag, 0)
            self._new_data[report_id]['tags'][tag] += 1


class RecalculateUnsafeCache:
    def __init__(self, roots=None, reports=None):
        self._cache_queryset = self.__get_cache_queryset(roots=roots, reports=reports)
        self._markreport_qs = self.__get_markreport_qs(roots=roots, reports=reports)
        self._new_data = self.__initialize_cache()
        self.__update_cache()

    def __get_cache_queryset(self, roots=None, reports=None):
        if isinstance(roots, list):
            return ReportUnsafeCache.objects.filter(report__root_id__in=roots)
        elif isinstance(reports, (set, list)):
            return ReportUnsafeCache.objects.filter(report_id__in=reports)
        return ReportUnsafeCache.objects.all()

    def __get_markreport_qs(self, roots=None, reports=None):
        qs_filters = {'result__gt': 0}
        if isinstance(roots, list):
            qs_filters['report__root_id__in'] = roots
        elif isinstance(reports, (set, list)):
            qs_filters['report_id__in'] = reports
        return MarkUnsafeReport.objects.filter(**qs_filters).exclude(type=ASSOCIATION_TYPE[2][0]).select_related('mark')

    def __initialize_cache(self):
        new_data = {}
        for cache_obj in self._cache_queryset:
            new_data[cache_obj.report_id] = {
                'marks_total': 0,
                'marks_confirmed': 0,
                'total_similarity': 0,
                'tags': {},
                'verdict': UNSAFE_VERDICTS[5][0]
            }
        return new_data

    def __update_cache(self):
        result_sum = {}
        for mr in self._markreport_qs:
            result_sum.setdefault(mr.report_id, 0)
            result_sum[mr.report_id] += mr.result

            self.__add_verdict(mr.report_id, mr.mark.verdict)
            self.__add_tags(mr.report_id, mr.mark.cache_tags)
            self._new_data[mr.report_id]['marks_total'] += 1
            self._new_data[mr.report_id]['marks_confirmed'] += int(mr.type == ASSOCIATION_TYPE[1][0])

        for r_id in result_sum:
            # if r_id in result_sum then marks_total > 0
            self._new_data[r_id]['total_similarity'] = result_sum[r_id] / self._new_data[r_id]['marks_total']

        update_cache_atomic(self._cache_queryset, self._new_data)

    def __add_verdict(self, report_id, verdict):
        old_verdict = self._new_data[report_id]['verdict']
        if old_verdict == UNSAFE_VERDICTS[5][0]:
            # No marks + V = V
            self._new_data[report_id]['verdict'] = verdict
        elif old_verdict == UNSAFE_VERDICTS[4][0]:
            # Incompatible + V = Incompatible
            return
        elif old_verdict != verdict:
            # V1 + V2 = Incompatible
            self._new_data[report_id]['verdict'] = UNSAFE_VERDICTS[4][0]
        else:
            # V + V = V
            return

    def __add_tags(self, report_id, tags_list):
        for tag in tags_list:
            self._new_data[report_id]['tags'].setdefault(tag, 0)
            self._new_data[report_id]['tags'][tag] += 1


class RecalculateUnknownCache:
    def __init__(self, roots=None, reports=None):
        self._cache_queryset = self.__get_cache_queryset(roots=roots, reports=reports)
        self._markreport_qs = self.__get_markreport_qs(roots=roots, reports=reports)
        self._new_data = self.__initialize_cache()
        self.__update_cache()

    def __get_cache_queryset(self, roots=None, reports=None):
        if isinstance(roots, list):
            return ReportUnknownCache.objects.filter(report__root_id__in=roots)
        elif isinstance(reports, (set, list)):
            return ReportUnknownCache.objects.filter(report_id__in=reports)
        return ReportUnknownCache.objects.all()

    def __get_markreport_qs(self, roots=None, reports=None):
        qs_filters = {}
        if isinstance(roots, list):
            qs_filters['report__root_id__in'] = roots
        elif isinstance(reports, (set, list)):
            qs_filters['report_id__in'] = reports
        return MarkUnknownReport.objects.filter(**qs_filters).exclude(type=ASSOCIATION_TYPE[2][0])

    def __initialize_cache(self):
        new_data = {}
        for cache_obj in self._cache_queryset:
            new_data[cache_obj.report_id] = {
                'marks_total': 0,
                'marks_confirmed': 0,
                'problems': {}
            }
        return new_data

    def __update_cache(self):
        for mr in self._markreport_qs:
            self._new_data[mr.report_id]['problems'].setdefault(mr.problem, 0)
            self._new_data[mr.report_id]['problems'][mr.problem] += 1
            self._new_data[mr.report_id]['marks_total'] += 1
            self._new_data[mr.report_id]['marks_confirmed'] += int(mr.type == ASSOCIATION_TYPE[1][0])
        update_cache_atomic(self._cache_queryset, self._new_data)


class UpdateSafeCachesOnMarkTagsChange:
    def __init__(self, mark, report_links):
        self._mark = mark
        self._report_links = report_links

        self._cache_queryset = ReportSafeCache.objects.filter(report_id__in=self._report_links)
        self._markreport_qs = MarkSafeReport.objects\
            .filter(report_id__in=self._report_links)\
            .exclude(type=ASSOCIATION_TYPE[2][0]).select_related('mark')

        self._collected = set()
        self._new_data = dict((cache_obj.report_id, {}) for cache_obj in self._cache_queryset)
        self.__update()

    def __update(self):
        for cache_obj in self._cache_queryset:
            self._new_data[cache_obj.report_id]['tags'] = {}

        for mr in self._markreport_qs:
            self.__add_tags(mr.report_id, mr.mark.cache_tags)

        self._collected.add('tags')
        update_cache_atomic(self._cache_queryset, self._new_data)

    def __add_tags(self, report_id, tags_list):
        for tag in tags_list:
            self._new_data[report_id]['tags'].setdefault(tag, 0)
            self._new_data[report_id]['tags'][tag] += 1


class UpdateSafeMarksTags:
    def __init__(self):
        queryset = SafeTag.objects.all()
        self._db_tags = dict((t.id, t.parent_id) for t in queryset)
        self._names = dict((t.id, t.name) for t in queryset)

    def __new_tags(self, tags):
        new_tags = set()
        for t_id in tags:
            parent = self._db_tags[t_id]
            while parent:
                if parent not in tags:
                    new_tags.add(parent)
                parent = self._db_tags[parent]
        return new_tags

    def __get_affected_marks(self):
        version_tags = {}
        for marktag in MarkSafeTag.objects.all():
            version_tags.setdefault(marktag.mark_version_id, set())
            version_tags[marktag.mark_version_id].add(marktag.tag_id)

        changed_versions = {}
        for version_id in version_tags:
            new_tags = self.__new_tags(version_tags[version_id])
            if new_tags:
                changed_versions[version_id] = new_tags

        for mark_version in MarkSafeHistory.objects\
                .filter(id__in=changed_versions, version=F('mark__version')).select_related('mark'):
            old_tags = set(mark_version.mark.cache_tags)
            mark_tags_ids = version_tags[mark_version.id]
            if mark_version.id in changed_versions:
                mark_tags_ids |= changed_versions[mark_version.id]
            new_tags = set(self._names[t_id] for t_id in mark_tags_ids)
            if old_tags != new_tags:
                mark_version.mark.cache_tags = list(sorted(new_tags))
                mark_version.mark.save()
                report_links = self._mark_links[mark_version.mark_id]
                markcache = UpdateSafeCachesOnMarkChange(mark_version.mark, report_links, report_links)
                markcache.update_tags()
                markcache.save()

    @cached_property
    def _mark_links(self):
        data = {}
        for mark_id, report_id in MarkSafeReport.objects.values_list('mark_id', 'report_id'):
            data.setdefault(mark_id, set())
            data[mark_id].add(report_id)
        return data


class UpdateUnsafeMarksTags:
    def __init__(self):
        queryset = UnsafeTag.objects.all()
        self._db_tags = dict((t.id, t.parent_id) for t in queryset)
        self._names = dict((t.id, t.name) for t in queryset)

    def __new_tags(self, tags):
        new_tags = set()
        for t_id in tags:
            parent = self._db_tags[t_id]
            while parent:
                if parent not in tags:
                    new_tags.add(parent)
                parent = self._db_tags[parent]
        return new_tags

    def __get_affected_marks(self):
        version_tags = {}
        for marktag in MarkUnsafeTag.objects.all():
            version_tags.setdefault(marktag.mark_version_id, set())
            version_tags[marktag.mark_version_id].add(marktag.tag_id)

        changed_versions = {}
        for version_id in version_tags:
            new_tags = self.__new_tags(version_tags[version_id])
            if new_tags:
                changed_versions[version_id] = new_tags

        for mark_version in MarkUnsafeHistory.objects\
                .filter(id__in=changed_versions, version=F('mark__version')).select_related('mark'):
            old_tags = set(mark_version.mark.cache_tags)
            mark_tags_ids = version_tags[mark_version.id]
            if mark_version.id in changed_versions:
                mark_tags_ids |= changed_versions[mark_version.id]
            new_tags = set(self._names[t_id] for t_id in mark_tags_ids)
            if old_tags != new_tags:
                mark_version.mark.cache_tags = list(sorted(new_tags))
                mark_version.mark.save()
                report_links = self._mark_links[mark_version.mark_id]
                markcache = UpdateUnsafeCachesOnMarkChange(mark_version.mark, report_links, report_links)
                markcache.update_tags()
                markcache.save()

    @cached_property
    def _mark_links(self):
        data = {}
        for mark_id, report_id in MarkUnsafeReport.objects.values_list('mark_id', 'report_id'):
            data.setdefault(mark_id, set())
            data[mark_id].add(report_id)
        return data
