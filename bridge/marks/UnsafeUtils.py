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

import io
import json
import copy
import hashlib
from collections import OrderedDict

from django.core.files import File
from django.db.models import Count, Case, When, Q

from bridge.vars import ASSOCIATION_TYPE, UNKNOWN_ERROR, ERROR_TRACE_FILE, COMPARE_FUNCTIONS, CONVERT_FUNCTIONS
from bridge.utils import logger, BridgeException, ArchiveFileContent, RequreLock, file_checksum, require_lock

from reports.models import ReportUnsafe
from marks.models import MarkUnsafe, MarkUnsafeHistory, MarkUnsafeReport, UnsafeConvertionCache, ConvertedTrace

from marks.utils import ConfirmAssociationBase, UnconfirmAssociationBase
from caches.utils import RecalculateUnsafeCache, UpdateUnsafeCachesOnMarkChange


ET_FILE_NAME = 'converted-error-trace.json'


def perform_unsafe_mark_create(user, report, serializer):
    convert_func = serializer.validated_data['function']
    with RequreLock(UnsafeConvertionCache):
        try:
            conv = UnsafeConvertionCache.objects.get(unsafe=report, converted__function=convert_func).converted
        except UnsafeConvertionCache.DoesNotExist:
            error_trace = get_report_trace(report)
            conv = convert_error_trace(error_trace, convert_func)
            UnsafeConvertionCache.objects.create(unsafe=report, converted=conv)

    mark = serializer.save(job=report.decision.job, error_trace=conv)
    res = ConnectUnsafeMark(mark, prime_id=report.id, author=user)
    cache_upd = UpdateUnsafeCachesOnMarkChange(mark, res.old_links, res.new_links)
    cache_upd.update_all()
    return mark, cache_upd.save()


def perform_unsafe_mark_update(user, serializer):
    mark = serializer.instance

    # Preserve data before we change the mark
    old_cache = {
        'function': mark.function,
        'error_trace': mark.error_trace_id,
        'attrs': copy.deepcopy(mark.cache_attrs),
        'tags': copy.deepcopy(mark.cache_tags),
        'verdict': mark.verdict,
        'status': mark.status,
        'threshold': mark.threshold
    }

    # Change the mark
    mark = serializer.save()

    # Update reports cache
    if old_cache['attrs'] != mark.cache_attrs or \
            old_cache['function'] != mark.function or \
            old_cache['error_trace'] != mark.error_trace_id:
        res = ConnectUnsafeMark(mark, author=user)
        cache_upd = UpdateUnsafeCachesOnMarkChange(mark, res.old_links, res.new_links)
        cache_upd.update_all()
    else:
        mark_report_qs = MarkUnsafeReport.objects.filter(mark=mark)
        old_links = new_links = set(mr.report_id for mr in mark_report_qs)
        cache_upd = UpdateUnsafeCachesOnMarkChange(mark, old_links, new_links)

        if old_cache['threshold'] != mark.threshold:
            UpdateAssociated(mark)
            cache_upd.update_all()

        if old_cache['tags'] != mark.cache_tags:
            cache_upd.update_tags()

        if old_cache['verdict'] != mark.verdict:
            cache_upd.update_verdicts()

        if old_cache['status'] != mark.status:
            cache_upd.update_statuses()

    # Returns association changes cache identifier
    return cache_upd.save()


def jaccard(forest1: set, forest2: set):
    similar = len(forest1 & forest2)
    res = len(forest1) + len(forest2) - similar
    if res == 0:
        return 1
    return similar / res


def get_report_trace(report):
    try:
        error_trace_str = ArchiveFileContent(report, 'error_trace', ERROR_TRACE_FILE).content.decode('utf8')
    except Exception as e:
        logger.exception(e, stack_info=True)
        raise BridgeException("Can't exctract error trace for unsafe '%s' from archive" % report.pk)
    return json.loads(error_trace_str)


@require_lock(ConvertedTrace)
def save_converted_trace(forests, function):
    fp = io.BytesIO(json.dumps(forests, ensure_ascii=False, sort_keys=True, indent=2).encode('utf8'))
    hash_sum = file_checksum(fp)
    try:
        return ConvertedTrace.objects.get(hash_sum=hash_sum, function=function)
    except ConvertedTrace.DoesNotExist:
        conv = ConvertedTrace(hash_sum=hash_sum, function=function)

    forests_hashsums = []
    for forest in forests:
        forest_str = json.dumps(forest, ensure_ascii=False)
        forest_hash = hashlib.md5(forest_str.encode('utf8')).hexdigest()
        forests_hashsums.append(forest_hash)

    conv.trace_cache = {'forest': forests_hashsums}
    conv.file.save(ET_FILE_NAME, File(fp), save=True)
    return conv


def convert_error_trace(error_trace, function):
    # Convert error trace to forests
    if function == 'relevant_call_forests':
        forests = RelevantCallForests(error_trace).forests
    elif function == 'thread_call_forests':
        forests = ThreadCallForests(error_trace).forests
    else:
        raise ValueError('Error trace convert function is not supported')
    return save_converted_trace(forests, function)


class RemoveUnsafeMark:
    def __init__(self, mark):
        self._mark = mark

    @require_lock(MarkUnsafeReport)
    def destroy(self):
        affected_reports = set(MarkUnsafeReport.objects.filter(mark=self._mark).values_list('report_id', flat=True))
        self._mark.delete()

        # Find reports that have marks associations when all association are disabled. It can be in 2 cases:
        # 1) All associations are unconfirmed/dissimilar
        # 2) All confirmed associations were with deleted mark
        # We need to update 2nd case, so automatic associations are counting again
        changed_ids = affected_reports - set(MarkUnsafeReport.objects.filter(
            report_id__in=affected_reports, associated=True
        ).values_list('report_id', flat=True))

        # Count automatic associations again
        MarkUnsafeReport.objects.filter(report_id__in=changed_ids, type=ASSOCIATION_TYPE[2][0]).update(associated=True)

        return affected_reports


class ConfirmUnsafeMark(ConfirmAssociationBase):
    model = MarkUnsafeReport

    def recalculate_cache(self, report_id):
        RecalculateUnsafeCache(report_id)


class UnconfirmUnsafeMark(UnconfirmAssociationBase):
    model = MarkUnsafeReport

    def recalculate_cache(self, report_id):
        RecalculateUnsafeCache(report_id)


class ConnectUnsafeMark:
    def __init__(self, mark: MarkUnsafe, prime_id=None, author=None):
        self._mark = mark
        self.old_links = self.__clear_old_associations()
        self.new_links = self.__add_new_associations(prime_id, author)

    def __clear_old_associations(self):
        mark_reports_qs = MarkUnsafeReport.objects.filter(mark=self._mark)
        reports = set(mark_reports_qs.values_list('report_id', flat=True))
        mark_reports_qs.delete()
        return reports

    def __add_new_associations(self, prime_id, author):
        if author is None:
            last_version = MarkUnsafeHistory.objects.get(mark=self._mark, version=self._mark.version)
            author = last_version.author

        reports_qs = ReportUnsafe.objects.filter(cache__attrs__contains=self._mark.cache_attrs).select_related('cache')
        compare_results = CompareMark(self._mark).compare(reports_qs)

        new_links = set()
        associations = []
        for report in reports_qs:
            new_association = MarkUnsafeReport(
                mark=self._mark, report_id=report.id, author=author, **compare_results[report.id]
            )
            if prime_id and report.id == prime_id:
                new_association.type = ASSOCIATION_TYPE[3][0]
            elif report.cache.marks_confirmed:
                # Do not count automatic associations if report has confirmed ones
                new_association.associated = False
            associations.append(new_association)
            new_links.add(report.id)
        MarkUnsafeReport.objects.bulk_create(associations)

        if prime_id:
            # Disable automatic associations
            MarkUnsafeReport.objects.filter(
                report_id=prime_id, associated=True, type=ASSOCIATION_TYPE[2][0]
            ).update(associated=False)
        return new_links


class ThreadCallForests:
    def __init__(self, error_trace):
        self._trace = error_trace
        self._forests_dict = OrderedDict()
        self.forests = self.__collect_forests()

    def __collect_forests(self):
        self.__parse_child(self._trace['trace'])
        return list(forest for forest in self._forests_dict.values() if forest)

    def __parse_child(self, node, thread=None):
        if node['type'] in {'statement', 'declaration', 'declarations'}:
            return []

        if node['type'] == 'thread':
            self._forests_dict.setdefault(node['thread'], [])
            children_call_trees = []
            for child in node['children']:
                children_call_trees.extend(self.__parse_child(child, node['thread']))
            # If thread has forests and don't have any relevant actions, than add forests for that thread
            if children_call_trees and not self._forests_dict[node['thread']]:
                self._forests_dict[node['thread']].append(children_call_trees)
            return []

        if node['type'] == 'function call':
            has_body_note = False
            children_call_trees = []
            for child in node['children']:
                has_body_note |= self.__has_note(child)
                children_call_trees.extend(self.__parse_child(child, thread))

            if children_call_trees or has_body_note or self.__has_relevant_note(node):
                return [{node.get('display', node['source']): children_call_trees}]
            # No children and no notes in body and no notes in call
            return []

        if node['type'] == 'action':
            children_call_trees = []
            for child in node['children']:
                children_call_trees.extend(self.__parse_child(child, thread))
            if node.get('relevant'):
                # Add to the thread forest its call tree with relevant action at the root
                if children_call_trees:
                    self._forests_dict[thread].append(children_call_trees)
                return []
            return children_call_trees

    def __has_note(self, node):
        if node['type'] == 'action':
            # Skip relevant actions
            if node.get('relevant'):
                return False
            for child in node['children']:
                if self.__has_note(child):
                    return True
            return False
        elif node['type'] == 'declarations':
            for child in node['children']:
                if self.__has_note(child):
                    return True
            return False
        return self.__has_relevant_note(node)

    def __has_relevant_note(self, node):
        return bool(node.get('notes')) and any(note['level'] < 2 for note in node['notes'])


class RelevantCallForests:
    def __init__(self, error_trace):
        self._trace = error_trace
        self.forests = []
        self.__parse_child(self._trace['trace'])

    def __parse_child(self, node):
        if node['type'] in {'statement', 'declaration', 'declarations'}:
            return []

        if node['type'] == 'thread':
            for child in node['children']:
                self.__parse_child(child)
            return []

        if node['type'] == 'function call':
            has_body_note = False
            children_call_trees = []
            for child in node['children']:
                has_body_note |= self.__has_note(child)
                children_call_trees.extend(self.__parse_child(child))

            if children_call_trees or has_body_note or self.__has_relevant_note(node):
                return [{node.get('display', node['source']): children_call_trees}]
            # No children and no notes in body and no notes in call
            return []

        if node['type'] == 'action':
            children_call_trees = []
            for child in node['children']:
                children_call_trees.extend(self.__parse_child(child))
            if node.get('relevant'):
                if children_call_trees:
                    self.forests.append(children_call_trees)
                return []
            return children_call_trees

    def __has_note(self, node):
        if node['type'] == 'action':
            # Skip relevant actions
            if node.get('relevant'):
                return False
            for child in node['children']:
                if self.__has_note(child):
                    return True
            return False
        elif node['type'] == 'declarations':
            for child in node['children']:
                if self.__has_note(child):
                    return True
            return False
        return self.__has_relevant_note(node)

    def __has_relevant_note(self, node):
        return bool(node.get('notes')) and any(note['level'] < 2 for note in node['notes'])


class CompareMark:
    def __init__(self, mark):
        self._mark = mark
        self._mark_cache = set(self._mark.error_trace.trace_cache['forest'])

    def __get_reports_cache(self, reports_qs):
        reports_ids = list(r.id for r in reports_qs)

        convert_function = COMPARE_FUNCTIONS[self._mark.function]['convert']
        new_cache = []
        reports_cache = {}
        for conv in UnsafeConvertionCache.objects\
                .filter(unsafe_id__in=reports_ids, converted__function=convert_function)\
                .select_related('converted'):
            reports_cache[conv.unsafe_id] = set(conv.converted.trace_cache['forest'])
        for report in reports_qs:
            if report.id in reports_cache:
                continue
            try:
                error_trace = get_report_trace(report)
                conv = convert_error_trace(error_trace, convert_function)
            except Exception as e:
                logger.exception(e)
                reports_cache[report.id] = None
            else:
                reports_cache[report.id] = set(conv.trace_cache['forest'])
                new_cache.append(UnsafeConvertionCache(unsafe_id=report.id, converted_id=conv.id))
        if new_cache:
            UnsafeConvertionCache.objects.bulk_create(new_cache)
        return reports_cache

    def compare(self, reports_qs):
        results = {}
        reports_cache = self.__get_reports_cache(reports_qs)
        for report_id in reports_cache:
            if reports_cache[report_id] is None:
                results[report_id] = {
                    'type': ASSOCIATION_TYPE[0][0], 'result': 0, 'error': str(UNKNOWN_ERROR), 'associated': False
                }
            else:
                res = jaccard(self._mark_cache, reports_cache[report_id])
                is_associated = bool(res > 0 and res >= self._mark.threshold)
                results[report_id] = {
                    'type': is_associated and ASSOCIATION_TYPE[2][0] or ASSOCIATION_TYPE[0][0],
                    'result': res, 'error': None, 'associated': is_associated
                }
        return results


class CompareReport:
    def __init__(self, report):
        self._report = report
        self._report_cache = {}
        self.__clear_old_cache()

    def __clear_old_cache(self):
        UnsafeConvertionCache.objects.filter(unsafe=self._report).delete()

    def __get_report_cache(self):
        reports_cache = {}
        new_cache = []
        error_trace = get_report_trace(self._report)
        for convert_function in CONVERT_FUNCTIONS:
            try:
                conv = convert_error_trace(error_trace, convert_function)
            except Exception as e:
                logger.exception(e)
                reports_cache[convert_function] = None
            else:
                reports_cache[convert_function] = set(conv.trace_cache['forest'])
                new_cache.append(UnsafeConvertionCache(unsafe=self._report, converted_id=conv.id))
        UnsafeConvertionCache.objects.bulk_create(new_cache)
        return reports_cache

    def __get_marks_cache(self, marks_qs):
        marks_cache = {}
        # WARNING: ensure there is select_related('error_trace') for marks queryset
        for mark in marks_qs:
            marks_cache[mark.id] = {
                'function': COMPARE_FUNCTIONS[mark.function]['convert'],
                'threshold': mark.threshold,
                'cache': set(mark.error_trace.trace_cache['forest'])
            }
        return marks_cache

    def compare(self, marks_qs):
        results = {}
        report_cache = self.__get_report_cache()
        marks_cache = self.__get_marks_cache(marks_qs)
        for mark_id in marks_cache:
            rep_cache_set = report_cache[marks_cache[mark_id]['function']]
            if rep_cache_set is None:
                results[mark_id] = {
                    'type': ASSOCIATION_TYPE[0][0], 'result': 0, 'error': str(UNKNOWN_ERROR), 'associated': False
                }
            else:
                res = jaccard(marks_cache[mark_id]['cache'], rep_cache_set)
                is_associated = bool(res > 0 and res >= marks_cache[mark_id]['threshold'])
                results[mark_id] = {
                    'type': is_associated and ASSOCIATION_TYPE[2][0] or ASSOCIATION_TYPE[0][0],
                    'result': res, 'error': None, 'associated': is_associated
                }
        return results


class UpdateAssociated:
    def __init__(self, mark):
        self._mark = mark
        self.__update()

    @require_lock(MarkUnsafeReport)
    def __update(self):
        queryset = MarkUnsafeReport.objects.filter(mark=self._mark)

        associate_condition = Q(result__gte=self._mark.threshold, result__gt=0)

        # If the mark threshold increased then some associations will become dissimilar
        res = queryset.filter(~associate_condition & ~Q(type=ASSOCIATION_TYPE[0][0]))\
            .update(type=ASSOCIATION_TYPE[0][0], associated=False)

        # If mark threshold decreased then some dissimilar associations can become automatic again
        res += queryset.filter(associate_condition & Q(type=ASSOCIATION_TYPE[0][0]))\
            .update(type=ASSOCIATION_TYPE[2][0])

        if not res:
            # Nothing changed due to new mark threshold
            return

        # Collect reports that don't have any confirmed associations
        # that have associations with the current mark
        without_confirmed = set(MarkUnsafeReport.objects.values('report_id').annotate(
            confirmed=Count(Case(When(type=ASSOCIATION_TYPE[3][0], then=1)))
        ).filter(
            confirmed=0, report_id__in=set(queryset.values_list('report_id', flat=True))
        ).values_list('report_id', flat=True))

        # Associate all automatic associations of reports without any confirmed marks
        MarkUnsafeReport.objects.filter(
            report_id__in=without_confirmed, type=ASSOCIATION_TYPE[2][0], associated=False
        ).update(associated=True)
