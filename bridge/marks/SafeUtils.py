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

from bridge.vars import ASSOCIATION_TYPE
from reports.models import ReportSafe
from marks.models import MarkSafe, MarkSafeHistory, MarkSafeReport, SafeAssociationLike
from caches.models import ReportSafeCache

from caches.utils import UpdateSafeCachesOnMarkChange, RecalculateSafeCache


def perform_safe_mark_create(user, report, serializer):
    mark = serializer.save(job=report.root.job)
    res = ConnectSafeMark(mark, prime_id=report.id, author=user)
    cache_upd = UpdateSafeCachesOnMarkChange(mark, res.old_links, res.new_links)
    cache_upd.update_all()
    return mark, cache_upd.save()


def perform_safe_mark_update(user, serializer):
    mark = serializer.instance

    # Preserve data before we change the mark
    old_cache = {
        'attrs': copy.deepcopy(mark.cache_attrs),
        'tags': copy.deepcopy(mark.cache_tags),
        'verdict': mark.verdict
    }

    # Change the mark
    autoconfirm = serializer.validated_data['mark_version']['autoconfirm']
    mark = serializer.save()

    # Update reports cache
    if old_cache['attrs'] != mark.cache_attrs:
        res = ConnectSafeMark(mark, author=user)
        cache_upd = UpdateSafeCachesOnMarkChange(mark, res.old_links, res.new_links)
        cache_upd.update_all()
    else:
        mark_report_qs = MarkSafeReport.objects.filter(mark=mark)
        old_links = new_links = set(mr.report_id for mr in mark_report_qs)
        cache_upd = UpdateSafeCachesOnMarkChange(mark, old_links, new_links)

        if not autoconfirm:
            # Reset association type and remove likes
            mark_report_qs.update(type=ASSOCIATION_TYPE[0][0])
            SafeAssociationLike.objects.filter(association__mark=mark).delete()
            cache_upd.update_all()

        if old_cache['tags'] != mark.cache_tags:
            cache_upd.update_tags()

        if old_cache['verdict'] != mark.verdict:
            cache_upd.update_verdicts()

    # Reutrn association changes cache identifier
    return cache_upd.save()


def remove_safe_marks(**kwargs):
    queryset = MarkSafe.objects.filter(**kwargs)
    if not queryset.count():
        return
    qs_filters = dict(('mark__{}'.format(k), v) for k, v in kwargs.items())
    affected_reports = set(MarkSafeReport.objects.filter(**qs_filters).values_list('report_id', flat=True))
    queryset.delete()
    RecalculateSafeCache(reports=affected_reports)


def confirm_safe_mark(user, mark_report):
    if mark_report.type == ASSOCIATION_TYPE[1][0]:
        return
    was_unconfirmed = (mark_report.type == ASSOCIATION_TYPE[2][0])
    mark_report.author = user
    mark_report.type = ASSOCIATION_TYPE[1][0]
    mark_report.associated = True
    mark_report.save()

    # Do not count automatic associations as there is already confirmed one
    change_num = MarkSafeReport.objects.filter(
        report_id=mark_report.report_id, associated=True, type=ASSOCIATION_TYPE[0][0]
    ).update(associated=False)

    if was_unconfirmed or change_num:
        RecalculateSafeCache(reports=[mark_report.report_id])
    else:
        cache_obj = ReportSafeCache.objects.get(report_id=mark_report.report_id)
        cache_obj.marks_confirmed += 1
        cache_obj.save()


def unconfirm_safe_mark(user, mark_report):
    if mark_report.type == ASSOCIATION_TYPE[2][0]:
        return
    was_confirmed = bool(mark_report.type == ASSOCIATION_TYPE[1][0])
    mark_report.author = user
    mark_report.type = ASSOCIATION_TYPE[2][0]
    mark_report.associated = False
    mark_report.save()

    if was_confirmed and not MarkSafeReport.objects\
            .filter(report_id=mark_report.report_id, type=ASSOCIATION_TYPE[1][0]).exists():
        # The report has lost the only confirmed mark,
        # so we need recalculate what associations we need to count for caches
        MarkSafeReport.objects.filter(report_id=mark_report.report_id)\
            .exclude(type=ASSOCIATION_TYPE[2][0]).update(associated=True)

    RecalculateSafeCache(reports=[mark_report.report_id])


class ConnectSafeMark:
    def __init__(self, mark, prime_id=None, author=None):
        self._mark = mark
        self.old_links = self.__clear_old_associations()
        self.new_links = self.__add_new_associations(prime_id, author)

    def __clear_old_associations(self):
        mark_reports_qs = MarkSafeReport.objects.filter(mark=self._mark)
        reports = set(mark_reports_qs.values_list('report_id', flat=True))
        mark_reports_qs.delete()
        return reports

    def __add_new_associations(self, prime_id, author):
        if author is None:
            last_version = MarkSafeHistory.objects.get(mark=self._mark, version=self._mark.version)
            author = last_version.author

        new_links = set()
        associations = []
        for report in ReportSafe.objects.filter(cache__attrs__contains=self._mark.cache_attrs)\
                .select_related('cache').only('id', 'cache__marks_confirmed'):
            new_association = MarkSafeReport(
                mark=self._mark, report_id=report.id, author=author,
                type=ASSOCIATION_TYPE[0][0], associated=True
            )
            if prime_id and report.id == prime_id:
                new_association.type = ASSOCIATION_TYPE[1][0]
            elif report.cache.marks_confirmed:
                # Do not count automatic associations if report has confirmed ones
                new_association.associated = False
            associations.append(new_association)
            new_links.add(report.id)
        MarkSafeReport.objects.bulk_create(associations)
        return new_links


# Used only after report is created, so there are never old associations
class ConnectSafeReport:
    def __init__(self, safe):
        self._report = safe
        self.__connect()

    def __connect(self):
        marks_qs = MarkSafe.objects.filter(cache_attrs__contained_by=self._report.cache.attrs)
        MarkSafeReport.objects.bulk_create(list(
            MarkSafeReport(mark_id=m_id, report=self._report, associated=True)
            for m_id in marks_qs.values_list('id', flat=True)
        ))
        RecalculateSafeCache(reports=[self._report.id])
