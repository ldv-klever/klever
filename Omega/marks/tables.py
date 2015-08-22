import json
from django.core.urlresolvers import reverse
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import ugettext_lazy as _
from Omega.tableHead import Header
from marks.models import *
from jobs.utils import JobAccess
from marks.CompareTrace import DEFAULT_COMPARE
from marks.ConvertTrace import DEFAULT_CONVERT


NO_ACCESS_COLOR = '#666666'
MARK_TITLES = {
    'mark_num': '№',
    'change_kind': _('Change kind'),
    'verdict': _("Verdict"),
    'sum_verdict': _('Final verdict'),
    'result': _('Similarity'),
    'status': _('Status'),
    'author': _('Author'),
    'report': _('Report'),
    'job': _('Job'),
    'format': _('Format'),
    'number': '№',
    'num_of_links': _('Number of associated leaf reports'),
}

STATUS_COLOR = {
    '0': '#D11919',
    '1': '#FF8533',
    '2': '#FF8533',
    '3': '#00B800',
}

UNSAFE_COLOR = {
    '0': '#A739CC',
    '1': '#D11919',
    '2': '#D11919',
    '3': '#FF8533',
    '4': '#D11919',
    '5': '#000000',
}

SAFE_COLOR = {
    '0': '#A739CC',
    '1': '#FF8533',
    '2': '#D11919',
    '3': '#D11919',
    '4': '#000000',
}

CHANGE_DATA = {
    '=': [_("Changed"), '#FF8533'],
    '+': [_("New"), '#00B800'],
    '-': [_("Deleted"), '#D11919']
}


def result_color(result):
    if 0 <= result <= 0.33:
        return '#E60000'
    elif 0.33 < result <= 0.66:
        return '#CC7A29'
    elif 0.66 < result <= 1:
        return '#00CC66'
    return None


class MarkChangesTable(object):

    def __init__(self, user, mark, changes):
        self.columns = ['report', 'change_kind', 'sum_verdict', 'job', 'format']
        self.mark = mark
        self.changes = changes
        self.__accessed_changes(user)
        self.attr_values_data = self.__add_attrs()
        self.header = Header(self.columns, MARK_TITLES).struct
        if isinstance(mark, MarkUnsafe):
            self.values = self.__get_unsafe_values()
        else:
            self.values = self.__get_safe_values()

    def __accessed_changes(self, user):
        for report in self.changes:
            if not JobAccess(user, report.root.job).can_view():
                del self.changes[report]

    def __add_attrs(self):
        data = {}
        attr_order = []
        for report in self.changes:
            for new_a in json.loads(report.attr_order):
                if new_a not in attr_order:
                    attr_order.append(new_a)
            for attr in report.attr.all():
                if attr.name.name not in data:
                    data[attr.name.name] = {}
                data[attr.name.name][report] = attr.value
        columns = []
        for name in attr_order:
            if name in data:
                columns.append(name)

        values_data = {}
        for report in self.changes:
            values_data[report] = {}
            for col in columns:
                cell_val = '-'
                if report in data[col]:
                    cell_val = data[col][report]
                values_data[report][col] = cell_val
        self.columns.extend(columns)
        return values_data

    def __get_unsafe_values(self):

        def colored_change(v1, v2, col1=None, col2=None):
            if col1 is not None and col2 is not None:
                return '<span style="color:%s">%s</span> ' \
                       '-> <span style="color:%s">%s</span>' % \
                       (col1, v1, col2, v2)
            return '<span>%s</span> -> <span>%s</span>' % (v1, v2)

        def get_verdict_change(rep):

            if all(x in self.changes[rep] for x in ['verdict1', 'verdict2']):
                tmp_unsafe = ReportUnsafe()
                tmp_unsafe.verdict = self.changes[rep]['verdict1']
                val1 = tmp_unsafe.get_verdict_display()
                if self.changes[rep]['verdict1'] == \
                        self.changes[rep]['verdict2']:
                    return '<span style="color:%s">%s</span>' % (
                        UNSAFE_COLOR[self.changes[rep]['verdict1']], val1)
                tmp_unsafe.verdict = self.changes[rep]['verdict2']
                val2 = tmp_unsafe.get_verdict_display()
                return colored_change(
                    val1, val2, UNSAFE_COLOR[self.changes[rep]['verdict1']],
                    UNSAFE_COLOR[self.changes[rep]['verdict2']])
            return '<span style="color:%s">%s</span>' % (
                UNSAFE_COLOR[rep.verdict],
                rep.get_verdict_display()
            )

        def get_status_change():
            v_set = self.mark.markunsafehistory_set.all().order_by('-version')
            last_version = v_set[0]
            try:
                prev_version = v_set[1]
            except IndexError:
                return '<span style="color:%s">%s</span>' % (
                    STATUS_COLOR[last_version.status],
                    last_version.get_status_display()
                )
            if prev_version.status == last_version.status:
                return '<span style="color:%s">%s</span>' % (
                    STATUS_COLOR[last_version.status],
                    last_version.get_status_display()
                )
            return colored_change(
                prev_version.get_status_display(),
                last_version.get_status_display(),
                STATUS_COLOR[prev_version.status],
                STATUS_COLOR[last_version.status]
            )

        def get_result_change(rep):
            if all(x in self.changes[rep] for x in ['result1', 'result2']):
                return colored_change(
                    "{:.0%}".format(self.changes[rep]['result1']),
                    "{:.0%}".format(self.changes[rep]['result2']),
                    result_color(self.changes[rep]['result1']),
                    result_color(self.changes[rep]['result2'])
                )
            elif 'result2' in self.changes[rep]:
                return '<span style="color:%s">%s</span>' % (
                    result_color(self.changes[rep]['result2']),
                    "{:.0%}".format(self.changes[rep]['result2']))
            else:
                return '-'

        values = []

        cnt = 0
        for report in self.changes:
            cnt += 1
            values_str = []
            for col in self.columns:
                val = '-'
                color = None
                href = None
                try:
                    report_mark = self.mark.markunsafereport_set.get(
                        report=report)
                except ObjectDoesNotExist:
                    report_mark = None
                if col in self.attr_values_data[report]:
                    val = self.attr_values_data[report][col]
                elif col == 'report':
                    val = cnt
                    href = reverse('reports:leaf', args=['unsafe', report.pk])
                elif col == 'sum_verdict':
                    val = get_verdict_change(report)
                elif col == 'status':
                    val = get_status_change()
                elif col == 'change_kind':
                    if self.changes[report]['kind'] in CHANGE_DATA:
                        val = CHANGE_DATA[self.changes[report]['kind']][0]
                        color = CHANGE_DATA[self.changes[report]['kind']][1]
                elif col == 'result':
                    if report_mark is not None and report_mark.broken:
                        val = '<span style="color:%s">%s</span>' % (
                            result_color(0), _("Comparison failed"))
                    else:
                        val = get_result_change(report)
                elif col == 'author':
                    if report_mark is not None:
                        val = "%s %s" % (
                            report_mark.mark.author.extended.last_name,
                            report_mark.mark.author.extended.first_name
                        )
                        href = reverse('users:show_profile',
                                       args=[report_mark.mark.author.pk])
                elif col == 'job':
                    val = report.root.job.name
                    href = reverse('jobs:job', args=[report.root.job.pk])
                elif col == 'format':
                    val = report.root.job.format
                values_str.append({
                    'value': val,
                    'color': color,
                    'href': href
                })
            values.append(values_str)
        return values

    def __get_safe_values(self):

        def colored_change(v1, v2, col1=None, col2=None):
            if col1 is not None and col2 is not None:
                return '<span style="color:%s">%s</span> ' \
                       '-> <span style="color:%s">%s</span>' % \
                       (col1, v1, col2, v2)
            return '<span>%s</span> -> <span>%s</span>' % (v1, v2)

        def get_verdict_change(rep):
            if all(x in self.changes[rep] for x in ['verdict1', 'verdict2']):
                tmp_safe = ReportSafe()
                tmp_safe.verdict = self.changes[rep]['verdict1']
                val1 = tmp_safe.get_verdict_display()
                if self.changes[rep]['verdict1'] == \
                        self.changes[rep]['verdict2']:
                    return '<span style="color:%s">%s</span>' % (
                        SAFE_COLOR[self.changes[rep]['verdict1']], val1)
                tmp_safe.verdict = self.changes[rep]['verdict2']
                val2 = tmp_safe.get_verdict_display()
                return colored_change(
                    val1, val2, SAFE_COLOR[self.changes[rep]['verdict1']],
                    SAFE_COLOR[self.changes[rep]['verdict2']])
            return '<span style="color:%s">%s</span>' % (
                SAFE_COLOR[rep.verdict],
                rep.get_verdict_display()
            )

        def get_status_change():
            v_set = self.mark.marksafehistory_set.all().order_by('-version')
            last_version = v_set[0]
            try:
                prev_version = v_set[1]
            except IndexError:
                return '<span style="color:%s">%s</span>' % (
                    STATUS_COLOR[last_version.status],
                    last_version.get_status_display()
                )
            if prev_version.status == last_version.status:
                return '<span style="color:%s">%s</span>' % (
                    STATUS_COLOR[last_version.status],
                    last_version.get_status_display()
                )
            return colored_change(
                prev_version.get_status_display(),
                last_version.get_status_display(),
                STATUS_COLOR[prev_version.status],
                STATUS_COLOR[last_version.status]
            )

        values = []

        cnt = 0
        for report in self.changes:
            cnt += 1
            values_str = []
            for col in self.columns:
                val = '-'
                color = None
                href = None
                try:
                    report_mark = self.mark.marksafereport_set.get(
                        report=report)
                except ObjectDoesNotExist:
                    continue
                if col in self.attr_values_data[report]:
                    val = self.attr_values_data[report][col]
                elif col == 'report':
                    val = cnt
                    href = reverse('reports:leaf', args=['safe', report.pk])
                elif col == 'sum_verdict':
                    val = get_verdict_change(report)
                elif col == 'status':
                    val = get_status_change()
                elif col == 'change_kind':
                    if self.changes[report]['kind'] in CHANGE_DATA:
                        val = CHANGE_DATA[self.changes[report]['kind']][0]
                        color = CHANGE_DATA[self.changes[report]['kind']][1]
                elif col == 'author':
                    val = "%s %s" % (
                        report_mark.mark.author.extended.last_name,
                        report_mark.mark.author.extended.first_name
                    )
                    href = reverse('users:show_profile',
                                   args=[report_mark.mark.author.pk])
                elif col == 'job':
                    val = report.root.job.name
                    href = reverse('jobs:job', args=[report.root.job.pk])
                elif col == 'format':
                    val = report.root.job.format
                values_str.append({
                    'value': val,
                    'color': color,
                    'href': href
                })
            values.append(values_str)
        return values


# Table data for showing links between the specified report and marks
class ReportMarkTable(object):
    def __init__(self, user, report):
        self.report = report
        self.type = 'safe'
        self.user = user
        self.columns = ['number', 'verdict']
        if isinstance(report, ReportUnsafe):
            self.columns.append('result')
            self.type = 'unsafe'
        elif not isinstance(report, ReportSafe):
            return
        self.columns.extend(['status', 'author'])
        self.header = Header(self.columns, MARK_TITLES).struct
        self.values = self.__get_values()

    def __get_values(self):
        value_data = []
        if isinstance(self.report, ReportUnsafe):
            mr_set = self.report.markunsafereport_set.all().order_by('-result')
        else:
            mr_set = self.report.marksafereport_set.all()
        cnt = 0
        for mark_rep in mr_set:
            cnt += 1
            values_row = []
            for col in self.columns:
                value = '-'
                href = None
                color = None
                if col == 'number':
                    value = cnt
                    href = reverse('marks:edit_mark',
                                   args=[self.type, mark_rep.mark.pk])
                elif col == 'verdict':
                    value = mark_rep.mark.get_verdict_display()
                    if self.type == 'unsafe':
                        color = UNSAFE_COLOR[mark_rep.mark.verdict]
                    else:
                        color = SAFE_COLOR[mark_rep.mark.verdict]
                elif col == 'result':
                    if mark_rep.broken:
                        value = _("Comparison failed")
                        color = result_color(0)
                    else:
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


class MarksList(object):

    def __init__(self, user, marks_type):
        self.columns = ['mark_num', 'num_of_links', 'verdict']
        if marks_type != 'unsafe' and marks_type != 'safe':
            return
        self.type = marks_type
        self.user = user
        self.columns.extend(['status', 'author', 'format'])
        self.attr_values_data, self.marks = self.__add_attrs()
        self.header = Header(self.columns, MARK_TITLES).struct
        self.values = self.__get_values()

    def __add_attrs(self):
        data = {}
        marks = []
        attr_order = []
        if self.type == 'unsafe':
            for mark in MarkUnsafe.objects.all():
                for new_a in json.loads(mark.attr_order):
                    if new_a not in attr_order:
                        attr_order.append(new_a)
                last_v = mark.markunsafehistory_set.get(version=mark.version)
                for attr in last_v.markunsafeattr_set.all():
                    if attr.is_compare:
                        if attr.attr.name.name not in data:
                            data[attr.attr.name.name] = {}
                        data[attr.attr.name.name][mark] = attr.attr.value
                marks.append(mark)
        else:
            for mark in MarkSafe.objects.all():
                for new_a in json.loads(mark.attr_order):
                    if new_a not in attr_order:
                        attr_order.append(new_a)
                last_v = mark.marksafehistory_set.get(version=mark.version)
                for attr in last_v.marksafeattr_set.all():
                    if attr.is_compare:
                        if attr.attr.name.name not in data:
                            data[attr.attr.name.name] = {}
                        data[attr.attr.name.name][mark] = attr.attr.value
                marks.append(mark)

        columns = []
        for name in attr_order:
            if name in data:
                columns.append(name)

        values_data = {}
        for mark in marks:
            values_data[mark] = {}
            for col in columns:
                cell_val = '-'
                if mark in data[col]:
                    cell_val = data[col][mark]
                values_data[mark][col] = cell_val
        self.columns.extend(columns)
        return values_data, marks

    def __get_values(self):
        values = []

        cnt = 0
        for mark in self.marks:
            cnt += 1
            values_str = []
            for col in self.columns:
                val = '-'
                color = None
                href = None
                if col in self.attr_values_data[mark]:
                    val = self.attr_values_data[mark][col]
                elif col == 'mark_num':
                    val = cnt
                    href = reverse('marks:edit_mark',
                                   args=[self.type, mark.pk])
                elif col == 'num_of_links':
                    if self.type == 'unsafe':
                        broken = len(
                            mark.markunsafereport_set.filter(broken=True))
                        if broken > 0:
                            val = _('%(all)s (%(broken)s are broken)') % {
                                'all': len(mark.markunsafereport_set.all()),
                                'broken': broken
                            }
                        else:
                            val = len(mark.markunsafereport_set.all())
                    else:
                        val = len(mark.marksafereport_set.all())
                elif col == 'verdict':
                    val = mark.get_verdict_display()
                    if self.type == 'safe':
                        color = SAFE_COLOR[mark.verdict]
                    else:
                        color = UNSAFE_COLOR[mark.verdict]
                elif col == 'status':
                    val = mark.get_status_display()
                    color = STATUS_COLOR[mark.status]
                elif col == 'author':
                    val = "%s %s" % (
                        mark.author.extended.last_name,
                        mark.author.extended.first_name
                    )
                    href = reverse('users:show_profile', args=[mark.author.pk])
                elif col == 'format':
                    val = mark.format
                values_str.append({'color': color, 'value': val, 'href': href})
            values.append(values_str)
        return values


class MarkAttrTable(object):

    def __init__(self, report=None, mark_version=None):
        self.report = report
        self.mark_version = mark_version
        self.header, self.values = self.__self_attrs()

    def __self_attrs(self):
        columns = []
        values = []
        if isinstance(self.mark_version, MarkUnsafeHistory):
            for name in json.loads(self.mark_version.mark.attr_order):
                try:
                    attr = self.mark_version.markunsafeattr_set.get(
                        attr__name__name=name)
                except ObjectDoesNotExist:
                    continue
                columns.append(attr.attr.name.name)
                values.append(
                    (attr.attr.name.name, attr.attr.value, attr.is_compare)
                )
        elif isinstance(self.mark_version, MarkSafeHistory):
            for name in json.loads(self.mark_version.mark.attr_order):
                try:
                    attr = self.mark_version.marksafeattr_set.get(
                        attr__name__name=name)
                except ObjectDoesNotExist:
                    continue
                columns.append(attr.attr.name.name)
                values.append(
                    (attr.attr.name.name, attr.attr.value, attr.is_compare)
                )
        else:
            for name in json.loads(self.report.attr_order):
                try:
                    attr = self.report.attr.get(name__name=name)
                except ObjectDoesNotExist:
                    continue
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
                    'checked': False,
                    'color': SAFE_COLOR[verdict[0]]
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
            if ((isinstance(self.mark_version, MarkUnsafeHistory) or
                isinstance(self.mark_version, MarkSafeHistory)) and
                    status_data['value'] == self.mark_version.status) or \
                    (self.mark_version is None and status_data['value'] == '0'):
                status_data['checked'] = True
            statuses.append(status_data)
        return statuses

    def __functions(self, func_type='compare'):
        if self.type != 'unsafe':
            return [], None
        functions = []
        if func_type == 'compare':
            selected_description = None

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
                        f.name == DEFAULT_COMPARE):
                    func_data['selected'] = True
                    selected_description = f.description
                functions.append(func_data)
        elif func_type == 'convert':
            if self.mark_version is not None:
                return [], None

            selected_description = None

            for f in MarkUnsafeConvert.objects.all().order_by('name'):
                func_data = {
                    'name': f.name,
                    'selected': False,
                    'value': f.pk,
                }
                if f.name == DEFAULT_CONVERT:
                    func_data['selected'] = True
                    selected_description = f.description
                functions.append(func_data)
        else:
            return [], None
        return functions, selected_description


# Table data for showing links between the specified mark and reports
class MarkReportsTable(object):
    def __init__(self, user, mark):
        self.columns = ['report', 'job']
        self.type = 'safe'
        self.user = user
        if isinstance(mark, MarkUnsafe):
            self.columns.append('result')
            self.type = 'unsafe'
        elif not isinstance(mark, MarkSafe):
            return
        self.mark = mark
        self.header = Header(self.columns, MARK_TITLES).struct
        self.values = self.__get_values()

    def __get_values(self):
        if self.type == 'unsafe':
            m_r_set = self.mark.markunsafereport_set.all().order_by('-result')
        else:
            m_r_set = self.mark.marksafereport_set.all()
        values = []
        cnt = 0
        for mark_report in m_r_set:
            report = mark_report.report
            cnt += 1
            values_str = []
            for col in self.columns:
                try:
                    if self.type == 'unsafe':
                        report_mark = self.mark.markunsafereport_set.get(
                            report=report)
                    else:
                        report_mark = self.mark.marksafereport_set.get(
                            report=report)
                except ObjectDoesNotExist:
                    continue
                val = '-'
                color = None
                href = None
                if col == 'report':
                    val = cnt
                    if JobAccess(self.user, report.root.job).can_view():
                        href = reverse('reports:leaf',
                                       args=[self.type, report.pk])
                elif col == 'result':
                    if report_mark.broken:
                        val = _("Comparison failed")
                        color = result_color(0)
                    else:
                        val = "{:.0%}".format(report_mark.result)
                        color = result_color(report_mark.result)
                elif col == 'job':
                    val = report.root.job.name
                    if JobAccess(self.user, report.root.job).can_view():
                        href = reverse('jobs:job', args=[report.root.job.pk])
                values_str.append({'value': val, 'href': href, 'color': color})
            values.append(values_str)
        return values


# Table data for showing links between the specified mark and reports,
# old version
class MarkReportsTable2(object):
    def __init__(self, user, mark):
        self.columns = ['report', 'verdict']
        self.type = 'safe'
        self.user = user
        if isinstance(mark, MarkUnsafe):
            self.columns.append('result')
            self.type = 'unsafe'
        elif not isinstance(mark, MarkSafe):
            return
        self.columns.extend(['status', 'author', 'job', 'format'])
        self.mark = mark
        self.attr_values_data, self.reports = self.__add_attrs()
        self.header = Header(self.columns, MARK_TITLES).struct
        self.values = self.__get_values()

    def __add_attrs(self):
        data = {}
        if self.type == 'unsafe':
            m_r_set = self.mark.markunsafereport_set.all().order_by('-result')
        else:
            m_r_set = self.mark.marksafereport_set.all()
        reports = []
        attr_order = []
        for mark_report in m_r_set:
            report = mark_report.report
            if not JobAccess(self.user, report.root.job).can_view():
                continue
            for new_a in json.loads(report.attr_order):
                if new_a not in attr_order:
                    attr_order.append(new_a)
            for attr in report.attr.all():
                if attr.name.name not in data:
                    data[attr.name.name] = {}
                data[attr.name.name][report] = attr.value
            reports.append(report)

        columns = []
        for name in attr_order:
            if name in data:
                columns.append(name)

        values_data = {}
        for report in reports:
            values_data[report] = {}
            for col in columns:
                cell_val = '-'
                if report in data[col]:
                    cell_val = data[col][report]
                values_data[report][col] = cell_val
        self.columns.extend(columns)
        return values_data, reports

    def __get_values(self):
        values = []
        cnt = 0
        for report in self.reports:
            cnt += 1
            values_str = []
            for col in self.columns:
                try:
                    if self.type == 'unsafe':
                        report_mark = self.mark.markunsafereport_set.get(
                            report=report)
                    else:
                        report_mark = self.mark.marksafereport_set.get(
                            report=report)
                except ObjectDoesNotExist:
                    continue
                val = '-'
                color = None
                href = None
                if col in self.attr_values_data[report]:
                    val = self.attr_values_data[report][col]
                elif col == 'report':
                    val = cnt
                    if JobAccess(self.user, report.root.job).can_view():
                        href = reverse('reports:leaf',
                                       args=[self.type, report.pk])
                elif col == 'verdict':
                    val = report.get_verdict_display()
                    color = UNSAFE_COLOR[report.verdict]
                elif col == 'status':
                    if self.type == 'unsafe':
                        l_v = self.mark.markunsafehistory_set.get(
                            version=self.mark.version)
                    else:
                        l_v = self.mark.marksafehistory_set.get(
                            version=self.mark.version)
                    val = l_v.get_status_display()
                    color = STATUS_COLOR[l_v.status]
                elif col == 'result':
                    if report_mark.broken:
                        val = _("Comparison failed")
                        color = result_color(0)
                    else:
                        val = "{:.0%}".format(report_mark.result)
                        color = result_color(report_mark.result)
                elif col == 'author':
                    val = "%s %s" % (
                        report_mark.mark.author.extended.last_name,
                        report_mark.mark.author.extended.first_name
                    )
                    href = reverse('users:show_profile',
                                   args=[report_mark.mark.author.pk])
                elif col == 'job':
                    val = report.root.job.name
                    if JobAccess(self.user, report.root.job).can_view():
                        href = reverse('jobs:job', args=[report.root.job.pk])
                elif col == 'format':
                    val = report.root.job.format
                values_str.append({'value': val, 'href': href, 'color': color})
            values.append(values_str)
        return values
