import re
from io import BytesIO
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.utils.translation import ugettext_lazy as _
from bridge.vars import USER_ROLES, JOB_ROLES
from bridge.utils import logger, unique_id, file_get_or_create, ArchiveFileContent
from marks.models import *
from reports.models import ReportComponent, Verdict
from marks.ConvertTrace import ConvertTrace
from marks.CompareTrace import CompareTrace

MARK_ERROR_TRACE_FILE_NAME = 'converted-error-trace.json'


class NewMark(object):

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
            self.error = 'Unknown error'
        elif self.type == 'safe' and isinstance(inst, ReportSafe) or \
                self.type == 'unsafe' and isinstance(inst, ReportUnsafe) or \
                self.type == 'unknown' and isinstance(inst, ReportUnknown):
            self.error = self.__create_mark(inst, args)
        elif self.type == 'unsafe' and isinstance(inst, MarkUnsafe) or \
                self.type == 'safe' and isinstance(inst, MarkSafe) or \
                self.type == 'unknown' and isinstance(inst, MarkUnknown):
            self.error = self.__change_mark(inst, args)
        else:
            logger.error('Wrong arguments', stack_info=True)
            self.error = 'Unknown error'
            return

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

        if self.type == 'unsafe':
            if any(x not in args for x in ['convert_id', 'compare_id']):
                logger.error('Not enough data to create unsafe mark', stack_info=True)
                return 'Unknown error'
            try:
                func = MarkUnsafeConvert.objects.get(pk=int(args['convert_id']))
            except ObjectDoesNotExist:
                logger.exception("Get MarkUnsafeConvert(pk=%s)" % args['convert_id'], stack_info=True)
                return _('The error traces conversion function was not found')

            error_trace = ArchiveFileContent(report.archive, report.error_trace)
            if error_trace.error is not None:
                return error_trace.error
            converted = ConvertTrace(func.name, error_trace.content)
            if converted.error is not None:
                logger.error(converted.error, stack_info=True)
                return _('Error trace converting failed')
            mark.error_trace = file_get_or_create(
                BytesIO(converted.pattern_error_trace.encode('utf8')), MARK_ERROR_TRACE_FILE_NAME
            )[0]

            try:
                mark.function = MarkUnsafeCompare.objects.get(pk=int(args['compare_id']))
            except ObjectDoesNotExist:
                logger.exception("Get MarkUnsafeCompare(pk=%s)" % args['compare_id'], stack_info=True)
                return _('The error traces comparison function was not found')
        elif self.type == 'unknown':
            mark.component = report.component

            if 'function' not in args or len(args['function']) == 0:
                return _('The pattern is required')
            mark.function = args['function']
            try:
                re.search(mark.function, '')
            except Exception as e:
                logger.exception("Wrong mark function (%s): %s" % (mark.function, e), stack_info=True)
                return _('The pattern is wrong, please refer to documentation on the standard Python '
                         'library for processing reqular expressions')

            if 'problem' not in args or len(args['problem']) == 0:
                return _('The problem is required')
            elif len(args['problem']) > 15:
                return _('The problem length must be less than 15 characters')
            mark.problem_pattern = args['problem']

            if len(MarkUnknown.objects.filter(
                    component=mark.component, problem_pattern=mark.problem_pattern, function=mark.function)) > 0:
                return _('Could not create a new mark since the similar mark exists already')

            if 'link' in args and len(args['link']) > 0:
                mark.link = args['link']

        if isinstance(args.get('is_modifiable'), bool) and self.user.extended.role == USER_ROLES[2][0]:
            mark.is_modifiable = args['is_modifiable']

        if self.type == 'unsafe' and args.get('verdict') in list(x[0] for x in MARK_UNSAFE) \
                or self.type == 'safe' and args.get('verdict') in list(x[0] for x in MARK_SAFE):
            mark.verdict = args['verdict']
        elif self.type != 'unknown':
            logger.error('Verdict is wrong: %s' % args.get('verdict'), stack_info=True)
            return 'Unknown error'

        if args.get('status') in list(x[0] for x in MARK_STATUS):
            mark.status = args['status']
        else:
            logger.error('Unknown mark status: %s' % args.get('status'), stack_info=True)
            return 'Unknown error'

        try:
            mark.save()
        except Exception as e:
            logger.exception('Saving mark failed: %s' % e, stack_info=True)
            return 'Unknown error'
        res = self.__update_mark(mark, args.get('tags'))
        if res is not None:
            mark.delete()
            return res

        if self.type != 'unknown':
            if self.__create_attributes(report, args.get('attrs')):
                mark.delete()
                return 'Unknown error'
        self.mark = mark
        self.changes = ConnectMarkWithReports(self.mark).changes
        UpdateTags(self.mark, changes=self.changes)
        return None

    def __change_mark(self, mark, args):
        recalc_verdicts = False

        if 'comment' not in args or len(args['comment']) == 0:
            return _('Change comment is required')
        old_tags = []
        last_v = None
        if self.type != 'unknown':
            last_v = mark.versions.order_by('-version').first()
            if last_v is None:
                logger.error('No mark versions found', stack_info=True)
                return 'Unknown error'
            old_tags = list(tag.tag for tag in last_v.tags.all())

        mark.author = self.user
        if self.type == 'unsafe' and 'compare_id' in args:
            try:
                new_func = MarkUnsafeCompare.objects.get(pk=int(args['compare_id']))
            except ObjectDoesNotExist:
                logger.exception("Get MarkUnsafeCompare(pk=%s)" % args['compare_id'], stack_info=True)
                return _('The error traces comparison function was not found')
            if mark.function != new_func:
                mark.function = new_func
                self.do_recalk = True

        if self.type == 'unknown':
            if 'function' not in args or len(args['function']) == 0:
                return _('The pattern is required')
            if args['function'] != mark.function:
                try:
                    re.search(args['function'], '')
                except Exception as e:
                    logger.exception("Wrong mark function (%s): %s" % (args['function'], e), stack_info=True)
                    return _('The pattern is wrong, please refer to documentation on the standard Python '
                             'library for processing reqular expressions')
                mark.function = args['function']
                self.do_recalk = True

            if 'problem' not in args or len(args['problem']) == 0:
                return _('The problem is required')
            elif len(args['problem']) > 15:
                return _('The problem length must be less than 15 characters')
            if args['problem'] != mark.problem_pattern:
                self.do_recalk = True
                mark.problem_pattern = args['problem']

            if len(MarkUnknown.objects.filter(Q(
                    component=mark.component, problem_pattern=mark.problem_pattern, function=mark.function
            ) & ~Q(pk=mark.pk))) > 0:
                return _('Could not change the mark since it would be similar to the existing mark')

            if 'link' in args and len(args['link']) > 0:
                mark.link = args['link']

        if (self.type == 'unsafe' and args.get('verdict') in list(x[0] for x in MARK_UNSAFE)) \
                or (self.type == 'safe' and args.get('verdict') in list(x[0] for x in MARK_SAFE)):
            if mark.verdict != args['verdict']:
                mark.verdict = args['verdict']
                recalc_verdicts = True
        elif self.type != 'unknown':
            logger.error('Verdict is wrong: %s' % args.get('verdict'), stack_info=True)
            return 'Unknown error'

        if args.get('status') in list(x[0] for x in MARK_STATUS):
            mark.status = args['status']
        else:
            logger.error('Unknown mark status: %s' % args.get('status'), stack_info=True)
            return 'Unknown error'

        if isinstance(args.get('is_modifiable'), bool) and self.user.extended.role == USER_ROLES[2][0]:
            mark.is_modifiable = args['is_modifiable']
        if 'description' in args:
            mark.description = str(args['description'])
        mark.version += 1

        res = self.__update_mark(mark, args.get('tags', []), args['comment'])
        if res is not None:
            self.mark_version.delete()
            return res

        if self.type != 'unknown':
            if self.__update_attributes(last_v, args.get('attrs')):
                self.mark_version.delete()
                return 'Unknown error'
        mark.save()
        self.mark = mark

        if self.calculate:
            if self.do_recalk:
                self.changes = ConnectMarkWithReports(self.mark).changes
            elif self.type != 'unknown':
                for mark_rep in mark.markreport_set.all():
                    self.changes[mark_rep.report] = {
                        'kind': '=',
                        'verdict1': mark_rep.report.verdict
                    }
                    if self.type == 'unsafe':
                        self.changes[mark_rep.report].update({
                            'result1': mark_rep.result,
                            'result2': mark_rep.result
                        })
                if recalc_verdicts:
                    self.changes = UpdateVerdict(mark, self.changes).changes
            UpdateTags(self.mark, changes=self.changes, old_tags=old_tags)
        return None

    def __update_mark(self, mark, tags, comment=''):
        args = {
            'mark': mark,
            'version': mark.version,
            'status': mark.status,
            'change_date': mark.change_date,
            'comment': comment,
            'author': mark.author,
            'description': mark.description,
        }
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

        if isinstance(tags, list):
            for tag in tags:
                if self.type == 'safe':
                    try:
                        safe_tag = SafeTag.objects.get(pk=tag)
                    except ObjectDoesNotExist:
                        return _('One of tags was not found')
                    MarkSafeTag.objects.get_or_create(tag=safe_tag, mark_version=self.mark_version)
                    newtag = safe_tag.parent
                    while newtag is not None:
                        MarkSafeTag.objects.get_or_create(tag=newtag, mark_version=self.mark_version)
                        newtag = newtag.parent
                elif self.type == 'unsafe':
                    try:
                        unsafe_tag = UnsafeTag.objects.get(pk=tag)
                    except ObjectDoesNotExist:
                        return _('One of tags was not found')
                    MarkUnsafeTag.objects.get_or_create(tag=unsafe_tag, mark_version=self.mark_version)
                    newtag = unsafe_tag.parent
                    while newtag is not None:
                        MarkUnsafeTag.objects.get_or_create(tag=newtag, mark_version=self.mark_version)
                        newtag = newtag.parent
        return None

    def __update_attributes(self, old_mark, attrs):
        if old_mark is None:
            logger.error('Need previous mark version', stack_info=True)
            return True
        if not isinstance(attrs, list):
            logger.error('Attributes must be a list', stack_info=True)
            return True
        for a in attrs:
            if not isinstance(a, dict) or 'attr' not in a or not isinstance(a.get('is_compare'), bool):
                logger.error('Wrong attribute found: %s' % a, stack_info=True)
                return True
        for a in old_mark.attrs.order_by('id'):
            create_args = {'attr': a.attr, 'is_compare': a.is_compare}
            for u_at in attrs:
                if u_at['attr'] == a.attr.name.name:
                    if u_at['is_compare'] != create_args['is_compare']:
                        self.do_recalk = True
                    create_args['is_compare'] = u_at['is_compare']
                    break
            else:
                logger.error('Attribute %s was not found in the new mark data' % a.attr.name.name, stack_info=True)
                return True
            self.mark_version.attrs.create(**create_args)
        return False

    def __create_attributes(self, report, attrs):
        if not isinstance(attrs, list):
            logger.error('Attributes must be a list', stack_info=True)
            return True
        for a in attrs:
            if not isinstance(a, dict) or 'attr' not in a or not isinstance(a.get('is_compare'), bool):
                logger.error('Wrong attribute found: %s' % a, stack_info=True)
                return True
        for a in report.attrs.order_by('id'):
            create_args = {'attr': a.attr}
            for u_at in attrs:
                if u_at['attr'] == a.attr.name.name:
                    create_args['is_compare'] = u_at['is_compare']
                    break
            else:
                logger.error('Attribute %s was not found in the new mark data' % a.attr.name.name, stack_info=True)
                return True
            self.mark_version.attrs.create(**create_args)
        return False


class ConnectReportWithMarks(object):
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
        UpdateTags(self.report)

    def __connect_unsafe(self):
        self.report.markreport_set.all().delete()
        marks_to_compare = []
        unsafe_attrs = []
        for r_attr in self.report.attrs.all():
            unsafe_attrs.append((r_attr.attr.name.name, r_attr.attr.value))
        for mark in MarkUnsafe.objects.all():
            mark_attrs = []
            for m_attr in mark.versions.get(version=mark.version).attrs.filter(is_compare=True):
                mark_attrs.append((m_attr.attr.name.name, m_attr.attr.value))
            if all(x in mark_attrs for x in [x for x in unsafe_attrs if x[0] in [y[0] for y in mark_attrs]]):
                marks_to_compare.append(mark)

        if len(marks_to_compare) == 0:
            return

        afc = ArchiveFileContent(self.report.archive, file_name=self.report.error_trace)
        if afc.error is not None:
            logger.error("Can't get error trace for unsafe '%s': %s" % (self.report.pk, afc.error), stack_info=True)
            return
        for mark in marks_to_compare:
            compare_failed = False
            with mark.error_trace.file as fp:
                compare = CompareTrace(mark.function.name, fp.read().decode('utf8'), afc.content)
            if compare.error is not None:
                logger.error("Error traces comparison failed: %s" % compare.error, stack_info=True)
                compare_failed = True
            if compare.result > 0 or compare_failed:
                MarkUnsafeReport.objects.create(
                    mark=mark, report=self.report, result=compare.result, broken=compare_failed, error=compare.error
                )

    def __connect_safe(self):
        self.report.markreport_set.all().delete()
        safe_attrs = []
        for r_attr in self.report.attrs.all():
            safe_attrs.append((r_attr.attr.name.name, r_attr.attr.value))
        for mark in MarkSafe.objects.all():
            mark_attrs = []
            for m_attr in mark.versions.get(version=mark.version).attrs.filter(is_compare=True):
                mark_attrs.append((m_attr.attr.name.name, m_attr.attr.value))
            if all(x in mark_attrs for x in [x for x in safe_attrs if x[0] in [y[0] for y in mark_attrs]]):
                MarkSafeReport.objects.create(mark=mark, report=self.report)

    def __connect_unknown(self):
        self.report.markreport_set.all().delete()
        changes = {self.report: {}}

        afc = ArchiveFileContent(self.report.archive, file_name=self.report.problem_description)
        if afc.error is not None:
            logger.error("Can't get problem desc for unknown '%s': %s" % (self.report.pk, afc.error), stack_info=True)
            return
        for mark in MarkUnknown.objects.filter(component=self.report.component):
            problem = MatchUnknown(afc.content, mark.function, mark.problem_pattern).problem
            if problem is None:
                continue
            elif len(problem) > 15:
                problem = 'Too long!'
                logger.error(
                    "Generated problem '%s' for mark %s is too long" % (problem, mark.identifier), stack_info=True
                )
            MarkUnknownReport.objects.create(
                mark=mark, report=self.report, problem=UnknownProblem.objects.get_or_create(name=problem)[0]
            )
            if self.report not in changes:
                changes[self.report]['kind'] = '+'
        if self.update_cache:
            update_unknowns_cache(changes)


class ConnectMarkWithReports(object):

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
        mark_attrs = []
        for attr in self.mark.versions.get(version=self.mark.version).attrs.filter(is_compare=True):
            mark_attrs.append((attr.attr.name.name, attr.attr.value))

        for mark_unsafe in self.mark.markreport_set.all():
            self.changes[mark_unsafe.report] = {
                'kind': '-', 'result1': mark_unsafe.result, 'verdict1': mark_unsafe.report.verdict,
            }
        self.mark.markreport_set.all().delete()
        with self.mark.error_trace.file as fp:
            pattern_error_trace = fp.read().decode('utf8')
        for unsafe in ReportUnsafe.objects.all():
            unsafe_attrs = []
            for r_attr in unsafe.attrs.filter(attr__name__name__in=list(x[0] for x in mark_attrs)):
                unsafe_attrs.append((r_attr.attr.name.name, r_attr.attr.value))
            if any(x not in mark_attrs for x in unsafe_attrs):
                continue
            compare_failed = False
            afc = ArchiveFileContent(unsafe.archive, file_name=unsafe.error_trace)
            if afc.error is not None:
                logger.error("Can't get error trace for unsafe '%s': %s" % (unsafe.pk, afc.error), stack_info=True)
                return
            compare = CompareTrace(self.mark.function.name, pattern_error_trace, afc.content)
            if compare.error is not None:
                logger.error("Error traces comparison failed: %s" % compare.error)
                compare_failed = True
                if self.mark.prime == unsafe:
                    self.mark.prime = None
                    self.mark.save()
            if compare.result > 0 or compare_failed:
                MarkUnsafeReport.objects.create(
                    mark=self.mark, report=unsafe, result=compare.result, broken=compare_failed, error=compare.error
                )
                if unsafe in self.changes:
                    self.changes[unsafe]['kind'] = '='
                    self.changes[unsafe]['result2'] = compare.result
                else:
                    self.changes[unsafe] = {
                        'kind': '+', 'result2': compare.result, 'verdict1': unsafe.verdict
                    }

    def __connect_safe_mark(self):
        mark_attrs = []
        for attr in self.mark.versions.get(version=self.mark.version).attrs.filter(is_compare=True):
            mark_attrs.append((attr.attr.name.name, attr.attr.value))

        for mark_safe in self.mark.markreport_set.all():
            self.changes[mark_safe.report] = {'kind': '=', 'verdict1': mark_safe.report.verdict}
        self.mark.markreport_set.all().delete()
        for safe in ReportSafe.objects.all():
            safe_attrs = []
            for r_attr in safe.attrs.filter(attr__name__name__in=list(x[0] for x in mark_attrs)):
                safe_attrs.append((r_attr.attr.name.name, r_attr.attr.value))
            if any(x not in mark_attrs for x in safe_attrs):
                continue
            MarkSafeReport.objects.create(mark=self.mark, report=safe)
            if safe in self.changes:
                self.changes[safe]['kind'] = '='
            else:
                self.changes[safe] = {'kind': '+', 'verdict1': safe.verdict}

    def __connect_unknown_mark(self):
        for mark_unknown in self.mark.markreport_set.all():
            self.changes[mark_unknown.report] = {'kind': '-'}
        self.mark.markreport_set.all().delete()
        for unknown in ReportUnknown.objects.filter(component=self.mark.component):
            afc = ArchiveFileContent(unknown.archive, file_name=unknown.problem_description)
            if afc.error is not None:
                logger.error("Can't get problem desc for unknown '%s': %s" % (unknown.pk, afc.error), stack_info=True)
                return
            problem = MatchUnknown(afc.content, self.mark.function, self.mark.problem_pattern).problem
            if problem is None:
                continue
            elif len(problem) > 15:
                problem = 'Too long!'
                logger.error("Problem '%s' for mark %s is too long" % (problem, self.mark.identifier), stack_info=True)
            MarkUnknownReport.objects.create(
                mark=self.mark, report=unknown, problem=UnknownProblem.objects.get_or_create(name=problem)[0]
            )
            if unknown in self.changes:
                self.changes[unknown]['kind'] = '='
            else:
                self.changes[unknown] = {'kind': '+'}
        update_unknowns_cache(self.changes)


class UpdateVerdict(object):

    def __init__(self, inst, changes=None):
        self.changes = changes
        if isinstance(inst, MarkUnsafe):
            self.__update_unsafes(inst)
        elif isinstance(inst, MarkSafe):
            self.__update_safes(inst)
        elif isinstance(inst, (ReportUnsafe, ReportSafe)):
            self.__update_report(inst)

    def __update_unsafes(self, mark):
        if not isinstance(self.changes, dict):
            return
        for mark_report in mark.markreport_set.all():
            unsafe = mark_report.report
            if unsafe not in self.changes:
                continue
            new_verdict = self.__calc_verdict(unsafe)
            if new_verdict != unsafe.verdict:
                self.__new_unsafe_verdict(unsafe, new_verdict)
            self.changes[unsafe]['verdict2'] = new_verdict

        # Updating unsafes that have lost changed mark
        for unsafe in self.changes:
            if self.changes[unsafe]['kind'] == '-':
                self.changes[unsafe]['verdict2'] = unsafe.verdict
                new_verdict = '5'
                if unsafe.verdict == '4':
                    new_verdict = self.__calc_verdict(unsafe)
                elif len(unsafe.markreport_set.all()) > 0:
                    continue
                if new_verdict != unsafe.verdict:
                    self.__new_unsafe_verdict(unsafe, new_verdict)
                    self.changes[unsafe]['verdict2'] = new_verdict

    def __update_safes(self, mark):
        if not isinstance(self.changes, dict):
            return
        for mark_report in mark.markreport_set.all():
            safe = mark_report.report
            if safe not in self.changes:
                continue
            new_verdict = self.__calc_verdict(safe)
            if new_verdict != safe.verdict:
                self.__new_safe_verdict(safe, new_verdict)
            self.changes[safe]['verdict2'] = new_verdict

        # Updating safes that have lost changed mark
        for safe in self.changes:
            if self.changes[safe]['kind'] == '-':
                self.changes[safe]['verdict2'] = safe.verdict
                new_verdict = '4'
                if safe.verdict == '3':
                    new_verdict = self.__calc_verdict(safe)
                elif len(safe.markreport_set.all()) > 0:
                    continue
                if new_verdict != safe.verdict:
                    self.__new_safe_verdict(safe, new_verdict)
                    self.changes[safe]['verdict2'] = new_verdict

    def __update_report(self, report):
        new_verdict = self.__calc_verdict(report)
        if new_verdict != report.verdict:
            if isinstance(report, ReportUnsafe):
                self.__new_unsafe_verdict(report, new_verdict)
            elif isinstance(report, ReportSafe):
                self.__new_safe_verdict(report, new_verdict)

    def __new_unsafe_verdict(self, unsafe, new):
        self.ccc = 0
        try:
            parent = ReportComponent.objects.get(pk=unsafe.parent_id)
        except ObjectDoesNotExist:
            parent = None
        while parent is not None:
            try:
                verdict = parent.verdict
            except ObjectDoesNotExist:
                verdict = Verdict.objects.create(report=parent)
            if unsafe.verdict == '0' and verdict.unsafe_unknown > 0:
                verdict.unsafe_unknown -= 1
            elif unsafe.verdict == '1' and verdict.unsafe_bug > 0:
                verdict.unsafe_bug -= 1
            elif unsafe.verdict == '2' and verdict.unsafe_target_bug > 0:
                verdict.unsafe_target_bug -= 1
            elif unsafe.verdict == '3' and verdict.unsafe_false_positive > 0:
                verdict.unsafe_false_positive -= 1
            elif unsafe.verdict == '4' and verdict.unsafe_inconclusive > 0:
                verdict.unsafe_inconclusive -= 1
            elif unsafe.verdict == '5' and verdict.unsafe_unassociated > 0:
                verdict.unsafe_unassociated -= 1
            if new == '0':
                verdict.unsafe_unknown += 1
            elif new == '1':
                verdict.unsafe_bug += 1
            elif new == '2':
                verdict.unsafe_target_bug += 1
            elif new == '3':
                verdict.unsafe_false_positive += 1
            elif new == '4':
                verdict.unsafe_inconclusive += 1
            elif new == '5':
                verdict.unsafe_unassociated += 1
            verdict.save()
            try:
                parent = ReportComponent.objects.get(pk=parent.parent_id)
            except ObjectDoesNotExist:
                parent = None
        unsafe.verdict = new
        unsafe.save()

    def __new_safe_verdict(self, safe, new):
        self.ccc = 0
        try:
            parent = ReportComponent.objects.get(pk=safe.parent_id)
        except ObjectDoesNotExist:
            parent = None
        while parent is not None:
            try:
                verdict = parent.verdict
            except ObjectDoesNotExist:
                verdict = Verdict.objects.create(report=parent)
            if safe.verdict == '0' and verdict.safe_unknown > 0:
                verdict.safe_unknown -= 1
            elif safe.verdict == '1' and verdict.safe_incorrect_proof > 0:
                verdict.safe_incorrect_proof -= 1
            elif safe.verdict == '2' and verdict.safe_missed_bug > 0:
                verdict.safe_missed_bug -= 1
            elif safe.verdict == '3' and verdict.safe_inconclusive > 0:
                verdict.safe_inconclusive -= 1
            elif safe.verdict == '4' and verdict.safe_unassociated > 0:
                verdict.safe_unassociated -= 1
            if new == '0':
                verdict.safe_unknown += 1
            elif new == '1':
                verdict.safe_incorrect_proof += 1
            elif new == '2':
                verdict.safe_missed_bug += 1
            elif new == '3':
                verdict.safe_inconclusive += 1
            elif new == '4':
                verdict.safe_unassociated += 1
            verdict.save()
            try:
                parent = ReportComponent.objects.get(pk=parent.parent_id)
            except ObjectDoesNotExist:
                parent = None
        safe.verdict = new
        safe.save()

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
        for mr in report.markreport_set.all():
            if new_verdict is not None and new_verdict != mr.mark.verdict:
                new_verdict = incompatable
                break
            else:
                new_verdict = mr.mark.verdict
        if new_verdict is None:
            new_verdict = unmarked
        return new_verdict


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
        if not self.mark.is_modifiable:
            return False
        if self.user.extended.role == USER_ROLES[3][0]:
            return True
        if isinstance(self.mark, MarkUnsafe):
            first_vers = self.mark.versions.order_by('version')[0]
        elif isinstance(self.mark, MarkSafe):
            first_vers = self.mark.versions.order_by('version')[0]
        elif isinstance(self.mark, MarkUnknown):
            first_vers = self.mark.versions.order_by('version')[0]
        else:
            return False
        if first_vers.author == self.user:
            return True
        if self.mark.job is not None:
            first_v = self.mark.job.versions.order_by('version')[0]
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
        if self.user.extended.role in [USER_ROLES[2][0], USER_ROLES[3][0]]:
            return True
        if isinstance(self.report, (ReportUnsafe, ReportSafe, ReportUnknown)):
            first_v = self.report.root.job.versions.order_by('version')[0]
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
        return False

    def can_delete(self):
        if not isinstance(self.user, User):
            return False
        if self.user.extended.role == USER_ROLES[2][0]:
            return True
        if not self.mark.is_modifiable:
            return False
        if self.user.extended.role == USER_ROLES[3][0]:
            return True
        if self.mark.versions.order_by('version')[0].author == self.user:
            return True
        return False


class TagsInfo(object):

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
            versions = self.mark.versions.order_by('-version')
            for tag in versions[0].tags.order_by('tag__tag'):
                self.tags_old.append(tag.tag.tag)
        elif isinstance(self.mark, (MarkUnsafeHistory, MarkSafeHistory)):
            for tag in self.mark.tags.order_by('tag__tag'):
                self.tags_old.append(tag.tag.tag)
        if self.type == 'unsafe':
            for tag in UnsafeTag.objects.all():
                if tag.tag not in self.tags_old:
                    self.tags_available.append(tag.tag)
        else:
            for tag in SafeTag.objects.all():
                if tag.tag not in self.tags_old:
                    self.tags_available.append(tag.tag)


class UpdateTags(object):

    def __init__(self, inst, changes=None, old_tags=None):
        self.changes = changes
        self.old_tags = old_tags
        if isinstance(inst, (MarkUnsafe, MarkSafe)):
            self.__update_tags(inst)
        elif isinstance(inst, (ReportSafe, ReportUnsafe)):
            self.__update_tags_for_report(inst)

    def __update_tags_for_report(self, report):
        for mark_rep in report.markreport_set.all():
            tag_data = []
            for mtag in mark_rep.mark.versions.order_by('-version').first().tags.all():
                rtag, created = mark_rep.report.tags.get_or_create(tag=mtag.tag)
                if created:
                    tag_data.append({
                        'kind': '+',
                        'tag': rtag.tag
                    })
                rtag.number += 1
                rtag.save()
            if isinstance(report, ReportUnsafe):
                self.__update_unsafe_parents(mark_rep.report, tag_data)
            else:
                self.__update_safe_parents(mark_rep.report, tag_data)

    def __update_tags(self, mark):
        if not isinstance(self.changes, dict):
            return
        mark_last_v = mark.versions.order_by('-version').first()
        for report in self.changes:
            tag_data = []
            if self.changes[report]['kind'] == '+':
                for mtag in mark_last_v.tags.all():
                    rtag, created = report.tags.get_or_create(tag=mtag.tag)
                    if created:
                        tag_data.append({'kind': '+', 'tag': rtag.tag})
                    rtag.number += 1
                    rtag.save()
            elif self.changes[report]['kind'] == '-':
                if isinstance(self.old_tags, list):
                    tag_list = self.old_tags
                else:
                    tag_list = []
                    for mtag in mark_last_v.tags.all():
                        tag_list.append(mtag.tag)
                for tag in tag_list:
                    try:
                        rtag = report.tags.get(tag=tag)
                        if rtag.number > 0:
                            rtag.number -= 1
                            rtag.save()
                            if rtag.number == 0:
                                rtag.delete()
                                tag_data.append({'kind': '-', 'tag': tag})
                    except ObjectDoesNotExist:
                        pass
            elif self.changes[report]['kind'] == '=':
                if not isinstance(self.old_tags, list):
                    continue
                for tag in self.old_tags:
                    try:
                        rtag = report.tags.get(tag=tag)
                        if rtag.number > 0:
                            rtag.number -= 1
                            rtag.save()
                            if rtag.number == 0:
                                rtag.delete()
                                tag_data.append({'kind': '-', 'tag': tag})
                    except ObjectDoesNotExist:
                        pass
                for mtag in mark_last_v.tags.all():
                    rtag, created = report.tags.get_or_create(
                        tag=mtag.tag)
                    if created:
                        tag_data.append({
                            'kind': '+',
                            'tag': rtag.tag
                        })
                    rtag.number += 1
                    rtag.save()
            else:
                continue
            if isinstance(report, ReportUnsafe):
                self.__update_unsafe_parents(report, tag_data)
            else:
                self.__update_safe_parents(report, tag_data)

    def __update_unsafe_parents(self, unsafe, tag_data):
        self.ccc = 0
        try:
            parent = ReportComponent.objects.get(pk=unsafe.parent_id)
        except ObjectDoesNotExist:
            parent = None
        while parent is not None:
            for td in tag_data:
                if td['kind'] == '-':
                    try:
                        reptag = parent.unsafe_tags.get(tag=td['tag'])
                        if reptag.number > 0:
                            reptag.number -= 1
                            reptag.save()
                            if reptag.number == 0:
                                reptag.delete()
                    except ObjectDoesNotExist:
                        pass
                elif td['kind'] == '+':
                    reptag = parent.unsafe_tags.get_or_create(tag=td['tag'])[0]
                    reptag.number += 1
                    reptag.save()
            try:
                parent = ReportComponent.objects.get(pk=parent.parent_id)
            except ObjectDoesNotExist:
                parent = None

    def __update_safe_parents(self, safe, tag_data):
        self.ccc = 1
        try:
            parent = ReportComponent.objects.get(pk=safe.parent_id)
        except ObjectDoesNotExist:
            parent = None
        while parent is not None:
            for td in tag_data:
                if td['kind'] == '-':
                    try:
                        reptag = parent.safe_tags.get(tag=td['tag'])
                        if reptag.number > 0:
                            reptag.number -= 1
                            reptag.save()
                            if reptag.number == 0:
                                reptag.delete()
                    except ObjectDoesNotExist:
                        pass
                elif td['kind'] == '+':
                    reptag = parent.safe_tags.get_or_create(tag=td['tag'])[0]
                    reptag.number += 1
                    reptag.save()
            try:
                parent = ReportComponent.objects.get(pk=parent.parent_id)
            except ObjectDoesNotExist:
                parent = None


class DeleteMark(object):

    def __init__(self, mark):
        self.mark = mark
        self.__delete()

    def __delete(self):
        changes = {}
        if not isinstance(self.mark, (MarkSafe, MarkUnsafe, MarkUnknown)):
            return
        for mark_report in self.mark.markreport_set.all():
            changes[mark_report.report] = {'kind': '-'}
        self.mark.markreport_set.all().delete()
        if isinstance(self.mark, MarkUnknown):
            update_unknowns_cache(changes)
        else:
            for report in changes:
                UpdateVerdict(report)
            UpdateTags(self.mark, changes=changes)
        self.mark.delete()


class MatchUnknown(object):
    def __init__(self, description, function, pattern):
        self.description = str(description)
        self.function = str(function)
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


def update_unknowns_cache(changes):
    from reports.models import ReportComponentLeaf
    reports_to_recalc = []
    for leaf in ReportComponentLeaf.objects.filter(unknown__in=list(changes)):
        if leaf.report not in reports_to_recalc:
            reports_to_recalc.append(leaf.report)
    for report in reports_to_recalc:
        data = {}
        for leaf in report.leaves.filter(~Q(unknown=None)):
            if leaf.unknown.component not in data:
                data[leaf.unknown.component] = {'unmarked': 0}
            mark_reports = leaf.unknown.markreport_set.all()
            if len(mark_reports) > 0:
                for mr in mark_reports:
                    if mr.problem not in data[leaf.unknown.component]:
                        data[leaf.unknown.component][mr.problem] = 0
                    data[leaf.unknown.component][mr.problem] += 1
            else:
                data[leaf.unknown.component]['unmarked'] += 1
        simplified_data = []
        for c in data:
            for problem in data[c]:
                if data[c][problem] > 0:
                    simplified_data.append({
                        'number': data[c][problem],
                        'component': c,
                        'problem': problem if isinstance(problem, UnknownProblem) else None
                    })
        cache_ids = []
        for d in simplified_data:
            cachedata = ComponentMarkUnknownProblem.objects.get_or_create(
                report=report, component=d['component'], problem=d['problem']
            )[0]
            cachedata.number = d['number']
            cachedata.save()
            cache_ids.append(cachedata.pk)
        ComponentMarkUnknownProblem.objects.filter(Q(report=report) & ~Q(id__in=cache_ids)).delete()
