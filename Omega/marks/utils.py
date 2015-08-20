import json
import tarfile
import hashlib
from io import BytesIO
from datetime import datetime
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import ugettext_lazy as _
from Omega.vars import USER_ROLES, JOB_ROLES
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
                self.type == 'unsafe' and isinstance(inst, ReportUnsafe):
            self.error = self.__create_mark(inst, args)
        elif self.type == 'unsafe' and isinstance(inst, MarkUnsafe) or \
                self.type == 'safe' and isinstance(inst, MarkSafe):
            self.error = self.__change_mark(inst, args)
        else:
            self.error = "Wrong parameters"

    def __create_mark(self, report, args):
        if self.type == 'unsafe':
            mark = MarkUnsafe()
        else:
            mark = MarkSafe()
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
        mark.format = report.root.job.format
        mark.type = report.root.job.type
        mark.job = report.root.job
        mark.attr_order = report.attr_order

        time_encoded = datetime.now().strftime("%Y%m%d%H%M%S%f%z").\
            encode('utf8')
        mark.identifier = hashlib.md5(time_encoded).hexdigest()

        if 'is_modifiable' in args and isinstance(args['is_modifiable'], bool) \
                and self.user.extended.role == USER_ROLES[2][0]:
            mark.is_modifiable = args['is_modifiable']

        if 'verdict' in args:
            if self.type == 'unsafe' and \
                    args['verdict'] in list(x[0] for x in MARK_UNSAFE):
                mark.verdict = args['verdict']
            elif args['verdict'] in list(x[0] for x in MARK_SAFE):
                mark.verdict = args['verdict']

        if 'status' in args and \
                args['status'] in list(x[0] for x in MARK_STATUS):
            mark.status = args['status']

        try:
            mark.save()
        except Exception as e:
            return e

        self.__update_mark(mark)
        if 'attrs' in args:
            res = self.__create_attributes(report, args['attrs'])
            if res is not None:
                mark.delete()
                return res
        self.mark = mark
        if self.calculate:
            self.__update_links()
        return None

    def __change_mark(self, mark, args):
        recalc_verdicts = False
        if not mark.is_modifiable:
            return "Mark is not modifiable"
        if 'comment' not in args or len(args['comment']) == 0:
            return 'Change comment is required'
        if self.type == 'unsafe':
            last_v = mark.markunsafehistory_set.all().order_by('-version')[0]
        else:
            last_v = mark.marksafehistory_set.all().order_by('-version')[0]

        mark.author = self.user

        if self.type == 'unsafe' and 'compare_id' in args:
            try:
                mark.function = MarkUnsafeCompare.objects.get(
                    pk=int(args['compare_id']))
                if mark.function != last_v.function:
                    self.do_recalk = True
            except ObjectDoesNotExist:
                return "Comparison function was not found"

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

        mark.version += 1
        mark.save()
        self.__update_mark(mark, args['comment'])
        if 'attrs' in args:
            res = self.__update_attributes(args['attrs'], last_v)
            if res is not None:
                mark.version -= 1
                mark.save()
                self.mark_version.delete()
                return res
        self.mark = mark
        if self.calculate:
            if self.do_recalk:
                self.__update_links()
            elif recalc_verdicts:
                self.changes = UpdateVerdict(mark, {}, '=').changes
        return None

    def __update_mark(self, mark, comment=''):
        if self.type == 'unsafe':
            new_version = MarkUnsafeHistory()
        else:
            new_version = MarkSafeHistory()

        new_version.mark = mark
        if self.type == 'unsafe':
            new_version.function = mark.function
        new_version.verdict = mark.verdict
        new_version.version = mark.version
        new_version.status = mark.status
        new_version.change_date = mark.change_date
        new_version.comment = comment
        new_version.author = mark.author
        new_version.save()
        self.mark_version = new_version

    def __update_attributes(self, attrs, old_mark):
        if not isinstance(attrs, list):
            return 'Wrong attributes'
        for a in attrs:
            if not isinstance(a, dict) or \
                    any(x not in a for x in ['attr', 'is_compare']):
                return 'Wrong args'
        if self.type == 'unsafe':
            old_set = old_mark.markunsafeattr_set.all()
        else:
            old_set = old_mark.marksafeattr_set.all()
        for a in old_set:
            create_args = {
                'mark': self.mark_version,
                'attr': a.attr,
                'is_compare': a.is_compare
            }
            for u_at in attrs:
                if u_at['attr'] == a.attr.name.name:
                    if u_at['is_compare'] != create_args['is_compare']:
                        self.do_recalk = True
                    create_args['is_compare'] = u_at['is_compare']
                    break
            if self.type == 'unsafe':
                MarkUnsafeAttr.objects.get_or_create(**create_args)
            else:
                MarkSafeAttr.objects.get_or_create(**create_args)
        return None

    def __create_attributes(self, report, attrs):
        if not isinstance(attrs, list):
            return 'Wrong attributes'
        for a in attrs:
            if not isinstance(a, dict) or \
                    any(x not in a for x in ['attr', 'is_compare']):
                return 'Wrong args'
        for a in report.attr.all():
            create_args = {
                'mark': self.mark_version,
                'attr': a
            }
            for u_at in attrs:
                if u_at['attr'] == a.name.name:
                    create_args['is_compare'] = u_at['is_compare']
                    break

            if self.type == 'unsafe':
                MarkUnsafeAttr.objects.get_or_create(**create_args)
            else:
                MarkSafeAttr.objects.get_or_create(**create_args)
        return None

    def __update_links(self):
        cm_res = ConnectMarks(self.mark)
        self.changes = cm_res.changes
        self.cnt = cm_res.cnt


class ConnectMarks(object):

    def __init__(self, inst):
        self.cnt = 0  # Number of new connections
        self.changes = {}  # Changes with reports' marks after connections
        if isinstance(inst, ReportUnsafe):
            self.__connect_unsafe(inst)
        elif isinstance(inst, ReportSafe):
            self.__connect_safe(inst)
        elif isinstance(inst, MarkUnsafe):
            self.__connect_unsafe_mark(inst)
        elif isinstance(inst, MarkSafe):
            self.__connect_safe_mark(inst)

    def __connect_unsafe(self, unsafe):
        self.cnt = 0
        unsafe.markunsafereport_set.all().delete()
        for mark in MarkUnsafe.objects.filter(type=unsafe.root.job.type):
            last_version = mark.markunsafehistory_set.get(version=mark.version)
            for attr in last_version.markunsafeattr_set.all():
                if attr.is_compare:
                    try:
                        unsafe.attr.get(name__name=attr.attr.name.name,
                                        value=attr.attr.value)
                    except ObjectDoesNotExist:
                        break
            else:
                compare_failed = False
                compare = CompareTrace(
                    mark.function.name,
                    mark.error_trace.decode('utf8'),
                    unsafe.error_trace.decode('utf8'))
                if compare.error is not None:
                    print(compare.error)
                    compare_failed = True
                if compare.result > 0 or compare_failed:
                    MarkUnsafeReport.objects.create(
                        mark=mark, report=unsafe, result=compare.result,
                        broken=compare_failed)
                    UpdateVerdict(mark, self.changes)
                    self.cnt += 1

    def __connect_safe(self, safe):
        self.cnt = 0
        for mark in MarkSafe.objects.filter(type=safe.root.job.type):
            if mark.type != safe.root.job.type:
                continue
            last_version = mark.marksafehistory_set.get(version=mark.version)
            for attr in last_version.marksafeattr_set.all():
                if attr.is_compare:
                    try:
                        safe.attr.get(name__name=attr.attr.name.name,
                                      value=attr.attr.value)
                    except ObjectDoesNotExist:
                        break
            else:
                MarkSafeReport.objects.create(mark=mark, report=safe)
                UpdateVerdict(mark, self.changes)
                self.cnt += 1

    def __connect_unsafe_mark(self, mark):
        self.cnt = 0
        last_version = mark.markunsafehistory_set.get(version=mark.version)

        for mark_unsafe in mark.markunsafereport_set.all():
            self.changes[mark_unsafe.report] = {
                'kind': '=',
                'result1': mark_unsafe.result,
                'verdict1': mark_unsafe.report.verdict,
            }
        mark.markunsafereport_set.all().delete()
        for unsafe in ReportUnsafe.objects.filter(root__job__type=mark.type):
            for attr in last_version.markunsafeattr_set.all():
                if attr.is_compare:
                    try:
                        unsafe.attr.get(name__name=attr.attr.name.name,
                                        value=attr.attr.value)
                    except ObjectDoesNotExist:
                        break
            else:
                compare_failed = False
                compare = CompareTrace(
                    mark.function.name,
                    mark.error_trace.decode('utf8'),
                    unsafe.error_trace.decode('utf8'))
                if compare.error is not None:
                    print(compare.error)
                    compare_failed = True
                if compare.result > 0 or compare_failed:
                    MarkUnsafeReport.objects.create(
                        mark=mark, report=unsafe, result=compare.result,
                        broken=compare_failed)
                    self.cnt += 1
        if self.cnt > 0:
            self.changes.update(UpdateVerdict(mark, self.changes).changes)

    def __connect_safe_mark(self, mark):
        self.cnt = 0
        for mark_safe in mark.marksafereport_set.all():
            self.changes[mark_safe.report] = {
                'kind': '=',
                'result1': mark_safe.result,
                'verdict1': mark_safe.report.verdict,
            }
        mark.marksafereport_set.all().delete()
        for safe in ReportSafe.objects.filter(root__job__type=mark.type):
            last_version = mark.marksafehistory_set.get(version=mark.version)
            for attr in last_version.marksafeattr_set.all():
                if attr.is_compare:
                    try:
                        safe.attr.get(name__name=attr.attr.name.name,
                                      value=attr.attr.value)
                    except ObjectDoesNotExist:
                        break
            else:
                MarkSafeReport.objects.create(mark=mark, report=safe)
                self.cnt += 1
        if self.cnt > 0:
            self.changes.update(UpdateVerdict(mark, self.changes).changes)


class UpdateVerdict(object):

    def __init__(self, inst, changes, def_kind='+'):
        self.changes = changes
        self.def_kind = def_kind
        if isinstance(inst, MarkUnsafe):
            self.__update_unsafes(inst)
        elif isinstance(inst, MarkSafe):
            self.__update_safes(inst)
        elif isinstance(inst, ReportUnsafe) or isinstance(inst, ReportSafe):
            self.__update_report(inst)

    def __update_unsafes(self, mark):
        updated_unsafes = []
        for mark_report in mark.markunsafereport_set.all():
            unsafe = mark_report.report
            updated_unsafes.append(unsafe)

            if unsafe not in self.changes:
                self.changes[unsafe] = {
                    'kind': self.def_kind,
                    'verdict1': unsafe.verdict,
                }
            self.changes[unsafe]['result2'] = mark_report.result
            new_verdict = self.__calc_verdict(unsafe)
            if new_verdict != unsafe.verdict:
                self.changes[unsafe]['verdict2'] = new_verdict
                self.__new_unsafe_verdict(unsafe, new_verdict)

        # Updating unsafes that have lost changed mark
        for unsafe in self.changes:
            if unsafe in updated_unsafes:
                continue
            self.changes[unsafe]['kind'] = '-'
            new_verdict = '5'
            if unsafe.verdict == '4':
                new_verdict = self.__calc_verdict(unsafe)
            elif len(unsafe.markunsafereport_set.all()) > 0:
                continue
            if new_verdict != unsafe.verdict:
                self.changes[unsafe]['verdict2'] = new_verdict
                self.__new_unsafe_verdict(unsafe, new_verdict)

    def __update_safes(self, mark):
        updated_safes = []
        for mark_report in mark.marksafereport_set.all():
            safe = mark_report.report
            updated_safes.append(safe)

            if safe not in self.changes:
                self.changes[safe] = {
                    'kind': self.def_kind,
                    'verdict1': safe.verdict
                }
            new_verdict = self.__calc_verdict(safe)
            if new_verdict != safe.verdict:
                self.changes[safe]['verdict2'] = new_verdict
                self.__new_safe_verdict(safe, new_verdict)

        # Updating safes that have lost changed mark
        for safe in self.changes:
            if safe in updated_safes:
                continue
            self.changes[safe]['kind'] = '-'
            new_verdict = '4'
            if safe.verdict == '3':
                new_verdict = self.__calc_verdict(safe)
            elif len(safe.marksafereport_set.all()) > 0:
                continue
            if new_verdict != safe.verdict:
                self.changes[safe]['verdict2'] = new_verdict
                self.__new_safe_verdict(safe, new_verdict)

    def __update_report(self, report):
        new_verdict = self.__calc_verdict(report)
        if new_verdict != report.verdict:
            if report not in self.changes:
                self.changes[report] = {}
            self.changes[report]['verdict2'] = new_verdict
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
        new_verdict = None
        if isinstance(report, ReportUnsafe):
            for uns_m_r in report.markunsafereport_set.all():
                if new_verdict is not None and \
                        new_verdict != uns_m_r.mark.verdict:
                    new_verdict = '4'
                    break
                else:
                    new_verdict = uns_m_r.mark.verdict
            if new_verdict is None:
                new_verdict = '5'
        elif isinstance(report, ReportSafe):
            new_verdict = None
            for s_m_r in report.marksafereport_set.all():
                if new_verdict is not None and \
                        new_verdict != s_m_r.mark.verdict:
                    new_verdict = '3'
                    break
                else:
                    new_verdict = s_m_r.mark.verdict
            if new_verdict is None:
                new_verdict = '4'
        return new_verdict


class CreateMarkTar(object):

    def __init__(self, mark, mark_type):
        self.mark = mark
        self.mark_type = mark_type
        self.marktar_name = ''
        self.memory = BytesIO()
        self.__full_tar()

    def __full_tar(self):

        def write_file_str(jobtar, file_name, file_content):
            file_content = file_content.encode('utf-8')
            t = tarfile.TarInfo(file_name)
            t.size = len(file_content)
            jobtar.addfile(t, BytesIO(file_content))

        self.marktar_name = 'EM__' + self.mark.identifier + '.tar.gz'
        marktar_obj = tarfile.open(fileobj=self.memory, mode='w:gz')
        if self.mark_type == 'unsafe' and isinstance(self.mark, MarkUnsafe):
            mark_history_set = self.mark.markunsafehistory_set.all()
        elif self.mark_type == 'safe' and isinstance(self.mark, MarkSafe):
            mark_history_set = self.mark.marksafehistory_set.all()
        else:
            return None
        for markversion in mark_history_set:
            version_data = {
                'status': markversion.status,
                'verdict': markversion.verdict,
                'comment': markversion.comment,
                'attrs': [],
            }
            if self.mark_type == 'unsafe':
                attr_set = markversion.markunsafeattr_set.all()
                version_data['function'] = markversion.function.name
            elif self.mark_type == 'safe':
                attr_set = markversion.marksafeattr_set.all()
            else:
                return None
            for attr in attr_set:
                version_data['attrs'].append({
                    'attr': attr.attr.name.name,
                    'value': attr.attr.value,
                    'is_compare': attr.is_compare
                })
            write_file_str(marktar_obj, 'version-%s' % markversion.version,
                           json.dumps(version_data))
        common_data = {
            'is_modifiable': self.mark.is_modifiable,
            'mark_type': self.mark_type,
            'type': self.mark.type,
            'format': self.mark.format
        }
        write_file_str(marktar_obj, 'markdata', json.dumps(common_data))
        if self.mark_type == 'unsafe':
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
            if self.type != 'safe' and self.type != 'unsafe':
                self.error = "Wrong mark type"
            elif not isinstance(args, dict) or not isinstance(user, User):
                self.error = "Wrong parameters"
            self.error = self.__create_mark(args)

        def __create_mark(self, args):
            if self.type == 'unsafe':
                mark = MarkUnsafe()
            else:
                mark = MarkSafe()
            mark.author = self.user

            if self.type == 'unsafe':
                mark.error_trace = args['error_trace'].encode('utf8')
                try:
                    mark.function = \
                        MarkUnsafeCompare.objects.get(pk=args['compare_id'])
                except ObjectDoesNotExist:
                    return _("The error traces comparison function was not found")
            mark.format = int(args['format'])
            if mark.format != FORMAT:
                return _('The mark format is not supported')
            mark.type = args['type']

            time_encoded = datetime.now().strftime("%Y%m%d%H%M%S%f%z").\
                encode('utf8')
            mark.identifier = hashlib.md5(time_encoded).hexdigest()

            if isinstance(args['is_modifiable'], bool):
                mark.is_modifiable = args['is_modifiable']

            if self.type == 'unsafe' and \
                    args['verdict'] in list(x[0] for x in MARK_UNSAFE):
                mark.verdict = args['verdict']
            elif args['verdict'] in list(x[0] for x in MARK_SAFE):
                mark.verdict = args['verdict']

            if args['status'] in list(x[0] for x in MARK_STATUS):
                mark.status = args['status']

            try:
                mark.save()
            except Exception as e:
                print(e)
                return _("Unknown error")

            self.__update_mark(mark)
            res = self.__create_attributes(args['attrs'])
            if res is not None:
                mark.delete()
                return res
            self.mark = mark
            return None

        def __update_mark(self, mark, comment=''):
            if self.type == 'unsafe':
                new_version = MarkUnsafeHistory()
            else:
                new_version = MarkSafeHistory()

            new_version.mark = mark
            if self.type == 'unsafe':
                new_version.function = mark.function
            new_version.verdict = mark.verdict
            new_version.version = mark.version
            new_version.status = mark.status
            new_version.change_date = mark.change_date
            new_version.comment = comment
            new_version.author = mark.author
            new_version.save()
            self.mark_version = new_version

        def __create_attributes(self, attrs):
            if not isinstance(attrs, list):
                return _('The attributes have wrong format')
            for a in attrs:
                if any(x not in a for x in ['attr', 'value', 'is_compare']):
                    return _('The attributes have wrong format')
            for a in attrs:
                attr_name = AttrName.objects.get_or_create(name=a['attr'])[0]
                attr = Attr.objects.get_or_create(
                    name=attr_name, value=a['value'])[0]
                create_args = {
                    'mark': self.mark_version,
                    'attr': attr,
                    'is_compare': a['is_compare']
                }
                if self.type == 'unsafe':
                    MarkUnsafeAttr.objects.get_or_create(**create_args)
                else:
                    MarkSafeAttr.objects.get_or_create(**create_args)
            return None

    def __create_mark_from_tar(self):

        def get_func_id(func_name):
            try:
                return MarkUnsafeCompare.objects.get(name=func_name).pk
            except ObjectDoesNotExist:
                return None

        inmemory = BytesIO(self.tar_arch.read())
        marktar_file = tarfile.open(fileobj=inmemory, mode='r')
        mark_data = None
        err_trace = None

        versions_data = {}
        for f in marktar_file.getmembers():
            file_name = f.name
            file_obj = marktar_file.extractfile(f)
            if file_name == 'markdata':
                mark_data = json.loads(file_obj.read().decode('utf-8'))
            elif file_name == 'error-trace':
                err_trace = file_obj.read().decode('utf-8')
            elif file_name.startswith('version-'):
                version_id = int(file_name.replace('version-', ''))
                versions_data[version_id] = json.loads(
                    file_obj.read().decode('utf-8'))

        if not isinstance(mark_data, dict) or \
                any(x not in mark_data for x in [
                    'mark_type', 'is_modifiable', 'type', 'format']):
            return _("The mark archive is corrupted")
        self.type = mark_data['mark_type']
        if self.type == 'unsafe':
            if err_trace is None:
                return _("The mark archive is corrupted: the error trace is not found")

        version_list = list(versions_data[v] for v in sorted(versions_data))
        for version in version_list:
            if any(x not in version
                   for x in ['verdict', 'status', 'comment', 'attrs']):
                return _("The mark archive is corrupted")
            if self.type == 'unsafe' and 'function' not in version:
                return _("The mark archive is corrupted")

        create_mark_data = {
            'format': mark_data['format'],
            'type': mark_data['type'],
            'is_modifiable': mark_data['is_modifiable'],
            'verdict': version_list[0]['verdict'],
            'status': version_list[0]['status'],
            'attrs': version_list[0]['attrs'],
            'compare_id': get_func_id(version_list[0]['function']),
        }
        if self.type == 'unsafe':
            create_mark_data['error_trace'] = err_trace

        umark = self.UploadMark(self.user, self.type, create_mark_data)
        if umark.error is not None:
            return umark.error
        mark = umark.mark
        if not (self.type == 'unsafe' and isinstance(mark, MarkUnsafe) or
                isinstance(mark, MarkSafe)):
            return _("Unknown error")
        for version_data in version_list[1:]:
            if len(version_data['comment']) == 0:
                version_data['comment'] = '1'

            updated_mark = NewMark(mark, self.user, self.type, {
                'attrs': version_data['attrs'],
                'verdict': version_data['verdict'],
                'status': version_data['status'],
                'comment': version_data['comment'],
                'compare_id': get_func_id(version_data['function']),
            }, False)

            if updated_mark.error is not None:
                mark.delete()
                return updated_mark.error

        ConnectMarks(mark)
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
            first_vers = self.mark.markunsafehistory_set.order_by('version')[0]
        elif isinstance(self.mark, MarkSafe):
            first_vers = self.mark.markunsafehistory_set.order_by('version')[0]
        else:
            return False
        if first_vers.author == self.user:
            return True
        if self.mark.job is not None:
            first_v = self.mark.job.jobhistory_set.order_by('version')[0]
            if first_v.change_author == self.user:
                return True
            last_vers = self.mark.job.jobhistory_set.order_by('-version')[0]
            if last_vers.global_role in [JOB_ROLES[2][0], JOB_ROLES[4][0]]:
                return True
            try:
                user_role = last_vers.userrole_set.get(user=self.user)
                if user_role.role in [JOB_ROLES[2][0], JOB_ROLES[4][0]]:
                    return True
            except ObjectDoesNotExist:
                return False
        return False

    def can_create(self):
        if not isinstance(self.user, User):
            return False
        if self.user.extended.role == USER_ROLES[2][0]:
            return True
        if self.user.extended.role == USER_ROLES[3][0]:
            return True
        if isinstance(self.report, ReportUnsafe) or \
                isinstance(self.report, ReportSafe):
            first_v = self.report.root.job.jobhistory_set.order_by('version')[0]
            if first_v.change_author == self.user:
                return True
            last_v = self.report.root.job.jobhistory_set.order_by('-version')[0]
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
        if isinstance(self.mark, MarkUnsafe):
            first_vers = self.mark.markunsafehistory_set.order_by('version')[0]
        elif isinstance(self.mark, MarkSafe):
            first_vers = self.mark.markunsafehistory_set.order_by('version')[0]
        else:
            return False
        if first_vers.author == self.user:
            return True
        return False
