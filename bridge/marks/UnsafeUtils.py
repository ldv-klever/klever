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

import io
import json
import copy
import hashlib
from collections import OrderedDict

from django.core.files import File
from django.db import transaction

from bridge.vars import ASSOCIATION_TYPE, UNKNOWN_ERROR, ERROR_TRACE_FILE
from bridge.utils import logger, BridgeException, ArchiveFileContent, file_checksum

from reports.models import ReportUnsafe
from marks.models import (
    MarkUnsafe, MarkUnsafeHistory, MarkUnsafeReport, UnsafeAssociationLike, UnsafeConvertionCache, ConvertedTrace
)
from caches.utils import RecalculateUnsafeCache, UpdateUnsafeCachesOnMarkChange
from caches.models import ReportUnsafeCache


ET_FILE_NAME = 'converted-error-trace.json'

DEFAULT_COMPARE = 'thread_call_forests'

COMPARE_FUNCTIONS = {
    'callback_call_forests': {
        'desc': 'Jaccard index of "callback_call_forests" convertion.',
        'convert': 'callback_call_forests'
    },
    'thread_call_forests': {
        'desc': 'Jaccard index of "thread_call_forests" convertion.',
        'convert': 'thread_call_forests'
    }
}

CONVERT_FUNCTIONS = {
    'callback_call_forests': """
This function is extracting the error trace call stack forests.
The forest is a couple of call trees under callback action.
Call tree is tree of function names in their execution order.
All its leaves are names of functions which calls or statements
are marked with the "note" or "warn" attribute. Returns list of forests.
    """,
    'thread_call_forests': """
This function extracts error trace call forests. Each call forest is one or more call trees in the same thread.
A call tree is a tree of names of functions in their execution order. Each call tree root is either a callback action
if it exists in a corresponding call stack or a thread function. All call tree leaves are names of functions
which calls or statements are marked with the “note” or “warn” attribute. If there are several such functions in
a call stack then the latests functions are chosen. The function returns a list of forests. A forests order corresponds
to an execution order of first statements of forest threads.
    """
}


def perform_unsafe_mark_create(user, report, serializer):
    convert_func = serializer.validated_data['function']
    try:
        conv = UnsafeConvertionCache.objects.get(unsafe=report, converted__function=convert_func).converted
    except UnsafeConvertionCache.DoesNotExist:
        error_trace = get_report_trace(report)
        conv = convert_error_trace(error_trace, convert_func)
        UnsafeConvertionCache.objects.create(unsafe=report, converted=conv)

    mark = serializer.save(job=report.root.job, error_trace=conv)
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
        'threshold': mark.threshold
    }

    # Change the mark
    autoconfirm = serializer.validated_data['mark_version']['autoconfirm']
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

        if not autoconfirm:
            # Reset association type and remove likes
            mark_report_qs.update(type=ASSOCIATION_TYPE[0][0])
            UnsafeAssociationLike.objects.filter(association__mark=mark).delete()
            cache_upd.update_all()

        if old_cache['threshold'] != mark.threshold:
            # Update tags and verdicts
            cache_upd.update_all()

        if old_cache['tags'] != mark.cache_tags:
            cache_upd.update_tags()

        if old_cache['verdict'] != mark.verdict:
            cache_upd.update_verdicts()

    # Reutrn association changes cache identifier
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
    # Convert erro trace to forests
    if function == 'callback_call_forests':
        forests = ErrorTraceForests(error_trace, only_callbacks=True).forests
    elif function == 'thread_call_forests':
        forests = ErrorTraceForests(error_trace).forests
    else:
        raise ValueError('Error trace convert function is not supported')
    return save_converted_trace(forests, function)


def remove_unsafe_marks(**kwargs):
    queryset = MarkUnsafe.objects.filter(**kwargs)
    if not queryset.count():
        return
    qs_filters = dict(('mark__{}'.format(k), v) for k, v in kwargs.items())
    affected_reports = set(MarkUnsafeReport.objects.filter(**qs_filters).values_list('report_id', flat=True))
    queryset.delete()
    RecalculateUnsafeCache(reports=affected_reports)


def confirm_unsafe_mark(user, mark_report):
    if mark_report.type == ASSOCIATION_TYPE[1][0]:
        return
    was_unconfirmed = (mark_report.type == ASSOCIATION_TYPE[2][0])
    mark_report.author = user
    mark_report.type = ASSOCIATION_TYPE[1][0]
    mark_report.associated = True
    mark_report.save()

    # Do not count automatic associations as there is already confirmed one
    change_num = MarkUnsafeReport.objects.filter(
        report_id=mark_report.report_id, associated=True, type=ASSOCIATION_TYPE[0][0]
    ).update(associated=False)

    if was_unconfirmed or change_num:
        RecalculateUnsafeCache(reports=[mark_report.report_id])
    else:
        cache_obj = ReportUnsafeCache.objects.get(report_id=mark_report.report_id)
        cache_obj.marks_confirmed += 1
        cache_obj.save()


def unconfirm_unsafe_mark(user, mark_report: MarkUnsafeReport):
    if mark_report.type == ASSOCIATION_TYPE[2][0]:
        return
    was_confirmed = bool(mark_report.type == ASSOCIATION_TYPE[1][0])
    mark_report.author = user
    mark_report.type = ASSOCIATION_TYPE[2][0]
    mark_report.associated = False
    mark_report.save()

    if was_confirmed and not MarkUnsafeReport.objects\
            .filter(report_id=mark_report.report_id, type=ASSOCIATION_TYPE[1][0]).exists():
        # The report has lost the only confirmed mark,
        # so we need recalculate what associations we need to count for caches
        with transaction.atomic():
            for mr in MarkUnsafeReport.objects.filter(report_id=mark_report.report_id)\
                    .exclude(type=ASSOCIATION_TYPE[2][0]).select_related('mark')\
                    .only('report_id', 'result', 'error', 'mark__threshold'):
                if mr.error or mr.result < mr.mark.threshold:
                    continue
                mr.associated = True
                mr.save()

    RecalculateUnsafeCache(reports=[mark_report.report_id])


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
                mark=self._mark, report_id=report.id, author=author,
                type=ASSOCIATION_TYPE[0][0], **compare_results[report.id]
            )
            if prime_id and report.id == prime_id:
                new_association.type = ASSOCIATION_TYPE[1][0]
            elif report.cache.marks_confirmed:
                # Do not count automatic associations if report has confirmed ones
                new_association.associated = False
            associations.append(new_association)
            new_links.add(report.id)
        MarkUnsafeReport.objects.bulk_create(associations)
        return new_links


# Used only after report is created, so there are never old associations
class ConnectUnsafeReport:
    def __init__(self, unsafe):
        self._report = unsafe
        self.__connect()

    def __connect(self):
        marks_qs = MarkUnsafe.objects\
            .filter(cache_attrs__contained_by=self._report.cache.attrs).select_related('error_trace')
        compare_results = CompareReport(self._report).compare(marks_qs)

        MarkUnsafeReport.objects.bulk_create(list(MarkUnsafeReport(
            mark_id=mark.id, report=self._report, **compare_results[mark.id]
        ) for mark in marks_qs))
        RecalculateUnsafeCache(reports=[self._report.id])


class ErrorTraceForests:
    def __init__(self, error_trace, only_callbacks=False):
        self._trace = error_trace
        self._only_callbacks = only_callbacks
        self._forests_dict = OrderedDict()
        self.forests = self.__collect_forests()

    def __collect_forests(self):
        self.__parse_child(self._trace['trace'])
        all_forests = []
        for thread_forests in self._forests_dict.values():
            all_forests.extend(thread_forests)
        return all_forests

    def __parse_child(self, node, thread=None):
        if node['type'] == 'statement':
            return []

        if node['type'] == 'thread':
            self._forests_dict[node['thread']] = []
            children_forests = []
            for child in node['children']:
                children_forests.extend(self.__parse_child(child, node['thread']))
            if not self._only_callbacks:
                # Children forests here have function roots, not callbacks
                self._forests_dict[node['thread']].extend(children_forests)
            return []

        if node['type'] == 'function call':
            has_body_note = False
            children_forests = []
            for child in node['children']:
                has_body_note |= self.__has_note(child)
                children_forests.extend(self.__parse_child(child, thread))

            if children_forests or has_body_note or bool(node.get('note')):
                return [{node.get('display', node['source']): children_forests}]
            # No children and no notes in body and no notes in call
            return []

        if node['type'] == 'action':
            new_forests = []
            for child in node['children']:
                new_forests.extend(self.__parse_child(child, thread))
            if node.get('callback'):
                self._forests_dict[thread].append({node['display']: new_forests})
                return []
            return new_forests

    def __has_note(self, node):
        if node['type'] == 'action':
            # Skip callback actions
            if node.get('callback'):
                return False
            for child in node['children']:
                if self.__has_note(child):
                    return True
            return False
        return bool(node.get('note'))


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
                    'result': 0, 'error': str(UNKNOWN_ERROR), 'associated': False
                }
            else:
                res = jaccard(self._mark_cache, reports_cache[report_id])
                results[report_id] = {
                    'result': res, 'error': None,
                    'associated': bool(res >= self._mark.threshold)
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
                    'result': 0, 'error': str(UNKNOWN_ERROR), 'associated': False
                }
            else:
                res = jaccard(marks_cache[mark_id]['cache'], rep_cache_set)
                results[mark_id] = {
                    'result': res, 'error': None,
                    'associated': bool(res >= marks_cache[mark_id]['threshold'])
                }
        return results
