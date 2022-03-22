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
import json
import re

from django.utils.translation import gettext_lazy as _

from bridge.vars import ASSOCIATION_TYPE, PROBLEM_DESC_FILE
from bridge.utils import BridgeException, logger, ArchiveFileContent, require_lock

from reports.models import ReportUnknown
from marks.models import MAX_PROBLEM_LEN, MarkUnknownHistory, MarkUnknownReport

from marks.utils import ConfirmAssociationBase, UnconfirmAssociationBase
from caches.utils import RecalculateUnknownCache, UpdateUnknownCachesOnMarkChange


def perform_unknown_mark_create(user, report, serializer):
    mark = serializer.save(job=report.decision.job, component=report.component)
    res = ConnectUnknownMark(mark, prime_id=report.id, author=user)
    cache_upd = UpdateUnknownCachesOnMarkChange(mark, res.old_links, res.new_links)
    cache_upd.update_all()
    return mark, cache_upd.save()


def perform_unknown_mark_update(user, serializer):
    mark = serializer.instance

    # Preserve data before we change the mark
    old_cache = {
        'cache_attrs': copy.deepcopy(mark.cache_attrs),
        'function': mark.function,
        'problem_pattern': mark.problem_pattern,
        'is_regexp': mark.is_regexp
    }

    # Change the mark
    mark = serializer.save()

    # Update reports cache
    if any(getattr(mark, f_name) != old_cache[f_name] for f_name in old_cache):
        res = ConnectUnknownMark(mark, author=user)
        cache_upd = UpdateUnknownCachesOnMarkChange(mark, res.old_links, res.new_links)
        cache_upd.update_all()
    else:
        mark_report_qs = MarkUnknownReport.objects.filter(mark=mark)
        old_links = new_links = set(mr.report_id for mr in mark_report_qs)
        cache_upd = UpdateUnknownCachesOnMarkChange(mark, old_links, new_links)

    # Return association changes cache identifier
    return cache_upd.save()


class RemoveUnknownMark:
    def __init__(self, mark):
        self._mark = mark

    @require_lock(MarkUnknownReport)
    def destroy(self):
        affected_reports = set(MarkUnknownReport.objects.filter(mark=self._mark).values_list('report_id', flat=True))
        self._mark.delete()

        # Find reports that have marks associations when all association are disabled. It can be in 2 cases:
        # 1) All associations are unconfirmed/dissimilar
        # 2) All confirmed associations were with deleted mark
        # We need to update 2nd case, so automatic associations are counting again
        changed_ids = affected_reports - set(MarkUnknownReport.objects.filter(
            report_id__in=affected_reports, associated=True
        ).values_list('report_id', flat=True))

        # Count automatic associations again
        MarkUnknownReport.objects.filter(report_id__in=changed_ids, type=ASSOCIATION_TYPE[2][0]).update(associated=True)

        return affected_reports


class ConfirmUnknownMark(ConfirmAssociationBase):
    model = MarkUnknownReport

    def recalculate_cache(self, report_id):
        RecalculateUnknownCache(report_id)


class UnconfirmUnknownMark(UnconfirmAssociationBase):
    model = MarkUnknownReport

    def recalculate_cache(self, report_id):
        RecalculateUnknownCache(report_id)


class MatchUnknown:
    def __init__(self, description, func, pattern, is_regexp):
        self.description = description
        self.function = func
        self.pattern = pattern
        if is_regexp:
            self.problem = self.__match_desc_regexp()
        else:
            self.problem = self.__match_desc()

        if isinstance(self.problem, str) and len(self.problem) == 0:
            self.problem = None
        if isinstance(self.problem, str) and len(self.problem) > MAX_PROBLEM_LEN:
            logger.error("Generated problem '%s' is too long" % self.problem)
            self.problem = 'Too long!'

    def __match_desc_regexp(self):
        try:
            m = re.search(self.function, self.description, re.MULTILINE)
        except Exception as e:
            logger.exception("Regexp error: %s" % e, stack_info=True)
            return None
        if m is None:
            return None
        try:
            return self.pattern.format(*m.groups())
        except IndexError:
            return self.pattern

    def __match_desc(self):
        if self.description.find(self.function) < 0:
            return None
        return self.pattern


class ConnectUnknownMark:
    def __init__(self, mark, prime_id=None, author=None):
        self._mark = mark
        self.old_links = self.__clear_old_associations()
        self.new_links = self.__add_new_associations(prime_id, author)

    def __clear_old_associations(self):
        mark_reports_qs = MarkUnknownReport.objects.filter(mark=self._mark)
        reports = set(mark_reports_qs.values_list('report_id', flat=True))
        mark_reports_qs.delete()
        return reports

    def __get_unknown_desc(self, report):
        try:
            return ArchiveFileContent(report, 'problem_description', PROBLEM_DESC_FILE).content.decode('utf8')
        except Exception as e:
            logger.error("Can't get problem description for unknown '%s': %s" % (report.id, e))
            return None

    def __add_new_associations(self, prime_id, author):
        if author is None:
            last_version = MarkUnknownHistory.objects.get(mark=self._mark, version=self._mark.version)
            author = last_version.author

        new_links = set()
        associations = []
        for report in ReportUnknown.objects\
                .filter(component=self._mark.component, cache__attrs__contains=self._mark.cache_attrs)\
                .select_related('cache').only('id', 'problem_description', 'cache__marks_confirmed'):
            unknown_desc = self.__get_unknown_desc(report)
            if not unknown_desc:
                continue
            problem = MatchUnknown(
                unknown_desc, self._mark.function,
                self._mark.problem_pattern, self._mark.is_regexp
            ).problem
            if not problem:
                continue

            new_association = MarkUnknownReport(
                mark=self._mark, report_id=report.id, author=author,
                type=ASSOCIATION_TYPE[2][0], problem=problem, associated=True
            )
            if prime_id and report.id == prime_id:
                new_association.type = ASSOCIATION_TYPE[3][0]
            elif report.cache.marks_confirmed:
                # Do not count automatic associations if report has confirmed ones
                new_association.associated = False
            associations.append(new_association)
            new_links.add(report.id)
        MarkUnknownReport.objects.bulk_create(associations)
        if prime_id:
            MarkUnknownReport.objects.filter(
                report_id=prime_id, associated=True, type=ASSOCIATION_TYPE[2][0]
            ).update(associated=False)
        return new_links


class CheckUnknownFunction:
    def __init__(self, report, mark_function, pattern, is_regexp):
        self._desc = self.__read_unknown_desc(report)
        self._func = mark_function
        self._pattern = pattern
        self._regexp = json.loads(is_regexp)
        if self._regexp:
            self.problem, self.match = self.__match_desc_regexp()
        else:
            self.problem, self.match = self.__match_desc()

        if isinstance(self.problem, str) and len(self.problem) == 0:
            self.problem = '-'
        if self.problem and len(self.problem) > 20:
            raise BridgeException(_('The problem length must be less than 20 characters'))

    def __read_unknown_desc(self, report):
        try:
            return ArchiveFileContent(report, 'problem_description', PROBLEM_DESC_FILE).content.decode('utf8')
        except Exception as e:
            raise BridgeException("Can't get problem description for unknown '{}': {}".format(report.pk, e))

    def __match_desc_regexp(self):
        try:
            m = re.search(self._func, self._desc, re.MULTILINE)
        except Exception as e:
            logger.exception("Regexp error: %s" % e, stack_info=True)
            return None, str(e)
        if m is not None:
            try:
                return self._pattern.format(*m.groups()), self.__get_matched_text(*m.span())
            except IndexError:
                return self._pattern, self.__get_matched_text(*m.span())
        return None, ''

    def __match_desc(self):
        start = self._desc.find(self._func)
        if start < 0:
            return None, ''
        end = start + len(self._func)
        return self._pattern, self.__get_matched_text(start, end)

    def __get_matched_text(self, start, end):
        line_breaks = list(a.start() for a in re.finditer('\n', self._desc))
        prev = -1
        f = 0
        for i in line_breaks:
            if i > start and f == 0:
                start = prev + 1
                f += 1
            prev = i
            if i >= end and f == 1:
                end = prev
                break
        else:
            end = len(self._desc)
        return self._desc[start:end]
