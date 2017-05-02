#
# Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
# Institute for System Programming of the Russian Academy of Sciences
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

import json
from io import BytesIO

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import F
from django.utils.translation import ugettext_lazy as _

from bridge.vars import USER_ROLES, UNKNOWN_ERROR, UNSAFE_VERDICTS, MARK_UNSAFE, MARK_STATUS
from bridge.utils import logger, unique_id, file_checksum, file_get_or_create, BridgeException

from users.models import User
from reports.models import Verdict, ReportComponentLeaf, ReportAttr, ReportUnsafe, Attr, AttrName
from marks.models import MarkUnsafe, MarkUnsafeHistory, MarkUnsafeReport, MarkUnsafeAttr,\
    MarkUnsafeTag, UnsafeTag, UnsafeReportTag, ReportUnsafeTag,\
    MarkUnsafeCompare, MarkUnsafeConvert, ConvertedTraces
from marks.ConvertTrace import GetConvertedErrorTrace, ET_FILE_NAME
from marks.CompareTrace import CompareTrace


class NewMark:
    def __init__(self, user, args):
        self._user = user
        self._args = args
        self.changes = {}
        self._conversion = None
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

        if 'convert_id' in self._args:
            try:
                self._conversion = MarkUnsafeConvert.objects.get(id=self._args['convert_id'])
            except ObjectDoesNotExist:
                logger.exception("Get MarkUnsafeConvert(pk=%s)" % self._args['convert_id'])
                raise BridgeException(_('The error traces conversion function was not found'))

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
        if self._conversion is None:
            raise ValueError('Not enough args')
        error_trace = GetConvertedErrorTrace(self._conversion, report).converted
        mark = MarkUnsafe.objects.create(
            identifier=unique_id(), author=self._user, prime=report, format=report.root.job.format,
            job=report.root.job, description=str(self._args.get('description', '')), function=self._comparison,
            verdict=self._args['verdict'], status=self._args['status'], is_modifiable=self._args['is_modifiable']
        )

        try:
            markversion = self.__create_version(mark, error_trace)
            self.__create_attributes(markversion.id, report)
        except Exception:
            mark.delete()
            raise
        RecalculateTags(list(ConnectMarks([mark]).changes.get(mark.id, {})))
        return mark

    def change_mark(self, mark, recalculate_cache=True):
        if len(self._args['comment']) == 0:
            raise BridgeException(_('Change comment is required'))
        if 'error_trace' not in self._args and not isinstance(self._args['error_trace'], str):
            raise ValueError('error_trace is required')
        error_trace = BytesIO(json.dumps(
            json.loads(self._args['error_trace']), ensure_ascii=False, sort_keys=True, indent=4
        ).encode('utf8'))

        last_v = MarkUnsafeHistory.objects.get(version=F('mark__version'))

        mark.author = self._user
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

        if file_checksum(error_trace) != last_v.error_trace.hash_sum:
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
            if do_recalc:
                changes = ConnectMarks([mark]).changes
            else:
                changes = self.__create_changes(mark)
                if recalc_verdicts:
                    changes = UpdateVerdicts(changes).changes
            self.changes = changes.get(mark.id, {})
            RecalculateTags(list(self.changes))
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
        error_trace = BytesIO(json.dumps(
            json.loads(self._args['error_trace']), ensure_ascii=False, sort_keys=True, indent=4
        ).encode('utf8'))
        mark = MarkUnsafe.objects.create(
            identifier=self._args['identifier'], author=self._user,
            description=str(self._args.get('description', '')),
            verdict=self._args['verdict'], status=self._args['status'],
            is_modifiable=self._args['is_modifiable'], function=self._comparison
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
            change_date=mark.change_date, comment=self._args['comment'], author=mark.author,
            error_trace=error_trace, function=mark.function, description=mark.description
        )
        MarkUnsafeTag.objects.bulk_create(
            list(MarkUnsafeTag(tag_id=t_id, mark_version=markversion) for t_id in self._args['tags'])
        )
        return markversion

    def __create_attributes(self, markversion_id, inst=None):
        if 'attrs' not in self._args or not isinstance(self._args['attrs'], list) or len(self._args['attrs']) == 0:
            raise ValueError('Attributes are needed: %s' % self._args.get('attrs'))
        for a in self._args['attrs']:
            if not isinstance(a, dict) or not isinstance(a.get('attr'), str) \
                    or not isinstance(a.get('is_compare'), bool):
                raise ValueError('Wrong attribute found: %s' % a)
            if inst is None and not isinstance(a.get('value'), str):
                raise ValueError('Wrong attribute found: %s' % a)

        need_recalc = False
        new_attrs = []
        if isinstance(inst, ReportUnsafe):
            for a_id, a_name in inst.attrs.order_by('id').values_list('attr_id', 'attr__name__name'):
                for a in self._args['attrs']:
                    if a['attr'] == a_name:
                        new_attrs.append(MarkUnsafeAttr(
                            mark_id=markversion_id, attr_id=a_id, is_compare=a['is_compare']
                        ))
                        break
                else:
                    raise ValueError('Not enough attributes in args')
        elif isinstance(inst, MarkUnsafeHistory):
            for a_id, a_name, is_compare in inst.attrs.order_by('id')\
                    .values_list('attr_id', 'attr__name__name', 'is_compare'):
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
            for a in self._args['attrs']:
                attr = Attr.objects.get_or_create(
                    name=AttrName.objects.get_or_create(name=a['attr'])[0], value=a['value']
                )
                new_attrs.append(MarkUnsafeAttr(mark_id=markversion_id, attr=attr, is_compare=a['is_compare']))
        MarkUnsafeAttr.objects.bulk_create(new_attrs)
        return need_recalc

    def __is_not_used(self):
        pass


class ConnectMarks:
    def __init__(self, marks):
        self._marks = marks
        self.changes = {}
        self._functions = {}
        self._patterns = {}
        self._primes = {}

        self.__clear_connections()
        self._unsafes_attrs = self.__get_unsafes_attrs()
        self._marks_attrs = self.__get_marks_attrs()

        self.__connect()
        self.__update_verdicts()
        self.__check_prime()

    def __get_unsafes_attrs(self):
        self.__is_not_used()
        unsafes = {}
        for unsafe in ReportUnsafe.objects.all():
            unsafes[unsafe] = set()
        for attr in ReportAttr.objects.filter(report__in=unsafes):
            unsafes[attr.report].add(attr.attr_id)
        return unsafes

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
        for m_id, f_name, pattern_id, prime_id in MarkUnsafeHistory.objects.filter(mark_id__in=marks_attrs)\
                .values_list('mark_id', 'function__name', 'error_trace_id', 'mark__prime_id'):
            self._functions[m_id] = f_name
            self._patterns[m_id] = pattern_id
            self._primes[m_id] = prime_id
        return marks_attrs

    def __clear_connections(self):
        for mr in MarkUnsafeReport.objects.filter(mark__in=self._marks).select_related('report'):
            if mr.mark_id not in self.changes:
                self.changes[mr.mark_id] = {}
            self.changes[mr.mark_id][mr.report] = {'kind': '-', 'result1': mr.result, 'verdict1': mr.report.verdict}
        MarkUnsafeReport.objects.filter(mark__in=self._marks).delete()

    def __connect(self):
        new_markreports = []
        for unsafe in self._unsafes_attrs:
            for mark_id in self._marks_attrs:
                if not self._marks_attrs[mark_id].issubset(self._unsafes_attrs[unsafe]):
                    del self._patterns[mark_id]
                    del self._functions[mark_id]
                    continue
        patterns = {}
        for converted in ConvertedTraces.objects.filter(id__in=set(self._patterns.values())):
            with converted.file as fp:
                patterns[converted.id] = fp.read().decode('utf8')
        for m_id in self._patterns:
            self._patterns[m_id] = patterns[self._patterns[m_id]]

        prime_lost = set()
        for unsafe in self._unsafes_attrs:
            for mark_id in self._marks_attrs:
                compare_error = None
                try:
                    compare = CompareTrace(self._functions[mark_id], self._patterns[mark_id], unsafe)
                except BridgeException as e:
                    compare_error = str(e)
                except Exception as e:
                    logger.exception("Error traces comparison failed: %s" % e)
                    compare_error = str(UNKNOWN_ERROR)

                if compare_error is not None and self._primes[mark_id] == unsafe.id:
                    prime_lost.add(mark_id)

                if compare.result > 0 or compare_error is not None:
                    new_markreports.append(MarkUnsafeReport(
                        mark_id=mark_id, report=unsafe, result=compare.result, error=compare_error
                    ))
                    if mark_id not in self.changes:
                        self.changes[mark_id] = {}
                    if unsafe in self.changes[mark_id]:
                        self.changes[mark_id][unsafe]['kind'] = '='
                        self.changes[mark_id][unsafe]['result2'] = compare.result
                    else:
                        self.changes[mark_id][unsafe] = {
                            'kind': '+', 'result2': compare.result, 'verdict1': unsafe.verdict
                        }
        MarkUnsafe.objects.filter(id__in=prime_lost).update(prime=None)
        MarkUnsafeReport.objects.bulk_create(new_markreports)

    def __update_verdicts(self):
        unsafe_verdicts = {}
        for mark_id in self.changes:
            for unsafe in self.changes[mark_id]:
                unsafe_verdicts[unsafe] = set()
        for mr in MarkUnsafeReport.objects.filter(report__in=unsafe_verdicts).select_related('mark'):
            unsafe_verdicts[mr.report].add(mr.mark.verdict)

        unsafes_to_update = {}
        for unsafe in unsafe_verdicts:
            old_verdict = unsafe.verdict
            new_verdict = self.__calc_verdict(unsafe_verdicts[unsafe])
            if old_verdict != new_verdict:
                unsafes_to_update[unsafe] = new_verdict
                for mark_id in self.changes:
                    if unsafe in self.changes[mark_id]:
                        self.changes[mark_id][unsafe]['verdict2'] = new_verdict
        self.__new_verdicts(unsafes_to_update)

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

    @transaction.atomic
    def __new_verdicts(self, unsafes):
        self.__is_not_used()
        verdict_attrs = {
            '0': 'unsafe_unknown',
            '1': 'unsafe_bug',
            '2': 'unsafe_target_bug',
            '3': 'unsafe_false_positive',
            '4': 'unsafe_inconclusive',
            '5': 'unsafe_unassociated'
        }
        for unsafe in unsafes:
            reports = set(leaf.report_id for leaf in ReportComponentLeaf.objects.filter(unsafe=unsafe))
            Verdict.objects.filter(**{'report_id__in': reports, '%s__gt' % verdict_attrs[unsafe.verdict]: 0}) \
                .update(**{verdict_attrs[unsafe.verdict]: F(verdict_attrs[unsafe.verdict]) - 1})
            Verdict.objects.filter(report_id__in=reports).update(**{
                verdict_attrs[unsafes[unsafe]]: F(verdict_attrs[unsafes[unsafe]]) + 1
            })
            unsafe.verdict = unsafes[unsafe]
            unsafe.save()

    def __check_prime(self):
        marks_to_update = set()
        for mark in self._marks:
            if mark.prime not in self.changes[mark.id] or self.changes[mark.id][mark.prime]['kind'] == '-':
                marks_to_update.add(mark.id)
        MarkUnsafe.objects.filter(id__in=marks_to_update).update(prime=None)

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
        for m_id, f_name, pattern_id, prime_id, verdict in MarkUnsafeHistory.objects.filter(mark_id__in=marks_attrs)\
                .values_list('mark_id', 'function__name', 'error_trace_id', 'mark__prime_id', 'verdict'):
            self._marks[m_id] = {'function': f_name, 'pattern': pattern_id, 'verdict': verdict}
        return marks_attrs

    def __connect(self):
        new_markreports = []
        for mark_id in self._marks_attrs:
            if not self._marks_attrs[mark_id].issubset(self._unsafe_attrs):
                del self._marks
                continue
        patterns = {}
        for converted in ConvertedTraces.objects.filter(id__in=set(self._marks[mid]['pattern'] for mid in self._marks)):
            with converted.file as fp:
                patterns[converted.id] = fp.read().decode('utf8')
        for m_id in self._marks:
            self._marks[m_id]['pattern'] = patterns[self._marks[m_id]['pattern']]

        for mark_id in self._marks:
            compare_error = None
            try:
                compare = CompareTrace(self._marks[mark_id]['function'], self._marks[mark_id]['pattern'], self._unsafe)
            except BridgeException as e:
                compare_error = str(e)
            except Exception as e:
                logger.exception("Error traces comparison failed: %s" % e)
                compare_error = str(UNKNOWN_ERROR)

            if compare.result > 0 or compare_error is not None:
                new_markreports.append(MarkUnsafeReport(
                    mark_id=mark_id, report=self._unsafe, result=compare.result, error=compare_error
                ))
        MarkUnsafeReport.objects.bulk_create(new_markreports)

        new_verdict = UNSAFE_VERDICTS[5][0]
        for v in set(self._marks[m_id]['verdict'] for m_id in self._marks):
            if new_verdict != UNSAFE_VERDICTS[5][0] and new_verdict != v:
                new_verdict = UNSAFE_VERDICTS[4][0]
                break
            else:
                new_verdict = v
        if self._unsafe.verdict != new_verdict:
            self.__new_verdict(new_verdict)

    @transaction.atomic
    def __new_verdict(self, new):
        verdict_attrs = {
            '0': 'unsafe_unknown',
            '1': 'unsafe_bug',
            '2': 'unsafe_target_bug',
            '3': 'unsafe_false_positive',
            '4': 'unsafe_inconclusive',
            '5': 'unsafe_unassociated'
        }
        reports = set(leaf.report_id for leaf in ReportComponentLeaf.objects.filter(unsafe=self._unsafe))
        Verdict.objects.filter(**{'report_id__in': reports, '%s__gt' % verdict_attrs[self._unsafe.verdict]: 0}) \
            .update(**{verdict_attrs[self._unsafe.verdict]: F(verdict_attrs[self._unsafe.verdict]) - 1})
        Verdict.objects.filter(report_id__in=reports).update(**{verdict_attrs[new]: F(verdict_attrs[new]) + 1})
        self._unsafe.verdict = new
        self._unsafe.save()


class RecalculateTags:
    def __init__(self, reports):
        self.reports = reports
        self.__fill_leaves_cache()
        self.__fill_reports_cache()

    def __fill_leaves_cache(self):
        UnsafeReportTag.objects.filter(report__in=self.reports).delete()
        marks = {}
        for m_id, r_id in MarkUnsafeReport.objects.filter(report__in=self.reports).values_list('mark_id', 'report_id'):
            if m_id not in marks:
                marks[m_id] = set()
            marks[m_id].add(r_id)
        tags = {}
        for t_id, m_id in MarkUnsafeTag.objects.filter(
            mark_version__mark_id__in=marks, mark_version__version=F('mark_version__mark__version')
        ).values_list('tag_id', 'mark_version__mark_id'):
            for r_id in marks[m_id]:
                if (t_id, r_id) not in tags:
                    tags[(t_id, r_id)] = 0
                tags[(t_id, r_id)] += 1
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
        for mr in MarkUnsafeReport.objects.filter(report__in=unsafe_verdicts).select_related('mark'):
            unsafe_verdicts[mr.report].add(mr.mark.verdict)

        unsafes_to_update = {}
        for unsafe in unsafe_verdicts:
            old_verdict = unsafe.verdict
            new_verdict = self.__calc_verdict(unsafe_verdicts[unsafe])
            if old_verdict != new_verdict:
                unsafes_to_update[unsafe] = new_verdict
                for mark_id in self.changes:
                    if unsafe in self.changes[mark_id]:
                        self.changes[mark_id][unsafe]['verdict2'] = new_verdict
        self.__new_verdicts(unsafes_to_update)

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

    @transaction.atomic
    def __new_verdicts(self, unsafes):
        self.__is_not_used()
        verdict_attrs = {
            '0': 'unsafe_unknown',
            '1': 'unsafe_bug',
            '2': 'unsafe_target_bug',
            '3': 'unsafe_false_positive',
            '4': 'unsafe_inconclusive',
            '5': 'unsafe_unassociated'
        }
        for unsafe in unsafes:
            reports = set(leaf.report_id for leaf in ReportComponentLeaf.objects.filter(unsafe=unsafe))
            Verdict.objects.filter(**{'report_id__in': reports, '%s__gt' % verdict_attrs[unsafe.verdict]: 0}) \
                .update(**{verdict_attrs[unsafe.verdict]: F(verdict_attrs[unsafe.verdict]) - 1})
            Verdict.objects.filter(report_id__in=reports).update(**{
                verdict_attrs[unsafes[unsafe]]: F(verdict_attrs[unsafes[unsafe]]) + 1
            })
            unsafe.verdict = unsafes[unsafe]
            unsafe.save()

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
        Verdict.objects.filter(report__root__in=self._roots).update(
            unsafe_bug=0, unsafe_target_bug=0, unsafe_false_positive=0,
            unsafe_unknown=0, unsafe_inconclusive=0, unsafe_unassociated=F('unsafe')
        )
        for unsafe in ReportUnsafe.objects.filter(root__in=self._roots):
            ConnectReport(unsafe)


def delete_marks(marks):
    changes = {}
    for mark in marks:
        changes[mark.id] = {}
    MarkUnsafe.objects.filter(id__in=changes).update(version=0)
    for mr in MarkUnsafeReport.objects.filter(mark__in=marks).select_related('report'):
        changes[mr.mark_id][mr.report] = {'kind': '-', 'verdict1': mr.report.verdict}
    MarkUnsafe.objects.filter(id__in=changes).delete()
    changes = UpdateVerdicts(changes).changes
    unsafes_changes = {}
    for m_id in changes:
        for report in changes[m_id]:
            unsafes_changes[report] = changes[m_id][report]
    RecalculateTags(unsafes_changes)
    return unsafes_changes
