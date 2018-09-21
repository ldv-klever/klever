#
# Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
# Ivannikov Institute for System Programming of the Russian Academy of Sciences
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

from datetime import datetime, timedelta
from django.db.models import Q, F, Case, When, Count, BooleanField
from django.urls import reverse
from django.utils.translation import ugettext_lazy as _
from django.utils.timezone import now

from bridge.vars import USER_ROLES, PRIORITY, SAFE_VERDICTS, UNSAFE_VERDICTS, ASSOCIATION_TYPE
from bridge.utils import get_templated_text

from jobs.models import Job, JobHistory, UserRole
from marks.models import ReportSafeTag, ReportUnsafeTag
from reports.models import ReportRoot, ReportComponent, ReportSafe, ReportUnsafe, ReportUnknown, ComponentResource

from jobs.utils import SAFES, UNSAFES, TITLES, get_resource_data, JobAccess, get_user_time
from service.models import SolvingProgress
from service.utils import GetJobsProgresses


DATE_COLUMNS = {
    'date', 'tasks:start_ts', 'tasks:finish_ts', 'subjobs:start_sj', 'subjobs:finish_sj', 'start_date', 'finish_date'
}

TASKS_COLUMNS = [
    'tasks', 'tasks:pending', 'tasks:processing', 'tasks:finished', 'tasks:error', 'tasks:cancelled',
    'tasks:total', 'tasks:solutions', 'tasks:total_ts', 'tasks:start_ts', 'tasks:finish_ts',
    'tasks:progress_ts', 'tasks:expected_time_ts'
]

SUBJOBS_COLUMNS = [
    'subjobs', 'subjobs:total_sj', 'subjobs:start_sj', 'subjobs:finish_sj',
    'subjobs:progress_sj', 'subjobs:expected_time_sj'
]


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
        col_data[0].insert(0, {'column': '', 'rows': self._max_depth, 'columns': 1, 'title': ''})
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
            columns_data.append({'column': col[0], 'rows': nrows, 'columns': col[1], 'title': self.__title(col[0])})
        return columns_data


class TableTree:
    no_mark = _('Without marks')
    total = _('Total')

    all_columns = ['role', 'author', 'date', 'status', 'unsafe'] + \
        list("unsafe:{0}".format(u) for u in UNSAFES) + \
        ['safe'] + list("safe:{0}".format(s) for s in SAFES) + \
        TASKS_COLUMNS + SUBJOBS_COLUMNS + \
        ['problem', 'problem:total', 'resource', 'tag', 'tag:safe', 'tag:unsafe', 'identifier', 'format',
         'version', 'parent_id', 'priority', 'start_date', 'finish_date', 'solution_wall_time', 'operator']

    def __init__(self, user, view):
        self._user = user
        self.view = view

        # Columns for view
        self.selected_columns = self.__selected()
        self.available_columns = self.__available()

        # Get jobs tree to visualise (just structure) and set of accessed jobs
        self._tree, self._job_ids, self._roots = self.__get_jobs_tree()

        self._core = self.__get_core_reports()

        # Some titles are collected during __get_columns()
        self._titles = TITLES

        # Should be after we get the tree because columns depends on what jobs are in the tree
        self._columns = self.__get_columns()
        self.header = Header(self._columns, self._titles).head_struct()

        # Collecting data for tables cells
        self._values_data = {}
        self.values = self.__get_values()

        # Table footer data
        self.footer_title_length, self.footer = self.__get_footer()

    def __column_title(self, column):
        col_parts = column.split(':')
        column_starts = []
        for i in range(0, len(col_parts)):
            column_starts.append(':'.join(col_parts[:(i + 1)]))
        titles = []
        for col_st in column_starts:
            titles.append(TITLES[col_st])
        concated_title = titles[0]
        for i in range(1, len(titles)):
            concated_title = '{0}/{1}'.format(concated_title, titles[i])
        return concated_title

    def __selected(self):
        return list({'value': col, 'title': self.__column_title(col)}
                    for col in self.view['columns'] if col in self.all_columns)

    def __available(self):
        return list({'value': col, 'title': self.__column_title(col)} for col in self.all_columns)

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

    def __get_jobs_tree(self):
        # Job order parameter
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

        # Jobs tree structure
        tree_struct = {}
        for job in Job.objects.only('id', 'parent_id'):
            tree_struct[job.id] = job.parent_id

        # Filters for jobs
        filters, unfilters = self.__view_filters()
        filters = Q(**filters)
        for unf_v in unfilters:
            filters &= ~Q(**{unf_v: unfilters[unf_v]})

        # Jobs' ids with view access
        accessed = JobAccess(self._user).can_view_jobs(filters)

        # Add parents without access to show the tree structure
        jobs_in_tree = set(accessed)
        for j_id in accessed:
            parent = tree_struct[j_id]
            while parent is not None:
                jobs_in_tree.add(parent)
                parent = tree_struct[parent]

        # Get ordered list of jobs
        jobs_list = list(j.id for j in Job.objects.filter(id__in=jobs_in_tree).order_by(jobs_order).only('id'))

        # Function collects children tree for specified job id (p_id)
        def get_job_children(p_id):
            children = []
            for oj_id in jobs_list:
                if tree_struct[oj_id] == p_id:
                    children.append({'id': oj_id, 'parent': p_id})
                    children.extend(get_job_children(oj_id))
            return children

        # Get roots' ids for DB reqeusts optimizations
        roots = dict((r_id, j_id) for r_id, j_id in ReportRoot.objects.filter(job_id__in=accessed)
                     .values_list('id', 'job_id'))

        return get_job_children(None), accessed, roots

    def __get_core_reports(self):
        cores = {}
        for report_id, root_id in ReportComponent.objects.filter(root_id__in=self._roots, parent=None)\
                .values_list('id', 'root_id'):
            cores[self._roots[root_id]] = report_id
        return cores

    def __get_columns(self):
        columns = ['name']
        extend_action = {
            'safe': lambda: ['safe:' + postfix for postfix in SAFES],
            'unsafe': lambda: ['unsafe:' + postfix for postfix in UNSAFES],
            'tag': lambda: self.__safe_tags_columns() + self.__unsafe_tags_columns(),
            'tag:safe': self.__safe_tags_columns,
            'tag:unsafe': self.__unsafe_tags_columns,
            'resource': self.__resource_columns,
            'problem': self.__unknowns_columns,
            'tasks': lambda: TASKS_COLUMNS[1:],
            'subjobs': lambda: SUBJOBS_COLUMNS[1:]
        }
        for col in self.view['columns']:
            if col in self.all_columns:
                if col in extend_action:
                    columns.extend(extend_action[col]())
                else:
                    columns.append(col)
        return columns

    def __tags_columns(self, tags_model, tags_type):
        tags_data = {}
        for tag in tags_model.objects.filter(report__root_id__in=self._roots, report__parent=None) \
                .values('tag__tag', 'tag_id'):
            tag_id = 'tag:{0}:tag_{1}'.format(tags_type, tag['tag_id'])
            if tag_id not in tags_data:
                tags_data[tag_id] = tag['tag__tag']
                self._titles[tag_id] = tag['tag__tag']
        return list(sorted(tags_data, key=tags_data.get))

    def __safe_tags_columns(self):
        return self.__tags_columns(ReportSafeTag, 'safe')

    def __unsafe_tags_columns(self):
        return self.__tags_columns(ReportUnsafeTag, 'unsafe')

    def __resource_columns(self):
        # Get filters
        filters = {'report__root_id__in': self._roots}
        if 'resource_component' in self.view:
            filters['component__name__' + self.view['resource_component'][0]] = self.view['resource_component'][1]

        # Get resource columns and fill its titles (components' names)
        resource_columns = []
        for c_id, c_name in ComponentResource.objects.filter(**filters).exclude(component=None)\
                .values_list('component_id', 'component__name').distinct().order_by('component__name'):
            column = 'resource:component_{0}'.format(c_id)
            self._titles[column] = c_name
            resource_columns.append(column)
        resource_columns.append('resource:total')

        return resource_columns

    def __unknowns_columns(self):
        # Get queryset for unknowns
        queryset = ReportUnknown.objects.filter(root_id__in=self._roots)
        if 'problem_component' in self.view:
            queryset = queryset.filter(**{
                'component__name__' + self.view['problem_component'][0]: self.view['problem_component'][1]
            })

        # Is unknown mark unconfirmed
        unconfirmed = Case(When(markreport_set__type=ASSOCIATION_TYPE[2][0], then=True),
                           default=False, output_field=BooleanField())
        queryset = queryset.values('component_id').annotate(unconfirmed=unconfirmed)\
            .values_list('markreport_set__problem_id', 'markreport_set__problem__name',
                         'component_id', 'component__name', 'unconfirmed')
        if 'problem_problem' in self.view:
            queryset = queryset.filter(**{
                'markreport_set__problem__name__' + self.view['problem_problem'][0]: self.view['problem_problem'][1]
            })
        queryset = queryset.distinct().order_by('component__name', 'markreport_set__problem__name')

        columns = []
        prev_col_c_id = None  # Previous component
        has_unmarked = False  # Do component "prev_col_c_id" has unmarked unknowns
        for p_id, p_name, c_id, c_name, unconfirmed in queryset:
            # Add unmarked column (if there are unmarked unknowns)
            # and total column for previous component
            if prev_col_c_id is not None and prev_col_c_id != c_id:
                if has_unmarked:
                    unmarked_column = 'problem:pr_component_{0}:no_mark'.format(prev_col_c_id)
                    columns.append(unmarked_column)
                    self._titles[unmarked_column] = self.no_mark
                    has_unmarked = False
                total_column = 'problem:pr_component_{0}:total'.format(prev_col_c_id)
                columns.append(total_column)
                self._titles[total_column] = self.total
            prev_col_c_id = c_id

            if p_id is None or unconfirmed:
                # We will add unmarked column at the end together with total
                has_unmarked = True
            else:
                column = 'problem:pr_component_{0}:problem_{1}'.format(c_id, p_id)
                self._titles[column] = p_name
                columns.append(column)
            self._titles['problem:pr_component_{0}'.format(c_id)] = c_name

        if prev_col_c_id is not None:
            if has_unmarked:
                unmarked_column = 'problem:pr_component_{0}:no_mark'.format(prev_col_c_id)
                columns.append(unmarked_column)
                self._titles[unmarked_column] = self.no_mark
            total_column = 'problem:pr_component_{0}:total'.format(prev_col_c_id)
            columns.append(total_column)
            self._titles[total_column] = self.total

        columns.append('problem:total')
        return columns

    def __get_values(self):
        self.__init_values_data()
        self.__collect_jobdata()
        self.__collect_verdicts()
        if any(x.startswith('problem:pr_component_') for x in self._columns):
            self.__collect_unknowns()
        if any(x.startswith('tag:safe:') for x in self._columns):
            self.__collect_safe_tags()
        if any(x.startswith('tag:unsafe:') for x in self._columns):
            self.__collect_unsafe_tags()
        if any(x.startswith('resource:') for x in self._columns):
            self.__collect_resourses()
        if 'role' in self._columns:
            self.__collect_roles()

        progress_columns = {'priority', 'solutions', 'start_date', 'finish_date', 'solution_wall_time', 'operator'}\
            | set(TASKS_COLUMNS) | set(SUBJOBS_COLUMNS)
        if any(x in progress_columns for x in self._columns):
            self.__collect_progress_data()

        table_rows = []
        for job in self._tree:
            row_values = []
            col_id = 0
            for col in self._columns:
                col_id += 1
                cell_value = '-' if job['id'] in self._job_ids else ''
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
                        cell_value = get_templated_text('{% load humanize %}{{ date|naturaltime }}', date=cell_value)
                row_values.append({
                    'id': '__'.join(col.split(':')) + ('__%d' % col_id),
                    'value': cell_value, 'href': href
                })
            table_rows.append({
                'id': job['id'], 'parent': job['parent'],
                'black': job['id'] not in self._job_ids,
                'values': row_values
            })
        return table_rows

    def __init_values_data(self):
        for j_id, name in Job.objects.values_list('id', 'name'):
            self._values_data[j_id] = {'name': name}

    def __collect_jobdata(self):
        for j in Job.objects.filter(id__in=self._job_ids).select_related('change_author', 'parent'):
            self._values_data[j.id].update({
                'identifier': j.identifier, 'name': (j.name, reverse('jobs:job', args=[j.id])),
                'format': j.format, 'version': j.version, 'date': j.change_date, 'status': j.get_status_display()
            })
            if j.id in self._core:
                self._values_data[j.id]['status'] = (self._values_data[j.id]['status'],
                                                     reverse('reports:component', args=[self._core[j.id]]))
            if j.parent is not None:
                self._values_data[j.id]['parent_id'] = j.parent.identifier
            if j.change_author is not None:
                self._values_data[j.id]['author'] = (j.change_author.get_full_name(),
                                                     reverse('users:show_profile', args=[j.change_author_id]))

    def __get_safes_without_confirmed(self):
        # Collect safes data
        safe_columns_map = {
            SAFE_VERDICTS[0][0]: 'safe:unknown',
            SAFE_VERDICTS[1][0]: 'safe:incorrect',
            SAFE_VERDICTS[2][0]: 'safe:missed_bug',
            SAFE_VERDICTS[3][0]: 'safe:inconclusive',
            SAFE_VERDICTS[4][0]: 'safe:unassociated'
        }
        for r_id, v, number in ReportSafe.objects.filter(root_id__in=self._roots)\
                .values('root_id').annotate(number=Count('id')).values_list('root_id', 'verdict', 'number'):
            j_id = self._roots[r_id]
            safes_url = reverse('reports:safes', args=[self._core[j_id]])
            self._values_data[j_id][safe_columns_map[v]] = (number, '%s?verdict=%s' % (safes_url, v))
            if 'safe:total' not in self._values_data[j_id]:
                self._values_data[j_id]['safe:total'] = [0, safes_url]
            self._values_data[j_id]['safe:total'][0] += number

        # Fix total data
        for j_id in self._values_data:
            if 'safe:total' in self._values_data[j_id]:
                self._values_data[j_id]['safe:total'] = tuple(self._values_data[j_id]['safe:total'])

    def __get_unsafes_without_confirmed(self):
        # Collect unsafes data
        unsafe_columns_map = {
            UNSAFE_VERDICTS[0][0]: 'unsafe:unknown',
            UNSAFE_VERDICTS[1][0]: 'unsafe:bug',
            UNSAFE_VERDICTS[2][0]: 'unsafe:target_bug',
            UNSAFE_VERDICTS[3][0]: 'unsafe:false_positive',
            UNSAFE_VERDICTS[4][0]: 'unsafe:inconclusive',
            UNSAFE_VERDICTS[5][0]: 'unsafe:unassociated'
        }
        for r_id, v, number in ReportUnsafe.objects.filter(root_id__in=self._roots)\
                .values('root_id').annotate(number=Count('id')).values_list('root_id', 'verdict', 'number'):
            j_id = self._roots[r_id]
            unsafes_url = reverse('reports:unsafes', args=[self._core[j_id]])
            self._values_data[j_id][unsafe_columns_map[v]] = (number, '%s?verdict=%s' % (unsafes_url, v))
            if 'unsafe:total' not in self._values_data[j_id]:
                self._values_data[j_id]['unsafe:total'] = [0, unsafes_url]
            self._values_data[j_id]['unsafe:total'][0] += number

        # Fix total data
        for j_id in self._values_data:
            if 'unsafe:total' in self._values_data[j_id]:
                self._values_data[j_id]['unsafe:total'] = tuple(self._values_data[j_id]['unsafe:total'])

    def __get_safes_with_confirmed(self):
        # Collect safes data
        safe_columns_map = {
            SAFE_VERDICTS[0][0]: 'safe:unknown',
            SAFE_VERDICTS[1][0]: 'safe:incorrect',
            SAFE_VERDICTS[2][0]: 'safe:missed_bug',
            SAFE_VERDICTS[3][0]: 'safe:inconclusive',
            SAFE_VERDICTS[4][0]: 'safe:unassociated'
        }
        for r_id, v, total, confirmed in ReportSafe.objects.filter(root_id__in=self._roots)\
                .values('root_id').annotate(total=Count('id'), confirmed=Count(Case(When(has_confirmed=True, then=1))))\
                .values_list('root_id', 'verdict', 'total', 'confirmed'):
            j_id = self._roots[r_id]
            url = reverse('reports:safes', args=[self._core[j_id]])
            if v == SAFE_VERDICTS[4][0]:
                self._values_data[j_id]['safe:unassociated'] = (total, '%s?verdict=%s' % (url, v))
            else:
                self._values_data[j_id][safe_columns_map[v]] = '{0} ({1})'.format(
                    '<a href="{0}?verdict={1}&confirmed=1">{2}</a>'.format(url, v, confirmed) if confirmed > 0 else 0,
                    '<a href="{0}?verdict={1}">{2}</a>'.format(url, v, total) if total > 0 else 0
                )
            if 'safe:total' not in self._values_data[j_id]:
                self._values_data[j_id]['safe:total'] = [0, 0]
            self._values_data[j_id]['safe:total'][0] += confirmed
            self._values_data[j_id]['safe:total'][1] += total

        # Fix total data
        for j_id in self._values_data:
            if 'safe:total' in self._values_data[j_id]:
                url = reverse('reports:safes', args=[self._core[j_id]])
                confirmed, total = self._values_data[j_id]['safe:total']
                self._values_data[j_id]['safe:total'] = '{0} ({1})'.format(
                    '<a href="{0}?confirmed=1">{1}</a>'.format(url, confirmed) if confirmed > 0 else 0,
                    '<a href="{0}">{1}</a>'.format(url, total) if total > 0 else 0
                )

    def __get_unsafes_with_confirmed(self):
        unsafe_columns_map = {
            UNSAFE_VERDICTS[0][0]: 'unsafe:unknown',
            UNSAFE_VERDICTS[1][0]: 'unsafe:bug',
            UNSAFE_VERDICTS[2][0]: 'unsafe:target_bug',
            UNSAFE_VERDICTS[3][0]: 'unsafe:false_positive',
            UNSAFE_VERDICTS[4][0]: 'unsafe:inconclusive',
            UNSAFE_VERDICTS[5][0]: 'unsafe:unassociated'
        }

        # Collect unsafes
        for r_id, v, total, confirmed in ReportUnsafe.objects.filter(root_id__in=self._roots)\
                .values('root_id').annotate(total=Count('id'), confirmed=Count(Case(When(has_confirmed=True, then=1))))\
                .values_list('root_id', 'verdict', 'total', 'confirmed'):
            j_id = self._roots[r_id]
            url = reverse('reports:unsafes', args=[self._core[j_id]])
            if v == UNSAFE_VERDICTS[5][0]:
                self._values_data[j_id]['unsafe:unassociated'] = (total, '%s?verdict=%s' % (url, v))
            else:
                self._values_data[j_id][unsafe_columns_map[v]] = '{0} ({1})'.format(
                    '<a href="{0}?verdict={1}&confirmed=1">{2}</a>'.format(url, v, confirmed) if confirmed > 0 else 0,
                    '<a href="{0}?verdict={1}">{2}</a>'.format(url, v, total) if total > 0 else 0
                )
            if 'unsafe:total' not in self._values_data[j_id]:
                self._values_data[j_id]['unsafe:total'] = [0, 0]
            self._values_data[j_id]['unsafe:total'][0] += confirmed
            self._values_data[j_id]['unsafe:total'][1] += total

        # Fix total data
        for j_id in self._values_data:
            if 'unsafe:total' in self._values_data[j_id]:
                url = reverse('reports:unsafes', args=[self._core[j_id]])
                confirmed, total = self._values_data[j_id]['unsafe:total']
                self._values_data[j_id]['unsafe:total'] = '{0} ({1})'.format(
                    '<a href="{0}?confirmed=1">{1}</a>'.format(url, confirmed) if confirmed > 0 else 0,
                    '<a href="{0}">{1}</a>'.format(url, total) if total > 0 else 0
                )

    def __collect_verdicts(self):
        if any(col.startswith('safe:') for col in self._columns):
            if 'hidden' in self.view and 'confirmed_marks' in self.view['hidden']:
                self.__get_safes_without_confirmed()
            else:
                self.__get_safes_with_confirmed()

        if any(col.startswith('unsafe:') for col in self._columns):
            if 'hidden' in self.view and 'confirmed_marks' in self.view['hidden']:
                self.__get_unsafes_without_confirmed()
            else:
                self.__get_unsafes_with_confirmed()

        # Total unknowns numbers
        if 'problem:total' in self._columns:
            for r_id, total in ReportUnknown.objects.filter(root_id__in=self._roots) \
                    .values('root_id').annotate(total=Count('id')).values_list('root_id', 'total'):
                j_id = self._roots[r_id]
                self._values_data[j_id]['problem:total'] = (total, reverse('reports:unknowns', args=[self._core[j_id]]))

    def __collect_unknowns(self):
        # Queryset for marked/unmarked unknowns
        unconfirmed = Case(When(markreport_set__type=ASSOCIATION_TYPE[2][0], then=True),
                           default=False, output_field=BooleanField())
        queryset = ReportUnknown.objects.filter(root_id__in=self._roots).values('root_id')\
            .annotate(number=Count('id', distinct=True), unconfirmed=unconfirmed)\
            .values_list('root_id', 'component_id', 'markreport_set__problem_id', 'number', 'unconfirmed')

        unmarked = {}

        # Marked unknowns
        for r_id, c_id, p_id, number, unconfirmed in queryset:
            if p_id is None or unconfirmed:
                if (r_id, c_id) not in unmarked:
                    unmarked[(r_id, c_id)] = 0
                unmarked[(r_id, c_id)] += number
            else:
                job_id = self._roots[r_id]
                url = '{0}?component={1}&problem={2}'.format(
                    reverse('reports:unknowns', args=[self._core[job_id]]), c_id, p_id)
                self._values_data[job_id]['problem:pr_component_{0}:problem_{1}'.format(c_id, p_id)] = (number, url)

        # Unmarked unknowns
        for r_id, c_id in unmarked:
            job_id = self._roots[r_id]
            url = '{0}?component={1}&problem=0'.format(reverse('reports:unknowns', args=[self._core[job_id]]), c_id)
            self._values_data[job_id]['problem:pr_component_{0}:no_mark'.format(c_id)] = (unmarked[(r_id, c_id)], url)

        # Total unknowns for each component
        for r_id, c_id, total in ReportUnknown.objects.filter(root_id__in=self._roots)\
                .values('component_id').annotate(total=Count('id')).values_list('root_id', 'component_id', 'total'):
            job_id = self._roots[r_id]
            url = '{0}?component={1}'.format(reverse('reports:unknowns', args=[self._core[job_id]]), c_id)
            self._values_data[job_id]['problem:pr_component_{0}:total'.format(c_id)] = (total, url)

    def __collect_safe_tags(self):
        for st in ReportSafeTag.objects.filter(report__root_id__in=self._roots, report__parent=None)\
                .annotate(root_id=F('report__root_id')):

            self._values_data[self._roots[st.root_id]]['tag:safe:tag_' + str(st.tag_id)] = (
                st.number, '%s?tag=%s' % (reverse('reports:safes', args=[st.report_id]), st.tag_id)
            )

    def __collect_unsafe_tags(self):
        for ut in ReportUnsafeTag.objects.filter(report__root_id__in=self._roots, report__parent=None)\
                .annotate(root_id=F('report__root_id')):
            self._values_data[self._roots[ut.root_id]]['tag:unsafe:tag_' + str(ut.tag_id)] = (
                ut.number, '%s?tag=%s' % (reverse('reports:unsafes', args=[ut.report_id]), ut.tag_id)
            )

    def __collect_resourses(self):
        data_format = self._user.extended.data_format
        accuracy = self._user.extended.accuracy
        for cr in ComponentResource.objects.filter(report__root_id__in=self._roots, report__parent=None)\
                .annotate(root_id=F('report__root_id')):
            job_id = self._roots[cr.root_id]
            rd = get_resource_data(data_format, accuracy, cr)
            resourses_value = "%s %s %s" % (rd[0], rd[1], rd[2])
            if cr.component_id is None:
                self._values_data[job_id]['resource:total'] = resourses_value
            else:
                self._values_data[job_id]['resource:component_' + str(cr.component_id)] = resourses_value

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

    def __collect_progress_data(self):
        jobs_with_progress = set()
        progresses = GetJobsProgresses(self._user, self._job_ids).table_data()
        for j_id in progresses:
            self._values_data[j_id].update(progresses[j_id])

        for progress in SolvingProgress.objects.filter(job_id__in=self._job_ids):
            self._values_data[progress.job_id].update({
                'priority': progress.get_priority_display(),
                'tasks:total': progress.tasks_total,
                'tasks:cancelled': progress.tasks_cancelled,
                'tasks:error': progress.tasks_error,
                'tasks:finished': progress.tasks_finished,
                'tasks:processing': progress.tasks_processing,
                'tasks:pending': progress.tasks_pending,
                'tasks:solutions': progress.solutions
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

    def __get_footer(self):
        # Must be the same lists as lists in jobtree.js
        countable = {
            'tasks:pending', 'tasks:processing', 'tasks:finished', 'tasks:error',
            'tasks:cancelled', 'tasks:total', 'tasks:solutions', 'tasks:total_ts', 'subjobs:total_sj'
        }
        countable_prefexes = {'safe:', 'unsafe:', 'tag:', 'problem:'}

        # Footer title length
        foot_length = 1
        for col in self._columns:
            if col in countable or any(col.startswith(prefix) for prefix in countable_prefexes):
                break
            foot_length += 1
        else:
            foot_length = None

        # Footer columns
        footer = []
        if foot_length is not None and len(self.values) > 0:
            f_len = len(self.values[0]['values'])
            for i in range(foot_length - 1, f_len):
                footer.append(self.values[0]['values'][i]['id'])

        return foot_length, footer
