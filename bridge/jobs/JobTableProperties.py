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
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.template import Template, Context
from django.utils.translation import ugettext_lazy as _, string_concat
from django.utils.timezone import now, timedelta
from bridge.vars import JOB_DEF_VIEW, USER_ROLES, PRIORITY
from jobs.models import Job
from marks.models import ReportSafeTag, ReportUnsafeTag, ComponentMarkUnknownProblem
from reports.models import Verdict, ComponentResource, ReportComponent, ComponentUnknown, LightResource
from jobs.utils import SAFES, UNSAFES, TITLES, get_resource_data, JobAccess, get_user_time


ORDERS = [
    ('name', 'name'),
    ('change_author__extended__last_name', 'author'),
    ('change_date', 'date'),
    ('status', 'status'),
    ('solvingprogress__start_date', 'start_date'),
    ('solvingprogress__finish_date', 'finish_date')
]

ORDER_TITLES = {
    'name':  _('Title'),
    'author': string_concat(_('Author'), '/', _('Last name')),
    'date': _('Date'),
    'status': _('Decision status'),
    'start_date': _('Start date'),
    'finish_date': _('Finish date')
}

ALL_FILTERS = [
    'name', 'change_author', 'change_date', 'status', 'resource_component',
    'problem_component', 'problem_problem', 'format', 'priority', 'finish_date'
]

FILTER_TITLES = {
    'name': _('Title'),
    'change_author': _('Last change author'),
    'change_date': _('Last change date'),
    'status': _('Decision status'),
    'resource_component': string_concat(_('Consumed resources'), '/', _('Component name')),
    'problem_component': string_concat(_('Unknowns'), '/', _('Component name')),
    'problem_problem': _('Problem name'),
    'format': _('Format'),
    'priority': _('Priority'),
    'finish_date': _('Finish decision date')
}


def all_user_columns():
    columns = ['role', 'author', 'date', 'status', 'unsafe']
    for unsafe in UNSAFES:
        columns.append("unsafe:%s" % unsafe)
    columns.append('safe')
    for safe in SAFES:
        columns.append("safe:%s" % safe)
    columns.extend([
        'problem', 'resource', 'tag', 'tag:safe', 'tag:unsafe', 'identifier', 'format', 'version', 'type', 'parent_id',
        'priority', 'start_date', 'finish_date', 'solution_wall_time', 'operator', 'tasks_pending', 'tasks_processing',
        'tasks_finished', 'tasks_error', 'tasks_cancelled', 'tasks_total', 'solutions', 'progress'
    ])
    return columns


def get_view(user, view=None, view_id=None):
    if view is not None:
        return json.loads(view), None
    if view_id is None:
        pref_view = user.preferableview_set.filter(view__type='1')
        if len(pref_view):
            return json.loads(pref_view[0].view.view), pref_view[0].view_id
    elif view_id == 'default':
        return JOB_DEF_VIEW, 'default'
    else:
        user_view = user.view_set.filter(pk=int(view_id), type='1')
        if len(user_view):
            return json.loads(user_view[0].view), user_view[0].pk
    return JOB_DEF_VIEW, 'default'


class FilterForm(object):

    def __init__(self, user, view=None, view_id=None):
        (self.view, self.view_id) = get_view(user, view, view_id)
        self.selected_columns = self.__selected()
        self.available_columns = self.__available()
        self.selected_orders = self.__selected_orders()
        self.available_orders = self.__available_orders()
        self.available_filters = []
        self.selected_filters = self.__view_filters()
        self.user_views = self.__user_views(user)

    def __column_title(self, column):
        self.ccc = 1
        col_parts = column.split(':')
        column_starts = []
        for i in range(0, len(col_parts)):
            column_starts.append(':'.join(col_parts[:(i + 1)]))
        titles = []
        for col_st in column_starts:
            titles.append(TITLES[col_st])
        concated_title = titles[0]
        for i in range(1, len(titles)):
            concated_title = string_concat(concated_title, '/', titles[i])
        return concated_title

    def __selected(self):
        columns = []
        all_columns = all_user_columns()
        for col in self.view['columns']:
            if col in all_columns:
                columns.append({
                    'value': col,
                    'title': self.__column_title(col)
                })
        return columns

    def __available(self):
        columns = []
        for col in all_user_columns():
            columns.append({
                'value': col,
                'title': self.__column_title(col)
            })
        return columns

    def __available_orders(self):
        available_orders = []
        user_orders = self.view['orders']
        for o in [x[1] for x in ORDERS]:
            if not(o in user_orders or ('-%s' % o) in user_orders):
                available_orders.append({
                    'value': o,
                    'title': ORDER_TITLES[o]
                })
        return available_orders

    def __selected_orders(self):
        new_orders = []
        user_orders = self.view['orders']
        for o in user_orders:
            if o in [x[1] for x in ORDERS]:
                new_orders.append({
                    'value': o,
                    'title': ORDER_TITLES[o],
                    'up': 0
                })
            elif o.startswith('-') and o[1:] in [x[1] for x in ORDERS]:
                new_orders.append({
                    'value': o[1:],
                    'title': ORDER_TITLES[o[1:]],
                    'up': 1
                })
        return new_orders

    def __user_views(self, user):
        view_data = []
        views = user.view_set.filter(type='1')
        for v in views:
            view_data.append({
                'title': v.name,
                'id': v.pk,
                'selected': (self.view_id == v.pk)
            })
        return view_data

    def __view_filters(self):
        view_filters = []
        selected_filters = []
        for f_name in self.view['filters']:
            if f_name in ALL_FILTERS:
                f = self.view['filters'][f_name]
                if f_name == 'change_date':
                    date_vals = f['value'].split(':', 1)
                    f_val = {'valtype': date_vals[0], 'valval': date_vals[1]}
                elif f_name == 'finish_date':
                    date_vals = f['value'].split(':', 1)
                    f_val = {'val_0': int(date_vals[0]), 'val_1': int(date_vals[1])}
                else:
                    f_val = f['value']
                selected_filters.append(f_name)
                view_filters.append({
                    'name': f_name,
                    'name_title': FILTER_TITLES[f_name],
                    'type': f['type'],
                    'value': f_val,
                })
        for f_name in ALL_FILTERS:
            if f_name not in selected_filters:
                self.available_filters.append({
                    'name': f_name,
                    'name_title': FILTER_TITLES[f_name],
                })
        return view_filters


class TableTree(object):

    def __init__(self, user, view=None, view_id=None):
        self.user = user
        self.columns = ['name']
        self.view = get_view(user, view, view_id)[0]
        self.titles = TITLES
        self.head_filters = self.__head_filters()
        self.jobdata = []
        self.__collect_jobdata()
        self.__table_columns()
        self.header = self.Header(self.columns, self.titles).head_struct()
        self.footer_title_length = self.__count_footer()
        self.values = self.__values()
        self.footer = self.__get_footer()
        self.counter = self.Counter()

    class Counter(object):
        def __init__(self):
            self.cnt = 1
            self.dark = False

        def increment(self):
            self.cnt += 1
            if self.cnt % 2:
                self.dark = False
            else:
                self.dark = True

    class Header(object):

        def __init__(self, columns, titles):
            self.columns = columns
            self.titles = titles

        def head_struct(self):
            col_data = []
            depth = self.__max_depth()
            for d in range(1, depth + 1):
                col_data.append(self.__cellspan_level(d, depth))
            # For checkboxes
            col_data[0].insert(0, {
                'column': '',
                'rows': depth,
                'columns': 1,
                'title': '',
            })
            return col_data

        def __max_depth(self):
            max_depth = 0
            if len(self.columns):
                max_depth = 1
            for col in self.columns:
                depth = len(col.split(':'))
                if depth > max_depth:
                    max_depth = depth
            return max_depth

        def __title(self, column):
            if column in self.titles:
                return self.titles[column]
            return column

        def __cellspan_level(self, lvl, max_depth):
            # Get first lvl identifiers of all table columns.
            # Example: 'a:b:c:d:e' (lvl=3) -> 'a:b:c'
            # Example: 'a:b' (lvl=3) -> ''
            # And then colecting single identifiers and their amount without ''.
            # Example: [a, a, a, b, '', c, c, c, c, '', '', c, d, d] ->
            # [(a, 3), (b, 1), (c, 4), (c, 1), (d, 2)]
            columns_of_lvl = []
            prev_col = ''
            cnt = 0
            for col in self.columns:
                col_start = ''
                col_parts = col.split(':')
                if len(col_parts) >= lvl:
                    col_start = ':'.join(col_parts[:lvl])
                    if col_start == prev_col:
                        cnt += 1
                    else:
                        if prev_col != '':
                            columns_of_lvl.append([prev_col, cnt])
                        cnt = 1
                else:
                    if prev_col != '':
                        columns_of_lvl.append([prev_col, cnt])
                    cnt = 0
                prev_col = col_start

            if len(prev_col) > 0 and cnt > 0:
                columns_of_lvl.append([prev_col, cnt])

            # Collecting data of cell span for columns.
            columns_data = []
            for col in columns_of_lvl:
                nrows = max_depth - lvl + 1
                for column in self.columns:
                    if column.startswith(col[0] + ':') and col[0] != column:
                        nrows = 1
                        break
                columns_data.append({
                    'column': col[0],
                    'rows': nrows,
                    'columns': col[1],
                    'title': self.__title(col[0]),
                })
            return columns_data

    def __count_footer(self):
        foot_length = 0
        for col in self.header[0]:
            if col['column'] in ['name', 'author', 'date', 'status', '',
                                 'resource', 'format', 'version', 'type',
                                 'identifier', 'parent_id', 'role',
                                 'priority', 'start_date', 'finish_date',
                                 'solution_wall_time', 'operator', 'progress']:
                foot_length += col['columns']
            else:
                return foot_length
        return None

    def __get_footer(self):
        footer = []
        if self.footer_title_length is not None:
            if len(self.values):
                f_len = len(self.values[0]['values'])
                for i in range(self.footer_title_length - 1, f_len):
                    footer.append(self.values[0]['values'][i]['id'])
        return footer

    def __collect_jobdata(self):
        orders = []
        rowdata = []
        blackdata = []
        for order in self.view['orders']:
            for o in ORDERS:
                if o[1] == order:
                    orders.append(o[0])
                elif order.startswith('-') and o[1] == order[1:]:
                    orders.append('-%s' % o[0])

        for job in Job.objects.filter(**self.__view_filters()).order_by(*orders):
            if JobAccess(self.user, job).can_view():
                rowdata.append(job)

        for job in rowdata:
            parent = job.parent
            row_job_data = {
                'job': job,
                'parent': parent,
                'parent_pk': None,
                'black': False,
                'pk': job.pk,
                'light': job.light
            }
            if parent is not None:
                row_job_data['parent_id'] = parent.identifier
                row_job_data['parent_pk'] = parent.pk
            self.jobdata.append(row_job_data)
            while parent is not None and parent not in list(blackdata + rowdata):
                next_parent = parent.parent
                row_job_data = {
                    'job': parent,
                    'parent': next_parent,
                    'parent_pk': None,
                    'black': True,
                    'pk': parent.pk,
                    'light': job.light
                }
                if next_parent is not None:
                    row_job_data['parent_pk'] = next_parent.pk
                self.jobdata.append(row_job_data)
                blackdata.append(parent)
                parent = next_parent
        self.__order_jobs()

    def __order_jobs(self):
        ordered_jobs = []
        first_jobs = []
        other_jobs = []
        for j in self.jobdata:
            if j['parent'] is None:
                first_jobs.append(j)
            else:
                other_jobs.append(j)

        def get_all_children(job):
            children = []
            for oj in other_jobs:
                if oj['parent'] == job['job']:
                    children.append(oj)
                    children.extend(get_all_children(oj))
            return children

        for j in first_jobs:
            ordered_jobs.append(j)
            ordered_jobs.extend(get_all_children(j))
        self.jobdata = ordered_jobs

    def __head_filters(self):
        head_filters = {}
        allowed_types = ['iexact', 'istartswith', 'icontains']
        for f in self.view['filters']:
            f_data = self.view['filters'][f]
            if f_data['type'] not in allowed_types:
                continue
            if f == 'resource_component':
                head_filters['resource_component'] = {'component__name__' + f_data['type']: f_data['value']}
            elif f == 'problem_component':
                head_filters['problem_component'] = {'component__name__' + f_data['type']: f_data['value']}
            elif f == 'problem_problem':
                head_filters['problem_problem'] = {'problem__name__' + f_data['type']: f_data['value']}
        return head_filters

    def __view_filters(self):

        def name_filter(fdata):
            if fdata['type'] in ['iexact', 'istartswith', 'icontains']:
                return {'name__' + fdata['type']: fdata['value']}
            return {}

        def author_filter(fdata):
            if fdata['type'] == 'is':
                try:
                    return {'change_author__pk': int(fdata['value'])}
                except ValueError:
                    return {}
            return {}

        def date_filter(fdata):
            (measure, value) = fdata['value'].split(':', 1)
            try:
                value = int(value)
            except ValueError:
                return {}
            if measure in ['minutes', 'hours', 'days', 'weeks']:
                # limit_time = pytz.timezone('UTC').localize(datetime.now()) - timedelta(**{measure: value})
                limit_time = now() - timedelta(**{measure: value})
                if fdata['type'] == 'older':
                    return {'change_date__lt': limit_time}
                elif fdata['type'] == 'younger':
                    return {'change_date__gt': limit_time}
            return {}

        def priority_filter(fdata):
            if fdata['type'] == 'e':
                return {'solvingprogress__priority': fdata['value']}
            elif fdata['type'] == 'me':
                priorities = []
                for pr in PRIORITY:
                    priorities.append(pr[0])
                    if pr[0] == fdata['value']:
                        return {'solvingprogress__priority__in': priorities}
            elif fdata['type'] == 'le':
                priorities = []
                for pr in reversed(PRIORITY):
                    priorities.append(pr[0])
                    if pr[0] == fdata['value']:
                        return {'solvingprogress__priority__in': priorities}
            return {}

        def finish_date_filter(fdata):
            (month, year) = fdata['value'].split(':', 1)
            try:
                (month, year) = (int(month), int(year))
            except ValueError:
                return {}
            return {
                'solvingprogress__finish_date__month__' + fdata['type']: month,
                'solvingprogress__finish_date__year__' + fdata['type']: year
            }

        action = {
            'name': name_filter,
            'change_author': author_filter,
            'change_date': date_filter,
            'status': lambda fdata: {'status__in': fdata['value']},
            'format': lambda fdata: {'format': fdata['value']} if fdata['type'] == 'is' else {},
            'priority': priority_filter,
            'finish_date': finish_date_filter
        }

        filters = {}
        for f in self.view['filters']:
            if f in action:
                filters.update(action[f](self.view['filters'][f]))
        return filters

    def __table_columns(self):
        extend_action = {
            'safe': lambda: ['safe:' + postfix for postfix in SAFES],
            'unsafe': lambda: ['unsafe:' + postfix for postfix in UNSAFES],
            'resource': self.__resource_columns,
            'problem': self.__unknowns_columns,
            'tag': lambda: self.__safe_tags_columns() + self.__unsafe_tags_columns(),
            'tag:safe': self.__safe_tags_columns,
            'tag:unsafe': self.__unsafe_tags_columns
        }
        all_columns = all_user_columns()
        for col in self.view['columns']:
            if col in all_columns:
                if col in extend_action:
                    self.columns.extend(extend_action[col]())
                else:
                    self.columns.append(col)

    def __safe_tags_columns(self):
        tags_data = {}
        for job in self.jobdata:
            try:
                root_report = ReportComponent.objects.get(root__job=job['job'], parent=None)
            except ObjectDoesNotExist:
                continue
            for tag in root_report.safe_tags.all():
                tag_name = tag.tag.tag
                tag_id = 'tag:safe:tag_%s' % tag.tag_id
                if tag_id not in tags_data:
                    tags_data[tag_id] = tag_name
                    self.titles[tag_id] = tag_name
        return list(sorted(tags_data, key=tags_data.get))

    def __unsafe_tags_columns(self):
        tags_data = {}
        for job in self.jobdata:
            try:
                root_report = ReportComponent.objects.get(root__job=job['job'], parent=None)
            except ObjectDoesNotExist:
                continue
            for tag in root_report.unsafe_tags.all():
                tag_name = tag.tag.tag
                tag_id = 'tag:unsafe:tag_%s' % tag.tag_id
                if tag_id not in tags_data:
                    tags_data[tag_id] = tag_name
                    self.titles[tag_id] = tag_name
        return list(sorted(tags_data, key=tags_data.get))

    def __resource_columns(self):
        components = {}
        for job in self.jobdata:
            if job['light']:
                filters = {'report__job': job['job']}
                res_table = LightResource
            else:
                filters = {'report__root__job': job['job'], 'report__parent': None}
                res_table = ComponentResource
            if 'resource_component' in self.head_filters:
                filters.update(self.head_filters['resource_component'])
            for compres in res_table.objects.filter(~Q(component=None) & Q(**filters)):
                components['resource:component_' + str(compres.component.pk)] = compres.component.name
        self.titles.update(components)
        components = list(sorted(components, key=components.get))
        components.append('resource:total')
        return components

    def __unknowns_columns(self):
        problems = {}
        cmup_filter = {'report__parent': None}
        cu_filter = {'report__parent': None}
        if 'problem_component' in self.head_filters:
            cmup_filter.update(self.head_filters['problem_component'])
            cu_filter.update(self.head_filters['problem_component'])
        if 'problem_problem' in self.head_filters:
            cmup_filter.update(self.head_filters['problem_problem'])

        for job in self.jobdata:
            cmup_filter['report__root__job'] = job['job']
            cu_filter['report__root__job'] = job['job']
            found_comp_ids = []
            for cmup in ComponentMarkUnknownProblem.objects.filter(**cmup_filter):
                problem = cmup.problem
                comp_id = 'pr_component_%s' % str(cmup.component.pk)
                comp_name = cmup.component.name
                found_comp_ids.append(cmup.component_id)
                if problem is None:
                    if comp_id in problems:
                        if 'z_no_mark' not in problems[comp_id]['problems']:
                            problems[comp_id]['problems']['z_no_mark'] = _('Without marks')
                    else:
                        problems[comp_id] = {
                            'title': comp_name,
                            'problems': {
                                'z_no_mark': _('Without marks'),
                                'z_total': _('Total')
                            }
                        }
                else:
                    probl_id = 'problem_%s' % str(problem.pk)
                    probl_name = problem.name
                    if comp_id in problems:
                        if probl_id not in problems[comp_id]['problems']:
                            problems[comp_id]['problems'][probl_id] = probl_name
                    else:
                        problems[comp_id] = {
                            'title': comp_name,
                            'problems': {
                                probl_id: probl_name,
                                'z_total': _('Total')
                            }
                        }
            for cmup in ComponentUnknown.objects.filter(Q(**cu_filter) & ~Q(component_id__in=found_comp_ids)):
                problems['pr_component_%s' % cmup.component_id] = {
                    'title': cmup.component.name,
                    'problems': {
                        'z_total': _('Total')
                    }
                }

        ordered_ids = list(x[0] for x in list(
            sorted(problems.items(), key=lambda x_y: x_y[1]['title'])
        ))

        new_columns = []
        for comp_id in ordered_ids:
            self.titles['problem:%s' % comp_id] = problems[comp_id]['title']
            has_total = False
            has_nomark = False
            # With sorting time is increased 4-6 times
            # for probl_id in problems[comp_id]['problems']:
            for probl_id in sorted(problems[comp_id]['problems'],
                                   key=problems[comp_id]['problems'].get):
                if probl_id == 'z_total':
                    has_total = True
                elif probl_id == 'z_no_mark':
                    has_nomark = True
                else:
                    column = 'problem:%s:%s' % (comp_id, probl_id)
                    new_columns.append(column)
                    self.titles[column] = \
                        problems[comp_id]['problems'][probl_id]
            if has_nomark:
                column = 'problem:%s:z_no_mark' % comp_id
                new_columns.append(column)
                self.titles[column] = problems[comp_id]['problems']['z_no_mark']
            if has_total:
                column = 'problem:%s:z_total' % comp_id
                new_columns.append(column)
                self.titles[column] = problems[comp_id]['problems']['z_total']

        new_columns.append('problem:total')
        return new_columns

    def __values(self):
        values_data = {}
        names_data = {}
        for job in self.jobdata:
            if not job['black']:
                parent_id = '-'
                if 'parent_id' in job:
                    parent_id = job['parent_id']
                values_data[job['pk']] = {'parent_id': parent_id}

        job_pks = [job['pk'] for job in self.jobdata]

        def collect_progress_data():
            for j in self.jobdata:
                if j['pk'] in values_data:
                    try:
                        progress = j['job'].solvingprogress
                    except ObjectDoesNotExist:
                        continue
                    values_data[j['pk']].update({
                        'priority': progress.get_priority_display(),
                        'tasks_total': progress.tasks_total,
                        'tasks_cancelled': progress.tasks_cancelled,
                        'tasks_error': progress.tasks_error,
                        'tasks_finished': progress.tasks_finished,
                        'tasks_processing': progress.tasks_processing,
                        'tasks_pending': progress.tasks_pending,
                        'solutions': progress.solutions
                    })
                    if progress.tasks_total == 0:
                        values_data[j['pk']]['progress'] = '0%'
                    else:
                        finished_tasks = progress.tasks_cancelled + progress.tasks_error + progress.tasks_finished
                        values_data[j['pk']]['progress'] = "%.0f%% (%s/%s)" % (
                            100 * (finished_tasks / progress.tasks_total),
                            finished_tasks,
                            progress.tasks_total
                        )
                    if progress.start_date is not None:
                        values_data[j['pk']]['start_date'] = progress.start_date
                        if progress.finish_date is not None:
                            values_data[j['pk']]['finish_date'] = progress.finish_date
                            values_data[j['pk']]['solution_wall_time'] = get_user_time(
                                self.user,
                                int((progress.finish_date - progress.start_date).total_seconds() * 1000)
                            )
                    try:
                        values_data[j['pk']]['operator'] = (
                            j['job'].reportroot.user.extended.last_name +
                            ' ' + j['job'].reportroot.user.extended.first_name,
                            reverse('users:show_profile', args=[j['job'].reportroot.user.pk])
                        )
                    except ObjectDoesNotExist:
                        pass

        def collect_authors():
            for j in self.jobdata:
                if j['pk'] in values_data:
                    author = j['job'].change_author
                    if author is not None:
                        name = author.extended.last_name + ' ' + author.extended.first_name
                        author_href = reverse('users:show_profile', args=[author.pk])
                        values_data[j['pk']]['author'] = (name, author_href)

        def collect_jobs_data():
            for j in self.jobdata:
                if j['pk'] in values_data:
                    date = j['job'].change_date
                    if self.user.extended.data_format == 'hum':
                        date = Template('{% load humanize %}{{ date|naturaltime }}').render(Context({
                            'date': date
                        }))
                    values_data[j['pk']].update({
                        'identifier': j['job'].identifier,
                        'format': j['job'].format,
                        'version': j['job'].version,
                        'type': j['job'].get_type_display(),
                        'date': date
                    })
                    try:
                        report = ReportComponent.objects.get(
                            root__job=j['job'], parent=None)
                        values_data[j['pk']]['status'] = (
                            j['job'].get_status_display(),
                            reverse('reports:component',
                                    args=[j['pk'], report.pk])
                        )
                    except ObjectDoesNotExist:
                        values_data[j['pk']]['status'] = \
                            j['job'].get_status_display()
                names_data[j['pk']] = j['job'].name

        def collect_verdicts():
            for verdict in Verdict.objects.filter(
                    report__root__job_id__in=job_pks, report__parent=None):
                if verdict.report.root.job_id in values_data:
                    values_data[verdict.report.root.job_id].update({
                        'unsafe:total': (
                            verdict.unsafe,
                            reverse('reports:list', args=[verdict.report.pk, 'unsafes'])),
                        'unsafe:bug': (
                            verdict.unsafe_bug,
                            reverse('reports:list_verdict', args=[verdict.report.pk, 'unsafes', '1'])
                        ),
                        'unsafe:target_bug': (
                            verdict.unsafe_target_bug,
                            reverse('reports:list_verdict', args=[verdict.report.pk, 'unsafes', '2'])
                        ),
                        'unsafe:false_positive': (
                            verdict.unsafe_false_positive,
                            reverse('reports:list_verdict', args=[verdict.report.pk, 'unsafes', '3'])
                        ),
                        'unsafe:unknown': (
                            verdict.unsafe_unknown,
                            reverse('reports:list_verdict', args=[verdict.report.pk, 'unsafes', '0'])
                        ),
                        'unsafe:unassociated': (
                            verdict.unsafe_unassociated,
                            reverse('reports:list_verdict', args=[verdict.report.pk, 'unsafes', '5'])
                        ),
                        'unsafe:inconclusive': (
                            verdict.unsafe_inconclusive,
                            reverse('reports:list_verdict', args=[verdict.report.pk, 'unsafes', '4'])
                        ),
                        'safe:total': (
                            verdict.safe,
                            reverse('reports:list', args=[verdict.report.pk, 'safes'])),
                        'safe:missed_bug': (
                            verdict.safe_missed_bug,
                            reverse('reports:list_verdict', args=[verdict.report.pk, 'safes', '2'])
                        ),
                        'safe:unknown': (
                            verdict.safe_unknown,
                            reverse('reports:list_verdict', args=[verdict.report.pk, 'safes', '0'])
                        ),
                        'safe:inconclusive': (
                            verdict.safe_inconclusive,
                            reverse('reports:list_verdict', args=[verdict.report.pk, 'safes', '3'])
                        ),
                        'safe:unassociated': (
                            verdict.safe_unassociated,
                            reverse('reports:list_verdict', args=[verdict.report.pk, 'safes', '4'])
                        ),
                        'safe:incorrect': (
                            verdict.safe_incorrect_proof,
                            reverse('reports:list_verdict', args=[verdict.report.pk, 'safes', '1'])
                        ),
                        'problem:total': (
                            verdict.unknown,
                            reverse('reports:list', args=[verdict.report.pk, 'unknowns'])
                        )
                    })

        def collect_roles():
            user_role = self.user.extended.role
            for j in self.jobdata:
                if j['pk'] in values_data:
                    try:
                        first_version = j['job'].versions.get(version=1)
                        last_version = j['job'].versions.get(version=j['job'].version)
                    except ObjectDoesNotExist:
                        return
                    if first_version.change_author == self.user:
                        values_data[j['pk']]['role'] = _('Author')
                    elif user_role == USER_ROLES[2][0]:
                        values_data[j['pk']]['role'] = self.user.extended.get_role_display()
                    else:
                        job_user_role = last_version.userrole_set.filter(
                            user=self.user)
                        if len(job_user_role):
                            values_data[j['pk']]['role'] = job_user_role[0].get_role_display()
                        else:
                            values_data[j['pk']]['role'] = last_version.get_global_role_display()

        def collect_safe_tags():
            for st in ReportSafeTag.objects.filter(report__root__job_id__in=job_pks, report__parent=None):
                curr_job_id = st.report.root.job.pk
                if curr_job_id in values_data:
                    values_data[curr_job_id]['tag:safe:tag_' + str(st.tag_id)] = (
                        st.number, reverse('reports:list_tag', args=[st.report_id, 'safes', st.tag_id])
                    )

        def collect_unsafe_tags():
            for ut in ReportUnsafeTag.objects.filter(report__root__job_id__in=job_pks, report__parent=None):
                curr_job_id = ut.report.root.job.pk
                if curr_job_id in values_data:
                    values_data[curr_job_id]['tag:unsafe:tag_' + str(ut.tag_id)] = (
                        ut.number, reverse('reports:list_tag', args=[ut.report_id, 'unsafes', ut.tag_id])
                    )

        def collect_resourses():
            light_job_pks = [j['pk'] for j in self.jobdata if j['light'] and j['pk'] in values_data]
            other_job_pks = [j['pk'] for j in self.jobdata if not j['light'] and j['pk'] in values_data]
            for cr in ComponentResource.objects.filter(report__root__job_id__in=other_job_pks, report__parent=None):
                rd = get_resource_data(self.user, cr)
                resourses_value = "%s %s %s" % (rd[0], rd[1], rd[2])
                if cr.component is None:
                    values_data[cr.report.root.job_id]['resource:total'] = resourses_value
                else:
                    values_data[cr.report.root.job_id]['resource:component_' + str(cr.component_id)] = resourses_value
            for lr in LightResource.objects.filter(report__job_id__in=light_job_pks):
                rd = get_resource_data(self.user, lr)
                resourses_value = "%s %s %s" % (rd[0], rd[1], rd[2])
                if lr.component is None:
                    values_data[lr.report.job_id]['resource:total'] = resourses_value
                else:
                    values_data[lr.report.job_id]['resource:component_' + str(lr.component_id)] = resourses_value

        def collect_unknowns():
            for cmup in ComponentMarkUnknownProblem.objects.filter(
                    report__root__job_id__in=job_pks, report__parent=None):
                job_pk = cmup.report.root.job_id
                if job_pk in values_data:
                    if cmup.problem is None:
                        values_data[job_pk]['problem:pr_component_' + str(cmup.component_id) + ':z_no_mark'] = (
                            cmup.number,
                            reverse('reports:unknowns_problem', args=[cmup.report.pk, cmup.component.pk, 0])
                        )
                    else:
                        values_data[job_pk][
                            'problem:pr_component_' + str(cmup.component_id) + ':problem_' + str(cmup.problem_id)
                        ] = (cmup.number, reverse('reports:unknowns_problem',
                                                  args=[cmup.report.pk, cmup.component.pk, cmup.problem_id]))
            for cu in ComponentUnknown.objects.filter(report__root__job_id__in=job_pks, report__parent=None):
                job_pk = cu.report.root.job_id
                if job_pk in values_data:
                    values_data[job_pk]['problem:pr_component_' + str(cu.component_id) + ':z_total'] = (
                        cu.number, reverse('reports:unknowns', args=[cu.report_id, cu.component_id])
                    )

        if 'author' in self.columns:
            collect_authors()
        if any(x in ['name', 'identifier', 'format', 'version', 'type', 'date'] for x in self.columns):
            collect_jobs_data()
        if any(x.startswith('safe:') or x.startswith('unsafe:') or x == 'problem:total' for x in self.columns):
            collect_verdicts()
        if any(x.startswith('problem:pr_component_') for x in self.columns):
            collect_unknowns()
        if any(x.startswith('resource:') for x in self.columns):
            collect_resourses()
        if any(x.startswith('tag:safe:') for x in self.columns):
            collect_safe_tags()
        if any(x.startswith('tag:unsafe:') for x in self.columns):
            collect_unsafe_tags()
        if 'role' in self.columns:
            collect_roles()
        collect_progress_data()

        table_rows = []
        for job in self.jobdata:
            row_values = []
            col_id = 0
            for col in self.columns:
                col_id += 1
                if job['black']:
                    cell_value = ''
                else:
                    cell_value = '-'
                href = None
                if col == 'name' and job['pk'] in names_data:
                    cell_value = names_data[job['pk']]
                    if job['pk'] in values_data and not job['black']:
                        href = reverse('jobs:job', args=[job['pk']])
                elif job['pk'] in values_data:
                    if col in values_data[job['pk']]:
                        if isinstance(values_data[job['pk']][col], tuple):
                            cell_value = values_data[job['pk']][col][0]
                            if cell_value != 0:
                                href = values_data[job['pk']][col][1]
                        else:
                            cell_value = values_data[job['pk']][col]
                row_values.append({
                    'value': cell_value,
                    'id': '__'.join(col.split(':')) + ('__%d' % col_id),
                    'href': href
                })
            table_rows.append({
                'id': job['pk'],
                'parent': job['parent_pk'],
                'values': row_values,
                'black': job['black']
            })
        return table_rows
