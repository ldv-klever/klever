import json
from django.core.urlresolvers import reverse
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.utils.translation import ugettext_lazy as _
from bridge.tableHead import Header
from bridge.vars import MARKS_UNSAFE_VIEW, MARKS_SAFE_VIEW, MARKS_UNKNOWN_VIEW
from marks.models import *
from jobs.utils import JobAccess
from marks.CompareTrace import DEFAULT_COMPARE
from marks.ConvertTrace import DEFAULT_CONVERT


MARK_TITLES = {
    'mark_num': '№',
    'change_kind': _('Change kind'),
    'verdict': _("Verdict"),
    'sum_verdict': _('Total verdict'),
    'result': _('Similarity'),
    'status': _('Status'),
    'author': _('Author'),
    'report': _('Report'),
    'job': _('Job'),
    'format': _('Format'),
    'number': '№',
    'num_of_links': _('Number of associated leaf reports'),
    'problem': _("Problem"),
    'component': _('Component'),
    'pattern': _('Problem pattern'),
    'checkbox': ''
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
        if isinstance(mark, MarkUnknown):
            self.columns = ['report', 'change_kind', 'job', 'format']
        self.mark = mark
        self.changes = changes
        self.__accessed_changes(user)
        if not isinstance(mark, MarkUnknown):
            self.attr_values_data = self.__add_attrs()
        self.header = Header(self.columns, MARK_TITLES).struct
        if isinstance(mark, MarkUnsafe):
            self.values = self.__get_unsafe_values()
        elif isinstance(mark, MarkSafe):
            self.values = self.__get_safe_values()
        elif isinstance(mark, MarkUnknown):
            self.values = self.__get_unknown_values()

    def __accessed_changes(self, user):
        for report in self.changes:
            if not JobAccess(user, report.root.job).can_view():
                del self.changes[report]

    def __add_attrs(self):
        data = {}
        columns = []
        for report in self.changes:
            for rep_attr in report.attrs.order_by('id'):
                if rep_attr.attr.name.name not in columns:
                    columns.append(rep_attr.attr.name.name)
                if rep_attr.attr.name.name not in data:
                    data[rep_attr.attr.name.name] = {}
                data[rep_attr.attr.name.name][report] = rep_attr.attr.value
        values = {}
        for report in self.changes:
            values[report] = {}
            for col in columns:
                cell_val = '-'
                if report in data[col]:
                    cell_val = data[col][report]
                values[report][col] = cell_val
        self.columns.extend(columns)
        return values

    def __get_unsafe_values(self):

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
                return '<span style="color:%s">%s</span> -> ' \
                       '<span style="color:%s">%s</span>' % \
                       (UNSAFE_COLOR[self.changes[rep]['verdict1']], val1,
                        UNSAFE_COLOR[self.changes[rep]['verdict2']], val2)
            return '<span style="color:%s">%s</span>' % (
                UNSAFE_COLOR[rep.verdict],
                rep.get_verdict_display()
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
                if col in self.attr_values_data[report]:
                    val = self.attr_values_data[report][col]
                elif col == 'report':
                    val = cnt
                    href = reverse('reports:leaf', args=['unsafe', report.pk])
                elif col == 'sum_verdict':
                    val = get_verdict_change(report)
                elif col == 'status':
                    val = self.__status_change()
                elif col == 'change_kind':
                    if self.changes[report]['kind'] in CHANGE_DATA:
                        val = CHANGE_DATA[self.changes[report]['kind']][0]
                        color = CHANGE_DATA[self.changes[report]['kind']][1]
                elif col == 'author':
                    if self.mark.author is not None:
                        val = "%s %s" % (
                            self.mark.author.extended.last_name,
                            self.mark.author.extended.first_name
                        )
                        href = reverse('users:show_profile',
                                       args=[self.mark.author.pk])
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
                return '<span style="color:%s">%s</span> -> ' \
                       '<span style="color:%s">%s</span>' % \
                       (SAFE_COLOR[self.changes[rep]['verdict1']], val1,
                        SAFE_COLOR[self.changes[rep]['verdict2']], val2)
            return '<span style="color:%s">%s</span>' % (
                SAFE_COLOR[rep.verdict],
                rep.get_verdict_display()
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
                if col in self.attr_values_data[report]:
                    val = self.attr_values_data[report][col]
                elif col == 'report':
                    val = cnt
                    href = reverse('reports:leaf', args=['safe', report.pk])
                elif col == 'sum_verdict':
                    val = get_verdict_change(report)
                elif col == 'status':
                    val = self.__status_change()
                elif col == 'change_kind':
                    if self.changes[report]['kind'] in CHANGE_DATA:
                        val = CHANGE_DATA[self.changes[report]['kind']][0]
                        color = CHANGE_DATA[self.changes[report]['kind']][1]
                elif col == 'author':
                    val = "%s %s" % (
                        self.mark.author.extended.last_name,
                        self.mark.author.extended.first_name
                    )
                    href = reverse('users:show_profile',
                                   args=[self.mark.author.pk])
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

    def __status_change(self):
        version_set = self.mark.versions.all().order_by('-version')
        last_version = version_set[0]
        try:
            prev_version = version_set[1]
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
        return '<span style="color:%s">%s</span> ' \
               '-> <span style="color:%s">%s</span>' % \
               (STATUS_COLOR[prev_version.status],
                prev_version.get_status_display(),
                STATUS_COLOR[last_version.status],
                last_version.get_status_display())

    def __get_unknown_values(self):
        values = []
        cnt = 0
        for report in self.changes:
            cnt += 1
            values_str = []
            for col in self.columns:
                val = '-'
                color = None
                href = None
                if col == 'report':
                    val = cnt
                    href = reverse('reports:leaf', args=['unknown', report.pk])
                elif col == 'status':
                    val = self.__status_change()
                elif col == 'change_kind':
                    if self.changes[report]['kind'] in CHANGE_DATA:
                        val = CHANGE_DATA[self.changes[report]['kind']][0]
                        color = CHANGE_DATA[self.changes[report]['kind']][1]
                elif col == 'author':
                    val = "%s %s" % (
                        self.mark.author.extended.last_name,
                        self.mark.author.extended.first_name
                    )
                    href = reverse('users:show_profile',
                                   args=[self.mark.author.pk])
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
        self.user = user
        if isinstance(report, ReportUnsafe):
            self.columns = ['number', 'verdict', 'result', 'status', 'author']
            self.type = 'unsafe'
        elif isinstance(report, ReportSafe):
            self.columns = ['number', 'verdict', 'status', 'author']
            self.type = 'safe'
        elif isinstance(report, ReportUnknown):
            self.columns = ['number', 'problem', 'status', 'author']
            self.type = 'unknown'
        else:
            return
        self.header = Header(self.columns, MARK_TITLES).struct
        self.values = self.__get_values()

    def __get_values(self):
        value_data = []
        cnt = 0
        for mark_rep in self.report.markreport_set.all():
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
                elif col == 'problem':
                    value = mark_rep.problem.name
                    if mark_rep.mark.link is not None:
                        href = mark_rep.mark.link
                        if not href.startswith('http'):
                            href = 'http://' + mark_rep.mark.link
                values_row.append({
                    'value': value, 'href': href, 'color': color
                })
            value_data.append(values_row)
        return value_data


class MarksList(object):

    def __init__(self, user, marks_type, view=None, view_id=None):
        self.user = user
        self.type = marks_type
        if self.type not in ['unsafe', 'safe', 'unknown']:
            return
        self.authors = []
        self.view, self.view_id = self.__get_view(view, view_id)
        self.columns = self.__get_columns()
        self.marks = self.__get_marks()
        if self.type != 'unknown':
            self.attr_values = self.__get_attrs()
        self.header = Header(self.columns, MARK_TITLES).struct
        self.values = self.__get_values()

    def __get_view(self, view, view_id):
        def_views = {
            'unsafe': MARKS_UNSAFE_VIEW,
            'safe': MARKS_SAFE_VIEW,
            'unknown': MARKS_UNKNOWN_VIEW
        }
        view_types = {
            'unsafe': '7',
            'safe': '8',
            'unknown': '9',
        }

        if view is not None:
            return json.loads(view), None
        if view_id is None:
            pref_view = self.user.preferableview_set.filter(
                view__type=view_types[self.type])
            if len(pref_view) > 0:
                return json.loads(pref_view[0].view.view), pref_view[0].view_id
        elif view_id == 'default':
            return def_views[self.type], 'default'
        else:
            try:
                user_view = self.user.view_set.get(
                    pk=int(view_id), type=view_types[self.type])
                return json.loads(user_view.view), user_view.pk
            except ObjectDoesNotExist:
                pass
        return def_views[self.type], 'default'

    def __get_columns(self):
        columns = ['checkbox', 'mark_num']
        if self.type == 'unknown':
            for col in ['num_of_links', 'status', 'component', 'author', 'format', 'pattern']:
                if col in self.view['columns']:
                    columns.append(col)
        else:
            for col in ['num_of_links', 'verdict', 'status', 'author', 'format']:
                if col in self.view['columns']:
                    columns.append(col)
        return columns

    def __get_marks(self):
        filters = {}
        unfilter = {}
        if 'filters' in self.view:
            if 'status' in self.view['filters']:
                if self.view['filters']['status']['type'] == 'is':
                    filters['status'] = self.view['filters']['status']['value']
                else:
                    unfilter['status'] = self.view['filters']['status']['value']
            if self.type != 'unknown' and 'verdict' in self.view['filters']:
                if self.view['filters']['verdict']['type'] == 'is':
                    filters['verdict'] = self.view['filters']['verdict']['value']
                else:
                    unfilter['verdict'] = self.view['filters']['verdict']['value']
            if 'component' in self.view['filters']:
                if self.view['filters']['component']['type'] == 'is':
                    filters['component__name'] = self.view['filters']['component']['value']
                elif self.view['filters']['component']['type'] == 'startswith':
                    filters['component__name__istartswith'] = self.view['filters']['component']['value']
            if 'author' in self.view['filters']:
                filters['author_id'] = self.view['filters']['author']['value']

        if self.type == 'unsafe':
            return MarkUnsafe.objects.filter(Q(**filters) & ~Q(**unfilter))
        elif self.type == 'safe':
            return MarkSafe.objects.filter(Q(**filters) & ~Q(**unfilter))
        return MarkUnknown.objects.filter(Q(**filters) & ~Q(**unfilter))

    def __get_attrs(self):
        data = {}
        columns = []
        for mark in self.marks:
            try:
                for attr in mark.versions.get(version=mark.version).attrs.order_by('id'):
                    if attr.is_compare:
                        if attr.attr.name.name not in columns:
                            columns.append(attr.attr.name.name)
                        if attr.attr.name.name not in data:
                            data[attr.attr.name.name] = {}
                        data[attr.attr.name.name][mark] = attr.attr.value
            except ObjectDoesNotExist:
                pass
        values = {}
        for mark in self.marks:
            values[mark] = {}
            for col in columns:
                cell_val = '-'
                if mark in data[col]:
                    cell_val = data[col][mark]
                values[mark][col] = cell_val
        self.columns.extend(columns)
        return values

    def __get_values(self):
        values = []
        cnt = 0
        for mark in self.marks:
            if mark.author not in self.authors:
                self.authors.append(mark.author)
            cnt += 1
            values_str = []
            order_by_value = ''
            for col in self.columns:
                val = '-'
                color = None
                href = None
                if self.type != 'unknown' and col in self.attr_values[mark]:
                    val = self.attr_values[mark][col]
                    if 'order' in self.view and self.view['order'] == col:
                        order_by_value = val
                    if 'filters' in self.view and not self.__filter_attr(col, val):
                        break
                elif col == 'mark_num':
                    val = cnt
                    href = reverse('marks:edit_mark',
                                   args=[self.type, mark.pk])
                elif col == 'num_of_links':
                    val = len(mark.markreport_set.all())
                    if 'order' in self.view and self.view['order'] == 'num_of_links':
                        order_by_value = val
                    if self.type == 'unsafe':
                        broken = len(mark.markreport_set.filter(broken=True))
                        if broken > 0:
                            val = _('%(all)s (%(broken)s are broken)') % {
                                'all': len(mark.markreport_set.all()),
                                'broken': broken
                            }
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
                elif col == 'component':
                    val = mark.component.name
                elif col == 'pattern':
                    val = mark.problem_pattern
                if col == 'checkbox':
                    values_str.append({'checkbox': mark.pk})
                else:
                    values_str.append({'color': color, 'value': val, 'href': href})
            else:
                values.append((order_by_value, values_str))

        ordered_values = []
        if 'order' in self.view and self.view['order'] == 'num_of_links':
            for ord_by, val_str in reversed(sorted(values, key=lambda x: x[0])):
                ordered_values.append(val_str)
        elif 'order' in self.view:
            for ord_by, val_str in sorted(values, key=lambda x: x[0]):
                ordered_values.append(val_str)
        else:
            ordered_values = list(x[1] for x in values)
        return ordered_values

    def __filter_attr(self, attribute, value):
        if 'attr' in self.view['filters'] and self.view['filters']['attr']['attr'] == attribute:
            fvalue = self.view['filters']['attr']['value']
            ftype = self.view['filters']['attr']['type']
            if ftype == 'iexact' and fvalue.lower() != value.lower():
                return False
            elif ftype == 'istartswith' and not value.lower().startswith(fvalue.lower()):
                return False
        return True


class MarkData(object):
    def __init__(self, mark_type, mark_version=None, report=None):
        self.type = mark_type
        self.mark_version = mark_version
        self.verdicts = self.__verdict_info()
        self.statuses = self.__status_info()
        if isinstance(self.mark_version, MarkUnsafeHistory) or isinstance(report, ReportUnsafe):
            self.comparison, self.compare_desc = self.__functions('compare')
            self.convertion, self.convert_desc = self.__functions('convert')
        self.unknown_data = self.__unknown_info()
        self.attributes = self.__get_attributes(report)
        self.description = ''
        if isinstance(self.mark_version,
                      (MarkUnsafeHistory, MarkSafeHistory, MarkUnknownHistory)):
            self.description = self.mark_version.description

    def __get_attributes(self, report):
        values = []
        if isinstance(self.mark_version, (MarkUnsafeHistory, MarkSafeHistory)):
            for attr in self.mark_version.attrs.order_by('id'):
                values.append((attr.attr.name.name, attr.attr.value, attr.is_compare))
        elif isinstance(report, (ReportUnsafe, ReportSafe)):
            for rep_attr in report.attrs.order_by('id'):
                values.append((rep_attr.attr.name.name, rep_attr.attr.value, True))
        else:
            return None
        return values

    def __unknown_info(self):
        unknown_markdata = []
        if not isinstance(self.mark_version, MarkUnknownHistory):
            return unknown_markdata
        unknown_markdata.extend([self.mark_version.function,
                                 self.mark_version.problem_pattern,
                                 self.mark_version.link])
        return unknown_markdata

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
                isinstance(self.mark_version, MarkSafeHistory) or
                isinstance(self.mark_version, MarkUnknownHistory)) and
                    verdict[0] == self.mark_version.status) or \
                    (self.mark_version is None and verdict[0] == MARK_STATUS[0][0]):
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
                elif f.name == DEFAULT_COMPARE:
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
        self.user = user
        if isinstance(mark, MarkUnsafe):
            self.columns.append('result')
            self.type = 'unsafe'
        elif isinstance(mark, MarkSafe):
            self.type = 'safe'
        elif isinstance(mark, MarkUnknown):
            self.type = 'unknown'
        else:
            return
        self.mark = mark
        self.header = Header(self.columns, MARK_TITLES).struct
        self.values = self.__get_values()

    def __get_values(self):
        values = []
        cnt = 0
        for mark_report in self.mark.markreport_set.all():
            report = mark_report.report
            cnt += 1
            values_str = []
            for col in self.columns:
                val = '-'
                color = None
                href = None
                if col == 'report':
                    val = cnt
                    if JobAccess(self.user, report.root.job).can_view():
                        href = reverse('reports:leaf', args=[self.type, report.pk])
                elif col == 'result':
                    if mark_report.broken:
                        val = _("Comparison failed")
                        color = result_color(0)
                    else:
                        val = "{:.0%}".format(mark_report.result)
                        color = result_color(mark_report.result)
                elif col == 'job':
                    val = report.root.job.name
                    if JobAccess(self.user, report.root.job).can_view():
                        href = reverse('jobs:job', args=[report.root.job.pk])
                values_str.append({'value': val, 'href': href, 'color': color})
            values.append(values_str)
        return values
