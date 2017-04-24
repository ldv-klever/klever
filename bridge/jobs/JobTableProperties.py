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
from django.db.models import Q, F
from django.template import Template, Context
from django.utils.translation import ugettext_lazy as _, string_concat
from django.utils.timezone import now, timedelta
from bridge.vars import JOB_DEF_VIEW, USER_ROLES, PRIORITY, JOB_STATUS, JOB_WEIGHT
from users.models import View
from jobs.models import Job, JobHistory, UserRole, RunHistory
from marks.models import ReportSafeTag, ReportUnsafeTag, ComponentMarkUnknownProblem
from reports.models import Verdict, ComponentResource, ReportComponent, ComponentUnknown, LightResource, ReportRoot,\
    TaskStatistic
from jobs.utils import SAFES, UNSAFES, TITLES, get_resource_data, JobAccess, get_user_time
from service.models import SolvingProgress


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
        'problem', 'problem:total', 'resource', 'tag', 'tag:safe', 'tag:unsafe', 'identifier', 'format', 'version',
        'type', 'parent_id', 'priority', 'start_date', 'finish_date', 'solution_wall_time', 'operator', 'tasks_pending',
        'tasks_processing', 'tasks_finished', 'tasks_error', 'tasks_cancelled', 'tasks_total', 'solutions', 'progress',
        'average_time', 'local_average_time', 'max_time'
    ])
    return columns


def get_view(user, view=None, view_id=None):
    if view is not None:
        return json.loads(view), None
    if view_id is None:
        pref_view = user.preferableview_set.filter(view__type='1').select_related('view').first()
        if pref_view:
            return json.loads(pref_view.view.view), pref_view.view_id
    elif view_id == 'default':
        return JOB_DEF_VIEW, 'default'
    else:
        user_view = View.objects.filter(Q(id=view_id, type='1') & (Q(shared=True) | Q(author=user))).first()
        if user_view:
            return json.loads(user_view.view), user_view.pk
    return JOB_DEF_VIEW, 'default'


class FilterForm:
    def __init__(self, user, view=None, view_id=None):
        self.user = user
        (self.view, self.view_id) = get_view(user, view, view_id)
        self.user_views = self.__user_views()
        self.selected_columns = self.__selected()
        self.available_columns = self.__available()
        self.selected_orders = self.__selected_orders()
        self.available_orders = self.__available_orders()
        self.available_filters = []
        self.selected_filters = self.__view_filters()

    def __column_title(self, column):
        self.__is_not_used()
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

    def __user_views(self):
        return View.objects.filter(Q(type='1') & (Q(author=self.user) | Q(shared=True))).order_by('name')

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

    def __is_not_used(self):
        pass


class TableTree:
    def __init__(self, user, view=None, view_id=None):
        self._user = user
        self._columns = ['name']
        self._view = get_view(user, view, view_id)[0]
        self._titles = TITLES
        self._head_filters = self.__head_filters()
        self._jobdata = []
        self._job_ids = []
        self._light_jobs = []
        self._full_jobs = []
        self._values_data = {}
        self.__collect_jobdata()
        self.__table_columns()
        self.header = self.Header(self._columns, self._titles).head_struct()
        self.footer_title_length = self.__count_footer()
        self.values = self.__get_values()
        self.footer = self.__get_footer()

    class Header:
        def __init__(self, columns, titles):
            self.columns = columns
            self.titles = titles
            self._max_depth = self.__max_depth()

        def head_struct(self):
            col_data = []
            for d in range(1, self._max_depth + 1):
                col_data.append(self.__cellspan_level(d))
            # For checkboxes
            col_data[0].insert(0, {
                'column': '',
                'rows': self._max_depth,
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

        def __cellspan_level(self, lvl):
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
                nrows = self._max_depth - lvl + 1
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

    def __is_countable(self, col):
        if col in {'unsafe', 'safe', 'tag', 'problem', 'tasks_pending', 'tasks_processing',
                   'tasks_finished', 'tasks_error', 'tasks_cancelled', 'tasks_total', 'solutions'}:
            return True
        self.__is_not_used()
        return False

    def __count_footer(self):
        foot_length = 0
        for col in self.header[0]:
            if self.__is_countable(col['column']):
                return foot_length
            foot_length += col['columns']
        return None

    def __get_footer(self):
        footer = []
        if self.footer_title_length is not None and len(self.values) > 0:
            f_len = len(self.values[0]['values'])
            for i in range(self.footer_title_length - 1, f_len):
                footer.append(self.values[0]['values'][i]['id'])
        return footer

    def __collect_jobdata(self):
        orders = []
        rowdata = []

        for order in self._view['orders']:
            for o in ORDERS:
                if o[1] == order:
                    orders.append(o[0])
                elif order.startswith('-') and o[1] == order[1:]:
                    orders.append('-%s' % o[0])

        tree_struct = {}
        for job in Job.objects.all().only('id', 'parent_id', 'name'):
            tree_struct[job.id] = (job.parent_id, job.name, job.identifier)

        for job in Job.objects.filter(**self.__view_filters()).order_by(*orders):
            if JobAccess(self._user, job).can_view():
                if job.weight == JOB_WEIGHT[1][0]:
                    self._light_jobs.append(job.id)
                else:
                    self._full_jobs.append(job.id)
                self._job_ids.append(job.id)
                rowdata.append({
                    'id': job.id,
                    'name': job.name,
                    'parent': job.parent_id,
                    'parent_identifier': tree_struct[job.parent_id][2] if job.parent_id is not None else None,
                    'black': False,
                    'weight': job.weight,
                    'identifier': job.identifier
                })

        added_jobs = list(self._job_ids)
        for job in rowdata:
            parent = job['parent']
            self._jobdata.append(job)
            while parent is not None and parent not in added_jobs:
                self._jobdata.append({
                    'name': tree_struct[parent][1],
                    'parent': tree_struct[parent][0],
                    'black': True,
                    'id': parent
                })
                added_jobs.append(parent)
                parent = tree_struct[parent][0]

        ordered_jobs = []
        first_jobs = []
        other_jobs = []
        for j in self._jobdata:
            if j['parent'] is None:
                first_jobs.append(j)
            else:
                other_jobs.append(j)

        def get_all_children(p):
            children = []
            for oj in other_jobs:
                if oj['parent'] == p['id']:
                    children.append(oj)
                    children.extend(get_all_children(oj))
            return children

        for j in first_jobs:
            ordered_jobs.append(j)
            ordered_jobs.extend(get_all_children(j))
        self._jobdata = ordered_jobs

    def __head_filters(self):
        head_filters = {}
        allowed_types = ['iexact', 'istartswith', 'icontains']
        for f in self._view['filters']:
            f_data = self._view['filters'][f]
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
            if fdata['type'] in {'iexact', 'istartswith', 'icontains'}:
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
            if measure in {'minutes', 'hours', 'days', 'weeks'}:
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
        for f in self._view['filters']:
            if f in action:
                filters.update(action[f](self._view['filters'][f]))
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
        for col in self._view['columns']:
            if col in all_columns:
                if col in extend_action:
                    self._columns.extend(extend_action[col]())
                else:
                    self._columns.append(col)

    def __safe_tags_columns(self):
        tags_data = {}
        for tag in ReportSafeTag.objects.filter(report__root__job_id__in=self._job_ids, report__parent=None)\
                .values('tag__tag', 'tag_id'):
            tag_id = 'tag:safe:tag_%s' % tag['tag_id']
            if tag_id not in tags_data:
                tags_data[tag_id] = tag['tag__tag']
                self._titles[tag_id] = tag['tag__tag']
        return list(sorted(tags_data, key=tags_data.get))

    def __unsafe_tags_columns(self):
        tags_data = {}
        for tag in ReportUnsafeTag.objects.filter(report__root__job_id__in=self._job_ids, report__parent=None) \
                .values('tag__tag', 'tag_id'):
            tag_id = 'tag:unsafe:tag_%s' % tag['tag_id']
            if tag_id not in tags_data:
                tags_data[tag_id] = tag['tag__tag']
                self._titles[tag_id] = tag['tag__tag']
        return list(sorted(tags_data, key=tags_data.get))

    def __resource_columns(self):
        components = {}
        filters = {'report__job_id__in': self._light_jobs}
        if 'resource_component' in self._head_filters:
            filters.update(self._head_filters['resource_component'])
        for cr in LightResource.objects.filter(**filters).exclude(component=None)\
                .values('component', 'component__name').distinct():
            components['resource:component_' + str(cr['component'])] = cr['component__name']

        del filters['report__job_id__in']
        filters['report__root__job_id__in'] = self._full_jobs
        # 4 JOINs in query!!!
        for cr in ComponentResource.objects.filter(**filters).exclude(component=None)\
                .values('component', 'component__name').distinct():
            components['resource:component_' + str(cr['component'])] = cr['component__name']

        self._titles.update(components)
        components = list(sorted(components, key=components.get))
        components.append('resource:total')
        return components

    def __unknowns_columns(self):
        problems = {}
        cmup_filter = {'report__parent': None}
        cu_filter = {'report__parent': None}
        if 'problem_component' in self._head_filters:
            cmup_filter.update(self._head_filters['problem_component'])
            cu_filter.update(self._head_filters['problem_component'])
        if 'problem_problem' in self._head_filters:
            cmup_filter.update(self._head_filters['problem_problem'])
        cmup_filter['report__root__job_id__in'] = self._job_ids
        cu_filter['report__root__job_id__in'] = self._job_ids

        found_comp_ids = set()
        for cmup in ComponentMarkUnknownProblem.objects.filter(**cmup_filter).select_related('component', 'problem'):
            found_comp_ids.add(cmup.component_id)
            comp_id = 'pr_component_%s' % str(cmup.component_id)
            if cmup.problem is None:
                if comp_id in problems:
                    if 'z_no_mark' not in problems[comp_id]['problems']:
                        problems[comp_id]['problems']['z_no_mark'] = _('Without marks')
                else:
                    problems[comp_id] = {
                        'title': cmup.component.name,
                        'problems': {
                            'z_no_mark': _('Without marks'),
                            'z_total': _('Total')
                        }
                    }
            else:
                probl_id = 'problem_%s' % str(cmup.problem_id)
                if comp_id in problems:
                    if probl_id not in problems[comp_id]['problems']:
                        problems[comp_id]['problems'][probl_id] = cmup.problem.name
                else:
                    problems[comp_id] = {
                        'title': cmup.component.name,
                        'problems': {
                            probl_id: cmup.problem.name,
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
            self._titles['problem:%s' % comp_id] = problems[comp_id]['title']
            has_total = False
            has_nomark = False
            # With sorting time is increased 4-6 times
            # for probl_id in problems[comp_id]['problems']:
            for probl_id in sorted(problems[comp_id]['problems'], key=problems[comp_id]['problems'].get):
                if probl_id == 'z_total':
                    has_total = True
                elif probl_id == 'z_no_mark':
                    has_nomark = True
                else:
                    column = 'problem:%s:%s' % (comp_id, probl_id)
                    new_columns.append(column)
                    self._titles[column] = problems[comp_id]['problems'][probl_id]
            if has_nomark:
                column = 'problem:%s:z_no_mark' % comp_id
                new_columns.append(column)
                self._titles[column] = problems[comp_id]['problems']['z_no_mark']
            if has_total:
                column = 'problem:%s:z_total' % comp_id
                new_columns.append(column)
                self._titles[column] = problems[comp_id]['problems']['z_total']

        new_columns.append('problem:total')
        return new_columns

    def __get_values(self):
        for job in self._jobdata:
            if job['black']:
                self._values_data[job['id']] = {'name': job['name']}
            else:
                self._values_data[job['id']] = {
                    'name': (job['name'], reverse('jobs:job', args=[job['id']])),
                    'identifier': job['identifier']
                }
                if job['parent_identifier'] is not None:
                    self._values_data[job['id']]['parent_id'] = job['parent_identifier']

        if 'author' in self._columns:
            self.__collect_authors()
        if any(x in {'format', 'version', 'type', 'date', 'status'} for x in self._columns):
            self.__collect_jobs_data()
        if any(x.startswith('safe:') or x.startswith('unsafe:') or x == 'problem:total' for x in self._columns):
            self.__collect_verdicts()
        if any(x.startswith('problem:pr_component_') for x in self._columns):
            self.__collect_unknowns()
        if any(x.startswith('resource:') for x in self._columns):
            self.__collect_resourses()
        if any(x.startswith('tag:safe:') for x in self._columns):
            self.__collect_safe_tags()
        if any(x.startswith('tag:unsafe:') for x in self._columns):
            self.__collect_unsafe_tags()
        if 'role' in self._columns:
            self.__collect_roles()
        progress_columns = {
            'priority', 'solutions', 'progress', 'start_date', 'finish_date', 'solution_wall_time', 'operator',
            'tasks_total', 'tasks_cancelled', 'tasks_error', 'tasks_finished', 'tasks_processing', 'tasks_pending'
        }
        if any(x in progress_columns for x in self._columns):
            self.__collect_progress_data()

        table_rows = []
        for job in self._jobdata:
            row_values = []
            col_id = 0
            for col in self._columns:
                col_id += 1
                if job['black']:
                    cell_value = ''
                else:
                    cell_value = '-'
                href = None
                if job['id'] in self._values_data and col in self._values_data[job['id']]:
                    if isinstance(self._values_data[job['id']][col], tuple):
                        cell_value = self._values_data[job['id']][col][0]
                        if cell_value != 0:
                            href = self._values_data[job['id']][col][1]
                    else:
                        cell_value = self._values_data[job['id']][col]
                row_values.append({
                    'value': cell_value,
                    'id': '__'.join(col.split(':')) + ('__%d' % col_id),
                    'href': href
                })
            table_rows.append({
                'id': job['id'],
                'parent': job['parent'],
                'values': row_values,
                'black': job['black']
            })
        return table_rows

    def __collect_progress_data(self):
        jobs_with_progress = set()
        for progress in SolvingProgress.objects.filter(job_id__in=self._job_ids):
            self._values_data[progress.job_id].update({
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
                self._values_data[progress.job_id]['progress'] = '0%'
            else:
                finished_tasks = progress.tasks_cancelled + progress.tasks_error + progress.tasks_finished
                self._values_data[progress.job_id]['progress'] = "%.0f%% (%s/%s)" % (
                    100 * (finished_tasks / progress.tasks_total),
                    finished_tasks,
                    progress.tasks_total
                )
            if progress.start_date is not None:
                self._values_data[progress.job_id]['start_date'] = progress.start_date
                if progress.finish_date is not None:
                    self._values_data[progress.job_id]['finish_date'] = progress.finish_date
                    self._values_data[progress.job_id]['solution_wall_time'] = get_user_time(
                        self._user,
                        int((progress.finish_date - progress.start_date).total_seconds() * 1000)
                    )
            jobs_with_progress.add(progress.job_id)

        stat_average_time = TaskStatistic.objects.get_or_create()[0].average_time
        solving_jobs = set(j.id for j in Job.objects.filter(
            id__in=self._job_ids, status__in=[JOB_STATUS[1][0], JOB_STATUS[2][0]]
        ))
        for root in ReportRoot.objects.filter(job_id__in=list(jobs_with_progress)).select_related('user'):
            self._values_data[root.job_id]['operator'] = (
                root.user.get_full_name(),
                reverse('users:show_profile', args=[root.user_id])
            )
            if root.job_id in solving_jobs:
                total_tasks = root.tasks_total
                solved_tasks = self._values_data[root.job_id]['tasks_error'] + \
                    self._values_data[root.job_id]['tasks_finished']
                progress = '-'
                if total_tasks > 0:
                    curr_progress = int(solved_tasks / total_tasks * 100)
                    if curr_progress < 100:
                        progress = '%s%%' % curr_progress
                else:
                    progress = '0%'
                if progress != '-' and total_tasks > solved_tasks:
                    self._values_data[root.job_id]['progress'] = progress
                    self._values_data[root.job_id]['average_time'] = get_user_time(
                        self._user, (total_tasks - solved_tasks) * stat_average_time
                    )
                    self._values_data[root.job_id]['local_average_time'] = get_user_time(
                        self._user, (total_tasks - solved_tasks) * root.average_time
                    )
                    if 'max_time' in self._columns:
                        # TODO: optimize it
                        with RunHistory.objects.filter(job=root.job_id).order_by('id').last().configuration.file as fp:
                            time_limit = json.loads(fp.read().decode('utf8'))['resource limits']['CPU time']
                        if isinstance(time_limit, int):
                            self._values_data[root.job_id]['max_time'] = get_user_time(
                                self._user, time_limit * (total_tasks - solved_tasks)
                            )

    def __collect_authors(self):
        for j in Job.objects.filter(id__in=self._job_ids) \
                .exclude(change_author=None)\
                .only('id', 'change_author_id', 'change_author__first_name', 'change_author__last_name'):
            self._values_data[j.id]['author'] = (
                j.change_author.get_full_name(),
                reverse('users:show_profile', args=[j.change_author_id])
            )

    def __collect_jobs_data(self):
        for j in Job.objects.filter(id__in=self._job_ids):
            date = j.change_date
            if self._user.extended.data_format == 'hum':
                date = Template('{% load humanize %}{{ date|naturaltime }}').render(Context({'date': date}))
            self._values_data[j.id].update({
                'format': j.format,
                'version': j.version,
                'type': j.get_type_display(),
                'date': date,
                'status': j.get_status_display()
            })
        for report in ReportComponent.objects.filter(root__job_id__in=self._job_ids, parent=None)\
                .values('id', 'root__job_id'):
            self._values_data[report['root__job_id']]['status'] = (
                self._values_data[report['root__job_id']]['status'],
                reverse('reports:component', args=[report['root__job_id'], report['id']])
            )

    def __collect_verdicts(self):
        for verdict in Verdict.objects.filter(report__root__job_id__in=self._job_ids, report__parent=None)\
                .annotate(job_id=F('report__root__job_id')):
            self._values_data[verdict.job_id].update({
                'unsafe:total': (
                    verdict.unsafe,
                    reverse('reports:list', args=[verdict.report_id, 'unsafes'])
                ),
                'unsafe:bug': (
                    verdict.unsafe_bug,
                    reverse('reports:list_verdict', args=[verdict.report_id, 'unsafes', '1'])
                ),
                'unsafe:target_bug': (
                    verdict.unsafe_target_bug,
                    reverse('reports:list_verdict', args=[verdict.report_id, 'unsafes', '2'])
                ),
                'unsafe:false_positive': (
                    verdict.unsafe_false_positive,
                    reverse('reports:list_verdict', args=[verdict.report_id, 'unsafes', '3'])
                ),
                'unsafe:unknown': (
                    verdict.unsafe_unknown,
                    reverse('reports:list_verdict', args=[verdict.report_id, 'unsafes', '0'])
                ),
                'unsafe:unassociated': (
                    verdict.unsafe_unassociated,
                    reverse('reports:list_verdict', args=[verdict.report_id, 'unsafes', '5'])
                ),
                'unsafe:inconclusive': (
                    verdict.unsafe_inconclusive,
                    reverse('reports:list_verdict', args=[verdict.report_id, 'unsafes', '4'])
                ),
                'safe:total': (
                    verdict.safe,
                    reverse('reports:list', args=[verdict.report_id, 'safes'])
                ),
                'safe:missed_bug': (
                    verdict.safe_missed_bug,
                    reverse('reports:list_verdict', args=[verdict.report_id, 'safes', '2'])
                ),
                'safe:unknown': (
                    verdict.safe_unknown,
                    reverse('reports:list_verdict', args=[verdict.report_id, 'safes', '0'])
                ),
                'safe:inconclusive': (
                    verdict.safe_inconclusive,
                    reverse('reports:list_verdict', args=[verdict.report_id, 'safes', '3'])
                ),
                'safe:unassociated': (
                    verdict.safe_unassociated,
                    reverse('reports:list_verdict', args=[verdict.report_id, 'safes', '4'])
                ),
                'safe:incorrect': (
                    verdict.safe_incorrect_proof,
                    reverse('reports:list_verdict', args=[verdict.report_id, 'safes', '1'])
                ),
                'problem:total': (
                    verdict.unknown,
                    reverse('reports:list', args=[verdict.report_id, 'unknowns'])
                )
            })

    def __collect_roles(self):
        user_role = self._user.extended.role

        is_author = set()
        for fv in JobHistory.objects.filter(job_id__in=self._job_ids, version=1, change_author_id=self._user.id)\
                .only('job_id'):
            is_author.add(fv.job_id)

        global_roles = {}
        for fv in JobHistory.objects.filter(job_id__in=self._job_ids, version=F('job__version'))\
                .only('job_id', 'global_role'):
            global_roles[fv.job_id] = fv.get_global_role_display()

        job_user_roles = {}
        for ur in UserRole.objects\
                .filter(user=self._user, job__job_id__in=self._job_ids, job__version=F('job__job__version'))\
                .only('job__job_id', 'role'):
            job_user_roles[ur.job.job_id] = ur.get_role_display()

        for j_id in self._job_ids:
            if j_id in is_author:
                self._values_data[j_id]['role'] = _('Author')
            elif user_role == USER_ROLES[2][0]:
                self._values_data[j_id]['role'] = USER_ROLES[2][1]
            elif j_id in job_user_roles:
                self._values_data[j_id]['role'] = job_user_roles[j_id]
            else:
                self._values_data[j_id]['role'] = global_roles[j_id]

    def __collect_safe_tags(self):
        for st in ReportSafeTag.objects.filter(report__root__job_id__in=self._job_ids, report__parent=None)\
                .annotate(job_id=F('report__root__job_id')):
            self._values_data[st.job_id]['tag:safe:tag_' + str(st.tag_id)] = (
                st.number, reverse('reports:list_tag', args=[st.report_id, 'safes', st.tag_id])
            )

    def __collect_unsafe_tags(self):
        for ut in ReportUnsafeTag.objects.filter(report__root__job_id__in=self._job_ids, report__parent=None)\
                .annotate(job_id=F('report__root__job_id')):
            self._values_data[ut.job_id]['tag:unsafe:tag_' + str(ut.tag_id)] = (
                ut.number, reverse('reports:list_tag', args=[ut.report_id, 'unsafes', ut.tag_id])
            )

    def __collect_resourses(self):
        data_format = self._user.extended.data_format
        accuracy = self._user.extended.accuracy
        for cr in ComponentResource.objects.filter(report__root__job_id__in=self._full_jobs, report__parent=None)\
                .annotate(job_id=F('report__root__job_id')):
            rd = get_resource_data(data_format, accuracy, cr)
            resourses_value = "%s %s %s" % (rd[0], rd[1], rd[2])
            if cr.component_id is None:
                self._values_data[cr.job_id]['resource:total'] = resourses_value
            else:
                self._values_data[cr.job_id]['resource:component_' + str(cr.component_id)] = resourses_value
        for lr in LightResource.objects.filter(report__job_id__in=self._light_jobs)\
                .annotate(job_id=F('report__job_id')):
            rd = get_resource_data(data_format, accuracy, lr)
            resourses_value = "%s %s %s" % (rd[0], rd[1], rd[2])
            if lr.component_id is None:
                self._values_data[lr.job_id]['resource:total'] = resourses_value
            else:
                self._values_data[lr.job_id]['resource:component_' + str(lr.component_id)] = resourses_value

    def __collect_unknowns(self):
        for cmup in ComponentMarkUnknownProblem.objects\
                .filter(report__root__job_id__in=self._job_ids, report__parent=None)\
                .annotate(job_id=F('report__root__job_id')):
            if cmup.problem_id is None:
                self._values_data[cmup.job_id]['problem:pr_component_' + str(cmup.component_id) + ':z_no_mark'] = (
                    cmup.number,
                    reverse('reports:unknowns_problem', args=[cmup.report_id, cmup.component_id, 0])
                )
            else:
                self._values_data[cmup.job_id][
                    'problem:pr_component_%s:problem_%s' % (cmup.component_id, cmup.problem_id)
                ] = (
                    cmup.number, reverse(
                        'reports:unknowns_problem', args=[cmup.report_id, cmup.component_id, cmup.problem_id]
                    )
                )
        for cu in ComponentUnknown.objects.filter(report__root__job_id__in=self._job_ids, report__parent=None)\
                .annotate(job_id=F('report__root__job_id')):
            self._values_data[cu.job_id]['problem:pr_component_' + str(cu.component_id) + ':z_total'] = (
                cu.number, reverse('reports:unknowns', args=[cu.report_id, cu.component_id])
            )

    def __is_not_used(self):
        pass
