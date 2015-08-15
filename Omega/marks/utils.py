from datetime import datetime
from django.core.urlresolvers import reverse
import hashlib
from django.core.exceptions import ObjectDoesNotExist
from marks.models import *
from reports.models import ReportComponent
from django.utils.translation import ugettext_lazy as _
from Omega.tableHead import Header


MARK_TITLES = {
    'mark_num': '№',
    'change_kind': _('Change kind'),
    'verdict': _("Verdict"),
    'result': _('Similarity'),
    'status': _('Status'),
    'author': _('Author'),
    'report': _('Report'),
    'job': _('Job'),
    'format': _('Psi format')
}

STATUS_COLOR = {
    '0': '#D11919',
    '1': '#FF8533',
    '2': '#FF8533',
    '3': '#00CC00',
}

UNSAFE_COLOR = {
    '0': '#D147FF',
    '1': '#D11919',
    '2': '#D11919',
    '3': '#FF8533',
}

SAFE_COLOR = {}


def result_color(result):
    if 0 < result <= 0.33:
        return '#E60000'
    elif 0.33 < result <= 0.66:
        return '#CC7A29'
    elif 0.66 < result <= 1:
        return '#00CC66'
    return None


def run_function(func, *args):
    if isinstance(func, MarkUnsafeCompare):
        new_func = "def mark_unsafe_compare(pattern_error_trace, error_trace):"
        func_name = 'mark_unsafe_compare'
    elif isinstance(func, MarkUnsafeConvert):
        new_func = "def mark_unsafe_convert(error_trace):"
        func_name = 'mark_unsafe_convert'
    else:
        return None
    new_func += '\n    ' + '\n    '.join(func.body.split('\n'))
    d = {}
    exec(new_func, d)
    return d[func_name](*args)


class NewMark(object):

    def __init__(self, inst, user, mark_type, args):
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
        self.mark_version = None
        self.user = user
        self.type = mark_type
        self.do_recalk = False
        if self.type != 'safe' and self.type != 'unsafe':
            self.error = "Wrong mark type"
        elif not isinstance(args, dict) or not isinstance(user, User):
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
        mark = MarkUnsafe()
        mark.author = self.user

        if self.type == 'unsafe':
            if 'convert_id' in args:
                try:
                    func = MarkUnsafeConvert.objects.get(
                        pk=int(args['convert_id']))
                    converted = run_function(
                        func, report.error_trace.decode('utf8'))
                    if converted is not None and len(converted) > 0:
                        mark.error_trace = converted.encode('utf8')
                    else:
                        return "Error in converting trace"
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

        time_encoded = datetime.now().strftime("%Y%m%d%H%M%S%f%z").\
            encode('utf8')
        mark.identifier = hashlib.md5(time_encoded).hexdigest()

        if 'is_modifiable' in args and isinstance(args['is_modifiable'], bool):
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
        self.do_recalk = True
        return None

    def __change_mark(self, mark, args):

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
            if self.type == 'unsafe' and \
                    args['verdict'] in list(x[0] for x in MARK_UNSAFE):
                mark.verdict = args['verdict']
            elif args['verdict'] in list(x[0] for x in MARK_SAFE):
                mark.verdict = args['verdict']

        if 'status' in args and \
                args['status'] in list(x[0] for x in MARK_STATUS):
            mark.status = args['status']

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
        for a in old_mark.markunsafeattr_set.all():
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


class AttrTable(object):

    def __init__(self, report=None, mark_version=None):
        self.report = report
        self.mark_version = mark_version
        self.header, self.values = self.__self_attrs()

    def __self_attrs(self):
        columns = []
        values = []
        if isinstance(self.mark_version, MarkUnsafeHistory):
            for attr in self.mark_version.markunsafeattr_set.all().order_by(
                    'attr__name__name'):
                columns.append(attr.attr.name.name)
                values.append(
                    (attr.attr.name.name, attr.attr.value, attr.is_compare)
                )
        elif isinstance(self.mark_version, MarkSafeHistory):
            for attr in self.mark_version.marksafeattr_set.all().order_by(
                    'attr__name__name'):
                columns.append(attr.attr.name.name)
                values.append(
                    (attr.attr.name.name, attr.attr.value, attr.is_compare)
                )
        else:
            for attr in self.report.attr.all().order_by('name__name'):
                columns.append(attr.name.name)
                values.append((attr.name.name, attr.value, True))
        return Header(columns, {}).struct, values


class MarkData(object):
    def __init__(self, mark_type, mark_version=None):
        self.type = mark_type
        self.mark_version = mark_version
        self.verdicts = self.__verdict_info()
        self.statuses = self.__status_info()
        self.comparison, self.compare_desc = self.__functions('compare')
        self.convertion, self.convert_desc = self.__functions('convert')

    def __verdict_info(self):
        verdicts = []
        if self.type == 'unsafe':
            for verdict in MARK_UNSAFE:
                verdict_data = {
                    'title': verdict[1],
                    'value': verdict[0],
                    'checked': False,
                    'color': UNSAFE_COLOR[verdict[0]]
                }
                if (isinstance(self.mark_version, MarkUnsafeHistory) and
                        verdict_data['value'] == self.mark_version.verdict) or \
                        (not isinstance(self.mark_version, MarkUnsafeHistory)
                         and verdict_data['value'] == '0'):
                    verdict_data['checked'] = True
                verdicts.append(verdict_data)
        elif self.type == 'safe':
            for verdict in MARK_SAFE:
                verdict_data = {
                    'title': verdict[1],
                    'value': verdict[0],
                    'checked': False
                }
                if (isinstance(self.mark_version, MarkSafeHistory) and
                        verdict_data['value'] == self.mark_version.verdict) or \
                        (not isinstance(self.mark_version, MarkSafeHistory)
                         and verdict_data['value'] == '0'):
                    verdict_data['checked'] = True
                verdicts.append(verdict_data)
        return verdicts

    def __status_info(self):
        statuses = []
        for verdict in MARK_STATUS:
            status_data = {
                'title': verdict[1],
                'value': verdict[0],
                'checked': False,
                'color': STATUS_COLOR[verdict[0]]
            }
            if (isinstance(self.mark_version, MarkUnsafeHistory) and
                    status_data['value'] == self.mark_version.status) or \
                    (not isinstance(self.mark_version, MarkUnsafeHistory)
                     and status_data['value'] == '0'):
                status_data['checked'] = True
            statuses.append(status_data)
        return statuses

    def __functions(self, func_type='compare'):
        __functions = []
        def_func = None
        if func_type == 'compare':
            selected_description = None
            try:
                def_func = MarkDefaultFunctions.objects.all()[0].compare
            except IndexError:
                pass

            for f in MarkUnsafeCompare.objects.all().order_by('name'):
                func_data = {
                    'name': f.name,
                    'selected': False,
                    'value': f.pk,
                }
                if isinstance(self.mark_version, MarkUnsafeHistory):
                    if self.mark_version.function == f:
                        func_data['selected'] = True
                        selected_description = f.description
                elif (not isinstance(self.mark_version, MarkUnsafe) and
                        def_func == f):
                    func_data['selected'] = True
                    selected_description = f.description
                __functions.append(func_data)
        elif func_type == 'convert':
            if self.mark_version is not None:
                return [], None

            selected_description = None
            try:
                def_func = MarkDefaultFunctions.objects.all()[0].convert
            except IndexError:
                pass

            for f in MarkUnsafeConvert.objects.all().order_by('name'):
                func_data = {
                    'name': f.name,
                    'selected': False,
                    'value': f.pk,
                }
                if def_func == f:
                    func_data['selected'] = True
                    selected_description = f.description
                __functions.append(func_data)
        else:
            return [], None
        return __functions, selected_description


class ConnectMarks(object):
    def __init__(self, inst):
        # Number of new connections
        self.cnt = 0
        self.old_connections = {}
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
        for mark in MarkUnsafe.objects.all():
            last_version = mark.markunsafehistory_set.get(version=mark.version)
            for attr in last_version.markunsafeattr_set.all():
                if attr.is_compare:
                    try:
                        unsafe.attr.get(name__name=attr.attr.name.name,
                                        value=attr.attr.value)
                    except ObjectDoesNotExist:
                        break
            else:
                new_result = run_function(
                    mark.function, mark.error_trace, unsafe.error_trace)
                if new_result > 0:
                    MarkUnsafeReport.objects.create(
                        mark=mark, report=unsafe, result=new_result)
                    self.__update_verdicts(mark)
                    self.cnt += 1

    def __connect_safe(self, safe):
        self.cnt = 0
        for mark in MarkSafe.objects.all():
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

    def __connect_unsafe_mark(self, mark):
        self.cnt = 0
        for mark_unsafe in mark.markunsafereport_set.all():
            self.old_connections[mark_unsafe.report] = {
                'result': mark_unsafe.result,
                'verdict': mark_unsafe.report.verdict,
            }
        mark.markunsafereport_set.all().delete()
        for unsafe in ReportUnsafe.objects.all():
            last_version = mark.markunsafehistory_set.get(version=mark.version)
            for attr in last_version.markunsafeattr_set.all():
                if attr.is_compare:
                    try:
                        unsafe.attr.get(name__name=attr.attr.name.name,
                                        value=attr.attr.value)
                    except ObjectDoesNotExist:
                        break
            else:
                new_result = run_function(
                    mark.function, mark.error_trace, unsafe.error_trace)
                if new_result > 0:
                    MarkUnsafeReport.objects.create(
                        mark=mark, report=unsafe, result=new_result)
                    self.cnt += 1
        if self.cnt > 0:
            self.__update_verdicts(mark)

    def __connect_safe_mark(self, mark):
        self.cnt = 0
        for mark_safe in mark.marksafereport_set.all():
            self.old_connections[mark_safe.report] = {
                'result': mark_safe.result,
                'verdict': mark_safe.report.verdict,
            }
        mark.marksafereport_set.all().delete()
        for safe in ReportSafe.objects.all():
            last_version = mark.marksafehistory_set.get(version=mark.version)
            for attr in last_version.marksafeattr_set.all():
                if attr.is_compare:
                    try:
                        safe.attr.get(name__name=attr.attr.name.name,
                                      value=attr.attr.value)
                    except ObjectDoesNotExist:
                        break
            else:
                MarkUnsafeReport.objects.get_or_create(mark=mark, report=safe)
                self.cnt += 1

    def __update_verdicts(self, mark):
        if isinstance(mark, MarkUnsafe):
            updated_unsafes = []
            for mark_report in mark.markunsafereport_set.all():
                unsafe = mark_report.report
                updated_unsafes.append(unsafe)

                new_verdict = None
                for uns_m_r in unsafe.markunsafereport_set.all():
                    if new_verdict is not None and \
                            new_verdict != uns_m_r.mark.verdict:
                        new_verdict = '4'
                        break
                    else:
                        new_verdict = uns_m_r.mark.verdict
                if new_verdict is None:
                    new_verdict = '5'
                if new_verdict != unsafe.verdict:
                    if unsafe in self.old_connections:
                        self.old_connections[unsafe]['verdict'] = unsafe.verdict
                    else:
                        self.old_connections[unsafe] = {
                            'verdict': unsafe.verdict,
                            'result': mark_report.result
                        }
                    self.__new_unsafe_verdict(unsafe, new_verdict)

            # Updating unsafes that have lost changed mark
            for unsafe in self.old_connections:
                if unsafe in updated_unsafes:
                    continue

                curr_verdict = '5'
                if unsafe.verdict == '4':
                    new_verdict = None
                    for uns_m_r in unsafe.markunsafereport_set.all():
                        if new_verdict is not None and \
                                new_verdict != uns_m_r.mark.verdict:
                            new_verdict = '4'
                            break
                        else:
                            new_verdict = uns_m_r.mark.verdict
                    if new_verdict == '4':
                        continue
                    elif new_verdict is not None:
                        curr_verdict = new_verdict
                elif len(unsafe.markunsafereport_set.all()) > 0:
                    continue
                if curr_verdict != unsafe.verdict:
                    self.old_connections[unsafe]['verdict'] = unsafe.verdict
                    self.__new_unsafe_verdict(unsafe, curr_verdict)
        elif isinstance(mark, MarkSafe):
            updated_safes = []
            for mark_report in mark.marksafereport_set.all():
                safe = mark_report.report
                updated_safes.append(safe)

                new_verdict = None
                for s_m_r in safe.marksafereport_set.all():
                    if new_verdict is not None and \
                            new_verdict != s_m_r.mark.verdict:
                        new_verdict = '3'
                        break
                    else:
                        new_verdict = s_m_r.mark.verdict
                if new_verdict is None:
                    new_verdict = '4'
                if new_verdict != safe.verdict:
                    if safe in self.old_connections:
                        self.old_connections[safe]['verdict'] = safe.verdict
                    else:
                        self.old_connections[safe] = {
                            'verdict': safe.verdict,
                            'result': mark_report.result
                        }
                    self.__new_safe_verdict(safe, new_verdict)
            for safe in self.old_connections:
                if safe in updated_safes:
                    continue

                curr_verdict = '4'
                if safe.verdict == '3':
                    new_verdict = None
                    for uns_m_r in safe.marksafereport_set.all():
                        if new_verdict is not None and \
                                new_verdict != uns_m_r.mark.verdict:
                            new_verdict = '3'
                            break
                        else:
                            new_verdict = uns_m_r.mark.verdict
                    if new_verdict == '3':
                        continue
                    elif new_verdict is not None:
                        curr_verdict = new_verdict
                elif len(safe.marksafereport_set.all()) > 0:
                    continue
                if curr_verdict != safe.verdict:
                    self.old_connections[safe]['verdict'] = safe.verdict
                    self.__new_safe_verdict(safe, curr_verdict)

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
                # Case when report havn't saved the verdicts (total=0)
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
                # Case when report havn't saved the verdicts (total=0)
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


class MarkChangesTable(object):
    def __init__(self, mark, old_data=None):
        # If old_data is None, all mark connections will be shown.
        if old_data is None:
            self.columns = ['verdict']
        else:
            self.columns = ['mark_num', 'change_kind', 'verdict']
        if isinstance(mark, MarkUnsafe):
            self.columns.append('result')
        elif not isinstance(mark, MarkSafe):
            return
        self.columns.extend(['status', 'author', 'report', 'job', 'format'])
        self.mark = mark
        self.old_data = old_data
        self.attr_values_data, self.reports = self.__add_attrs()
        self.header = Header(self.columns, MARK_TITLES).struct
        self.values = self.__get_unsafe_values()

    def __add_attrs(self):
        data = {}
        if isinstance(self.mark, MarkUnsafe):
            markreport_set = self.mark.markunsafereport_set.all().order_by('-result')
        else:
            markreport_set = self.mark.marksafereport_set.all()
        reports = []
        for mark_report in markreport_set:
            report = mark_report.report
            for attr in report.attr.all():
                if attr.name.name not in data:
                    data[attr.name.name] = {}
                data[attr.name.name][report] = attr.value
            reports.append(report)
        if self.old_data is not None:
            for report in self.old_data:
                if report not in reports:
                    for attr in report.attr.all():
                        if attr.name.name not in data:
                            data[attr.name.name] = {}
                        data[attr.name.name][report] = attr.value

        columns = []
        for name in sorted(data):
            columns.append(name)

        cnt = 0
        values_data = {}
        for report in reports:
            values_data[report] = {}
            for col in columns:
                cell_val = '-'
                if report in data[col]:
                    cell_val = data[col][report]
                cnt += 1
                values_data[report][col] = cell_val
        self.columns.extend(columns)
        return values_data, reports

    def __get_unsafe_values(self):

        def get_status_change():
            v_set = self.mark.markunsafehistory_set.all().order_by('-version')
            last_version = v_set[0]
            try:
                prev_version = v_set[1]
            except IndexError:
                return last_version.get_status_display()
            if prev_version.status == last_version.status:
                return last_version.get_status_display()
            return "%s->%s" % (prev_version.get_status_display(),
                               last_version.get_status_display())

        def get_verdict_change(rep):
            if self.old_data is not None:
                if rep in self.old_data:
                    if self.old_data[rep]['verdict'] == rep.verdict:
                        return rep.get_verdict_display()
                    tmp_unsafe = ReportUnsafe()
                    tmp_unsafe.verdict = self.old_data[rep]['verdict']
                    return "%s->%s" % (tmp_unsafe.get_verdict_display(),
                                       rep.get_verdict_display())
            return rep.get_verdict_display()

        def get_result_change(rep):
            if self.old_data is not None:
                if rep in self.old_data:
                    if self.old_data[rep]['result'] == report_mark.result:
                        return "{:.0%}".format(report_mark.result)
                    return "%s -> %s" % (
                        "{:.0%}".format(float(self.old_data[rep]['result'])),
                        "{:.0%}".format(float(report_mark.result))
                    )
            return "{:.0%}".format(report_mark.result)

        values = []

        cnt = 0
        for report in self.reports:
            cnt += 1
            values_str = []
            for col in self.columns:
                values_data = {}
                try:
                    report_mark = self.mark.markunsafereport_set.get(
                        report=report)
                except ObjectDoesNotExist:
                    values_data['value'] = '-'
                    continue
                if col in self.attr_values_data[report]:
                    values_data['value'] = self.attr_values_data[report][col]
                elif col == 'mark_num':
                    values_data['value'] = cnt
                    values_data['href'] = reverse('marks:edit_mark',
                                                  args=['unsafe', self.mark.pk])
                elif col == 'report':
                    values_data['value'] = cnt
                    values_data['href'] = reverse('reports:leaf',
                                                  args=['unsafe', report.pk])
                elif col == 'verdict':
                    values_data['value'] = get_verdict_change(report)
                elif col == 'status':
                    values_data['value'] = get_status_change()
                elif col == 'change_kind':
                    if self.old_data is None:
                        values_data['value'] = '-'
                    elif report in self.old_data:
                        try:
                            self.mark.markunsafereport_set.get(report=report)
                            values_data['value'] = _("Changed")
                            values_data['color'] = '#CC7A29'
                        except ObjectDoesNotExist:
                            values_data['value'] = _("Deleted")
                            values_data['color'] = '#B80000'
                    else:
                        values_data['value'] = _("New")
                        values_data['color'] = '#008F00'
                elif col == 'result':
                    values_data['value'] = get_result_change(report)
                elif col == 'author':
                    values_data['value'] = "%s %s" % (
                        report_mark.mark.author.extended.last_name,
                        report_mark.mark.author.extended.first_name
                    )
                    values_data['href'] = reverse(
                        'users:show_profile',
                        args=[report_mark.mark.author.pk]
                    )
                elif col == 'job':
                    values_data['value'] = report.root.job.name
                    values_data['href'] = reverse('jobs:job',
                                                  args=[report.root.job.pk])
                elif col == 'format':
                    values_data['value'] = report.root.job.format
                else:
                    values_data['value'] = '-'
                values_str.append(values_data)
            values.append(values_str)
        return values


class ReportMarkTable(object):
    def __init__(self, report):
        self.report = report
        self.type = 'safe'
        self.columns = ['number', 'verdict']
        if isinstance(report, ReportUnsafe):
            self.columns.append('result')
            self.type = 'unsafe'
        elif not isinstance(report, ReportSafe):
            return
        self.columns.extend(['status', 'author'])
        self.titles = MARK_TITLES
        self.titles['number'] = '№'
        self.header = Header(self.columns, self.titles).struct
        self.values = self.__get_values()

    def __get_values(self):
        cnt = 0
        value_data = []
        if isinstance(self.report, ReportUnsafe):
            m_set = self.report.markunsafereport_set.all().order_by('-result')
        elif isinstance(self.report, ReportSafe):
            m_set = self.report.marksafereport_set.all().order_by('-result')
        else:
            return value_data
        for mark_rep in m_set:
            cnt += 1
            values_row = []
            for col in self.columns:
                href = None
                value = '-'
                color = None
                if col == 'number':
                    value = cnt
                    href = reverse('marks:edit_mark',
                                   args=[self.type, mark_rep.mark.pk])
                elif col == 'verdict':
                    value = mark_rep.mark.get_verdict_display()
                    color = UNSAFE_COLOR[mark_rep.mark.verdict]
                elif col == 'result':
                    value = "{:.0%}".format(mark_rep.result)
                    color = result_color(mark_rep.result)
                elif col == 'status':
                    value = mark_rep.mark.get_status_display()
                    color = STATUS_COLOR[mark_rep.mark.status]
                elif col == 'author':
                    if mark_rep.mark.author is not None:
                        value = "%s %s" % (
                            mark_rep.mark.author.extended.last_name,
                            mark_rep.mark.author.extended.first_name
                        )
                        href = reverse(
                            'users:show_profile',
                            args=[mark_rep.mark.author.pk]
                        )
                values_row.append({
                    'value': value, 'href': href, 'color': color
                })
            value_data.append(values_row)
        return value_data


class MarkListTable(object):
    def __init__(self, marks_type):
        self.columns = ['mark_num', 'verdict']
        if marks_type == 'unsafe':
            self.columns.append('result')
        elif marks_type != 'safe':
            return
        self.type = marks_type
        self.columns.extend(['status', 'author', 'report', 'job', 'format'])
        self.attr_values_data, self.reports = self.__add_attrs()
        self.header = Header(self.columns, MARK_TITLES).struct
        self.values = self.__get_unsafe_values()

    def __add_attrs(self):
        data = {}
        if self.type == 'unsafe':
            markreport_set = MarkUnsafeReport.objects.all().order_by('-result')
        else:
            markreport_set = MarkSafeReport.objects.all()
        reports = []
        for mark_report in markreport_set:
            for attr in mark_report.report.attr.all():
                if attr.name.name not in data:
                    data[attr.name.name] = {}
                data[attr.name.name][mark_report] = attr.value
            reports.append(mark_report)

        columns = []
        for name in sorted(data):
            columns.append(name)

        cnt = 0
        values_data = {}
        for mark_report in reports:
            values_data[mark_report] = {}
            for col in columns:
                cell_val = '-'
                if mark_report in data[col]:
                    cell_val = data[col][mark_report]
                cnt += 1
                values_data[mark_report][col] = cell_val
        self.columns.extend(columns)
        return values_data, reports

    def __get_unsafe_values(self):
        values = []

        cnt_data = {}
        cnt_marks = 0
        cnt_reports = 0
        for m_rep in self.reports:
            if m_rep.mark not in cnt_data:
                cnt_marks += 1
                cnt_data[m_rep.mark] = cnt_marks
            if m_rep.report not in cnt_data:
                cnt_reports += 1
                cnt_data[m_rep.report] = cnt_reports
        for m_rep in self.reports:
            values_str = []
            for col in self.columns:
                values_data = {}
                if col in self.attr_values_data[m_rep]:
                    values_data['value'] = self.attr_values_data[m_rep][col]
                elif col == 'mark_num':
                    values_data['value'] = cnt_data[m_rep.mark]
                    values_data['href'] = reverse(
                        'marks:edit_mark',
                        args=['unsafe', m_rep.mark.pk]
                    )
                elif col == 'report':
                    values_data['value'] = cnt_data[m_rep.report]
                    values_data['href'] = reverse(
                        'reports:leaf',
                        args=['unsafe', m_rep.report.pk]
                    )
                elif col == 'verdict':
                    values_data['value'] = m_rep.mark.get_verdict_display()
                    values_data['color'] = UNSAFE_COLOR[m_rep.mark.verdict]
                elif col == 'status':
                    values_data['value'] = m_rep.mark.get_status_display()
                    values_data['color'] = STATUS_COLOR[m_rep.mark.status]
                elif col == 'result':
                    values_data['value'] = "{:.0%}".format(float(m_rep.result))
                elif col == 'author':
                    values_data['value'] = "%s %s" % (
                        m_rep.mark.author.extended.last_name,
                        m_rep.mark.author.extended.first_name
                    )
                    values_data['href'] = reverse(
                        'users:show_profile',
                        args=[m_rep.mark.author.pk]
                    )
                elif col == 'job':
                    values_data['value'] = m_rep.report.root.job.name
                    values_data['href'] = reverse(
                        'jobs:job', args=[m_rep.report.root.job.pk])
                elif col == 'format':
                    values_data['value'] = m_rep.report.root.job.format
                else:
                    values_data['value'] = '-'
                values_str.append(values_data)
            values.append(values_str)
        return values
