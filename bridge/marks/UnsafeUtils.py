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
from django.db.models import Case, When, Value, Q, F
from django.utils.translation import ugettext as _

from rest_framework.exceptions import APIException

from bridge.vars import ASSOCIATION_TYPE, UNKNOWN_ERROR, ERROR_TRACE_FILE, COMPARE_FUNCTIONS, CONVERT_FUNCTIONS
from bridge.utils import logger, BridgeException, ArchiveFileContent, file_checksum

from reports.models import ReportUnsafe
from marks.models import MarkUnsafe, MarkUnsafeHistory, MarkUnsafeReport, UnsafeConvertionCache, ConvertedTrace

from marks.utils import RemoveMarksBase, ConfirmAssociationBase, UnconfirmAssociationBase
from caches.utils import RecalculateUnsafeCache, UpdateUnsafeCachesOnMarkChange


ET_FILE_NAME = 'converted-error-trace.json'


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
    # Convert error trace to forests
    if function == 'callback_call_forests':
        forests = CallbackCallForests(error_trace).forests
    elif function == 'thread_call_forests':
        forests = ThreadCallForests(error_trace).forests
    else:
        raise ValueError('Error trace convert function is not supported')
    return save_converted_trace(forests, function)


class RemoveUnsafeMarks(RemoveMarksBase):
    model = MarkUnsafe
    associations_model = MarkUnsafeReport

    def update_associated(self):
        queryset = self.without_associations_qs
        with transaction.atomic():
            for mr in queryset.select_related('mark'):
                mr.associated = bool(mr.result > 0 and mr.result >= mr.mark.threshold)
                mr.save()


class ConfirmUnsafeMark(ConfirmAssociationBase):
    model = MarkUnsafeReport

    def can_confirm_validation(self):
        if not self.association.result:
            raise APIException(_("You can't confirm mark with zero similarity"))

    def recalculate_cache(self, report_id):
        RecalculateUnsafeCache(reports=[report_id])


class UnconfirmUnsafeMark(UnconfirmAssociationBase):
    model = MarkUnsafeReport

    def get_automatically_associated_qs(self):
        queryset = super(UnconfirmUnsafeMark, self).get_automatically_associated_qs()
        return queryset.filter(error=None, result__gte=F('mark__threshold'), result__gt=0)

    def recalculate_cache(self, report_id):
        RecalculateUnsafeCache(reports=[report_id])


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

        if prime_id:
            MarkUnsafeReport.objects.filter(
                report_id=prime_id, associated=True, type=ASSOCIATION_TYPE[0][0]
            ).update(associated=False)
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


class ThreadCallForests:
    def __init__(self, error_trace):
        self._trace = error_trace
        self._forests_dict = OrderedDict()
        self.forests = self.__collect_forests()

    def __collect_forests(self):
        self.__parse_child(self._trace['trace'])
        return list(forest for forest in self._forests_dict.values() if forest)

    def __parse_child(self, node, thread=None):
        if node['type'] == 'statement':
            return []

        if node['type'] == 'thread':
            self._forests_dict.setdefault(node['thread'], [])
            for child in node['children']:
                self.__parse_child(child, node['thread'])
            return []

        if node['type'] == 'function call':
            has_body_note = False
            children_call_trees = []
            for child in node['children']:
                has_body_note |= self.__has_note(child)
                children_call_trees.extend(self.__parse_child(child, thread))

            if children_call_trees or has_body_note or bool(node.get('note')):
                return [{node.get('display', node['source']): children_call_trees}]
            # No children and no notes in body and no notes in call
            return []

        if node['type'] == 'action':
            children_call_trees = []
            for child in node['children']:
                children_call_trees.extend(self.__parse_child(child, thread))
            if node.get('callback'):
                # Add to the thread forest its call tree with callback action at the root
                if children_call_trees:
                    self._forests_dict[thread].append(children_call_trees)
                return []
            return children_call_trees

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


class CallbackCallForests:
    def __init__(self, error_trace):
        self._trace = error_trace
        self.forests = []
        self.__parse_child(self._trace['trace'])

    def __parse_child(self, node):
        if node['type'] == 'statement':
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

            if children_call_trees or has_body_note or bool(node.get('note')):
                return [{node.get('display', node['source']): children_call_trees}]
            # No children and no notes in body and no notes in call
            return []

        if node['type'] == 'action':
            children_call_trees = []
            for child in node['children']:
                children_call_trees.extend(self.__parse_child(child))
            if node.get('callback'):
                if children_call_trees:
                    self.forests.append(children_call_trees)
                return []
            return children_call_trees

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
                    'associated': bool(res > 0 and res >= self._mark.threshold)
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
                    'associated': bool(res > 0 and res >= marks_cache[mark_id]['threshold'])
                }
        return results


class UpdateAssociated:
    def __init__(self, mark):
        self._mark = mark
        self.__update()

    def __update(self):
        queryset = MarkUnsafeReport.objects.filter(mark=self._mark)
        has_confirmed = queryset.filter(type=ASSOCIATION_TYPE[1][0]).exists()

        if has_confirmed:
            # Because of the mark threshold some associations can't be confirmed already
            queryset.filter(
                result__lt=self._mark.threshold, type=ASSOCIATION_TYPE[1][0]
            ).update(type=ASSOCIATION_TYPE[0][0])

        associate_condition = Q(result__gte=self._mark.threshold, result__gt=0)
        if has_confirmed:
            associate_condition &= Q(type=ASSOCIATION_TYPE[1][0])

        queryset.update(associated=Case(When(condition=associate_condition, then=Value(True)), default=Value(False)))
