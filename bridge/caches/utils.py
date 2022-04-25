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

import copy
import uuid
from collections import defaultdict

from django.db import transaction
from django.db.models import Q, F, Count
from django.utils.functional import cached_property

from bridge.vars import SAFE_VERDICTS, UNSAFE_VERDICTS, ASSOCIATION_TYPE

from marks.models import (
    MarkSafe, MarkSafeHistory, MarkUnsafe, MarkUnsafeHistory, MarkUnknown,
    MarkSafeReport, MarkUnsafeReport, MarkUnknownReport, MarkSafeTag, MarkUnsafeTag, Tag
)
from caches.models import (
    ASSOCIATION_CHANGE_KIND, ReportSafeCache, ReportUnsafeCache, ReportUnknownCache,
    SafeMarkAssociationChanges, UnsafeMarkAssociationChanges, UnknownMarkAssociationChanges
)
from reports.verdicts import safe_verdicts_sum, unsafe_verdicts_sum, BugStatusCollector


@transaction.atomic
def update_cache_atomic(queryset, data):
    for rep_cache in queryset.select_for_update():
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
            .filter(report_id__in=self._affected_reports, associated=True).select_related('mark')

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
                'decision_id': cache_obj.decision_id,
                'verdict': cache_obj.verdict,
                'tags': cache_obj.tags
            }
        return old_data

    def __init_new_data(self):
        return dict((cache_obj.report_id, {}) for cache_obj in self._cache_queryset)

    def update_all(self):
        if 'verdicts' in self._collected and 'tags' in self._collected:
            return
        for cache_obj in self._cache_queryset:
            self._new_data[cache_obj.report_id]['verdict'] = SAFE_VERDICTS[4][0]
            self._new_data[cache_obj.report_id]['tags'] = {}
            self._new_data[cache_obj.report_id]['marks_total'] = 0
            self._new_data[cache_obj.report_id]['marks_confirmed'] = 0
            self._new_data[cache_obj.report_id]['marks_automatic'] = 0

        # Count automatic associations
        automatic_qs = MarkSafeReport.objects\
            .filter(report_id__in=self._affected_reports, type=ASSOCIATION_TYPE[2][0]).values('report_id')\
            .annotate(number=Count('report_id')).values_list('report_id', 'number')
        for report_id, automatic_num in automatic_qs:
            self._new_data[report_id]['marks_automatic'] = automatic_num

        for mr in self._markreport_qs:
            self.__add_verdict(mr.report_id, mr.mark.verdict)
            self.__add_tags(mr.report_id, mr.mark.cache_tags)
            self._new_data[mr.report_id]['marks_total'] += 1
            self._new_data[mr.report_id]['marks_confirmed'] += int(mr.type == ASSOCIATION_TYPE[3][0])

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
        self._new_data[report_id]['verdict'] = safe_verdicts_sum(self._new_data[report_id]['verdict'], verdict)

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
                decision_id=self._old_data[report_id]['decision_id'], report_id=report_id,
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
            .filter(report_id__in=self._affected_reports, associated=True).select_related('mark')

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
                'decision_id': cache_obj.decision_id,
                'verdict': cache_obj.verdict,
                'status': cache_obj.status,
                'tags': cache_obj.tags
            }
        return old_data

    def __init_new_data(self):
        return dict((cache_obj.report_id, {}) for cache_obj in self._cache_queryset)

    def update_all(self):
        if 'verdicts' in self._collected and 'tags' in self._collected:
            return

        for cache_obj in self._cache_queryset:
            self._new_data[cache_obj.report_id]['verdict'] = UNSAFE_VERDICTS[5][0]
            self._new_data[cache_obj.report_id]['status'] = None
            self._new_data[cache_obj.report_id]['tags'] = {}
            self._new_data[cache_obj.report_id]['marks_total'] = 0
            self._new_data[cache_obj.report_id]['marks_confirmed'] = 0
            self._new_data[cache_obj.report_id]['marks_automatic'] = 0

        # Count automatic associations
        automatic_qs = MarkUnsafeReport.objects \
            .filter(report_id__in=self._affected_reports, type=ASSOCIATION_TYPE[2][0]).values('report_id') \
            .annotate(number=Count('report_id')).values_list('report_id', 'number')
        for report_id, automatic_num in automatic_qs:
            self._new_data[report_id]['marks_automatic'] = automatic_num

        statuses_collector = BugStatusCollector()
        for mr in self._markreport_qs:
            self.__add_verdict(mr.report_id, mr.mark.verdict)
            statuses_collector.add(mr.report_id, mr.mark.verdict, mr.mark.status)
            self.__add_tags(mr.report_id, mr.mark.cache_tags)
            self._new_data[mr.report_id]['marks_total'] += 1
            self._new_data[mr.report_id]['marks_confirmed'] += int(mr.type == ASSOCIATION_TYPE[3][0])

        for report_id, status in statuses_collector.result.items():
            self._new_data[report_id]['status'] = status

        self._collected.add('verdicts')
        self._collected.add('statuses')
        self._collected.add('tags')

    def update_verdicts(self):
        if 'verdicts' in self._collected:
            return

        for cache_obj in self._cache_queryset:
            self._new_data[cache_obj.report_id]['verdict'] = UNSAFE_VERDICTS[5][0]

        for mr in self._markreport_qs:
            self.__add_verdict(mr.report_id, mr.mark.verdict)

        self._collected.add('verdicts')

    def update_statuses(self):
        if 'statuses' in self._collected:
            return
        for cache_obj in self._cache_queryset:
            self._new_data[cache_obj.report_id]['status'] = None

        statuses_collector = BugStatusCollector()
        for mr in self._markreport_qs:
            statuses_collector.add(mr.report_id, mr.mark.verdict, mr.mark.status)
        for report_id, status in statuses_collector.result.items():
            self._new_data[report_id]['status'] = status

        self._collected.add('statuses')

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
        self._new_data[report_id]['verdict'] = unsafe_verdicts_sum(self._new_data[report_id]['verdict'], verdict)

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
            status_old = self._old_data[report_id]['status']
            status_new = self._new_data[report_id].get('status', status_old)
            tags_old = self._old_data[report_id]['tags']
            tags_new = self._new_data[report_id].get('tags', tags_old)
            changes_objects.append(UnsafeMarkAssociationChanges(
                identifier=identifier, mark=self._mark,
                decision_id=self._old_data[report_id]['decision_id'], report_id=report_id,
                kind=self._change_kinds[report_id],
                verdict_old=verdict_old, verdict_new=verdict_new,
                tags_old=tags_old, tags_new=tags_new,
                status_old=status_old, status_new=status_new
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
        self._markreport_qs = MarkUnknownReport.objects.filter(report_id__in=self._affected_reports, associated=True)

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
                'decision_id': cache_obj.decision_id,
                'problems': cache_obj.problems
            }
        return old_data

    def __init_new_data(self):
        return dict((cache_obj.report_id, {}) for cache_obj in self._cache_queryset)

    def update_all(self):
        for cache_obj in self._cache_queryset:
            self._new_data[cache_obj.report_id]['problems'] = {}
            self._new_data[cache_obj.report_id]['marks_total'] = 0
            self._new_data[cache_obj.report_id]['marks_confirmed'] = 0
            self._new_data[cache_obj.report_id]['marks_automatic'] = 0

        # Count automatic associations
        automatic_qs = MarkUnknownReport.objects \
            .filter(report_id__in=self._affected_reports, type=ASSOCIATION_TYPE[2][0]).values('report_id') \
            .annotate(number=Count('report_id')).values_list('report_id', 'number')
        for report_id, automatic_num in automatic_qs:
            self._new_data[report_id]['marks_automatic'] = automatic_num

        for mr in self._markreport_qs:
            self._new_data[mr.report_id]['problems'].setdefault(mr.problem, 0)
            self._new_data[mr.report_id]['problems'][mr.problem] += 1
            self._new_data[mr.report_id]['marks_total'] += 1
            self._new_data[mr.report_id]['marks_confirmed'] += int(mr.type == ASSOCIATION_TYPE[3][0])

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
                decision_id=self._old_data[report_id]['decision_id'], report_id=report_id,
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
        for cache_obj in ReportSafeCache.objects.filter(report_id__in=self._new_links).select_for_update():
            # All safe links after the population are automatic
            cache_obj.marks_automatic += 1

            if cache_obj.marks_confirmed == 0:
                # If report has confirmed mark, then new populated mark can't affect its cache
                cache_obj.verdict = safe_verdicts_sum(cache_obj.verdict, self._mark.verdict)
                cache_obj.tags = self.__sum_tags(cache_obj.tags)
                cache_obj.marks_total += 1

            # Populated mark can't be confirmed, so we don't need to update confirmed number
            cache_obj.save()

    def __update_unsafes(self):
        # Filter new_links with automatic associations as just such associations can affect report's cache
        affected_reports = set(MarkUnsafeReport.objects.filter(
            report_id__in=self._new_links, mark=self._mark, type=ASSOCIATION_TYPE[2][0]
        ).values_list('report_id', flat=True))

        with transaction.atomic():
            for cache_obj in ReportUnsafeCache.objects.filter(report_id__in=affected_reports).select_for_update():
                cache_obj.marks_automatic += 1
                if cache_obj.marks_confirmed == 0:
                    # If report has confirmed mark, then new populated mark can't affect its cache
                    cache_obj.verdict = unsafe_verdicts_sum(cache_obj.verdict, self._mark.verdict)
                    cache_obj.status = BugStatusCollector.sum(cache_obj.status, self._mark.status, cache_obj.verdict)
                    cache_obj.tags = self.__sum_tags(cache_obj.tags)
                    cache_obj.marks_total += 1
                # Populated mark can't be confirmed, so we don't need to update confirmed number
                cache_obj.save()

    def __update_unknowns(self):
        new_problems = dict(MarkUnknownReport.objects.filter(mark=self._mark).values_list('report_id', 'problem'))

        with transaction.atomic():
            for cache_obj in ReportUnknownCache.objects.filter(report_id__in=self._new_links)\
                    .select_for_update():
                # All unknown links after the population are automatic
                cache_obj.marks_automatic += 1

                # If report has confirmed mark, then new populated mark can't affect its cache
                if cache_obj.marks_confirmed == 0 and cache_obj.report_id in new_problems:
                    problem = new_problems[cache_obj.report_id]
                    cache_obj.problems.setdefault(problem, 0)
                    cache_obj.problems[problem] += 1
                    cache_obj.marks_total += 1

                # Populated mark can't be confirmed, so we don't need to update confirmed number
                cache_obj.save()

    def __sum_tags(self, old_tags):
        old_tags = copy.deepcopy(old_tags)
        for tag_name in self._mark.cache_tags:
            old_tags.setdefault(tag_name, 0)
            old_tags[tag_name] += 1
        return old_tags


class RecalculateSafeCache:
    def __init__(self, report_s):
        if isinstance(report_s, int):
            self._qs_filter = Q(report_id=report_s)
        else:
            self._qs_filter = Q(report_id__in=report_s)
        self.__recalculate()

    def __recalculate(self):
        cache_queryset = ReportSafeCache.objects.filter(self._qs_filter)

        # Initialize default values
        new_data = {}
        for cache_obj in cache_queryset:
            new_data[cache_obj.report_id] = {
                'tags': {},
                'verdict': SAFE_VERDICTS[4][0],
                'marks_total': 0,
                'marks_automatic': 0,
                'marks_confirmed': 0
            }

        # Collect safes cache (just automatic and confirmed associations can affect the cache)
        markreport_qs = MarkSafeReport.objects.filter(
            Q(type__in=[ASSOCIATION_TYPE[2][0], ASSOCIATION_TYPE[3][0]]) & self._qs_filter
        ).select_related('mark').only('type', 'mark__verdict', 'mark__cache_tags', 'report_id', 'associated')
        for mr in markreport_qs:
            new_data[mr.report_id]['marks_automatic'] += int(mr.type == ASSOCIATION_TYPE[2][0])
            if not mr.associated:
                continue
            new_data[mr.report_id]['marks_total'] += 1
            new_data[mr.report_id]['marks_confirmed'] += int(mr.type == ASSOCIATION_TYPE[3][0])
            new_data[mr.report_id]['verdict'] = safe_verdicts_sum(
                new_data[mr.report_id]['verdict'], mr.mark.verdict
            )
            for tag in mr.mark.cache_tags:
                new_data[mr.report_id]['tags'].setdefault(tag, 0)
                new_data[mr.report_id]['tags'][tag] += 1

        update_cache_atomic(cache_queryset, new_data)


class RecalculateUnsafeCache:
    def __init__(self, report_s):
        if isinstance(report_s, int):
            self._qs_filter = Q(report_id=report_s)
        else:
            self._qs_filter = Q(report_id__in=report_s)
        self.__recalculate()

    def __recalculate(self):
        cache_queryset = ReportUnsafeCache.objects.filter(self._qs_filter)

        # Initialize default values
        new_data = {}
        for cache_obj in cache_queryset:
            new_data[cache_obj.report_id] = {
                'tags': {},
                'verdict': UNSAFE_VERDICTS[5][0],
                'status': None,
                'marks_total': 0,
                'marks_automatic': 0,
                'marks_confirmed': 0
            }

        statuses_collector = BugStatusCollector()

        # Collect unsafes cache (just automatic and confirmed associations can affect the cache)
        markreport_qs = MarkUnsafeReport.objects.filter(
            Q(type__in=[ASSOCIATION_TYPE[2][0], ASSOCIATION_TYPE[3][0]]) & self._qs_filter
        ).select_related('mark').only('type', 'mark__verdict', 'mark__cache_tags', 'report_id', 'associated')
        for mr in markreport_qs:
            new_data[mr.report_id]['marks_automatic'] += int(mr.type == ASSOCIATION_TYPE[2][0])
            if not mr.associated:
                continue
            new_data[mr.report_id]['marks_total'] += 1
            new_data[mr.report_id]['marks_confirmed'] += int(mr.type == ASSOCIATION_TYPE[3][0])
            new_data[mr.report_id]['verdict'] = unsafe_verdicts_sum(
                new_data[mr.report_id]['verdict'], mr.mark.verdict
            )
            statuses_collector.add(mr.report_id, mr.mark.verdict, mr.mark.status)
            for tag in mr.mark.cache_tags:
                new_data[mr.report_id]['tags'].setdefault(tag, 0)
                new_data[mr.report_id]['tags'][tag] += 1

        for report_id, status in statuses_collector.result.items():
            new_data[report_id]['status'] = status

        update_cache_atomic(cache_queryset, new_data)


class RecalculateUnknownCache:
    def __init__(self, report_s):
        if isinstance(report_s, int):
            self._qs_filter = Q(report_id=report_s)
        else:
            self._qs_filter = Q(report_id__in=report_s)
        self.__recalculate()

    def __recalculate(self):
        cache_queryset = ReportUnknownCache.objects.filter(self._qs_filter)

        # Initialize default values
        new_data = {}
        for cache_obj in cache_queryset:
            new_data[cache_obj.report_id] = {
                'problems': {},
                'marks_total': 0,
                'marks_automatic': 0,
                'marks_confirmed': 0
            }

        # Collect unsafes cache (just automatic and confirmed associations can affect the cache)
        markreport_qs = MarkUnknownReport.objects.filter(
            Q(type__in=[ASSOCIATION_TYPE[2][0], ASSOCIATION_TYPE[3][0]]) & self._qs_filter
        ).only('type', 'problem', 'report_id', 'associated')
        for mr in markreport_qs:
            new_data[mr.report_id]['marks_automatic'] += int(mr.type == ASSOCIATION_TYPE[2][0])
            if not mr.associated:
                continue
            new_data[mr.report_id]['marks_total'] += 1
            new_data[mr.report_id]['marks_confirmed'] += int(mr.type == ASSOCIATION_TYPE[3][0])
            new_data[mr.report_id]['problems'].setdefault(mr.problem, 0)
            new_data[mr.report_id]['problems'][mr.problem] += 1

        update_cache_atomic(cache_queryset, new_data)


class UpdateMarksTags:
    def __init__(self):
        queryset = Tag.objects.all()
        self._db_tags = dict((t.id, t.parent_id) for t in queryset)
        self._names = dict((t.id, t.name) for t in queryset)
        self.__update_safe_marks()
        self.__update_unsafe_marks()

    def __new_tags(self, tags):
        new_tags = set()
        for t_id in tags:
            parent = self._db_tags[t_id]
            while parent:
                if parent not in tags:
                    new_tags.add(parent)
                parent = self._db_tags[parent]
        return new_tags

    def __update_safe_marks(self):
        # Update only last versions
        version_tags = defaultdict(set)
        for marktag in MarkSafeTag.objects.filter(mark_version__version=F('mark_version__mark__version')):
            version_tags[marktag.mark_version_id].add(marktag.tag_id)

        changed_versions = {}
        for version_id in version_tags:
            new_tags = self.__new_tags(version_tags[version_id])
            if new_tags:
                changed_versions[version_id] = new_tags

        mark_links = defaultdict(set)
        for mark_id, report_id in MarkSafeReport.objects.values_list('mark_id', 'report_id'):
            mark_links[mark_id].add(report_id)

        for mark_version in MarkSafeHistory.objects.filter(id__in=changed_versions).select_related('mark'):
            old_tags = set(mark_version.mark.cache_tags)
            mark_tags_ids = version_tags[mark_version.id] | changed_versions[mark_version.id]
            new_tags = set(self._names[t_id] for t_id in mark_tags_ids)
            if old_tags != new_tags:
                mark_version.mark.cache_tags = list(sorted(new_tags))
                mark_version.mark.save()
                report_links = mark_links[mark_version.mark_id]
                markcache = UpdateSafeCachesOnMarkChange(mark_version.mark, report_links, report_links)
                markcache.update_tags()
                markcache.save()

    def __update_unsafe_marks(self):
        # Update only last versions
        version_tags = defaultdict(set)
        for marktag in MarkUnsafeTag.objects.filter(mark_version__version=F('mark_version__mark__version')):
            version_tags[marktag.mark_version_id].add(marktag.tag_id)

        changed_versions = {}
        for version_id in version_tags:
            new_tags = self.__new_tags(version_tags[version_id])
            if new_tags:
                changed_versions[version_id] = new_tags

        mark_links = defaultdict(set)
        for mark_id, report_id in MarkUnsafeReport.objects.values_list('mark_id', 'report_id'):
            mark_links[mark_id].add(report_id)

        for mark_version in MarkUnsafeHistory.objects.filter(id__in=changed_versions).select_related('mark'):
            old_tags = set(mark_version.mark.cache_tags)
            mark_tags_ids = version_tags[mark_version.id] | changed_versions[mark_version.id]
            new_tags = set(self._names[t_id] for t_id in mark_tags_ids)
            if old_tags != new_tags:
                mark_version.mark.cache_tags = list(sorted(new_tags))
                mark_version.mark.save()
                report_links = mark_links[mark_version.mark_id]
                markcache = UpdateUnsafeCachesOnMarkChange(mark_version.mark, report_links, report_links)
                markcache.update_tags()
                markcache.save()
