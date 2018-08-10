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

import os
import json
from io import BytesIO

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import F
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _

from bridge.vars import USER_ROLES, UNKNOWN_ERROR, UNSAFE_VERDICTS, MARK_UNSAFE, MARK_STATUS, MARK_TYPE,\
    ASSOCIATION_TYPE
from bridge.utils import logger, unique_id, file_checksum, file_get_or_create, BridgeException

from users.models import User
from reports.models import ReportComponentLeaf, ReportAttr, ReportUnsafe, Attr, AttrName
from marks.models import MarkUnsafe, MarkUnsafeHistory, MarkUnsafeReport, MarkUnsafeAttr,\
    MarkUnsafeTag, UnsafeTag, UnsafeReportTag, ReportUnsafeTag,\
    MarkUnsafeCompare, ConvertedTraces, UnsafeAssociationLike
from marks.ConvertTrace import GetConvertedErrorTrace, ET_FILE_NAME
from marks.CompareTrace import CompareTrace, CheckTraceFormat


class NewMark:
    def __init__(self, user, args):
        self._user = user
        self._args = args
        self.changes = {}
        self._comparison = None
        self.__check_args()

    def __check_args(self):
        if not isinstance(self._args, dict):
            raise ValueError('Wrong type: args (%s)' % type(self._args))
        if not isinstance(self._user, User):
            raise ValueError('Wrong type: user (%s)' % type(self._user))
        if self._args.get('verdict') not in set(x[0] for x in MARK_UNSAFE):
            raise ValueError('Unsupported verdict: %s' % self._args.get('verdict'))
        if self._args.get('status') not in set(x[0] for x in MARK_STATUS):
            raise ValueError('Unsupported status: %s' % self._args.get('status'))
        if not isinstance(self._args.get('comment'), str):
            self._args['comment'] = ''

        if 'compare_id' not in self._args:
            raise ValueError('compare_id is required')
        try:
            self._comparison = MarkUnsafeCompare.objects.get(id=self._args['compare_id'])
        except ObjectDoesNotExist:
            logger.exception("Get MarkUnsafeCompare(pk=%s)" % self._args['compare_id'])
            raise BridgeException(_('The error traces comparison function was not found'))

        if self._user.extended.role != USER_ROLES[2][0]:
            self._args['is_modifiable'] = MarkUnsafe._meta.get_field('is_modifiable').default
        elif not isinstance(self._args.get('is_modifiable'), bool):
            raise ValueError('Wrong type: is_modifiable (%s)' % type(self._args.get('is_modifiable')))

        if 'tags' not in self._args or not isinstance(self._args['tags'], list):
            raise ValueError('Unsupported tags: %s' % self._args.get('tags'))

        if 'autoconfirm' in self._args and not isinstance(self._args['autoconfirm'], bool):
            raise ValueError('Wrong type: autoconfirm (%s)' % type(self._args['autoconfirm']))

        tags = set(int(t) for t in self._args['tags'])
        if len(tags) > 0:
            tags_in_db = {}
            for tid, pid in UnsafeTag.objects.all().values_list('id', 'parent_id'):
                tags_in_db[tid] = pid
            if any(t not in tags_in_db for t in tags):
                raise BridgeException(_('One of tags was not found'))
            tags_parents = set()
            for t in tags:
                while tags_in_db[t] is not None:
                    tags_parents.add(tags_in_db[t])
                    t = tags_in_db[t]
            tags |= tags_parents
        self._args['tags'] = tags

    def create_mark(self, report):
        error_trace = GetConvertedErrorTrace(self._comparison.convert, report).converted
        mark = MarkUnsafe.objects.create(
            identifier=unique_id(), author=self._user, change_date=now(), format=report.root.job.format,
            job=report.root.job, description=str(self._args.get('description', '')), function=self._comparison,
            verdict=self._args['verdict'], status=self._args['status'], is_modifiable=self._args['is_modifiable']
        )

        try:
            markversion = self.__create_version(mark, error_trace)
            self.__create_attributes(markversion.id, report)
        except Exception:
            mark.delete()
            raise
        self.changes = ConnectMarks([mark], prime_id=report.id).changes.get(mark.id, {})
        self.__get_tags_changes(RecalculateTags(list(self.changes)).changes)
        update_confirmed_cache([report])
        return mark

    def change_mark(self, mark, recalculate_cache=True):
        error_trace = None
        if 'error_trace' in self._args and isinstance(self._args['error_trace'], str):
            try:
                et_json = json.loads(self._args['error_trace'])
                CheckTraceFormat(self._comparison.name, et_json)
            except Exception as e:
                logger.exception(e)
                raise BridgeException(_('Converted error trace has wrong format. Inspect logs for more info.'))
            error_trace = BytesIO(json.dumps(et_json, ensure_ascii=False, sort_keys=True, indent=4).encode('utf8'))

        last_v = MarkUnsafeHistory.objects.get(mark=mark, version=F('mark__version'))

        mark.author = self._user
        mark.change_date = now()
        mark.status = self._args['status']
        mark.description = str(self._args.get('description', ''))
        mark.version += 1
        mark.is_modifiable = self._args['is_modifiable']

        recalc_verdicts = False
        if mark.verdict != self._args['verdict']:
            mark.verdict = self._args['verdict']
            recalc_verdicts = True

        do_recalc = False
        if mark.function != self._comparison:
            mark.function = self._comparison
            do_recalc = True

        if error_trace is not None and file_checksum(error_trace) != last_v.error_trace.hash_sum:
            do_recalc = True
            error_trace = file_get_or_create(error_trace, ET_FILE_NAME, ConvertedTraces)[0]
        else:
            error_trace = last_v.error_trace

        markversion = self.__create_version(mark, error_trace)

        try:
            do_recalc |= self.__create_attributes(markversion.id, last_v)
        except Exception:
            markversion.delete()
            raise
        mark.save()

        if recalculate_cache:
            if do_recalc or not self._args.get('autoconfirm', False):
                MarkUnsafeReport.objects.filter(mark_id=mark.id).update(type=ASSOCIATION_TYPE[0][0])
                UnsafeAssociationLike.objects.filter(association__mark=mark).delete()
            if do_recalc:
                changes = ConnectMarks([mark]).changes
            else:
                changes = self.__create_changes(mark)
                if recalc_verdicts:
                    changes = UpdateVerdicts(changes).changes
            self.changes = changes.get(mark.id, {})
            self.__get_tags_changes(RecalculateTags(list(self.changes)).changes)
            update_confirmed_cache(list(self.changes))
        return mark

    def upload_mark(self):
        if 'error_trace' not in self._args and not isinstance(self._args['error_trace'], str):
            raise ValueError('Unsafe mark error_trace is required')
        if 'format' not in self._args:
            raise BridgeException(_('Unsafe mark format is required'))
        if isinstance(self._args.get('identifier'), str) and 0 < len(self._args['identifier']) < 255:
            if MarkUnsafe.objects.filter(identifier=self._args['identifier']).count() > 0:
                raise BridgeException(_("The mark with identifier specified in the archive already exists"))
        else:
            self._args['identifier'] = unique_id()
        error_trace = file_get_or_create(BytesIO(json.dumps(
            json.loads(self._args['error_trace']), ensure_ascii=False, sort_keys=True, indent=4
        ).encode('utf8')), ET_FILE_NAME, ConvertedTraces)[0]
        mark = MarkUnsafe.objects.create(
            identifier=self._args['identifier'], author=self._user, change_date=now(), format=self._args['format'],
            type=MARK_TYPE[2][0], function=self._comparison, description=str(self._args.get('description', '')),
            verdict=self._args['verdict'], status=self._args['status'], is_modifiable=self._args['is_modifiable']
        )

        try:
            markversion = self.__create_version(mark, error_trace)
            self.__create_attributes(markversion.id)
        except Exception:
            mark.delete()
            raise
        return mark

    def __create_changes(self, mark):
        self.__is_not_used()
        changes = {mark.id: {}}
        for mr in mark.markreport_set.all().select_related('report'):
            changes[mark.id][mr.report] = {'kind': '=', 'verdict1': mr.report.verdict}
        return changes

    def __create_version(self, mark, error_trace):
        markversion = MarkUnsafeHistory.objects.create(
            mark=mark, version=mark.version, status=mark.status, verdict=mark.verdict,
            author=mark.author, change_date=mark.change_date, comment=self._args['comment'],
            error_trace=error_trace, function=mark.function, description=mark.description
        )
        MarkUnsafeTag.objects.bulk_create(
            list(MarkUnsafeTag(tag_id=t_id, mark_version=markversion) for t_id in self._args['tags'])
        )
        return markversion

    def __create_attributes(self, markversion_id, inst=None):
        if 'attrs' in self._args and (not isinstance(self._args['attrs'], list) or len(self._args['attrs']) == 0):
            del self._args['attrs']
        if 'attrs' in self._args:
            for a in self._args['attrs']:
                if not isinstance(a, dict) or not isinstance(a.get('attr'), str) \
                        or not isinstance(a.get('is_compare'), bool):
                    raise ValueError('Wrong attribute found: %s' % a)
                if inst is None and not isinstance(a.get('value'), str):
                    raise ValueError('Wrong attribute found: %s' % a)

        need_recalc = False
        new_attrs = []
        if isinstance(inst, ReportUnsafe):
            for a_id, a_name, associate in inst.attrs.order_by('id')\
                    .values_list('attr_id', 'attr__name__name', 'associate'):
                if 'attrs' in self._args:
                    for a in self._args['attrs']:
                        if a['attr'] == a_name:
                            new_attrs.append(MarkUnsafeAttr(
                                mark_id=markversion_id, attr_id=a_id, is_compare=a['is_compare']
                            ))
                            break
                    else:
                        raise ValueError('Not enough attributes in args')
                else:
                    new_attrs.append(MarkUnsafeAttr(mark_id=markversion_id, attr_id=a_id, is_compare=associate))
        elif isinstance(inst, MarkUnsafeHistory):
            for a_id, a_name, is_compare in inst.attrs.order_by('id')\
                    .values_list('attr_id', 'attr__name__name', 'is_compare'):
                if 'attrs' in self._args:
                    for a in self._args['attrs']:
                        if a['attr'] == a_name:
                            new_attrs.append(MarkUnsafeAttr(
                                mark_id=markversion_id, attr_id=a_id, is_compare=a['is_compare']
                            ))
                            if a['is_compare'] != is_compare:
                                need_recalc = True
                            break
                    else:
                        raise ValueError('Not enough attributes in args')
                else:
                    new_attrs.append(MarkUnsafeAttr(mark_id=markversion_id, attr_id=a_id, is_compare=is_compare))
        else:
            if 'attrs' not in self._args:
                raise ValueError('Attributes are required')
            for a in self._args['attrs']:
                attr = Attr.objects.get_or_create(
                    name=AttrName.objects.get_or_create(name=a['attr'])[0], value=a['value']
                )[0]
                new_attrs.append(MarkUnsafeAttr(mark_id=markversion_id, attr=attr, is_compare=a['is_compare']))
        MarkUnsafeAttr.objects.bulk_create(new_attrs)
        return need_recalc

    def __get_tags_changes(self, data):
        for report in self.changes:
            if report.id in data and len(data[report.id]) > 0:
                self.changes[report]['tags'] = list(sorted(data[report.id]))

    def __is_not_used(self):
        pass


class ConnectMarks:
    def __init__(self, marks, prime_id=None):
        self._marks = marks
        self._prime_id = prime_id
        self.changes = {}
        self._functions = {}
        self._patterns = {}

        self._marks_attrs = self.__get_marks_attrs()
        self._unsafes_attrs = self.__get_unsafes_attrs()
        if len(self._unsafes_attrs) == 0:
            return
        self.__clear_connections()
        self._author = dict((m.id, m.author) for m in self._marks)

        self.__connect()
        self.__update_verdicts()

    def __get_unsafes_attrs(self):
        self.__is_not_used()
        attrs_ids = set()
        for m_id in self._marks_attrs:
            attrs_ids |= self._marks_attrs[m_id]

        unsafes_attrs = {}
        for r_id, a_id in ReportAttr.objects.exclude(report__reportunsafe=None).filter(attr_id__in=attrs_ids)\
                .values_list('report_id', 'attr_id'):
            if r_id not in unsafes_attrs:
                unsafes_attrs[r_id] = set()
            unsafes_attrs[r_id].add(a_id)
        return unsafes_attrs

    def __get_marks_attrs(self):
        attr_filters = {
            'mark__mark__in': self._marks, 'is_compare': True,
            'mark__version': F('mark__mark__version')
        }
        marks_attrs = {}
        for attr_id, mark_id in MarkUnsafeAttr.objects.filter(**attr_filters).values_list('attr_id', 'mark__mark_id'):
            if mark_id not in marks_attrs:
                marks_attrs[mark_id] = set()
            marks_attrs[mark_id].add(attr_id)
        for m_id, f_name, pattern_id in MarkUnsafeHistory.objects\
                .filter(mark_id__in=marks_attrs, version=F('mark__version'))\
                .values_list('mark_id', 'function__name', 'error_trace_id'):
            self._functions[m_id] = f_name
            self._patterns[m_id] = pattern_id
        return marks_attrs

    def __clear_connections(self):
        for mr in MarkUnsafeReport.objects.filter(mark__in=self._marks).select_related('report'):
            if mr.mark_id not in self.changes:
                self.changes[mr.mark_id] = {}
            self.changes[mr.mark_id][mr.report] = {'kind': '-', 'result1': mr.result, 'verdict1': mr.report.verdict}
        MarkUnsafeReport.objects.filter(mark__in=self._marks).delete()

    def __connect(self):
        marks_reports = {}
        unsafes_ids = set()
        for mark_id in self._marks_attrs:
            marks_reports[mark_id] = set()
            for unsafe_id in self._unsafes_attrs:
                if self._marks_attrs[mark_id].issubset(self._unsafes_attrs[unsafe_id]):
                    marks_reports[mark_id].add(unsafe_id)
                    unsafes_ids.add(unsafe_id)
            if len(marks_reports[mark_id]) == 0:
                del self._patterns[mark_id]
                del self._functions[mark_id]
        patterns = {}
        for converted in ConvertedTraces.objects.filter(id__in=set(self._patterns.values())):
            with converted.file as fp:
                patterns[converted.id] = fp.read().decode('utf8')
        for m_id in self._patterns:
            self._patterns[m_id] = patterns[self._patterns[m_id]]

        new_markreports = []
        for unsafe in ReportUnsafe.objects.filter(id__in=unsafes_ids):
            for mark_id in self._patterns:
                if unsafe.id not in marks_reports[mark_id]:
                    continue
                compare_error = None
                compare_result = 0
                try:
                    compare_result = CompareTrace(self._functions[mark_id], self._patterns[mark_id], unsafe).result
                except BridgeException as e:
                    compare_error = str(e)
                except Exception as e:
                    logger.exception("Error traces comparison failed: %s" % e)
                    compare_error = str(UNKNOWN_ERROR)

                ass_type = ASSOCIATION_TYPE[0][0]
                if self._prime_id == unsafe.id:
                    ass_type = ASSOCIATION_TYPE[1][0]
                new_markreports.append(MarkUnsafeReport(
                    mark_id=mark_id, report=unsafe, result=compare_result, error=compare_error,
                    type=ass_type, author=self._author[mark_id]
                ))
                if mark_id not in self.changes:
                    self.changes[mark_id] = {}
                if unsafe in self.changes[mark_id]:
                    self.changes[mark_id][unsafe]['kind'] = '='
                    self.changes[mark_id][unsafe]['result2'] = compare_result
                else:
                    self.changes[mark_id][unsafe] = {
                        'kind': '+', 'result2': compare_result, 'verdict1': unsafe.verdict
                    }
        MarkUnsafeReport.objects.bulk_create(new_markreports)

    def __update_verdicts(self):
        unsafe_verdicts = {}
        for mark_id in self.changes:
            for unsafe in self.changes[mark_id]:
                unsafe_verdicts[unsafe] = set()
        for mr in MarkUnsafeReport.objects.filter(report__in=unsafe_verdicts, error=None, result__gt=0)\
                .select_related('mark'):
            unsafe_verdicts[mr.report].add(mr.mark.verdict)

        unsafes_to_update = {}
        for unsafe in unsafe_verdicts:
            old_verdict = unsafe.verdict
            new_verdict = self.__calc_verdict(unsafe_verdicts[unsafe])
            if old_verdict != new_verdict:
                if new_verdict not in unsafes_to_update:
                    unsafes_to_update[new_verdict] = set()
                unsafes_to_update[new_verdict].add(unsafe.id)
                for mark_id in self.changes:
                    if unsafe in self.changes[mark_id]:
                        self.changes[mark_id][unsafe]['verdict2'] = new_verdict
        self.__new_verdicts(unsafes_to_update)

    @transaction.atomic
    def __new_verdicts(self, unsafes_to_update):
        self.__is_not_used()
        for v in unsafes_to_update:
            ReportUnsafe.objects.filter(id__in=unsafes_to_update[v]).update(verdict=v)

    def __calc_verdict(self, verdicts):
        self.__is_not_used()
        new_verdict = UNSAFE_VERDICTS[5][0]
        for v in verdicts:
            if new_verdict != UNSAFE_VERDICTS[5][0] and new_verdict != v:
                new_verdict = UNSAFE_VERDICTS[4][0]
                break
            else:
                new_verdict = v
        return new_verdict

    def __is_not_used(self):
        pass


class ConnectReport:
    def __init__(self, unsafe):
        self._unsafe = unsafe
        self._marks = {}

        MarkUnsafeReport.objects.filter(report=self._unsafe).delete()
        self._unsafe_attrs = set(a_id for a_id, in self._unsafe.attrs.values_list('attr_id'))
        self._marks_attrs = self.__get_marks_attrs()

        self.__connect()

    def __get_marks_attrs(self):
        attr_filters = {'is_compare': True, 'mark__version': F('mark__mark__version')}
        marks_attrs = {}
        for attr_id, mark_id in MarkUnsafeAttr.objects.filter(**attr_filters).values_list('attr_id', 'mark__mark_id'):
            if mark_id not in marks_attrs:
                marks_attrs[mark_id] = set()
            marks_attrs[mark_id].add(attr_id)
        for m_id, f_name, pattern_id, verdict in MarkUnsafeHistory.objects\
                .filter(mark_id__in=marks_attrs, version=F('mark__version'))\
                .values_list('mark_id', 'function__name', 'error_trace_id', 'verdict'):
            self._marks[m_id] = {'function': f_name, 'pattern': pattern_id, 'verdict': verdict}
        return marks_attrs

    def __connect(self):
        new_markreports = []
        for mark_id in self._marks_attrs:
            if not self._marks_attrs[mark_id].issubset(self._unsafe_attrs):
                del self._marks[mark_id]
                continue
        patterns = {}
        for converted in ConvertedTraces.objects.filter(id__in=set(self._marks[mid]['pattern'] for mid in self._marks)):
            with converted.file as fp:
                patterns[converted.id] = fp.read().decode('utf8')
        for m_id in self._marks:
            self._marks[m_id]['pattern'] = patterns[self._marks[m_id]['pattern']]

        for mark_id in self._marks:
            compare_result = 0
            compare_error = None
            try:
                compare = CompareTrace(self._marks[mark_id]['function'], self._marks[mark_id]['pattern'], self._unsafe)
                compare_result = compare.result
            except BridgeException as e:
                compare_error = str(e)
            except Exception as e:
                logger.exception("Error traces comparison failed: %s" % e)
                compare_error = str(UNKNOWN_ERROR)
            new_markreports.append(MarkUnsafeReport(
                mark_id=mark_id, report=self._unsafe, result=compare_result, error=compare_error
            ))
        MarkUnsafeReport.objects.bulk_create(new_markreports)

        new_verdict = UNSAFE_VERDICTS[5][0]
        for v in set(self._marks[m_id]['verdict'] for m_id in
                     list(mr.mark_id for mr in new_markreports if mr.error is None and mr.result > 0)):
            if new_verdict != UNSAFE_VERDICTS[5][0] and new_verdict != v:
                new_verdict = UNSAFE_VERDICTS[4][0]
                break
            else:
                new_verdict = v
        if self._unsafe.verdict != new_verdict:
            self._unsafe.verdict = new_verdict
            self._unsafe.save()


class RecalculateTags:
    def __init__(self, reports):
        self.reports = reports
        self.changes = {}
        self.__fill_leaves_cache()
        self.__fill_reports_cache()

    def __fill_leaves_cache(self):
        old_numbers = {}
        tags_names = {}
        for urt in UnsafeReportTag.objects.filter(report__in=self.reports).select_related('tag'):
            old_numbers[(urt.tag_id, urt.report_id)] = urt.number
            tags_names[urt.tag_id] = urt.tag.tag
        UnsafeReportTag.objects.filter(report__in=self.reports).delete()
        marks = {}
        for m_id, r_id in MarkUnsafeReport.objects.filter(report__in=self.reports, error=None, result__gt=0) \
                .exclude(type=ASSOCIATION_TYPE[2][0]).values_list('mark_id', 'report_id'):
            if m_id not in marks:
                marks[m_id] = set()
            marks[m_id].add(r_id)
        tags = {}
        for t_id, m_id, t_name in MarkUnsafeTag.objects.filter(
            mark_version__mark_id__in=marks, mark_version__version=F('mark_version__mark__version')
        ).values_list('tag_id', 'mark_version__mark_id', 'tag__tag'):
            tags_names[t_id] = t_name
            for r_id in marks[m_id]:
                if (t_id, r_id) not in tags:
                    tags[(t_id, r_id)] = 0
                tags[(t_id, r_id)] += 1
        for tr_id in set(tags) | set(old_numbers):
            old_n = old_numbers.get(tr_id, 0)
            new_n = tags.get(tr_id, 0)
            if tr_id[1] not in self.changes:
                self.changes[tr_id[1]] = []
            self.changes[tr_id[1]].append((tags_names[tr_id[0]], old_n, new_n))
        UnsafeReportTag.objects.bulk_create(list(
            UnsafeReportTag(report_id=r_id, tag_id=t_id, number=tags[(t_id, r_id)]) for t_id, r_id in tags)
        )

    def __fill_reports_cache(self):
        reports = set(leaf['report_id']
                      for leaf in ReportComponentLeaf.objects.filter(unsafe__in=self.reports).values('report_id'))
        ReportUnsafeTag.objects.filter(report_id__in=reports).delete()
        reports_data = {}
        all_unsafes = set()
        for leaf in ReportComponentLeaf.objects.filter(report_id__in=reports).exclude(unsafe=None):
            if leaf.report_id not in reports_data:
                reports_data[leaf.report_id] = {'leaves': set(), 'numbers': {}}
            reports_data[leaf.report_id]['leaves'].add(leaf.unsafe_id)
            all_unsafes.add(leaf.unsafe_id)
        for rt in UnsafeReportTag.objects.filter(report_id__in=all_unsafes):
            for rc_id in reports_data:
                if rt.report_id in reports_data[rc_id]['leaves']:
                    if rt.tag_id in reports_data[rc_id]['numbers']:
                        reports_data[rc_id]['numbers'][rt.tag_id] += rt.number
                    else:
                        reports_data[rc_id]['numbers'][rt.tag_id] = rt.number
        new_reporttags = []
        for rc_id in reports_data:
            for t_id in reports_data[rc_id]['numbers']:
                if reports_data[rc_id]['numbers'][t_id] > 0:
                    new_reporttags.append(ReportUnsafeTag(
                        report_id=rc_id, tag_id=t_id, number=reports_data[rc_id]['numbers'][t_id]
                    ))
        ReportUnsafeTag.objects.bulk_create(new_reporttags)


class UpdateVerdicts:
    def __init__(self, changes):
        self.changes = changes
        if len(self.changes) > 0:
            self.__update_verdicts()

    def __update_verdicts(self):
        unsafe_verdicts = {}
        for mark_id in self.changes:
            for unsafe in self.changes[mark_id]:
                unsafe_verdicts[unsafe] = set()
        for mr in MarkUnsafeReport.objects.filter(report__in=unsafe_verdicts, error=None, result__gt=0)\
                .exclude(type=ASSOCIATION_TYPE[2][0]).select_related('mark'):
            unsafe_verdicts[mr.report].add(mr.mark.verdict)

        unsafes_to_update = {}
        for unsafe in unsafe_verdicts:
            old_verdict = unsafe.verdict
            new_verdict = self.__calc_verdict(unsafe_verdicts[unsafe])
            if old_verdict != new_verdict:
                if new_verdict not in unsafes_to_update:
                    unsafes_to_update[new_verdict] = set()
                unsafes_to_update[new_verdict].add(unsafe.id)
                for mark_id in self.changes:
                    if unsafe in self.changes[mark_id]:
                        self.changes[mark_id][unsafe]['verdict2'] = new_verdict
        self.__new_verdicts(unsafes_to_update)

    @transaction.atomic
    def __new_verdicts(self, unsafes_to_update):
        self.__is_not_used()
        for v in unsafes_to_update:
            ReportUnsafe.objects.filter(id__in=unsafes_to_update[v]).update(verdict=v)

    def __calc_verdict(self, verdicts):
        self.__is_not_used()
        new_verdict = UNSAFE_VERDICTS[5][0]
        for v in verdicts:
            if new_verdict != UNSAFE_VERDICTS[5][0] and new_verdict != v:
                new_verdict = UNSAFE_VERDICTS[4][0]
                break
            else:
                new_verdict = v
        return new_verdict

    def __is_not_used(self):
        pass


class RecalculateConnections:
    def __init__(self, roots):
        self._roots = roots
        self.__recalc()

    def __recalc(self):
        ReportUnsafeTag.objects.filter(report__root__in=self._roots).delete()
        UnsafeReportTag.objects.filter(report__root__in=self._roots).delete()
        MarkUnsafeReport.objects.filter(report__root__in=self._roots).delete()
        ReportUnsafe.objects.filter(root__in=self._roots).update(verdict=UNSAFE_VERDICTS[5][0], has_confirmed=False)
        unsafes = []
        for unsafe in ReportUnsafe.objects.filter(root__in=self._roots):
            ConnectReport(unsafe)
            unsafes.append(unsafe)
        RecalculateTags(unsafes)


class PopulateMarks:
    def __init__(self, manager):
        self.total = 0
        self._author = manager
        self._dbtags = {}
        self._functions = dict(MarkUnsafeCompare.objects.values_list('name', 'id'))
        self._tagnames = {}
        self._marks_data = {}
        self.__current_tags()
        self._marks = self.__get_data()
        self.__get_attrnames()
        self.__get_attrs()
        self.created = self.__create_marks()
        self.__create_related()
        changes = ConnectMarks(self.created.values()).changes
        reports = []
        for m_id in changes:
            reports.extend(changes[m_id])
        RecalculateTags(reports)

    def __current_tags(self):
        for t_id, parent_id, t_name in UnsafeTag.objects.values_list('id', 'parent_id', 'tag'):
            self._dbtags[t_id] = parent_id
            self._tagnames[t_name] = t_id

    def __get_tags(self, tags_data):
        tags = set()
        for t in tags_data:
            if t not in self._tagnames:
                raise BridgeException(_('Corrupted preset unsafe mark: not enough tags in the system'))
            t_id = self._tagnames[t]
            tags.add(t_id)
            while self._dbtags[t_id] is not None:
                t_id = self._dbtags[t_id]
                tags.add(t_id)
        return tags

    def __get_attrnames(self):
        attrnames = {}
        for a in AttrName.objects.all():
            attrnames[a.name] = a.id
        for mid in self._marks_data:
            for a in self._marks_data[mid]['attrs']:
                if a['attr'] in attrnames:
                    a['attr'] = attrnames[a['attr']]
                else:
                    newname = AttrName.objects.get_or_create(name=a['attr'])[0]
                    a['attr'] = newname.id
                    attrnames[newname.name] = newname.id

    def __get_attrs(self):
        attrs_in_db = {}
        for a in Attr.objects.all():
            attrs_in_db[(a.name_id, a.value)] = a.id
        attrs_to_create = []
        for mid in self._marks_data:
            for a in self._marks_data[mid]['attrs']:
                if (a['attr'], a['value']) not in attrs_in_db:
                    attrs_to_create.append(Attr(name_id=a['attr'], value=a['value']))
                    attrs_in_db[(a['attr'], a['value'])] = None
        if len(attrs_to_create) > 0:
            Attr.objects.bulk_create(attrs_to_create)
            self.__get_attrs()
        else:
            for mid in self._marks_data:
                for a in self._marks_data[mid]['attrs']:
                    a['attr'] = attrs_in_db[(a['attr'], a['value'])]
                    del a['value']

    def __create_marks(self):
        marks_in_db = {}
        for ma in MarkUnsafeAttr.objects.values('mark_id', 'attr_id', 'is_compare'):
            if ma['mark_id'] not in marks_in_db:
                marks_in_db[ma['mark_id']] = set()
            marks_in_db[ma['mark_id']].add((ma['attr_id'], ma['is_compare']))
        marks_to_create = []
        for mark in self._marks:
            attr_set = set((a['attr'], a['is_compare']) for a in self._marks_data[mark.identifier]['attrs'])
            if any(attr_set == marks_in_db[x] for x in marks_in_db):
                del self._marks_data[mark.identifier]
                continue
            marks_to_create.append(mark)
        MarkUnsafe.objects.bulk_create(marks_to_create)

        created_marks = {}
        marks_versions = []
        for mark in MarkUnsafe.objects.filter(versions=None):
            created_marks[mark.identifier] = mark
            marks_versions.append(MarkUnsafeHistory(
                mark=mark, verdict=mark.verdict, status=mark.status, description=mark.description,
                version=mark.version, author=mark.author, change_date=mark.change_date, comment='',
                function_id=self._marks_data[mark.identifier]['f_id'],
                error_trace=file_get_or_create(
                    self._marks_data[mark.identifier]['error trace'], ET_FILE_NAME, ConvertedTraces
                )[0]
            ))
        MarkUnsafeHistory.objects.bulk_create(marks_versions)
        return created_marks

    def __create_related(self):
        versions = {}
        for mh in MarkUnsafeHistory.objects.filter(mark__in=self.created.values()).select_related('mark'):
            versions[mh.mark.identifier] = mh.id

        new_tags = []
        for mid in self._marks_data:
            for tid in self._marks_data[mid]['tags']:
                new_tags.append(MarkUnsafeTag(tag_id=tid, mark_version_id=versions[mid]))
        MarkUnsafeTag.objects.bulk_create(new_tags)
        new_attrs = []
        for mid in self._marks_data:
            for a in self._marks_data[mid]['attrs']:
                new_attrs.append(MarkUnsafeAttr(mark_id=versions[mid], attr_id=a['attr'], is_compare=a['is_compare']))
        MarkUnsafeAttr.objects.bulk_create(new_attrs)

    def __get_data(self):
        presets_dir = os.path.join(settings.BASE_DIR, 'marks', 'presets', 'unsafes')

        new_marks = []
        for mark_settings in [os.path.join(presets_dir, x) for x in os.listdir(presets_dir)]:
            identifier = os.path.splitext(os.path.basename(mark_settings))[0]
            try:
                MarkUnsafe.objects.get(identifier=identifier)
                # The mark was already uploaded
                continue
            except ObjectDoesNotExist:
                pass

            with open(mark_settings, encoding='utf8') as fp:
                data = json.load(fp)
            if not isinstance(data, dict):
                raise BridgeException(_('Corrupted preset unsafe mark: wrong format'))
            if any(x not in data for x in ['status', 'verdict', 'is_modifiable', 'description', 'attrs', 'tags']):
                raise BridgeException(_('Corrupted preset unsafe mark: not enough data'))
            if not isinstance(data['attrs'], list) or not isinstance(data['tags'], list):
                raise BridgeException(_('Corrupted preset unsafe mark: attributes or tags is not a list'))
            if any(not isinstance(x, dict) for x in data['attrs']):
                raise BridgeException(_('Corrupted preset unsafe mark: one of attributes has wrong format'))
            if any(x not in y for x in ['attr', 'value', 'is_compare'] for y in data['attrs']):
                raise BridgeException(_('Corrupted preset unsafe mark: one of attributes does not have enough data'))
            if data['status'] not in list(x[0] for x in MARK_STATUS):
                raise BridgeException(_('Corrupted preset unsafe mark: wrong mark status'))
            if data['verdict'] not in list(x[0] for x in UNSAFE_VERDICTS):
                raise BridgeException(_('Corrupted preset unsafe mark: wrong mark verdict'))
            if not isinstance(data['description'], str):
                raise BridgeException(_('Corrupted preset unsafe mark: wrong description'))
            if not isinstance(data['is_modifiable'], bool):
                raise BridgeException(_('Corrupted preset unsafe mark: is_modifiable must be bool'))
            if 'error trace' not in data:
                raise BridgeException(_('Corrupted preset unsafe mark: error trace is required'))
            if 'comparison' not in data:
                raise BridgeException(_('Corrupted preset unsafe mark: comparison function name is required'))
            if data['comparison'] not in self._functions:
                raise BridgeException(_('Preset unsafe mark comparison fucntion is not supported'))

            new_marks.append(MarkUnsafe(
                identifier=identifier, author=self._author, change_date=now(), is_modifiable=data['is_modifiable'],
                verdict=data['verdict'], status=data['status'], description=data['description'], type=MARK_TYPE[1][0],
                function_id=self._functions[data['comparison']]
            ))
            self._marks_data[identifier] = {
                'f_id': self._functions[data['comparison']],
                'tags': self.__get_tags(data['tags']),
                'attrs': data['attrs'],
                'error trace': BytesIO(json.dumps(
                    data['error trace'], ensure_ascii=False, sort_keys=True, indent=4
                ).encode('utf8'))
            }
            self.total += 1
        return new_marks

    def __is_not_used(self):
        pass


def delete_marks(marks):
    changes = {}
    for mark in marks:
        changes[mark.id] = {}
    MarkUnsafe.objects.filter(id__in=changes).update(version=0)
    for mr in MarkUnsafeReport.objects.filter(mark__in=marks, error=None).select_related('report'):
        changes[mr.mark_id][mr.report] = {'kind': '-', 'verdict1': mr.report.verdict}
    MarkUnsafe.objects.filter(id__in=changes).delete()
    changes = UpdateVerdicts(changes).changes
    unsafes_changes = {}
    for m_id in changes:
        for report in changes[m_id]:
            unsafes_changes[report] = changes[m_id][report]
    RecalculateTags(unsafes_changes)
    update_confirmed_cache(list(unsafes_changes))
    return unsafes_changes


def update_confirmed_cache(unsafes):
    unsafes = list(unsafe.id for unsafe in unsafes)
    with_confirmed = set(r_id for r_id, in MarkUnsafeReport.objects.filter(
        report_id__in=unsafes, type=ASSOCIATION_TYPE[1][0], error=None, result__gt=0).values_list('report_id'))
    ReportUnsafe.objects.filter(id__in=unsafes).update(has_confirmed=False)
    ReportUnsafe.objects.filter(id__in=with_confirmed).update(has_confirmed=True)
