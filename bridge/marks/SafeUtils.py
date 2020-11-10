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

from bridge.vars import ASSOCIATION_TYPE
from bridge.utils import require_lock

from reports.models import ReportSafe
from marks.models import MarkSafeHistory, MarkSafeReport

from marks.utils import ConfirmAssociationBase, UnconfirmAssociationBase
from caches.utils import UpdateSafeCachesOnMarkChange, RecalculateSafeCache


def perform_safe_mark_create(user, report, serializer):
    mark = serializer.save(job=report.decision.job)
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

        if old_cache['tags'] != mark.cache_tags:
            cache_upd.update_tags()

        if old_cache['verdict'] != mark.verdict:
            cache_upd.update_verdicts()

    # Reutrn association changes cache identifier
    return cache_upd.save()


class RemoveSafeMark:
    def __init__(self, mark):
        self._mark = mark

    @require_lock(MarkSafeReport)
    def destroy(self):
        affected_reports = set(MarkSafeReport.objects.filter(mark=self._mark).values_list('report_id', flat=True))
        self._mark.delete()

        # Find reports that have marks associations when all association are disabled. It can be in 2 cases:
        # 1) All associations are unconfirmed/dissimilar
        # 2) All confirmed associations were with deleted mark
        # We need to update 2nd case, so automatic associations are counting again
        changed_ids = affected_reports - set(MarkSafeReport.objects.filter(
            report_id__in=affected_reports, associated=True
        ).values_list('report_id', flat=True))

        # Count automatic associations again
        MarkSafeReport.objects.filter(report_id__in=changed_ids, type=ASSOCIATION_TYPE[2][0]).update(associated=True)

        return affected_reports


class ConfirmSafeMark(ConfirmAssociationBase):
    model = MarkSafeReport

    def recalculate_cache(self, report_id):
        RecalculateSafeCache(report_id)


class UnconfirmSafeMark(UnconfirmAssociationBase):
    model = MarkSafeReport

    def recalculate_cache(self, report_id):
        RecalculateSafeCache(report_id)


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
                type=ASSOCIATION_TYPE[2][0], associated=True
            )
            if prime_id and report.id == prime_id:
                new_association.type = ASSOCIATION_TYPE[3][0]
            elif report.cache.marks_confirmed:
                # Do not count automatic associations if report has confirmed ones
                new_association.associated = False
            associations.append(new_association)
            new_links.add(report.id)
        MarkSafeReport.objects.bulk_create(associations)

        if prime_id:
            # Disable automatic associations
            MarkSafeReport.objects.filter(
                report_id=prime_id, associated=True, type=ASSOCIATION_TYPE[2][0]
            ).update(associated=False)
        return new_links
