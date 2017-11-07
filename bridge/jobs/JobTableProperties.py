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

from datetime import datetime
from django.core.urlresolvers import reverse
from django.db.models import Q, F, Case, When, Count
from django.template import Template, Context
from django.utils.translation import ugettext_lazy as _, string_concat
from django.utils.timezone import now, timedelta

from bridge.vars import USER_ROLES, PRIORITY, SAFE_VERDICTS, UNSAFE_VERDICTS, VIEW_TYPES

from jobs.models import Job, JobHistory, UserRole
from marks.models import ReportSafeTag, ReportUnsafeTag, ComponentMarkUnknownProblem
from reports.models import ComponentResource, ReportComponent, ComponentUnknown, ReportRoot, ReportComponentLeaf

from users.utils import ViewData
from jobs.utils import SAFES, UNSAFES, TITLES, get_resource_data, JobAccess, get_user_time
from service.models import SolvingProgress
from service.utils import GetJobsProgresses


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

DATE_COLUMNS = {'date', 'start_ts', 'finish_ts', 'start_sj', 'finish_sj', 'start_date', 'finish_date'}


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
        'tasks_processing', 'tasks_finished', 'tasks_error', 'tasks_cancelled', 'tasks_total', 'solutions',
        'total_ts', 'start_ts', 'finish_ts', 'progress_ts', 'expected_time_ts',
        'total_sj', 'start_sj', 'finish_sj', 'progress_sj', 'expected_time_sj'
    ])
    return columns


class TableTree:
    def __init__(self, user, view=None, view_id=None):
        self._user = user
        self._columns = ['name']

        self.view = ViewData(user, VIEW_TYPES[1][0], view=view, view_id=view_id)
        self.selected_columns = self.__selected()
        self.available_columns = self.__available()

        self._titles = TITLES
        self._head_filters = self.__head_filters()
        self._jobdata = []
        self._job_ids = []
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
                columns.append({'value': col, 'title': self.__column_title(col)})
        return columns

    def __available(self):
        columns = []
        for col in all_user_columns():
            columns.append({'value': col, 'title': self.__column_title(col)})
        return columns

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
        rowdata = []

        jobs_order = 'id'
        if 'order' in self.view:
            if self.view['order'][1] == 'title':
                jobs_order = 'name'
            elif self.view['order'][1] == 'date':
                jobs_order = 'change_date'
            elif self.view['order'][1] == 'start':
                jobs_order = 'solvingprogress__start_date'
            elif self.view['order'][1] == 'finish':
                jobs_order = 'solvingprogress__finish_date'
            if self.view['order'][0] == 'up':
                jobs_order = '-' + jobs_order

        tree_struct = {}
        for job in Job.objects.all().only('id', 'parent_id', 'name'):
            tree_struct[job.id] = (job.parent_id, job.name, job.identifier)

        filters, unfilters = self.__view_filters()
        filters = Q(**filters)
        for unf_v in unfilters:
            filters &= ~Q(**{unf_v: unfilters[unf_v]})
        for job in Job.objects.filter(filters).order_by(jobs_order):
            if JobAccess(self._user, job).can_view():
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
        if 'resource_component' in self.view:
            head_filters['resource_component'] = {
                'component__name__' + self.view['resource_component'][0]: self.view['resource_component'][1]
            }
        elif 'problem_component' in self.view:
            head_filters['problem_component'] = {
                'component__name__' + self.view['problem_component'][0]: self.view['problem_component'][1]
            }
        elif 'problem_problem' in self.view:
            head_filters['problem_problem'] = {
                'problem__name__' + self.view['problem_problem'][0]: self.view['problem_problem'][1]
            }
        return head_filters

    def __view_filters(self):
        filters = {}
        unfilters = {}

        if 'title' in self.view:
            filters['name__' + self.view['title'][0]] = self.view['title'][1]

        if 'change_author' in self.view:
            if self.view['change_author'][0] == 'is':
                filters['change_author__id'] = int(self.view['change_author'][1])
            else:
                unfilters['change_author__id'] = int(self.view['change_author'][1])

        if 'change_date' in self.view:
            limit_time = now() - timedelta(**{self.view['change_date'][2]: int(self.view['change_date'][1])})
            if self.view['change_date'][0] == 'older':
                filters['change_date__lt'] = limit_time
            elif self.view['change_date'][0] == 'younger':
                filters['change_date__gt'] = limit_time

        if 'status' in self.view:
            filters['status__in'] = self.view['status']

        if 'format' in self.view:
            if self.view['format'][0] == 'is':
                filters['format'] = int(self.view['format'][1])
            elif self.view['format'][0] == 'isnot':
                unfilters['format'] = int(self.view['format'][1])

        if 'priority' in self.view:
            if self.view['priority'][0] == 'e':
                filters['solvingprogress__priority'] = self.view['priority'][1]
            elif self.view['priority'][0] == 'me':
                priorities = []
                for pr in PRIORITY:
                    priorities.append(pr[0])
                    if pr[0] == self.view['priority'][1]:
                        filters['solvingprogress__priority__in'] = priorities
                        break
            elif self.view['priority'][0] == 'le':
                priorities = []
                for pr in reversed(PRIORITY):
                    priorities.append(pr[0])
                    if pr[0] == self.view['priority'][1]:
                        filters['solvingprogress__priority__in'] = priorities
                        break

        if 'finish_date' in self.view:
            filters['solvingprogress__finish_date__month__' + self.view['finish_date'][0]] = \
                int(self.view['finish_date'][1])
            filters['solvingprogress__finish_date__year__' + self.view['finish_date'][0]] = \
                int(self.view['finish_date'][2])

        if 'weight' in self.view:
            filters['weight__in'] = self.view['weight']

        return filters, unfilters

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
        filters = {'report__root__job_id__in': self._job_ids}
        if 'resource_component' in self._head_filters:
            filters.update(self._head_filters['resource_component'])

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
            'priority', 'solutions', 'start_date', 'finish_date', 'solution_wall_time', 'operator',
            'tasks_total', 'tasks_cancelled', 'tasks_error', 'tasks_finished', 'tasks_processing', 'tasks_pending',
            'total_ts', 'start_ts', 'finish_ts', 'progress_ts', 'expected_time_ts',
            'total_sj', 'start_sj', 'finish_sj', 'progress_sj', 'expected_time_sj'
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
                if col in DATE_COLUMNS:
                    if self._user.extended.data_format == 'hum' and isinstance(cell_value, datetime):
                        cell_value = Template('{% load humanize %}{{ date|naturaltime }}')\
                            .render(Context({'date': cell_value}))
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
        progresses = GetJobsProgresses(self._user, self._job_ids).data
        for j_id in progresses:
            self._values_data[j_id].update(progresses[j_id])

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
            if progress.start_date is not None:
                self._values_data[progress.job_id]['start_date'] = progress.start_date
                if progress.finish_date is not None:
                    self._values_data[progress.job_id]['finish_date'] = progress.finish_date
                    self._values_data[progress.job_id]['solution_wall_time'] = get_user_time(
                        self._user, int((progress.finish_date - progress.start_date).total_seconds() * 1000)
                    )
            jobs_with_progress.add(progress.job_id)

        for root in ReportRoot.objects.filter(job_id__in=self._job_ids).select_related('user'):
            self._values_data[root.job_id]['operator'] = (
                root.user.get_full_name(), reverse('users:show_profile', args=[root.user_id])
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
        if 'hidden' in self.view and 'confirmed_marks' in self.view['hidden']:
            self.__get_verdicts_without_confirmed()
        else:
            self.__get_verdicts_with_confirmed()

        for job_id, r_id, total in ReportComponentLeaf.objects\
                .filter(report__root__job_id__in=self._job_ids, report__parent=None)\
                .exclude(unknown=None).values('report__root__job_id')\
                .annotate(job_id=F('report__root__job_id'), total=Count('id'))\
                .values_list('job_id', 'report_id', 'total'):
            self._values_data[job_id]['problem:total'] = (total, reverse('reports:unknowns', args=[r_id]))

    def __get_verdicts_with_confirmed(self):
        unsafe_columns_map = {
            UNSAFE_VERDICTS[0][0]: 'unsafe:unknown',
            UNSAFE_VERDICTS[1][0]: 'unsafe:bug',
            UNSAFE_VERDICTS[2][0]: 'unsafe:target_bug',
            UNSAFE_VERDICTS[3][0]: 'unsafe:false_positive',
            UNSAFE_VERDICTS[4][0]: 'unsafe:inconclusive',
            UNSAFE_VERDICTS[5][0]: 'unsafe:unassociated'
        }
        safe_columns_map = {
            SAFE_VERDICTS[0][0]: 'safe:unknown',
            SAFE_VERDICTS[1][0]: 'safe:incorrect',
            SAFE_VERDICTS[2][0]: 'safe:missed_bug',
            SAFE_VERDICTS[3][0]: 'safe:inconclusive',
            SAFE_VERDICTS[4][0]: 'safe:unassociated'
        }
        for job_id, r_id, verdict, confirmed, total in ReportComponentLeaf.objects \
                .filter(report__root__job_id__in=self._job_ids, report__parent=None) \
                .exclude(unsafe=None).values('unsafe__verdict') \
                .annotate(job_id=F('report__root__job_id'), total=Count('id'),
                          confirmed=Count(Case(When(unsafe__has_confirmed=True, then=1)))) \
                .values_list('job_id', 'report_id', 'unsafe__verdict', 'confirmed', 'total'):
            unsafes_url = reverse('reports:unsafes', args=[r_id])
            if verdict == UNSAFE_VERDICTS[5][0]:
                self._values_data[job_id]['unsafe:unassociated'] = (total, '%s?verdict=%s' % (unsafes_url, verdict))
            else:
                if confirmed > 0:
                    val1 = '<a href="%s">%s</a>' % ('%s?verdict=%s&confirmed=1' % (unsafes_url, verdict), confirmed)
                else:
                    val1 = confirmed
                if total > 0:
                    val2 = '<a href="%s">%s</a>' % ('%s?verdict=%s' % (unsafes_url, verdict), total)
                else:
                    val2 = total
                self._values_data[job_id][unsafe_columns_map[verdict]] = '%s (%s)' % (val1, val2)
            if 'unsafe:total' not in self._values_data[job_id]:
                self._values_data[job_id]['unsafe:total'] = [0, 0, unsafes_url]
            self._values_data[job_id]['unsafe:total'][0] += confirmed
            self._values_data[job_id]['unsafe:total'][1] += total
        for job_id, r_id, verdict, confirmed, total in ReportComponentLeaf.objects \
                .filter(report__root__job_id__in=self._job_ids, report__parent=None) \
                .exclude(safe=None).values('safe__verdict') \
                .annotate(job_id=F('report__root__job_id'), total=Count('id'),
                          confirmed=Count(Case(When(safe__has_confirmed=True, then=1)))) \
                .values_list('job_id', 'report_id', 'safe__verdict', 'confirmed', 'total'):
            safes_url = reverse('reports:safes', args=[r_id])
            if verdict == SAFE_VERDICTS[4][0]:
                self._values_data[job_id]['safe:unassociated'] = (total, '%s?verdict=%s' % (safes_url, verdict))
            else:
                if confirmed > 0:
                    val1 = '<a href="%s">%s</a>' % ('%s?verdict=%s&confirmed=1' % (safes_url, verdict), confirmed)
                else:
                    val1 = confirmed
                if total > 0:
                    val2 = '<a href="%s">%s</a>' % ('%s?verdict=%s' % (safes_url, verdict), total)
                else:
                    val2 = total
                self._values_data[job_id][safe_columns_map[verdict]] = '%s (%s)' % (val1, val2)
            if 'safe:total' not in self._values_data[job_id]:
                self._values_data[job_id]['safe:total'] = [0, 0, safes_url]
            self._values_data[job_id]['safe:total'][0] += confirmed
            self._values_data[job_id]['safe:total'][1] += total

        for j_id in self._values_data:
            for col in ['unsafe:total', 'safe:total']:
                if col in self._values_data[j_id]:
                    if self._values_data[j_id][col][0] > 0:
                        val1 = '<a href="%s">%s</a>' % ('%s?confirmed=1' % self._values_data[j_id][col][2],
                                                        self._values_data[j_id][col][0])
                    else:
                        val1 = self._values_data[j_id][col][0]
                    if self._values_data[j_id][col][1] > 0:
                        val2 = '<a href="%s">%s</a>' % (
                            self._values_data[j_id][col][2], self._values_data[j_id][col][1]
                        )
                    else:
                        val2 = self._values_data[j_id][col][1]
                    self._values_data[j_id][col] = '%s (%s)' % (val1, val2)

    def __get_verdicts_without_confirmed(self):
        unsafe_columns_map = {
            UNSAFE_VERDICTS[0][0]: 'unsafe:unknown',
            UNSAFE_VERDICTS[1][0]: 'unsafe:bug',
            UNSAFE_VERDICTS[2][0]: 'unsafe:target_bug',
            UNSAFE_VERDICTS[3][0]: 'unsafe:false_positive',
            UNSAFE_VERDICTS[4][0]: 'unsafe:inconclusive',
            UNSAFE_VERDICTS[5][0]: 'unsafe:unassociated'
        }
        safe_columns_map = {
            SAFE_VERDICTS[0][0]: 'safe:unknown',
            SAFE_VERDICTS[1][0]: 'safe:incorrect',
            SAFE_VERDICTS[2][0]: 'safe:missed_bug',
            SAFE_VERDICTS[3][0]: 'safe:inconclusive',
            SAFE_VERDICTS[4][0]: 'safe:unassociated'
        }
        for job_id, r_id, verdict, total in ReportComponentLeaf.objects \
                .filter(report__root__job_id__in=self._job_ids, report__parent=None) \
                .exclude(unsafe=None).values('unsafe__verdict') \
                .annotate(job_id=F('report__root__job_id'), total=Count('id')) \
                .values_list('job_id', 'report_id', 'unsafe__verdict', 'total'):
            unsafes_url = reverse('reports:unsafes', args=[r_id])
            self._values_data[job_id][unsafe_columns_map[verdict]] = (total, '%s?verdict=%s' % (unsafes_url, verdict))
            if 'unsafe:total' not in self._values_data[job_id]:
                self._values_data[job_id]['unsafe:total'] = [0, unsafes_url]
            self._values_data[job_id]['unsafe:total'][0] += total
        for job_id, r_id, verdict, total in ReportComponentLeaf.objects \
                .filter(report__root__job_id__in=self._job_ids, report__parent=None) \
                .exclude(safe=None).values('safe__verdict') \
                .annotate(job_id=F('report__root__job_id'), total=Count('id')) \
                .values_list('job_id', 'report_id', 'safe__verdict', 'total'):
            safes_url = reverse('reports:safes', args=[r_id])
            self._values_data[job_id][safe_columns_map[verdict]] = total
            if 'safe:total' not in self._values_data[job_id]:
                self._values_data[job_id]['safe:total'] = [0, safes_url]
            self._values_data[job_id]['safe:total'][0] += total
        for j_id in self._values_data:
            if 'unsafe:total' in self._values_data[j_id]:
                self._values_data[j_id]['unsafe:total'] = (
                    self._values_data[j_id]['unsafe:total'][0], self._values_data[j_id]['unsafe:total'][1]
                )
            if 'safe:total' in self._values_data[j_id]:
                self._values_data[j_id]['safe:total'] = (
                    self._values_data[j_id]['safe:total'][0], self._values_data[j_id]['safe:total'][1]
                )

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
                st.number, '%s?tag=%s' % (reverse('reports:safes', args=[st.report_id]), st.tag_id)
            )

    def __collect_unsafe_tags(self):
        for ut in ReportUnsafeTag.objects.filter(report__root__job_id__in=self._job_ids, report__parent=None)\
                .annotate(job_id=F('report__root__job_id')):
            self._values_data[ut.job_id]['tag:unsafe:tag_' + str(ut.tag_id)] = (
                ut.number, '%s?tag=%s' % (reverse('reports:unsafes', args=[ut.report_id]), ut.tag_id)
            )

    def __collect_resourses(self):
        data_format = self._user.extended.data_format
        accuracy = self._user.extended.accuracy
        for cr in ComponentResource.objects.filter(report__root__job_id__in=self._job_ids, report__parent=None)\
                .annotate(job_id=F('report__root__job_id')):
            rd = get_resource_data(data_format, accuracy, cr)
            resourses_value = "%s %s %s" % (rd[0], rd[1], rd[2])
            if cr.component_id is None:
                self._values_data[cr.job_id]['resource:total'] = resourses_value
            else:
                self._values_data[cr.job_id]['resource:component_' + str(cr.component_id)] = resourses_value

    def __collect_unknowns(self):
        for cmup in ComponentMarkUnknownProblem.objects\
                .filter(report__root__job_id__in=self._job_ids, report__parent=None)\
                .annotate(job_id=F('report__root__job_id')):
            if cmup.problem_id is None:
                self._values_data[cmup.job_id]['problem:pr_component_' + str(cmup.component_id) + ':z_no_mark'] = (
                    cmup.number, '%s?component=%s&problem=%s' % (
                        reverse('reports:unknowns', args=[cmup.report_id]), cmup.component_id, 0
                    )
                )
            else:
                self._values_data[cmup.job_id][
                    'problem:pr_component_%s:problem_%s' % (cmup.component_id, cmup.problem_id)
                ] = (cmup.number, '%s?component=%s&problem=%s' % (
                    reverse('reports:unknowns', args=[cmup.report_id]), cmup.component_id, cmup.problem_id
                ))
        for cu in ComponentUnknown.objects.filter(report__root__job_id__in=self._job_ids, report__parent=None)\
                .annotate(job_id=F('report__root__job_id')):
            self._values_data[cu.job_id]['problem:pr_component_' + str(cu.component_id) + ':z_total'] = (
                cu.number, '%s?component=%s' % (reverse('reports:unknowns', args=[cu.report_id]), cu.component_id)
            )

    def __is_not_used(self):
        pass
