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

import re
import json
from io import BytesIO
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import F, Count
from django.utils.translation import ugettext_lazy as _
from bridge.vars import USER_ROLES, JOB_ROLES, MARKS_COMPARE_ATTRS, UNKNOWN_ERROR
from bridge.utils import logger, unique_id, ArchiveFileContent, file_checksum, file_get_or_create, BridgeException
from marks.models import *
from reports.models import Verdict, ReportComponentLeaf
from marks.ConvertTrace import GetConvertedErrorTrace, ET_FILE_NAME
from marks.CompareTrace import CompareTrace


class NewMark:
    def __init__(self, inst, user, mark_type, args, calculate=True):
        """
        After initialization has params: mark, mark_version and error:
        mark - Instance of created/changed MarkUnsafe/MarkSafe
        mark_version - instance of MarkUnsafeHistory/MarkSafeHistory,
                       last version for mark
        error - error message in case of failure, None if everything is OK
        user - User instance of mark author
        do_recalk - True/False - say if you need to recalk connections
                    between new mark and all leaves.
        :param inst: instance of ReportUnsafe/ReportSafe for creating mark
        and insatnce of MarkUnsafe/MarkSafe for changing it
        :param user: instance of User (author of mark change/creation)
        :param mark_type: 'safe', 'unsafe' or 'unknown'
        :param args: dictionary with keys:
            'status': see MARK_STATUS from bridge.vars, default - '0'.
            'verdict': see MARK_UNSAFE/MARK_SAFE from bridge.vars, default - '0'
            'convert_id': MarkUnsafeCompare id (only for creating unsafe mark)
            'compare_id': MarkUnsafeConvert id (only for unsafe mark)
            'attrs': list of dictionaries with required keys:
                    'attr': name of attribute (string)
                    'is_compare': True of False
            'is_modifiable': True or False, default - True
                            (only for creating mark)
        :return: Nothing
        """
        self.mark = None
        self.calculate = calculate
        self.mark_version = None
        self.user = user
        self.type = mark_type
        self.do_recalk = False
        self.changes = {}
        self.cnt = 0
        if not isinstance(args, dict) or not isinstance(user, User):
            logger.error('Wrong arguments', stack_info=True)
            raise BridgeException()
        elif self.type == 'safe' and isinstance(inst, ReportSafe) or \
                self.type == 'unsafe' and isinstance(inst, ReportUnsafe) or \
                self.type == 'unknown' and isinstance(inst, ReportUnknown):
            self.__create_mark(inst, args)
        elif self.type == 'unsafe' and isinstance(inst, MarkUnsafe) or \
                self.type == 'safe' and isinstance(inst, MarkSafe) or \
                self.type == 'unknown' and isinstance(inst, MarkUnknown):
            self.__change_mark(inst, args)
        else:
            logger.error('Wrong arguments')
            raise BridgeException()

    def __create_mark(self, report, args):
        init_args = {
            'identifier': unique_id(),
            'author': self.user,
            'format': report.root.job.format,
            'job': report.root.job,
            'description': str(args.get('description', ''))
        }
        if self.type == 'unsafe':
            mark = MarkUnsafe(**init_args)
        elif self.type == 'safe':
            mark = MarkSafe(**init_args)
        else:
            mark = MarkUnknown(**init_args)
        mark.author = self.user
        mark.prime = report

        error_trace = None
        if self.type == 'unsafe':
            if any(x not in args for x in ['convert_id', 'compare_id']):
                raise BridgeException(_('Not enough data to create an unsafe mark'))
            try:
                func = MarkUnsafeConvert.objects.get(pk=int(args['convert_id']))
            except ObjectDoesNotExist:
                logger.exception("Get MarkUnsafeConvert(pk=%s)" % args['convert_id'], stack_info=True)
                raise BridgeException(_('The error traces conversion function was not found'))
            error_trace = GetConvertedErrorTrace(func, report).converted
            try:
                mark.function = MarkUnsafeCompare.objects.get(pk=int(args['compare_id']))
            except ObjectDoesNotExist:
                logger.exception("Get MarkUnsafeCompare(pk=%s)" % args['compare_id'], stack_info=True)
                raise BridgeException(_('The error traces comparison function was not found'))
        elif self.type == 'unknown':
            mark.component = report.component

            if 'function' not in args or len(args['function']) == 0:
                raise BridgeException(_('The pattern is required'))
            mark.function = args['function']
            try:
                re.search(mark.function, '')
            except Exception as e:
                logger.exception("Wrong mark function (%s): %s" % (mark.function, e), stack_info=True)
                raise BridgeException(_('The pattern is wrong, please refer to documentation on the standard Python '
                                        'library for processing reqular expressions'))

            if 'problem' not in args or len(args['problem']) == 0:
                raise BridgeException(_('The problem is required'))
            elif len(args['problem']) > 15:
                raise BridgeException(_('The problem length must be less than 15 characters'))
            mark.problem_pattern = args['problem']

            if MarkUnknown.objects.filter(component=mark.component, problem_pattern=mark.problem_pattern).count() > 0:
                raise BridgeException(_('Could not create a new mark since the similar mark exists already'))

            if 'link' in args and len(args['link']) > 0:
                mark.link = args['link']

        if isinstance(args.get('is_modifiable'), bool) and self.user.extended.role == USER_ROLES[2][0]:
            mark.is_modifiable = args['is_modifiable']

        if self.type == 'unsafe' and args.get('verdict') in set(x[0] for x in MARK_UNSAFE) \
                or self.type == 'safe' and args.get('verdict') in set(x[0] for x in MARK_SAFE):
            mark.verdict = args['verdict']
        elif self.type != 'unknown':
            logger.error('Verdict is wrong: %s' % args.get('verdict'), stack_info=True)
            raise BridgeException()

        if args.get('status') not in set(x[0] for x in MARK_STATUS):
            logger.error('Unknown mark status: %s' % args.get('status'), stack_info=True)
            raise BridgeException()
        mark.status = args['status']

        try:
            mark.save()
        except Exception as e:
            logger.exception('Saving mark failed: %s' % e, stack_info=True)
            raise BridgeException(_('Saving the mark failed'))
        try:
            self.__update_mark(mark, args.get('tags'), error_trace)
        except Exception:
            mark.delete()
            raise

        if self.type != 'unknown':
            try:
                self.__create_attributes(report, args.get('attrs'))
            except Exception as e:
                logger.exception(e)
                mark.delete()
                raise BridgeException()
        self.mark = mark
        self.changes = ConnectMarkWithReports(self.mark).changes

        for leaf in self.changes:
            RecalculateTags(leaf)

    def __change_mark(self, mark, args):
        recalc_verdicts = False

        if 'comment' not in args or len(args['comment']) == 0:
            raise BridgeException(_('Change comment is required'))
        last_v = mark.versions.order_by('-version').first()
        if last_v is None:
            logger.error('No mark versions found', stack_info=True)
            raise BridgeException()

        mark.author = self.user
        error_trace = None
        if self.type == 'unsafe':
            try:
                new_func = MarkUnsafeCompare.objects.get(pk=int(args['compare_id']))
            except ObjectDoesNotExist:
                logger.exception("Get MarkUnsafeCompare(pk=%s)" % args['compare_id'], stack_info=True)
                raise BridgeException(_('The error traces comparison function was not found'))
            if mark.function != new_func:
                mark.function = new_func
                self.do_recalk = True

            if 'error_trace' in args and isinstance(args['error_trace'], str):
                error_trace = BytesIO(json.dumps(
                    json.loads(args['error_trace']), ensure_ascii=False, sort_keys=True, indent=4
                ).encode('utf8'))
                if file_checksum(error_trace) != last_v.error_trace.hash_sum:
                    self.do_recalk = True
                    error_trace = file_get_or_create(error_trace, ET_FILE_NAME, ConvertedTraces)[0]
                else:
                    error_trace = last_v.error_trace
            else:
                error_trace = last_v.error_trace

        if self.type == 'unknown':
            if 'function' not in args or len(args['function']) == 0:
                raise BridgeException(_('The pattern is required'))
            if args['function'] != mark.function:
                try:
                    re.search(args['function'], '')
                except Exception as e:
                    logger.exception("Wrong mark function (%s): %s" % (args['function'], e), stack_info=True)
                    raise BridgeException(_('The pattern is wrong, please refer to documentation on the standard '
                                            'Python library for processing reqular expressions'))
                mark.function = args['function']
                self.do_recalk = True

            if 'problem' not in args or len(args['problem']) == 0:
                raise BridgeException(_('The problem is required'))
            elif len(args['problem']) > 15:
                raise BridgeException(_('The problem length must be less than 15 characters'))
            if args['problem'] != mark.problem_pattern:
                self.do_recalk = True
                mark.problem_pattern = args['problem']

            if MarkUnknown.objects.filter(component=mark.component, problem_pattern=mark.problem_pattern)\
                    .exclude(id=mark.id).count() > 0:
                raise BridgeException(_('Could not change the mark since it would be similar to the existing mark'))

            if 'link' in args and len(args['link']) > 0:
                mark.link = args['link']

        if (self.type == 'unsafe' and args.get('verdict') in list(x[0] for x in MARK_UNSAFE)) \
                or (self.type == 'safe' and args.get('verdict') in list(x[0] for x in MARK_SAFE)):
            if mark.verdict != args['verdict']:
                mark.verdict = args['verdict']
                recalc_verdicts = True
        elif self.type != 'unknown':
            logger.error('Verdict is wrong: %s' % args.get('verdict'), stack_info=True)
            raise BridgeException()

        if args.get('status') in list(x[0] for x in MARK_STATUS):
            mark.status = args['status']
        else:
            logger.error('Unknown mark status: %s' % args.get('status'), stack_info=True)
            raise BridgeException()

        if isinstance(args.get('is_modifiable'), bool) and self.user.extended.role == USER_ROLES[2][0]:
            mark.is_modifiable = args['is_modifiable']
        if 'description' in args:
            mark.description = str(args['description'])
        mark.version += 1

        try:
            self.__update_mark(mark, args.get('tags', []), error_trace=error_trace, comment=args['comment'])
        except Exception:
            self.mark_version.delete()
            raise

        if self.type != 'unknown':
            try:
                self.__update_attributes(last_v, args.get('attrs'))
            except Exception:
                self.mark_version.delete()
                raise
        mark.save()
        self.mark = mark

        if self.calculate:
            if self.do_recalk:
                self.changes = ConnectMarkWithReports(self.mark).changes
                for r in self.changes:
                    RecalculateTags(r)
            elif self.type != 'unknown':
                self.changes = {}
                for mr in self.mark.markreport_set.all():
                    self.changes[mr.report] = {'kind': '=', 'verdict1': mr.report.verdict}
                if recalc_verdicts:
                    self.changes = UpdateVerdict(mark, self.changes).changes
                for report in self.changes:
                    RecalculateTags(report)

    def __update_mark(self, mark, tags, error_trace=None, comment=''):
        args = {
            'mark': mark,
            'version': mark.version,
            'status': mark.status,
            'change_date': mark.change_date,
            'comment': comment,
            'author': mark.author,
            'description': mark.description,
        }
        if error_trace is not None:
            args['error_trace'] = error_trace
        if self.type != 'safe':
            args['function'] = mark.function
        if self.type == 'unknown':
            args['link'] = mark.link
            args['problem_pattern'] = mark.problem_pattern
        else:
            args['verdict'] = mark.verdict

        if self.type == 'unsafe':
            self.mark_version = MarkUnsafeHistory.objects.create(**args)
        elif self.type == 'safe':
            self.mark_version = MarkSafeHistory.objects.create(**args)
        else:
            self.mark_version = MarkUnknownHistory.objects.create(**args)

        if isinstance(tags, list) and len(tags) > 0:
            tags = set(int(t) for t in tags)
            tables = {
                'safe': (SafeTag, MarkSafeTag),
                'unsafe': (UnsafeTag, MarkUnsafeTag)
            }
            tags_in_db = {}
            for t in tables[self.type][0].objects.all().only('id', 'parent_id'):
                tags_in_db[t.id] = t.parent_id
            if any(t not in tags_in_db for t in tags):
                raise BridgeException(_('One of tags was not found'))
            tags_parents = set()
            for t in tags:
                parent = tags_in_db[t]
                while parent is not None and parent not in tags:
                    tags_parents.add(parent)
                    parent = tags_in_db[parent]
            tags |= tags_parents
            tables[self.type][1].objects.bulk_create(
                list(tables[self.type][1](tag_id=t, mark_version=self.mark_version) for t in tags)
            )

    def __update_attributes(self, old_mark, attrs):
        if old_mark is None:
            logger.error('Need previous mark version', stack_info=True)
            raise BridgeException()
        if not isinstance(attrs, list):
            logger.error('Attributes must be a list', stack_info=True)
            raise BridgeException()
        if len(attrs) == 0:
            for ma in old_mark.attrs.order_by('id').values_list('attr__name__name', 'is_compare'):
                attrs.append({'attr': ma[0], 'is_compare': ma[1]})
        for a in attrs:
            if not isinstance(a, dict) or 'attr' not in a or not isinstance(a.get('is_compare'), bool):
                logger.error('Wrong attribute found: %s' % a, stack_info=True)
                raise BridgeException()
        attrs_table = {
            'safe': MarkSafeAttr,
            'unsafe': MarkUnsafeAttr
        }
        attrs_to_create = []
        for a in old_mark.attrs.order_by('id').values('attr_id', 'is_compare', 'attr__name__name'):
            create_args = {'mark_id': self.mark_version.id, 'attr_id': a['attr_id'], 'is_compare': a['is_compare']}
            for u_at in attrs:
                if u_at['attr'] == a['attr__name__name']:
                    if u_at['is_compare'] != create_args['is_compare']:
                        create_args['is_compare'] = u_at['is_compare']
                        self.do_recalk = True
                    break
            else:
                logger.error('Attribute %s was not found in the new mark data' % a['attr__name__name'], stack_info=True)
                raise BridgeException()
            attrs_to_create.append(attrs_table[self.type](**create_args))
        attrs_table[self.type].objects.bulk_create(attrs_to_create)

    def __create_attributes(self, report, attrs):
        if not isinstance(attrs, list):
            raise ValueError('Attributes must be a list')
        if len(attrs) == 0:
            job_type = report.root.job.type
            for ra in report.attrs.order_by('id').values_list('attr__name__name'):
                attrs.append({'attr': ra[0], 'is_compare': True})
                if job_type in MARKS_COMPARE_ATTRS and ra[0] not in MARKS_COMPARE_ATTRS[job_type]:
                    attrs[-1]['is_compare'] = False

        for a in attrs:
            if not isinstance(a, dict) or 'attr' not in a or not isinstance(a.get('is_compare'), bool):
                raise ValueError('Wrong attribute found: %s' % a)

        attrs_table = {
            'safe': MarkSafeAttr,
            'unsafe': MarkUnsafeAttr
        }
        attrs_to_create = []
        for a in report.attrs.order_by('id').values('attr_id', 'attr__name__name'):
            create_args = {'mark_id': self.mark_version.id, 'attr_id': a['attr_id']}
            for u_at in attrs:
                if u_at['attr'] == a['attr__name__name']:
                    create_args['is_compare'] = u_at['is_compare']
                    break
            else:
                raise ValueError('Attribute %s was not found in the new mark data' % a['attr__name__name'])
            attrs_to_create.append(attrs_table[self.type](**create_args))
        attrs_table[self.type].objects.bulk_create(attrs_to_create)


class ConnectReportWithMarks:
    def __init__(self, report, update_cache=True):
        self.update_cache = update_cache
        self.report = report
        if isinstance(self.report, ReportUnsafe):
            self.__connect_unsafe()
        elif isinstance(self.report, ReportSafe):
            self.__connect_safe()
        elif isinstance(self.report, ReportUnknown):
            self.__connect_unknown()
        UpdateVerdict(self.report)
        RecalculateTags(self.report)

    def __connect_unsafe(self):
        self.report.markreport_set.all().delete()
        new_markreports = []
        unsafe_attrs = set(self.report.attrs.values_list('attr__name__name', 'attr__value'))
        for mark in MarkUnsafe.objects.all().select_related('function'):
            last_v = mark.versions.get(version=mark.version)
            mark_attrs = set(last_v.attrs.filter(is_compare=True).values_list('attr__name__name', 'attr__value'))
            if all(x in mark_attrs for x in set(x for x in unsafe_attrs if x[0] in set(y[0] for y in mark_attrs))):
                compare_error = None
                with last_v.error_trace.file as fp:
                    try:
                        compare = CompareTrace(mark.function.name, fp.read().decode('utf8'), self.report)
                    except BridgeException as e:
                        compare_error = str(e)
                    except Exception as e:
                        logger.exception("Error traces comparison failed: %s" % e)
                        compare_error = str(UNKNOWN_ERROR)
                if compare.result > 0 or compare_error is not None:
                    new_markreports.append(MarkUnsafeReport(
                        mark=mark, report=self.report, result=compare.result, error=compare_error
                    ))
        MarkUnsafeReport.objects.bulk_create(new_markreports)

    def __connect_safe(self):
        self.report.markreport_set.all().delete()
        new_markreports = []
        safe_attrs = set(self.report.attrs.values_list('attr__name__name', 'attr__value'))
        for mark in MarkSafe.objects.all():
            last_v = mark.versions.get(version=mark.version)
            mark_attrs = set(last_v.attrs.filter(is_compare=True).values_list('attr__name__name', 'attr__value'))
            if all(x in mark_attrs for x in set(x for x in safe_attrs if x[0] in set(y[0] for y in mark_attrs))):
                new_markreports.append(MarkSafeReport(mark=mark, report=self.report))
        if len(new_markreports) > 0:
            MarkSafeReport.objects.bulk_create(new_markreports)

    def __connect_unknown(self):
        self.report.markreport_set.all().delete()

        try:
            problem_desc = ArchiveFileContent(self.report, self.report.problem_description).content.decode('utf8')
        except Exception as e:
            logger.exception("Can't get problem desc for unknown '%s': %s" % (self.report.id, e))
            return
        new_markreports = []
        for mark in MarkUnknown.objects.filter(component=self.report.component):
            problem = MatchUnknown(problem_desc, mark.function, mark.problem_pattern).problem
            if problem is None:
                continue
            elif len(problem) > 15:
                problem = 'Too long!'
                logger.error(
                    "Generated problem '%s' for mark %s is too long" % (problem, mark.identifier), stack_info=True
                )
            new_markreports.append(MarkUnknownReport(
                mark=mark, report=self.report, problem=UnknownProblem.objects.get_or_create(name=problem)[0]
            ))
        if len(new_markreports) > 0:
            MarkUnknownReport.objects.bulk_create(new_markreports)
        if self.update_cache:
            update_unknowns_cache([self.report])


class ConnectMarkWithReports:
    def __init__(self, mark):
        self.mark = mark
        self.changes = {}  # Changes with reports' marks after connections
        if isinstance(self.mark, MarkUnsafe):
            self.__connect_unsafe_mark()
        elif isinstance(self.mark, MarkSafe):
            self.__connect_safe_mark()
        elif isinstance(self.mark, MarkUnknown):
            self.__connect_unknown_mark()
        else:
            return
        self.changes.update(UpdateVerdict(self.mark, self.changes).changes)
        if self.mark.prime not in self.changes or self.changes[self.mark.prime]['kind'] == '-':
            self.mark.prime = None
            self.mark.save()

    def __connect_unsafe_mark(self):
        last_v = self.mark.versions.get(version=self.mark.version)
        mark_attrs = set(last_v.attrs.filter(is_compare=True).values_list('attr__name__name', 'attr__value'))
        for mark_unsafe in self.mark.markreport_set.all().select_related('report'):
            self.changes[mark_unsafe.report] = {
                'kind': '-', 'result1': mark_unsafe.result, 'verdict1': mark_unsafe.report.verdict,
            }
        self.mark.markreport_set.all().delete()
        with last_v.error_trace.file as fp:
            pattern_error_trace = fp.read().decode('utf8')
        new_markreports = []
        for unsafe in ReportUnsafe.objects.all():
            unsafe_attrs = set(unsafe.attrs.filter(
                attr__name__name__in=set(x[0] for x in mark_attrs)
            ).values_list('attr__name__name', 'attr__value'))
            if any(x not in mark_attrs for x in unsafe_attrs):
                continue
            compare_error = None
            try:
                compare = CompareTrace(self.mark.function.name, pattern_error_trace, unsafe)
            except BridgeException as e:
                compare_error = str(e)
            except Exception as e:
                logger.exception("Error traces comparison failed: %s" % e)
                compare_error = str(UNKNOWN_ERROR)

            if compare_error is not None and self.mark.prime == unsafe:
                self.mark.prime = None
                self.mark.save()
            if compare.result > 0 or compare_error is not None:
                new_markreports.append(MarkUnsafeReport(
                    mark=self.mark, report=unsafe, result=compare.result, error=compare_error
                ))
                if unsafe in self.changes:
                    self.changes[unsafe]['kind'] = '='
                    self.changes[unsafe]['result2'] = compare.result
                else:
                    self.changes[unsafe] = {
                        'kind': '+', 'result2': compare.result, 'verdict1': unsafe.verdict
                    }
        if len(new_markreports) > 0:
            MarkUnsafeReport.objects.bulk_create(new_markreports)

    def __connect_safe_mark(self):
        last_v = self.mark.versions.get(version=self.mark.version)
        mark_attrs = set(last_v.attrs.filter(is_compare=True).values_list('attr__name__name', 'attr__value'))

        for mark_safe in self.mark.markreport_set.all():
            self.changes[mark_safe.report] = {'kind': '=', 'verdict1': mark_safe.report.verdict}
        self.mark.markreport_set.all().delete()
        new_markreports = []
        for safe in ReportSafe.objects.all():
            safe_attrs = set(safe.attrs.filter(
                attr__name__name__in=set(x[0] for x in mark_attrs)
            ).values_list('attr__name__name', 'attr__value'))
            if any(x not in mark_attrs for x in safe_attrs):
                continue
            new_markreports.append(MarkSafeReport(mark=self.mark, report=safe))
            if safe in self.changes:
                self.changes[safe]['kind'] = '='
            else:
                self.changes[safe] = {'kind': '+', 'verdict1': safe.verdict}
        if len(new_markreports) > 0:
            MarkSafeReport.objects.bulk_create(new_markreports)

    def __connect_unknown_mark(self):
        for mark_unknown in self.mark.markreport_set.all():
            self.changes[mark_unknown.report] = {'kind': '-'}
        self.mark.markreport_set.all().delete()
        new_markreports = []
        for unknown in ReportUnknown.objects.filter(component=self.mark.component):
            try:
                problem_description = ArchiveFileContent(unknown, unknown.problem_description).content.decode('utf8')
            except Exception as e:
                logger.exception("Can't get problem description for unknown '%s': %s" % (unknown.id, e))
                return
            problem = MatchUnknown(problem_description, self.mark.function, self.mark.problem_pattern).problem
            if problem is None:
                continue
            elif len(problem) > 15:
                problem = 'Too long!'
                logger.error("Problem '%s' for mark %s is too long" % (problem, self.mark.identifier), stack_info=True)
            new_markreports.append(MarkUnknownReport(
                mark=self.mark, report=unknown, problem=UnknownProblem.objects.get_or_create(name=problem)[0]
            ))
            if unknown in self.changes:
                self.changes[unknown]['kind'] = '='
            else:
                self.changes[unknown] = {'kind': '+'}
        if len(new_markreports) > 0:
            MarkUnknownReport.objects.bulk_create(new_markreports)
        update_unknowns_cache(list(self.changes))


class UpdateVerdict:
    def __init__(self, inst, changes=None):
        self.changes = changes
        if isinstance(inst, MarkUnsafe):
            self.__update_unsafes(inst)
        elif isinstance(inst, MarkSafe):
            self.__update_safes(inst)
        elif isinstance(inst, (ReportUnsafe, ReportSafe)):
            self.__update_report(inst)

    def __update_unsafes(self, mark):
        for mark_report in mark.markreport_set.select_related('report'):
            unsafe = mark_report.report
            if isinstance(self.changes, dict) and unsafe not in self.changes:
                continue
            new_verdict = self.__calc_verdict(unsafe)
            if new_verdict != unsafe.verdict:
                self.__new_verdict(unsafe, new_verdict)
            if isinstance(self.changes, dict):
                self.changes[unsafe]['verdict2'] = new_verdict

        # Updating unsafes that have lost changed mark
        if isinstance(self.changes, dict):
            for unsafe in self.changes:
                if self.changes[unsafe]['kind'] == '-':
                    self.changes[unsafe]['verdict2'] = unsafe.verdict
                    new_verdict = '5'
                    if unsafe.verdict == '4':
                        new_verdict = self.__calc_verdict(unsafe)
                    elif unsafe.markreport_set.all().count() > 0:
                        continue
                    if new_verdict != unsafe.verdict:
                        self.__new_verdict(unsafe, new_verdict)
                        self.changes[unsafe]['verdict2'] = new_verdict

    def __update_safes(self, mark):
        for mark_report in mark.markreport_set.all().select_related('report'):
            safe = mark_report.report
            if isinstance(self.changes, dict) and safe not in self.changes:
                continue
            new_verdict = self.__calc_verdict(safe)
            if new_verdict != safe.verdict:
                self.__new_verdict(safe, new_verdict)
            if isinstance(self.changes, dict):
                self.changes[safe]['verdict2'] = new_verdict

        # Updating safes that have lost changed mark
        if isinstance(self.changes, dict):
            for safe in self.changes:
                if self.changes[safe]['kind'] == '-':
                    self.changes[safe]['verdict2'] = safe.verdict
                    new_verdict = '4'
                    if safe.verdict == '3':
                        new_verdict = self.__calc_verdict(safe)
                    elif safe.markreport_set.all().count() > 0:
                        continue
                    if new_verdict != safe.verdict:
                        self.__new_verdict(safe, new_verdict)
                        self.changes[safe]['verdict2'] = new_verdict

    def __update_report(self, report):
        new_verdict = self.__calc_verdict(report)
        if new_verdict != report.verdict:
            self.__new_verdict(report, new_verdict)

    def __new_verdict(self, report, new):
        self.__is_not_used()
        if isinstance(report, ReportSafe):
            verdict_attrs = {
                '0': 'safe_unknown',
                '1': 'safe_incorrect_proof',
                '2': 'safe_missed_bug',
                '3': 'safe_inconclusive',
                '4': 'safe_unassociated'
            }
            leaves_filter = {'safe': report}
        elif isinstance(report, ReportUnsafe):
            verdict_attrs = {
                '0': 'unsafe_unknown',
                '1': 'unsafe_bug',
                '2': 'unsafe_target_bug',
                '3': 'unsafe_false_positive',
                '4': 'unsafe_inconclusive',
                '5': 'unsafe_unassociated'
            }
            leaves_filter = {'unsafe': report}
        else:
            return
        reports = set(leaf.report_id for leaf in ReportComponentLeaf.objects.filter(**leaves_filter))
        Verdict.objects.filter(**{'report_id__in': reports, '%s__gt' % verdict_attrs[report.verdict]: 0})\
            .update(**{verdict_attrs[report.verdict]: F(verdict_attrs[report.verdict]) - 1})
        Verdict.objects.filter(report_id__in=reports).update(**{verdict_attrs[new]: F(verdict_attrs[new]) + 1})
        report.verdict = new
        report.save()

    def __calc_verdict(self, report):
        self.ccc = 0
        if isinstance(report, ReportUnsafe):
            incompatable = '4'
            unmarked = '5'
        elif isinstance(report, ReportSafe):
            incompatable = '3'
            unmarked = '4'
        else:
            return None
        new_verdict = None
        for mr in report.markreport_set.all().values('mark__verdict'):
            if new_verdict is not None and new_verdict != mr['mark__verdict']:
                new_verdict = incompatable
                break
            else:
                new_verdict = mr['mark__verdict']
        if new_verdict is None:
            new_verdict = unmarked
        return new_verdict

    def __is_not_used(self):
        pass


class MarkAccess(object):

    def __init__(self, user, mark=None, report=None):
        self.user = user
        self.mark = mark
        self.report = report

    def can_edit(self):
        if not isinstance(self.user, User):
            return False
        if self.user.extended.role == USER_ROLES[2][0]:
            return True
        if not self.mark.is_modifiable or self.mark.version == 0:
            return False
        if self.user.extended.role == USER_ROLES[3][0]:
            return True
        if isinstance(self.mark, (MarkUnsafe, MarkSafe, MarkUnknown)):
            first_vers = self.mark.versions.order_by('version').first()
        else:
            return False
        if first_vers.author == self.user:
            return True
        if self.mark.job is not None:
            first_v = self.mark.job.versions.order_by('version').first()
            if first_v.change_author == self.user:
                return True
            last_v = self.mark.job.versions.get(version=self.mark.job.version)
            if last_v.global_role in [JOB_ROLES[2][0], JOB_ROLES[4][0]]:
                return True
            try:
                user_role = last_v.userrole_set.get(user=self.user)
                if user_role.role in [JOB_ROLES[2][0], JOB_ROLES[4][0]]:
                    return True
            except ObjectDoesNotExist:
                return False
        return False

    def can_create(self):
        if not isinstance(self.user, User):
            return False
        if isinstance(self.report, (ReportUnsafe, ReportSafe, ReportUnknown)):
            if not self.report.archive and not isinstance(self.report, ReportSafe):
                return False
            if isinstance(self.report, ReportSafe) and not self.report.root.job.safe_marks:
                return False
            if self.user.extended.role in [USER_ROLES[2][0], USER_ROLES[3][0]]:
                return True
            first_v = self.report.root.job.versions.order_by('version').first()
            if first_v.change_author == self.user:
                return True
            try:
                last_v = self.report.root.job.versions.get(version=self.report.root.job.version)
            except ObjectDoesNotExist:
                return False
            if last_v.global_role in [JOB_ROLES[2][0], JOB_ROLES[4][0]]:
                return True
            try:
                user_role = last_v.userrole_set.get(user=self.user)
                if user_role.role in [JOB_ROLES[2][0], JOB_ROLES[4][0]]:
                    return True
            except ObjectDoesNotExist:
                return False
        elif self.user.extended.role in [USER_ROLES[2][0], USER_ROLES[3][0]]:
            return True
        return False

    def can_delete(self):
        if not isinstance(self.user, User):
            return False
        if self.user.extended.role == USER_ROLES[2][0]:
            return True
        if not self.mark.is_modifiable or self.mark.version == 0:
            return False
        if self.user.extended.role == USER_ROLES[3][0]:
            return True
        if self.mark.versions.order_by('version')[0].author == self.user:
            return True
        return False


class TagsInfo:
    def __init__(self, mark_type, mark=None):
        self.mark = mark
        self.type = mark_type
        self.tags_old = []
        self.tags_available = []
        self.__get_tags()

    def __get_tags(self):
        if self.type not in ['unsafe', 'safe']:
            return
        if isinstance(self.mark, (MarkUnsafe, MarkSafe)):
            last_v = self.mark.versions.get(version=self.mark.version)
            self.tags_old = list(t['tag__tag'] for t in last_v.tags.order_by('tag__tag').values('tag__tag'))
        elif isinstance(self.mark, (MarkUnsafeHistory, MarkSafeHistory)):
            self.tags_old = list(t['tag__tag'] for t in self.mark.tags.order_by('tag__tag').values('tag__tag'))
        if self.type == 'unsafe':
            table = UnsafeTag
        else:
            table = SafeTag
        self.tags_available = list(t['tag'] for t in table.objects.values('tag') if t['tag'] not in self.tags_old)


class RecalculateTags:
    def __init__(self, report):
        self.report = report
        self._safes = set()
        self._unsafes = set()
        self.__fill_leaves_cache()
        if isinstance(self.report, ReportSafe):
            self.__fill_reports_safe_cache()
        elif isinstance(self.report, ReportUnsafe):
            self.__fill_reports_unsafe_cache()

    def __fill_leaves_cache(self):
        if isinstance(self.report, ReportSafe):
            tags_model = MarkSafeTag
            cache_model = SafeReportTag
            vers_model = MarkSafeHistory
        elif isinstance(self.report, ReportUnsafe):
            tags_model = MarkUnsafeTag
            cache_model = UnsafeReportTag
            vers_model = MarkUnsafeHistory
        else:
            return

        # Clear the cache
        cache_model.objects.filter(report=self.report).delete()

        # Last versions of marks that are connected with report with id 'r_id'
        versions = vers_model.objects.filter(version=F('mark__version'), mark__markreport_set__report=self.report)

        new_reporttags = []
        for mt in tags_model.objects.filter(mark_version__in=versions)\
                .annotate(number=Count('id')).values('number', 'tag_id'):
            if mt['number'] > 0:
                new_reporttags.append(cache_model(report=self.report, tag_id=mt['tag_id'], number=mt['number']))
        cache_model.objects.bulk_create(new_reporttags)

    def __fill_reports_safe_cache(self):
        # Affected components' reports
        reports = set(leaf['report_id']
                      for leaf in ReportComponentLeaf.objects.filter(safe=self.report).values('report_id'))

        # Clear cache
        ReportSafeTag.objects.filter(report_id__in=reports).delete()

        # Get all safes for each affected report
        reports_data = {}
        all_safes = set()
        for leaf in ReportComponentLeaf.objects.filter(report_id__in=reports).exclude(safe=None)\
                .values('safe_id', 'report_id'):
            if leaf['report_id'] not in reports_data:
                reports_data[leaf['report_id']] = {'leaves': set(), 'numbers': {}}
            reports_data[leaf['report_id']]['leaves'].add(leaf['safe_id'])
            all_safes.add(leaf['safe_id'])
        for rt in SafeReportTag.objects.filter(report_id__in=all_safes):
            for rc_id in reports_data:
                if rt.report_id in reports_data[rc_id]['leaves']:
                    if rt.tag_id in reports_data[rc_id]['numbers']:
                        reports_data[rc_id]['numbers'][rt.tag_id] += rt.number
                    else:
                        reports_data[rc_id]['numbers'][rt.tag_id] = rt.number

        # Fill new cache
        new_reporttags = []
        for rc_id in reports_data:
            for t_id in reports_data[rc_id]['numbers']:
                if reports_data[rc_id]['numbers'][t_id] > 0:
                    new_reporttags.append(ReportSafeTag(
                        report_id=rc_id, tag_id=t_id, number=reports_data[rc_id]['numbers'][t_id]
                    ))
        ReportSafeTag.objects.bulk_create(new_reporttags)

    def __fill_reports_unsafe_cache(self):
        # Affected components' reports
        reports = set(leaf['report_id']
                      for leaf in ReportComponentLeaf.objects.filter(unsafe=self.report).values('report_id'))

        # Clear cache
        ReportUnsafeTag.objects.filter(report_id__in=reports).delete()

        # Get all unsafes for each affected report
        reports_data = {}
        all_unsafes = set()
        for leaf in ReportComponentLeaf.objects.filter(report_id__in=reports).exclude(unsafe=None)\
                .values('unsafe_id', 'report_id'):
            if leaf['report_id'] not in reports_data:
                reports_data[leaf['report_id']] = {'leaves': set(), 'numbers': {}}
            reports_data[leaf['report_id']]['leaves'].add(leaf['unsafe_id'])
            all_unsafes.add(leaf['unsafe_id'])

        # Get numbers of tags for each affected report
        for rt in UnsafeReportTag.objects.filter(report_id__in=all_unsafes):
            for rc_id in reports_data:
                if rt.report_id in reports_data[rc_id]['leaves']:
                    if rt.tag_id in reports_data[rc_id]['numbers']:
                        reports_data[rc_id]['numbers'][rt.tag_id] += rt.number
                    else:
                        reports_data[rc_id]['numbers'][rt.tag_id] = rt.number

        # Fill new cache
        new_reporttags = []
        for rc_id in reports_data:
            for t_id in reports_data[rc_id]['numbers']:
                if reports_data[rc_id]['numbers'][t_id] > 0:
                    new_reporttags.append(ReportUnsafeTag(
                        report_id=rc_id, tag_id=t_id, number=reports_data[rc_id]['numbers'][t_id]
                    ))
        ReportUnsafeTag.objects.bulk_create(new_reporttags)


class DeleteMark(object):
    def __init__(self, mark):
        self.mark = mark
        self.__delete()

    def __delete(self):
        if not isinstance(self.mark, (MarkSafe, MarkUnsafe, MarkUnknown)):
            return

        # Mark the mark as deleted
        self.mark.version = 0
        self.mark.save()

        # Get list of affected reports
        leaves = []
        for mark_report in self.mark.markreport_set.all():
            leaves.append(mark_report.report)

        self.mark.delete()
        if isinstance(self.mark, MarkUnknown):
            update_unknowns_cache(leaves)
        else:
            for report in leaves:
                UpdateVerdict(report)
                RecalculateTags(report)


class MatchUnknown(object):
    def __init__(self, description, func, pattern):
        self.description = str(description)
        self.function = str(func)
        self.pattern = str(pattern)
        self.max_pn = None
        self.numbers = []
        self.__check_pattern()
        self.problem = self.__match_description()
        if isinstance(self.problem, str) and len(self.problem) == 0:
            self.problem = None

    def __check_pattern(self):
        self.numbers = re.findall('{(\d+)}', self.pattern)
        self.numbers = [int(x) for x in self.numbers]
        self.max_pn = -1
        if len(self.numbers) > 0:
            self.max_pn = max(self.numbers)
        for n in range(self.max_pn + 1):
            if n not in self.numbers:
                self.max_pn = None
                self.numbers = []
                return

    def __match_description(self):
        for l in self.description.split('\n'):
            try:
                m = re.search(self.function, l)
            except Exception as e:
                logger.exception("Regexp error: %s" % e, stack_info=True)
                return None
            if m is not None:
                if self.max_pn is not None and len(self.numbers) > 0:
                    group_elements = []
                    for n in range(1, self.max_pn + 2):
                        try:
                            group_elements.append(m.group(n))
                        except IndexError:
                            group_elements.append('')
                    return self.pattern.format(*group_elements)
                return self.pattern
        return None


def update_unknowns_cache(unknowns):
    reports = []
    for leaf in ReportComponentLeaf.objects.filter(unknown__in=list(unknowns)):
        if leaf.report_id not in reports:
            reports.append(leaf.report_id)

    all_unknowns = {}
    components_data = {}
    for leaf in ReportComponentLeaf.objects.filter(report_id__in=reports).exclude(unknown=None)\
            .values('report_id', 'unknown_id', 'unknown__component_id'):
        if leaf['report_id'] not in all_unknowns:
            all_unknowns[leaf['report_id']] = set()
        all_unknowns[leaf['report_id']].add(leaf['unknown_id'])
        if leaf['unknown__component_id'] not in components_data:
            components_data[leaf['unknown__component_id']] = set()
        components_data[leaf['unknown__component_id']].add(leaf['unknown_id'])

    unknowns_ids = set()
    for rc_id in all_unknowns:
        unknowns_ids = unknowns_ids | all_unknowns[rc_id]
    marked_unknowns = set()
    problems_data = {}
    for mr in MarkUnknownReport.objects.filter(report_id__in=unknowns_ids):
        if mr.problem_id not in problems_data:
            problems_data[mr.problem_id] = set()
        problems_data[mr.problem_id].add(mr.report_id)
        marked_unknowns.add(mr.report_id)

    problems_data[None] = unknowns_ids - marked_unknowns

    new_cache = []
    for r_id in all_unknowns:
        for p_id in problems_data:
            for c_id in components_data:
                number = len(all_unknowns[r_id] & problems_data[p_id] & components_data[c_id])
                if number > 0:
                    new_cache.append(ComponentMarkUnknownProblem(
                        report_id=r_id, component_id=c_id, problem_id=p_id, number=number
                    ))
    ComponentMarkUnknownProblem.objects.filter(report_id__in=reports).delete()
    ComponentMarkUnknownProblem.objects.bulk_create(new_cache)
