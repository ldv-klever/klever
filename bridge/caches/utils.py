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

from django.db import transaction
from django.db.models import F
from django.utils.functional import cached_property

from bridge.vars import SAFE_VERDICTS, UNSAFE_VERDICTS, ASSOCIATION_TYPE
from bridge.utils import require_lock

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
                'job_id': cache_obj.job_id,
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
                'job_id': cache_obj.job_id,
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
            self._new_data[cache_obj.report_id]['verdict'] = UNSAFE_VERDICTS[5][0]
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
            changes_objects.append(UnsafeMarkAssociationChanges(
                identifier=identifier, mark=self._mark,
                job_id=self._old_data[report_id]['job_id'], report_id=report_id,
                kind=self._change_kinds[report_id],
                verdict_old=verdict_old, verdict_new=verdict_new,
                tags_old=tags_old, tags_new=tags_new
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
        # If report has confirmed mark, then new populated mark can't affect its cache
        for cache_obj in ReportSafeCache.objects.filter(report_id__in=self._new_links, marks_confirmed=0):
            # Populated mark can't be confirmed, so we don't need to update confirmed number
            cache_obj.marks_total += 1
            cache_obj.verdict = self.__sum_safe_verdict(cache_obj.verdict)
            cache_obj.tags = self.__sum_tags(cache_obj.tags)
            cache_obj.save()

    @transaction.atomic
    def __update_unsafes(self):
        # Filter new_links with associations where associated flag is True
        affected_reports = set(MarkUnsafeReport.objects.filter(
            report_id__in=self._new_links, mark=self._mark, associated=True
        ).values_list('report_id', flat=True))

        for cache_obj in ReportUnsafeCache.objects.filter(report_id__in=affected_reports):
            # Populated mark can't be confirmed, so we don't need to update confirmed number
            cache_obj.marks_total += 1
            cache_obj.verdict = self.__sum_unsafe_verdict(cache_obj.verdict)
            cache_obj.tags = self.__sum_tags(cache_obj.tags)
            cache_obj.save()

    @transaction.atomic
    def __update_unknowns(self):
        new_problems = dict(MarkUnknownReport.objects.filter(mark=self._mark).values_list('report_id', 'problem'))

        # If report has confirmed mark, then new populated mark can't affect its cache
        for cache_obj in ReportUnknownCache.objects.filter(report_id__in=self._new_links, marks_confirmed=0):
            # Populated mark can't be confirmed, so we don't need to update confirmed number
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


class RecalculateSafeCache:
    def __init__(self, report_s):
        if isinstance(report_s, int):
            self.__recalculate(report_id=report_s)
        else:
            self.__recalculate(report_id__in=report_s)

    @require_lock(MarkSafeReport)
    def __recalculate(self, **kwargs):
        caches = {}
        for cache_obj in ReportSafeCache.objects.select_for_update().filter(**kwargs):
            self.__reset_cache_obj(cache_obj)
            caches[cache_obj.report_id] = cache_obj
        for mr in MarkSafeReport.objects.filter(associated=True, **kwargs).select_related('mark')\
                .only('type', 'mark__verdict', 'mark__cache_tags', 'report_id'):
            self.__update_cache_obj(caches[mr.report_id], mr)
        for cache_obj in caches.values():
            cache_obj.save()

    def __reset_cache_obj(self, cache_obj):
        cache_obj.marks_total = cache_obj.marks_confirmed = 0
        cache_obj.tags = {}
        cache_obj.verdict = SAFE_VERDICTS[4][0]

    def __update_cache_obj(self, cache_obj, mr):
        cache_obj.marks_total += 1
        cache_obj.marks_confirmed += int(mr.type == ASSOCIATION_TYPE[1][0])
        cache_obj.verdict = self.__sum_verdict(cache_obj.verdict, mr.mark.verdict)
        for tag in mr.mark.cache_tags:
            cache_obj.tags.setdefault(tag, 0)
            cache_obj.tags[tag] += 1

    def __sum_verdict(self, old_verdict, new_verdict):
        if old_verdict == SAFE_VERDICTS[4][0]:
            # No marks + V = V
            return new_verdict
        elif old_verdict == SAFE_VERDICTS[3][0]:
            # Incompatible + V = Incompatible
            return old_verdict
        elif old_verdict != new_verdict:
            # V1 + V2 = Incompatible
            return SAFE_VERDICTS[3][0]
        # V + V = V
        return new_verdict


class RecalculateUnsafeCache:
    def __init__(self, report_s):
        if isinstance(report_s, int):
            self.__recalculate(report_id=report_s)
        else:
            self.__recalculate(report_id__in=report_s)

    @require_lock(MarkUnsafeReport)
    def __recalculate(self, **kwargs):
        caches = {}
        for cache_obj in ReportUnsafeCache.objects.select_for_update().filter(**kwargs):
            self.__reset_cache_obj(cache_obj)
            caches[cache_obj.report_id] = cache_obj
        for mr in MarkUnsafeReport.objects.filter(associated=True, **kwargs).select_related('mark')\
                .only('type', 'mark__verdict', 'mark__cache_tags', 'report_id'):
            self.__update_cache_obj(caches[mr.report_id], mr)
        for cache_obj in caches.values():
            cache_obj.save()

    def __reset_cache_obj(self, cache_obj):
        cache_obj.marks_total = cache_obj.marks_confirmed = 0
        cache_obj.tags = {}
        cache_obj.verdict = UNSAFE_VERDICTS[5][0]

    def __update_cache_obj(self, cache_obj, mr):
        cache_obj.marks_total += 1
        cache_obj.marks_confirmed += int(mr.type == ASSOCIATION_TYPE[1][0])
        cache_obj.verdict = self.__sum_verdict(cache_obj.verdict, mr.mark.verdict)
        for tag in mr.mark.cache_tags:
            cache_obj.tags.setdefault(tag, 0)
            cache_obj.tags[tag] += 1

    def __sum_verdict(self, old_verdict, new_verdict):
        if old_verdict == UNSAFE_VERDICTS[5][0]:
            # No marks + V = V
            return new_verdict
        elif old_verdict == UNSAFE_VERDICTS[4][0]:
            # Incompatible + V = Incompatible
            return old_verdict
        elif old_verdict != new_verdict:
            # V1 + V2 = Incompatible
            return UNSAFE_VERDICTS[4][0]
        # V + V = V
        return new_verdict


class RecalculateUnknownCache:
    def __init__(self, report_s):
        if isinstance(report_s, int):
            self.__recalculate(report_id=report_s)
        else:
            self.__recalculate(report_id__in=report_s)

    @require_lock(MarkUnknownReport)
    def __recalculate(self, **kwargs):
        caches = {}
        for cache_obj in ReportUnknownCache.objects.select_for_update().filter(**kwargs):
            self.__reset_cache_obj(cache_obj)
            caches[cache_obj.report_id] = cache_obj
        for mr in MarkUnknownReport.objects.filter(associated=True, **kwargs).select_related('mark')\
                .only('type', 'problem', 'report_id'):
            self.__update_cache_obj(caches[mr.report_id], mr)
        for cache_obj in caches.values():
            cache_obj.save()

    def __reset_cache_obj(self, cache_obj):
        cache_obj.marks_total = cache_obj.marks_confirmed = 0
        cache_obj.problems = {}

    def __update_cache_obj(self, cache_obj, mr):
        cache_obj.marks_total += 1
        cache_obj.marks_confirmed += int(mr.type == ASSOCIATION_TYPE[1][0])
        cache_obj.problems.setdefault(mr.problem, 0)
        cache_obj.problems[mr.problem] += 1


class UpdateSafeMarksTags:
    def __init__(self):
        queryset = SafeTag.objects.all()
        self._db_tags = dict((t.id, t.parent_id) for t in queryset)
        self._names = dict((t.id, t.name) for t in queryset)
        self.__update_marks()

    def __new_tags(self, tags):
        new_tags = set()
        for t_id in tags:
            parent = self._db_tags[t_id]
            while parent:
                if parent not in tags:
                    new_tags.add(parent)
                parent = self._db_tags[parent]
        return new_tags

    def __update_marks(self):
        # Update only last versions
        version_tags = {}
        for marktag in MarkSafeTag.objects.filter(mark_version__version=F('mark_version__mark__version')):
            version_tags.setdefault(marktag.mark_version_id, set())
            version_tags[marktag.mark_version_id].add(marktag.tag_id)

        changed_versions = {}
        for version_id in version_tags:
            new_tags = self.__new_tags(version_tags[version_id])
            if new_tags:
                changed_versions[version_id] = new_tags

        for mark_version in MarkSafeHistory.objects.filter(id__in=changed_versions).select_related('mark'):
            old_tags = set(mark_version.mark.cache_tags)
            mark_tags_ids = version_tags[mark_version.id] | changed_versions[mark_version.id]
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
        self.__update_marks()

    def __new_tags(self, tags):
        new_tags = set()
        for t_id in tags:
            parent = self._db_tags[t_id]
            while parent:
                if parent not in tags:
                    new_tags.add(parent)
                parent = self._db_tags[parent]
        return new_tags

    def __update_marks(self):
        # Update only last versions
        version_tags = {}
        for marktag in MarkUnsafeTag.objects.filter(mark_version__version=F('mark_version__mark__version')):
            version_tags.setdefault(marktag.mark_version_id, set())
            version_tags[marktag.mark_version_id].add(marktag.tag_id)

        changed_versions = {}
        for version_id in version_tags:
            new_tags = self.__new_tags(version_tags[version_id])
            if new_tags:
                changed_versions[version_id] = new_tags

        for mark_version in MarkUnsafeHistory.objects.filter(id__in=changed_versions).select_related('mark'):
            old_tags = set(mark_version.mark.cache_tags)
            mark_tags_ids = version_tags[mark_version.id] | changed_versions[mark_version.id]
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
