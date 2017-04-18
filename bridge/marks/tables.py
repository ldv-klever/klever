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
from django.core.urlresolvers import reverse
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q, F
from django.utils.translation import ugettext_lazy as _, ungettext_lazy
from bridge.tableHead import Header
from bridge.vars import MARKS_UNSAFE_VIEW, MARKS_SAFE_VIEW, MARKS_UNKNOWN_VIEW, MARKS_COMPARE_ATTRS
from bridge.utils import unique_id
from users.models import View
from marks.models import *
from jobs.utils import JobAccess
from marks.CompareTrace import DEFAULT_COMPARE
from marks.ConvertTrace import DEFAULT_CONVERT


MARK_TITLES = {
    'mark_num': '№',
    'report_num': _('Number of reports'),
    'change_kind': _('Change kind'),
    'verdict': _("Verdict"),
    'sum_verdict': _('Total verdict'),
    'result': _('Similarity'),
    'status': _('Status'),
    'author': _('Last change author'),
    'report': _('Report'),
    'job': _('Job'),
    'format': _('Format'),
    'number': '№',
    'num_of_links': _('Number of associated leaf reports'),
    'problem': _("Problem"),
    'component': _('Component'),
    'pattern': _('Problem pattern'),
    'checkbox': '',
    'type': _('Source'),
    'is_prime': _('Automatic association'),
    'has_prime': _('Has non-automatic association'),
    'tags': _('Tags')
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
    '=': (_("Changed"), '#FF8533'),
    '+': (_("New"), '#00B800'),
    '-': (_("Deleted"), '#D11919')
}


def result_color(result):
    if 0 <= result <= 0.33:
        return '#E60000'
    elif 0.33 < result <= 0.66:
        return '#CC7A29'
    elif 0.66 < result <= 1:
        return '#00CC66'
    return None


class MarkChangesTable:
    def __init__(self, user, mark, changes):
        self.columns = ['report', 'change_kind', 'sum_verdict', 'job', 'format']
        if isinstance(mark, MarkUnknown):
            self.columns = ['report', 'change_kind', 'job', 'format']
        self.mark = mark
        self.changes = changes
        self.__accessed_changes(user)
        if not isinstance(mark, MarkUnknown):
            self.attr_values_data = self.__add_attrs()
        if isinstance(mark, MarkUnsafe):
            self.values = self.__get_unsafe_values()
            self.mark_type = 'unsafe'
        elif isinstance(mark, MarkSafe):
            self.values = self.__get_safe_values()
            self.mark_type = 'safe'
        elif isinstance(mark, MarkUnknown):
            self.values = self.__get_unknown_values()
            self.mark_type = 'unknown'
        else:
            return
        self.cache_id = self.__save_data(user)

    def __save_data(self, user):
        try:
            cache = MarkAssociationsChanges.objects.get(user=user)
        except ObjectDoesNotExist:
            cache = MarkAssociationsChanges(user=user)
        cache.identifier = unique_id()
        cache.table_data = json.dumps({
            'mark_type': self.mark_type,
            'mark_id': self.mark.pk,
            'columns': self.columns,
            'values': self.values
        }, ensure_ascii=False, sort_keys=True, indent=4)
        cache.save()
        return cache.identifier

    def __accessed_changes(self, user):
        for report in self.changes:
            if not JobAccess(user, report.root.job).can_view():
                del self.changes[report]

    def __add_attrs(self):
        data = {}
        columns = []
        for report in self.changes:
            for ra in report.attrs.order_by('id').values_list('attr__name__name', 'attr__value'):
                if ra[0] not in columns:
                    columns.append(ra[0])
                if ra[0] not in data:
                    data[ra[0]] = {}
                data[ra[0]][report] = ra[1]
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
            if all(x in self.changes[rep] for x in {'verdict1', 'verdict2'}):
                tmp_unsafe = ReportUnsafe()
                tmp_unsafe.verdict = self.changes[rep]['verdict1']
                val1 = tmp_unsafe.get_verdict_display()
                if self.changes[rep]['verdict1'] == self.changes[rep]['verdict2']:
                    return '<span style="color:%s">%s</span>' % (UNSAFE_COLOR[self.changes[rep]['verdict1']], val1)
                tmp_unsafe.verdict = self.changes[rep]['verdict2']
                val2 = tmp_unsafe.get_verdict_display()
                return '<span style="color:%s">%s</span> -> <span style="color:%s">%s</span>' % (
                    UNSAFE_COLOR[self.changes[rep]['verdict1']], val1, UNSAFE_COLOR[self.changes[rep]['verdict2']], val2
                )
            return '<span style="color:%s">%s</span>' % (UNSAFE_COLOR[rep.verdict], rep.get_verdict_display())

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
                    href = reverse('reports:unsafe', args=[report.pk])
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
                        val = self.mark.author.get_full_name()
                        href = reverse('users:show_profile', args=[self.mark.author_id])
                elif col == 'job':
                    val = report.root.job.name
                    href = reverse('jobs:job', args=[report.root.job_id])
                elif col == 'format':
                    val = report.root.job.format
                values_str.append({
                    'value': str(val),
                    'color': color,
                    'href': href
                })
            values.append(values_str)
        return values

    def __get_safe_values(self):

        def get_verdict_change(rep):
            if all(x in self.changes[rep] for x in {'verdict1', 'verdict2'}):
                tmp_safe = ReportSafe()
                tmp_safe.verdict = self.changes[rep]['verdict1']
                val1 = tmp_safe.get_verdict_display()
                if self.changes[rep]['verdict1'] == self.changes[rep]['verdict2']:
                    return '<span style="color:%s">%s</span>' % (SAFE_COLOR[self.changes[rep]['verdict1']], val1)
                tmp_safe.verdict = self.changes[rep]['verdict2']
                val2 = tmp_safe.get_verdict_display()
                return '<span style="color:%s">%s</span> -> <span style="color:%s">%s</span>' % (
                    SAFE_COLOR[self.changes[rep]['verdict1']], val1, SAFE_COLOR[self.changes[rep]['verdict2']], val2
                )
            return '<span style="color:%s">%s</span>' % (SAFE_COLOR[rep.verdict], rep.get_verdict_display())

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
                    href = reverse('reports:safe', args=[report.pk])
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
                        val = self.mark.author.get_full_name()
                        href = reverse('users:show_profile', args=[self.mark.author_id])
                elif col == 'job':
                    val = report.root.job.name
                    href = reverse('jobs:job', args=[report.root.job_id])
                elif col == 'format':
                    val = report.root.job.format
                values_str.append({
                    'value': str(val),
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
                STATUS_COLOR[last_version.status], last_version.get_status_display()
            )
        if prev_version.status == last_version.status:
            return '<span style="color:%s">%s</span>' % (
                STATUS_COLOR[last_version.status], last_version.get_status_display()
            )
        return '<span style="color:%s">%s</span> -> <span style="color:%s">%s</span>' % (
            STATUS_COLOR[prev_version.status], prev_version.get_status_display(),
            STATUS_COLOR[last_version.status], last_version.get_status_display()
        )

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
                    href = reverse('reports:unknown', args=[report.pk])
                elif col == 'status':
                    val = self.__status_change()
                elif col == 'change_kind':
                    if self.changes[report]['kind'] in CHANGE_DATA:
                        val = CHANGE_DATA[self.changes[report]['kind']][0]
                        color = CHANGE_DATA[self.changes[report]['kind']][1]
                elif col == 'author':
                    if self.mark.author is not None:
                        val = self.mark.author.get_full_name()
                        href = reverse('users:show_profile', args=[self.mark.author_id])
                elif col == 'job':
                    val = report.root.job.name
                    href = reverse('jobs:job', args=[report.root.job_id])
                elif col == 'format':
                    val = report.root.job.format
                values_str.append({
                    'value': str(val),
                    'color': color,
                    'href': href
                })
            values.append(values_str)
        return values


# Table data for showing links between the specified report and marks
class ReportMarkTable:
    def __init__(self, user, report):
        self.report = report
        self.user = user
        if isinstance(report, ReportUnsafe):
            self.type = 'unsafe'
        elif isinstance(report, ReportSafe):
            self.type = 'safe'
        elif isinstance(report, ReportUnknown):
            self.type = 'unknown'
        else:
            return
        self.values = self.__get_values()

    def __get_values(self):
        value_data = []
        cnt = 0
        for mark_rep in self.report.markreport_set.select_related('mark', 'mark__author').order_by('mark__change_date'):
            cnt += 1
            row_data = {
                'id': mark_rep.mark_id,
                'number': cnt,
                'href': reverse('marks:view_mark', args=[self.type, mark_rep.mark_id]),
                'status': (mark_rep.mark.get_status_display(), STATUS_COLOR[mark_rep.mark.status]),
            }
            if self.type == 'unsafe':
                row_data['verdict'] = (mark_rep.mark.get_verdict_display(), UNSAFE_COLOR[mark_rep.mark.verdict])
                if mark_rep.broken:
                    row_data['similarity'] = (_("Comparison failed"), result_color(0), mark_rep.error)
                else:
                    row_data['similarity'] = ("{:.0%}".format(mark_rep.result), result_color(mark_rep.result), None)
            elif self.type == 'safe':
                row_data['verdict'] = (mark_rep.mark.get_verdict_display(), SAFE_COLOR[mark_rep.mark.verdict])
            else:
                problem_link = mark_rep.mark.link
                if problem_link is not None and not problem_link.startswith('http'):
                    problem_link = 'http://' + mark_rep.mark.link
                row_data['problem'] = (mark_rep.problem.name, problem_link)

            if mark_rep.mark.prime == self.report:
                row_data['is_prime'] = (_('No'), '#B12EAF')
            else:
                row_data['is_prime'] = (_('Yes'), '#000000')
            if mark_rep.mark.author is not None:
                row_data['author'] = (
                    mark_rep.mark.author.get_full_name(),
                    reverse('users:show_profile', args=[mark_rep.mark.author_id])
                )
            if len(mark_rep.mark.description) > 0:
                row_data['description'] = mark_rep.mark.description

            value_data.append(row_data)
        return value_data


class MarksList:
    def __init__(self, user, marks_type, view=None, view_id=None):
        self.user = user
        self.type = marks_type
        if self.type not in {'unsafe', 'safe', 'unknown'}:
            return
        view_types = {'unsafe': '7', 'safe': '8', 'unknown': '9'}
        self.view_type = view_types[self.type]

        self.authors = []
        self.view, self.view_id = self.__get_view(view, view_id)
        self.views = self.__views()
        self.columns = self.__get_columns()
        self.marks = self.__get_marks()
        if self.type != 'unknown':
            self.attr_values = self.__get_attrs()
        self.header = Header(self.columns, MARK_TITLES).struct
        self.values = self.__get_values()

    def __views(self):
        return View.objects.filter(Q(type=self.view_type) & (Q(author=self.user) | Q(shared=True))).order_by('name')

    def __get_view(self, view, view_id):
        def_views = {
            'unsafe': MARKS_UNSAFE_VIEW,
            'safe': MARKS_SAFE_VIEW,
            'unknown': MARKS_UNKNOWN_VIEW
        }

        if view is not None:
            return json.loads(view), None
        if view_id is None:
            pref_view = self.user.preferableview_set.filter(view__type=self.view_type)
            if len(pref_view) > 0:
                return json.loads(pref_view[0].view.view), pref_view[0].view_id
        elif view_id == 'default':
            return def_views[self.type], 'default'
        else:
            user_view = View.objects.filter(
                Q(id=view_id, type=self.view_type) & (Q(shared=True) | Q(author=self.user))
            ).first()
            if user_view:
                return json.loads(user_view.view), user_view.pk
        return def_views[self.type], 'default'

    def __get_columns(self):
        columns = ['checkbox', 'mark_num']
        if self.type == 'unknown':
            for col in ['num_of_links', 'status', 'component', 'author', 'format', 'pattern', 'type']:
                if col in self.view['columns']:
                    columns.append(col)
        else:
            for col in ['num_of_links', 'verdict', 'tags', 'status', 'author', 'format', 'type']:
                if col in self.view['columns']:
                    columns.append(col)
        return columns

    def __get_marks(self):
        filters = {}
        unfilter = {'version': 0}
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
            if 'type' in self.view['filters']:
                if self.view['filters']['type']['type'] == 'is':
                    filters['type'] = self.view['filters']['type']['value']
                else:
                    unfilter['type'] = self.view['filters']['type']['value']

        table_filters = Q(**filters)
        for uf in unfilter:
            table_filters = table_filters & ~Q(**{uf: unfilter[uf]})
        if self.type == 'unsafe':
            return MarkUnsafe.objects.filter(table_filters)
        elif self.type == 'safe':
            return MarkSafe.objects.filter(table_filters)
        return MarkUnknown.objects.filter(table_filters)

    def __get_attrs(self):
        if self.type == 'safe':
            vers_model = MarkSafeHistory
            attr_model = MarkSafeAttr
        else:
            vers_model = MarkUnsafeHistory
            attr_model = MarkUnsafeAttr
        last_versions = vers_model.objects.filter(version=F('mark__version'), mark__in=self.marks)

        data = {}
        attr_order = {}
        for ma in attr_model.objects.filter(mark__in=last_versions).order_by('id')\
                .values_list('mark__mark_id', 'attr__name__name', 'attr__value'):
            if ma[0] not in data:
                data[ma[0]] = {}
                attr_order[ma[0]] = []
            data[ma[0]][ma[1]] = ma[2]
            attr_order[ma[0]].append(ma[1])

        columns = []
        for mark in self.marks:
            if mark.id in attr_order:
                for a_name in attr_order[mark.id]:
                    if a_name not in columns:
                        columns.append(a_name)

        values = {}
        for mark in self.marks:
            values[mark] = {}
            for col in columns:
                cell_val = '-'
                if mark.id in data and col in data[mark.id]:
                    cell_val = data[mark.id][col]
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
                    href = reverse('marks:view_mark', args=[self.type, mark.id])
                elif col == 'num_of_links':
                    val = mark.markreport_set.count()
                    if 'order' in self.view and self.view['order'] == 'num_of_links':
                        order_by_value = val
                    if self.type == 'unsafe':
                        broken = len(mark.markreport_set.filter(broken=True))
                        if broken > 0:
                            val = ungettext_lazy(
                                '%(all)s (%(broken)s is broken)', '%(all)s (%(broken)s are broken)', broken
                            ) % {'all': len(mark.markreport_set.all()), 'broken': broken}
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
                    if mark.author is not None:
                        val = mark.author.get_full_name()
                        href = reverse('users:show_profile', args=[mark.author_id])
                elif col == 'format':
                    val = mark.format
                elif col == 'component':
                    val = mark.component.name
                elif col == 'pattern':
                    val = mark.problem_pattern
                elif col == 'type':
                    val = mark.get_type_display()
                elif col == 'tags':
                    last_v = mark.versions.get(version=mark.version)
                    if last_v is None:
                        val = '-'
                    else:
                        val = '; '.join(tag['tag__tag'] for tag in last_v.tags.order_by('tag__tag').values('tag__tag'))
                        if val == '':
                            val = '-'
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
        if isinstance(self.mark_version, (MarkUnsafeHistory, MarkSafeHistory, MarkUnknownHistory)):
            self.description = self.mark_version.description

    def __get_attributes(self, report):
        values = []
        if isinstance(self.mark_version, (MarkUnsafeHistory, MarkSafeHistory)):
            values = list(
                self.mark_version.attrs.order_by('id').values_list('attr__name__name', 'attr__value', 'is_compare')
            )
        elif isinstance(report, (ReportUnsafe, ReportSafe)):
            for ra in report.attrs.order_by('id').values_list('attr__name__name', 'attr__value'):
                is_compare = False
                if report.root.job.type in MARKS_COMPARE_ATTRS and ra[0] in MARKS_COMPARE_ATTRS[report.root.job.type]:
                    is_compare = True
                ra += (is_compare,)
                values.append(ra)
        else:
            return None
        return values

    def __unknown_info(self):
        if not isinstance(self.mark_version, MarkUnknownHistory):
            return []
        return [self.mark_version.function, self.mark_version.problem_pattern, self.mark_version.link]

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
                        (not isinstance(self.mark_version, MarkUnsafeHistory) and verdict_data['value'] == '0'):
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
                        (not isinstance(self.mark_version, MarkSafeHistory) and verdict_data['value'] == '0'):
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
            if (isinstance(self.mark_version, (MarkUnsafeHistory, MarkSafeHistory, MarkUnknownHistory)) and
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

            for f in MarkUnsafeCompare.objects.order_by('name'):
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

            for f in MarkUnsafeConvert.objects.order_by('name'):
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
        self.user = user
        if isinstance(mark, MarkUnsafe):
            self.type = 'unsafe'
            self.columns = ['report', 'job', 'result', 'is_prime']
        elif isinstance(mark, MarkSafe):
            self.type = 'safe'
            self.columns = ['job', 'report_num', 'has_prime']
        elif isinstance(mark, MarkUnknown):
            self.type = 'unknown'
            self.columns = ['job', 'report_num', 'has_prime']
        else:
            return
        self.mark = mark
        self.header = Header(self.columns, MARK_TITLES).struct
        self.values = self.__get_values()

    def __get_values(self):
        values = []
        cnt = 0
        if self.type == 'unsafe':
            for mark_report in self.mark.markreport_set.select_related('report', 'report__root__job'):
                report = mark_report.report
                cnt += 1
                values_str = []
                for col in self.columns:
                    val = '-'
                    color = None
                    href = None
                    comment = None
                    if col == 'report':
                        val = cnt
                        if JobAccess(self.user, report.root.job).can_view():
                            href = reverse('reports:%s' % self.type, args=[report.id])
                    elif col == 'result':
                        if mark_report.broken:
                            val = _("Comparison failed")
                            color = result_color(0)
                            if mark_report.error is not None:
                                comment = mark_report.error
                        else:
                            val = "{:.0%}".format(mark_report.result)
                            color = result_color(mark_report.result)
                    elif col == 'job':
                        val = report.root.job.name
                        if JobAccess(self.user, report.root.job).can_view():
                            href = reverse('jobs:job', args=[report.root.job_id])
                    elif col == 'is_prime':
                        if self.mark.prime == mark_report.report:
                            val = _('No')
                            color = '#B12EAF'
                        else:
                            val = _('Yes')
                    values_str.append({'value': val, 'href': href, 'color': color, 'comment': comment})
                values.append(values_str)
        else:
            report_filters = {
                'parent': None,
                'leaves__%s__markreport_set__mark' % self.type: self.mark
            }
            for report in ReportComponent.objects.filter(**report_filters).distinct().order_by('root__job__name')\
                    .select_related('root', 'root__job'):
                len_filter = {self.type + '__markreport_set__mark': self.mark}
                mark_leaves = report.leaves.filter(**len_filter)

                if self.mark.prime is not None and len(mark_leaves.filter(**{self.type: self.mark.prime})) > 0:
                    color = '#B12EAF'
                    has_primary = _('Yes')
                else:
                    has_primary = _('No')
                    color = None
                values.append([
                    {'value': report.root.job.name, 'href': reverse('jobs:job', args=[report.root.job_id])},
                    {
                        'value': len(mark_leaves),
                        'href': reverse('reports:list_mark', args=[report.id, self.type + 's', self.mark.id])
                    },
                    {'value': has_primary, 'color': color}
                ])
        return values
