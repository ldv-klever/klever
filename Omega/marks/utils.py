import re
import json
import tarfile
import hashlib
from io import BytesIO
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.utils.translation import ugettext_lazy as _
from django.utils.timezone import now
from Omega.vars import USER_ROLES, JOB_ROLES
from Omega.utils import print_err
from marks.models import *
from reports.models import ReportComponent, Attr, AttrName
from marks.ConvertTrace import ConvertTrace
from marks.CompareTrace import CompareTrace


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
        :param mark_type: 'safe' or 'unsafe'
        :param args: dictionary with keys:
            'status': see MARK_STATUS from Omega.vars, default - '0'.
            'verdict': see MARK_UNSAFE/MARK_SAFE from Omega.vars, default - '0'
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
            self.error = "Wrong parameters"
        elif self.type == 'safe' and isinstance(inst, ReportSafe) or \
                self.type == 'unsafe' and isinstance(inst, ReportUnsafe) or \
                self.type == 'unknown' and isinstance(inst, ReportUnknown):
            self.error = self.__create_mark(inst, args)
        elif self.type == 'unsafe' and isinstance(inst, MarkUnsafe) or \
                self.type == 'safe' and isinstance(inst, MarkSafe) or \
                self.type == 'unknown' and isinstance(inst, MarkUnknown):
            self.error = self.__change_mark(inst, args)
        else:
            self.error = "Wrong parameters"
            return

    def __create_mark(self, report, args):
        if self.type == 'unsafe':
            mark = MarkUnsafe()
        elif self.type == 'safe':
            mark = MarkSafe()
        else:
            mark = MarkUnknown()
        mark.author = self.user

        if self.type == 'unsafe':
            if 'convert_id' in args:
                try:
                    func = MarkUnsafeConvert.objects.get(
                        pk=int(args['convert_id']))
                    converted = ConvertTrace(
                        func.name, report.error_trace.decode('utf8'))
                    if converted.error is not None:
                        return converted.error
                    mark.error_trace = converted.pattern_error_trace\
                        .encode('utf8')
                except ObjectDoesNotExist:
                    return "Convertion function was not found"

            if 'compare_id' in args:
                try:
                    mark.function = MarkUnsafeCompare.objects.get(
                        pk=int(args['compare_id']))
                except ObjectDoesNotExist:
                    return "Comparison function was not found"
        elif self.type == 'unknown':
            if 'function' in args and len(args['function']) > 0:
                mark.function = args['function']
            else:
                return "Function is required"
            if 'problem' in args and len(args['problem']) > 0:
                mark.problem_pattern = args['problem']
            else:
                return "Problem name pattern is required"
            if 'link' in args and len(args['link']) > 0:
                mark.link = args['link']
            mark.component = report.component

        mark.format = report.root.job.format
        mark.type = report.root.job.type
        mark.job = report.root.job

        time_encoded = now().strftime("%Y%m%d%H%M%S%f%z").encode('utf8')
        mark.identifier = hashlib.md5(time_encoded).hexdigest()

        if 'is_modifiable' in args and isinstance(args['is_modifiable'], bool) \
                and self.user.extended.role == USER_ROLES[2][0]:
            mark.is_modifiable = args['is_modifiable']

        if 'verdict' in args:
            if self.type == 'unsafe' and args['verdict'] in list(x[0] for x in MARK_UNSAFE):
                mark.verdict = args['verdict']
            elif args['verdict'] in list(x[0] for x in MARK_SAFE):
                mark.verdict = args['verdict']

        if 'status' in args and \
                args['status'] in list(x[0] for x in MARK_STATUS):
            mark.status = args['status']
        tags = []
        if 'tags' in args:
            tags = args['tags']
        if 'description' in args:
            mark.description = args['description']

        try:
            mark.save()
        except Exception as e:
            return e

        if self.type != 'unknown':
            for attr in report.attrorder.order_by('id'):
                if self.type == 'safe':
                    SafeMarkAttrOrder.objects.create(
                        name=attr.name, mark_id=mark.pk)
                else:
                    UnsafeMarkAttrOrder.objects.create(
                        name=attr.name, mark_id=mark.pk)

        self.__update_mark(mark, tags=tags)
        if 'attrs' in args and self.type != 'unknown':
            res = self.__create_attributes(report, args['attrs'])
            if res is not None:
                mark.delete()
                return res
        self.mark = mark
        if self.calculate:
            self.changes = ConnectMarkWithReports(self.mark).changes
            UpdateTags(self.mark, changes=self.changes)
        return None

    def __change_mark(self, mark, args):
        recalc_verdicts = False

        if 'comment' not in args or len(args['comment']) == 0:
            return 'Change comment is required'
        old_tags = []
        last_v = None
        if self.type != 'unknown':
            last_v = mark.versions.order_by('-version')[0]
            for tag in last_v.tags.all():
                old_tags.append(tag.tag)
        mark.author = self.user
        if self.type == 'unsafe' and 'compare_id' in args:
            try:
                mark.function = MarkUnsafeCompare.objects.get(
                    pk=int(args['compare_id']))
                if mark.function != last_v.function:
                    self.do_recalk = True
            except ObjectDoesNotExist:
                return "Comparison function was not found"

        if self.type == 'unknown':
            if 'function' in args and len(args['function']) > 0:
                if args['function'] != mark.function:
                    self.do_recalk = True
                    mark.function = args['function']
            if 'problem' in args and 0 < len(args['problem']) < 15:
                if args['problem'] != mark.problem_pattern:
                    self.do_recalk = True
                    mark.problem_pattern = args['problem']
            if 'link' in args and len(args['link']) > 0:
                mark.link = args['link']

        if 'verdict' in args:
            if (self.type == 'unsafe' and
                    args['verdict'] in list(x[0] for x in MARK_UNSAFE)) or \
                    (args['verdict'] in list(x[0] for x in MARK_SAFE)):
                if mark.verdict != args['verdict']:
                    recalc_verdicts = True
                mark.verdict = args['verdict']

        if 'status' in args and \
                args['status'] in list(x[0] for x in MARK_STATUS):
            mark.status = args['status']

        if 'is_modifiable' in args and isinstance(args['is_modifiable'], bool) \
                and self.user.extended.role == USER_ROLES[2][0]:
            mark.is_modifiable = args['is_modifiable']
        if 'description' in args:
            mark.description = args['description']

        tags = []
        if 'tags' in args:
            tags = args['tags']

        mark.version += 1
        mark.save()
        self.__update_mark(mark, args['comment'], tags=tags)
        if 'attrs' in args and last_v is not None:
            res = self.__update_attributes(args['attrs'], last_v)
            if res is not None:
                mark.version -= 1
                mark.save()
                self.mark_version.delete()
                return res

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

    def __update_mark(self, mark, comment='', tags=None):
        if self.type == 'unsafe':
            new_version = MarkUnsafeHistory()
        elif self.type == 'safe':
            new_version = MarkSafeHistory()
        else:
            new_version = MarkUnknownHistory()

        new_version.mark = mark
        if self.type == 'unsafe':
            new_version.function = mark.function
        elif self.type == 'unknown':
            new_version.link = mark.link
            new_version.problem_pattern = mark.problem_pattern
            new_version.function = mark.function
        if self.type != 'unknown':
            new_version.verdict = mark.verdict
        new_version.version = mark.version
        new_version.status = mark.status
        new_version.change_date = mark.change_date
        new_version.comment = comment
        new_version.author = mark.author
        new_version.description = mark.description
        new_version.save()
        self.mark_version = new_version
        if isinstance(tags, list):
            for tag in tags:
                if self.type == 'safe':
                    safetag = SafeTag.objects.get_or_create(tag=tag)[0]
                    MarkSafeTag.objects.create(tag=safetag,
                                               mark_version=new_version)
                elif self.type == 'unsafe':
                    unsafetag = UnsafeTag.objects.get_or_create(tag=tag)[0]
                    MarkUnsafeTag.objects.create(tag=unsafetag,
                                                 mark_version=new_version)

    def __update_attributes(self, attrs, old_mark):
        if not isinstance(attrs, list):
            return 'Wrong attributes'
        for a in attrs:
            if not isinstance(a, dict) or \
                    any(x not in a for x in ['attr', 'is_compare']):
                return 'Wrong args'
        for a in old_mark.attrs.all():
            create_args = {
                'attr': a.attr,
                'is_compare': a.is_compare
            }
            for u_at in attrs:
                if u_at['attr'] == a.attr.name.name:
                    if u_at['is_compare'] != create_args['is_compare']:
                        self.do_recalk = True
                    create_args['is_compare'] = u_at['is_compare']
                    break
            self.mark_version.attrs.get_or_create(**create_args)
        return None

    def __create_attributes(self, report, attrs):
        if not isinstance(attrs, list):
            return 'Wrong attributes'
        for a in attrs:
            if not isinstance(a, dict) or \
                    any(x not in a for x in ['attr', 'is_compare']):
                return 'Wrong args'
        for a in report.attr.all():
            create_args = {'attr': a}
            for u_at in attrs:
                if u_at['attr'] == a.name.name:
                    create_args['is_compare'] = u_at['is_compare']
                    break
            self.mark_version.attrs.get_or_create(**create_args)
        return None


class ConnectReportWithMarks(object):
    def __init__(self, report):
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
        for mark in MarkUnsafe.objects.filter(type=self.report.root.job.type):
            for attr in mark.versions.get(version=mark.version).attrs.all():
                if attr.is_compare:
                    try:
                        if self.report.attr.get(name__name=attr.attr.name.name)\
                                .value != attr.attr.value:
                            break
                    except ObjectDoesNotExist:
                        pass
            else:
                compare_failed = False
                compare = CompareTrace(
                    mark.function.name,
                    mark.error_trace.decode('utf8'),
                    self.report.error_trace.decode('utf8'))
                if compare.error is not None:
                    print_err(compare.error)
                    compare_failed = True
                if compare.result > 0 or compare_failed:
                    MarkUnsafeReport.objects.create(
                        mark=mark, report=self.report, result=compare.result,
                        broken=compare_failed)

    def __connect_safe(self):
        self.report.markreport_set.all().delete()
        for mark in MarkSafe.objects.filter(type=self.report.root.job.type):
            for attr in mark.versions.get(version=mark.version).attrs.all():
                if attr.is_compare:
                    try:
                        if self.report.attr.get(name__name=attr.attr.name.name)\
                                .value != attr.attr.value:
                            break
                    except ObjectDoesNotExist:
                        pass
            else:
                MarkSafeReport.objects.create(mark=mark, report=self.report)

    def __connect_unknown(self):
        self.report.markreport_set.all().delete()
        changes = {}
        for mark in MarkUnknown.objects.filter(
                type=self.report.root.job.type,
                component=self.report.component):
            problem = MatchUnknown(
                self.report.problem_description.decode('utf8'),
                mark.function,
                mark.problem_pattern
            ).problem
            if problem is None:
                continue
            elif len(problem) > 15:
                problem = 'Too long!'
                print_err("Generated problem '%s' for mark %s is too long" % (problem, mark.identifier))
            problem = UnknownProblem.objects.get_or_create(name=problem)[0]
            MarkUnknownReport.objects.create(
                mark=mark, report=self.report, problem=problem)
            if self.report not in changes:
                changes[self.report] = {'kind': '+'}
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

    def __connect_unsafe_mark(self):
        last_version = self.mark.versions.get(version=self.mark.version)
        for mark_unsafe in self.mark.markreport_set.all():
            self.changes[mark_unsafe.report] = {
                'kind': '-',
                'result1': mark_unsafe.result,
                'verdict1': mark_unsafe.report.verdict,
            }
        self.mark.markreport_set.all().delete()
        for unsafe in ReportUnsafe.objects.filter(
                root__job__type=self.mark.type):
            for attr in last_version.attrs.all():
                if attr.is_compare:
                    try:
                        if unsafe.attr.get(name__name=attr.attr.name.name)\
                                .value != attr.attr.value:
                            break
                    except ObjectDoesNotExist:
                        pass
            else:
                compare_failed = False
                compare = CompareTrace(
                    self.mark.function.name,
                    self.mark.error_trace.decode('utf8'),
                    unsafe.error_trace.decode('utf8'))
                if compare.error is not None:
                    print_err(compare.error)
                    compare_failed = True
                if compare.result > 0 or compare_failed:
                    MarkUnsafeReport.objects.create(
                        mark=self.mark, report=unsafe, result=compare.result,
                        broken=compare_failed)
                    if unsafe in self.changes:
                        self.changes[unsafe]['kind'] = '='
                        self.changes[unsafe]['result2'] = compare.result
                    else:
                        self.changes[unsafe] = {
                            'kind': '+',
                            'result2': compare.result,
                            'verdict1': unsafe.verdict
                        }

    def __connect_safe_mark(self):
        last_version = self.mark.versions.get(version=self.mark.version)
        for mark_safe in self.mark.markreport_set.all():
            self.changes[mark_safe.report] = {
                'kind': '=',
                'verdict1': mark_safe.report.verdict,
            }
        self.mark.markreport_set.all().delete()
        for safe in ReportSafe.objects.filter(root__job__type=self.mark.type):
            for attr in last_version.attrs.all():
                if attr.is_compare:
                    try:
                        if safe.attr.get(name__name=attr.attr.name.name)\
                                .value != attr.attr.value:
                            break
                    except ObjectDoesNotExist:
                        pass
            else:
                MarkSafeReport.objects.create(mark=self.mark, report=safe)
                if safe in self.changes:
                    self.changes[safe]['kind'] = '='
                else:
                    self.changes[safe] = {'kind': '+', 'verdict1': safe.verdict}

    def __connect_unknown_mark(self):
        for mark_unknown in self.mark.markreport_set.all():
            self.changes[mark_unknown.report] = {'kind': '-'}
        self.mark.markreport_set.all().delete()
        for unknown in ReportUnknown.objects.filter(
                component=self.mark.component):
            problem = MatchUnknown(
                unknown.problem_description.decode('utf8'),
                self.mark.function,
                self.mark.problem_pattern
            ).problem
            if problem is None:
                continue
            elif len(problem) > 15:
                problem = 'Too long!'
                print_err("Generated problem '%s' for mark %s is too long" % (problem, self.mark.identifier))
            problem = UnknownProblem.objects.get_or_create(name=problem)[0]
            MarkUnknownReport.objects.create(
                mark=self.mark, report=unknown, problem=problem)
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
                # Case when upload report havn't saved the verdicts (total=0)
                # (Error in upload report)
                return
            if unsafe.verdict == '0' and verdict.unsafe_unknown > 0:
                verdict.unsafe_unknown -= 1
            elif unsafe.verdict == '1' and verdict.unsafe_bug > 0:
                verdict.unsafe_bug -= 1
            elif unsafe.verdict == '2' and verdict.unsafe_target_bug > 0:
                verdict.unsafe_target_bug -= 1
            elif unsafe.verdict == '3' and \
                    verdict.unsafe_false_positive > 0:
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
                return
            if safe.verdict == '0' and verdict.safe_unknown > 0:
                verdict.safe_unknown -= 1
            elif safe.verdict == '1' and verdict.safe_incorrect_proof > 0:
                verdict.safe_incorrect_proof -= 1
            elif safe.verdict == '2' and verdict.safe_missed_bug > 0:
                verdict.safe_missed_bug -= 1
            elif safe.verdict == '3' and \
                    verdict.safe_inconclusive > 0:
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


class CreateMarkTar(object):

    def __init__(self, mark):
        self.mark = mark
        if isinstance(self.mark, MarkUnsafe):
            self.type = 'unsafe'
        elif isinstance(self.mark, MarkSafe):
            self.type = 'safe'
        elif isinstance(self.mark, MarkUnknown):
            self.type = 'unknown'
        else:
            return
        self.marktar_name = ''
        self.memory = BytesIO()
        self.__full_tar()

    def __full_tar(self):

        def write_file_str(jobtar, file_name, file_content):
            file_content = file_content.encode('utf-8')
            t = tarfile.TarInfo(file_name)
            t.size = len(file_content)
            jobtar.addfile(t, BytesIO(file_content))

        self.marktar_name = 'Mark-%s-%s.tar.gz' % (self.type, self.mark.identifier[:10])
        marktar_obj = tarfile.open(fileobj=self.memory, mode='w:gz')
        for markversion in self.mark.versions.all():
            version_data = {
                'status': markversion.status,
                'comment': markversion.comment,
                'description': markversion.description
            }
            if self.type == 'unknown':
                version_data['function'] = markversion.function
                version_data['problem'] = markversion.problem_pattern
                if markversion.link is not None:
                    version_data['link'] = markversion.link
            else:
                version_data['attrs'] = []
                version_data['tags'] = []
                version_data['verdict'] = markversion.verdict
                if self.type == 'unsafe':
                    version_data['function'] = markversion.function.name
                for tag in markversion.tags.all():
                    version_data['tags'].append(tag.tag.tag)
                for attr in markversion.attrs.all():
                    version_data['attrs'].append({
                        'attr': attr.attr.name.name,
                        'value': attr.attr.value,
                        'is_compare': attr.is_compare
                    })
            write_file_str(marktar_obj, 'version-%s' % markversion.version,
                           json.dumps(version_data))
        common_data = {
            'is_modifiable': self.mark.is_modifiable,
            'mark_type': self.type,
            'type': self.mark.type,
            'format': self.mark.format
        }
        if self.type == 'unknown':
            common_data['component'] = self.mark.component.name
        write_file_str(marktar_obj, 'markdata', json.dumps(common_data))
        if self.type == 'unsafe':
            write_file_str(marktar_obj, 'error-trace',
                           self.mark.error_trace.decode('utf8'))
        marktar_obj.close()


class ReadTarMark(object):

    def __init__(self, user, tar_archive):
        self.mark = None
        self.type = None
        self.user = user
        self.tar_arch = tar_archive
        self.error = self.__create_mark_from_tar()

    class UploadMark(object):

        def __init__(self, user, mark_type, args):
            self.mark = None
            self.mark_version = None
            self.user = user
            self.type = mark_type
            if not isinstance(args, dict) or not isinstance(user, User):
                self.error = _("Unknown error")
            else:
                self.error = self.__create_mark(args)

        def __create_mark(self, args):
            if self.type == 'unsafe':
                mark = MarkUnsafe()
            elif self.type == 'safe':
                mark = MarkSafe()
            else:
                mark = MarkUnknown()
            mark.author = self.user

            if self.type == 'unsafe':
                mark.error_trace = args['error_trace'].encode('utf8')
                try:
                    mark.function = \
                        MarkUnsafeCompare.objects.get(pk=args['compare_id'])
                except ObjectDoesNotExist:
                    return _("The error traces comparison "
                             "function was not found")
            mark.format = int(args['format'])
            if mark.format != FORMAT:
                return _('The mark format is not supported')
            mark.type = args['type']

            time_encoded = now().strftime("%Y%m%d%H%M%S%f%z").encode('utf8')
            mark.identifier = hashlib.md5(time_encoded).hexdigest()

            if isinstance(args['is_modifiable'], bool):
                mark.is_modifiable = args['is_modifiable']

            if self.type == 'unsafe' and \
                    args['verdict'] in list(x[0] for x in MARK_UNSAFE):
                mark.verdict = args['verdict']
            elif self.type == 'safe' and \
                    args['verdict'] in list(x[0] for x in MARK_SAFE):
                mark.verdict = args['verdict']
            elif self.type == 'unknown':
                mark.component = Component.objects.get_or_create(name=args['component'])[0]
                mark.function = args['function']
                mark.problem_pattern = args['problem']
                if 'link' in args and len(args['link']) > 0:
                    mark.function = args['link']

            if args['status'] in list(x[0] for x in MARK_STATUS):
                mark.status = args['status']

            tags = []
            if 'tags' in args and self.type != 'unknown':
                tags = args['tags']
            if 'description' in args:
                mark.description = args['description']

            try:
                mark.save()
            except Exception as e:
                print_err(e)
                return _("Unknown error")

            self.__update_mark(mark, tags=tags)
            if self.type != 'unknown':
                res = self.__create_attributes(args['attrs'], mark)
                if res is not None:
                    mark.delete()
                    return res
            self.mark = mark
            return None

        def __update_mark(self, mark, comment='', tags=None):
            if self.type == 'unsafe':
                new_version = MarkUnsafeHistory()
            elif self.type == 'safe':
                new_version = MarkSafeHistory()
            else:
                new_version = MarkUnknownHistory()

            new_version.mark = mark
            if self.type == 'unsafe':
                new_version.function = mark.function
            if self.type == 'unknown':
                new_version.function = mark.function
                new_version.problem_pattern = mark.problem_pattern
                new_version.link = mark.link
            else:
                new_version.verdict = mark.verdict
            new_version.version = mark.version
            new_version.status = mark.status
            new_version.change_date = mark.change_date
            new_version.comment = comment
            new_version.author = mark.author
            new_version.description = mark.description
            new_version.save()
            if isinstance(tags, list):
                for tag in tags:
                    if self.type == 'safe':
                        safetag = SafeTag.objects.get_or_create(tag=tag)[0]
                        MarkSafeTag.objects.create(tag=safetag,
                                                   mark_version=new_version)
                    elif self.type == 'unsafe':
                        unsafetag = UnsafeTag.objects.get_or_create(tag=tag)[0]
                        MarkUnsafeTag.objects.create(tag=unsafetag,
                                                     mark_version=new_version)
            self.mark_version = new_version

        def __create_attributes(self, attrs, mark):
            attr_order = []
            if not isinstance(attrs, list):
                return _('The attributes have wrong format')
            for a in attrs:
                if any(x not in a for x in ['attr', 'value', 'is_compare']):
                    return _('The attributes have wrong format')
            for a in attrs:
                attr_order.append(a['attr'])
                attr_name = AttrName.objects.get_or_create(name=a['attr'])[0]
                attr = Attr.objects\
                    .get_or_create(name=attr_name, value=a['value'])[0]
                create_args = {
                    'mark': self.mark_version,
                    'attr': attr,
                    'is_compare': a['is_compare']
                }
                if self.type == 'unsafe':
                    MarkUnsafeAttr.objects.get_or_create(**create_args)
                else:
                    MarkSafeAttr.objects.get_or_create(**create_args)
            for attr in attr_order:
                if self.type == 'safe':
                    SafeMarkAttrOrder.objects.create(
                        name=AttrName.objects.get_or_create(name=attr)[0],
                        mark_id=mark.pk
                    )
                else:
                    UnsafeMarkAttrOrder.objects.create(
                        name=AttrName.objects.get_or_create(name=attr)[0],
                        mark_id=mark.pk
                    )
            return None

    def __create_mark_from_tar(self):

        def get_func_id(func_name):
            try:
                return MarkUnsafeCompare.objects.get(name=func_name).pk
            except ObjectDoesNotExist:
                return 0

        inmemory = BytesIO(self.tar_arch.read())
        marktar_file = tarfile.open(fileobj=inmemory, mode='r')
        mark_data = None
        err_trace = None

        versions_data = {}
        for f in marktar_file.getmembers():
            file_name = f.name
            file_obj = marktar_file.extractfile(f)
            if file_name == 'markdata':
                try:
                    mark_data = json.loads(file_obj.read().decode('utf-8'))
                except ValueError:
                    return _("The mark archive is corrupted")
            elif file_name == 'error-trace':
                err_trace = file_obj.read().decode('utf-8')
            elif file_name.startswith('version-'):
                version_id = int(file_name.replace('version-', ''))
                try:
                    versions_data[version_id] = json.loads(file_obj.read().decode('utf-8'))
                except ValueError:
                    return _("The mark archive is corrupted")

        if not isinstance(mark_data, dict) or \
                any(x not in mark_data for x in [
                    'mark_type', 'is_modifiable', 'type', 'format']):
            return _("The mark archive is corrupted")
        self.type = mark_data['mark_type']
        if self.type not in ['safe', 'unsafe', 'unknown']:
            return _("The mark archive is corrupted")
        if self.type == 'unsafe' and err_trace is None:
            return _("The mark archive is corrupted: "
                     "the pattern error trace is not found")
        elif self.type == 'unknown' and 'component' not in mark_data:
            return _("The mark archive is corrupted")

        version_list = list(versions_data[v] for v in sorted(versions_data))
        for version in version_list:
            if any(x not in version for x in ['status', 'comment']):
                return _("The mark archive is corrupted")
            if self.type == 'unsafe' and 'function' not in version:
                return _("The mark archive is corrupted")
            if self.type != 'unknown' and any(
                    x not in version for x in ['verdict', 'attrs', 'tags']):
                return _("The mark archive is corrupted")
            if self.type == 'unknown' \
                    and any(x not in version for x in ['problem', 'function']):
                return _("The mark archive is corrupted")

        new_m_args = mark_data
        new_m_args.update(version_list[0])
        if self.type == 'unsafe':
            new_m_args['error_trace'] = err_trace
            new_m_args['compare_id'] = get_func_id(version_list[0]['function'])
            del new_m_args['function'], new_m_args['mark_type']

        umark = self.UploadMark(self.user, self.type, new_m_args)
        if umark.error is not None:
            return umark.error
        mark = umark.mark
        if not isinstance(mark, (MarkUnsafe, MarkSafe, MarkUnknown)):
            return _("Unknown error")
        for version_data in version_list[1:]:
            if len(version_data['comment']) == 0:
                version_data['comment'] = '1'
            if self.type == 'unsafe':
                version_data['compare_id'] = \
                    get_func_id(version_data['function'])
            del version_data['function']
            upd_mark = NewMark(mark, self.user, self.type, version_data, False)
            if upd_mark.error is not None:
                mark.delete()
                return upd_mark.error

        UpdateTags(mark, changes=ConnectMarkWithReports(mark).changes)
        self.mark = mark
        return None


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
            last_v = self.report.root.job.versions.get(
                version=self.report.root.job.version)
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
            for mtag in mark_rep.mark.versions.order_by('-version')[0].tags.all():
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
        mark_last_v = mark.versions.order_by('-version')[0]
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
            m = re.search(self.function, l)
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
    reports_to_recalc = []
    for unknown in changes:
        for report in unknown.leaves.all():
            if report.report not in reports_to_recalc:
                reports_to_recalc.append(report.report)
    for report in reports_to_recalc:
        problems = {}
        report.mark_unknowns_cache.all().delete()
        total_unknowns = {}
        for leaf in report.leaves.filter(~Q(unknown=None)):
            component = leaf.unknown.component
            if component not in total_unknowns:
                total_unknowns[component] = 0
            total_unknowns[component] += 1
            for mark_report in leaf.unknown.markreport_set.all():
                new_id = (component, mark_report.problem)
                if new_id not in problems:
                    problems[new_id] = {
                        'num': 0,
                        'unknowns': []
                    }
                if leaf.unknown not in problems[new_id]['unknowns']:
                    problems[new_id]['num'] += 1
                    problems[new_id]['unknowns'].append(leaf.unknown)
        total_numbers = {}
        for component, problem in problems:
            ComponentMarkUnknownProblem.objects.create(
                report=report,
                component=component,
                problem=problem,
                number=problems[(component, problem)]['num']
            )
            if component not in total_numbers:
                total_numbers[component] = 0
            total_numbers[component] += problems[(component, problem)]['num']
        for component in total_numbers:
            unmarked = total_unknowns[component] - total_numbers[component]
            if unmarked > 0:
                ComponentMarkUnknownProblem.objects.create(
                    report=report,
                    component=component,
                    problem=None,
                    number=unmarked
                )
