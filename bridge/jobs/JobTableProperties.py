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

from datetime import timedelta
from slugify import slugify

from django.db.models import Q, F, Case, When, Count
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _
from django.utils.timezone import now

from bridge.vars import USER_ROLES, PRIORITY, SafeVerdicts, UnsafeVerdicts, JOB_WEIGHT
from bridge.utils import construct_url
from bridge.tableHead import ComplexHeaderMixin

from jobs.models import Job, JobHistory, UserRole
from reports.models import ReportRoot, ReportComponent

from users.utils import HumanizedValue
from jobs.utils import SAFES, UNSAFES, TITLES, JobAccess
from service.models import Decision
from service.serializers import ProgressSerializerRO
from caches.models import ReportSafeCache, ReportUnsafeCache, ReportUnknownCache


TASKS_COLUMNS = [
    'tasks', 'tasks:pending', 'tasks:processing', 'tasks:finished', 'tasks:error', 'tasks:cancelled',
    'tasks:total', 'tasks:solutions', 'tasks:total_ts', 'tasks:start_ts', 'tasks:finish_ts',
    'tasks:progress_ts', 'tasks:expected_time_ts'
]

SUBJOBS_COLUMNS = [
    'subjobs', 'subjobs:total_sj', 'subjobs:start_sj', 'subjobs:finish_sj',
    'subjobs:progress_sj', 'subjobs:expected_time_sj'
]


class TableTree(ComplexHeaderMixin):
    no_mark = _('Without marks')
    total = _('Total')

    def __init__(self, user, view):
        self._user = user
        self.view = view

        # Columns for view
        self.selected_columns = self.__selected()
        self.available_columns = self.__available()

        self._slugs = {}

        # Get jobs tree to visualise (just structure) and set of accessed jobs
        self._tree, self._job_ids, self._roots = self.__get_jobs_tree()

        self._core = self.__get_core_reports()

        # Some titles are collected during __get_columns()
        self._titles = TITLES.copy()

        # Should be after we get the tree because columns depends on what jobs are in the tree
        self._columns = self.__get_columns()
        self.header = self.head_struct(self._columns, self._titles)

        # Collecting data for tables cells
        self._values_data = {}
        self.values = self.__get_values()

        # Table footer data
        self.footer_title_length, self.footer = self.__get_footer()

    def slugify(self, source):
        if source not in self._slugs:
            self._slugs[source] = slugify(source)
        return self._slugs[source]

    @cached_property
    def all_columns(self):
        return ['role', 'author', 'date', 'status', 'unsafe'] + \
               list("unsafe:{0}".format(u) for u in UNSAFES) + \
               ['safe'] + list("safe:{0}".format(s) for s in SAFES) + \
               TASKS_COLUMNS + SUBJOBS_COLUMNS + [
                   'problem', 'problem:total', 'resource', 'tag', 'tag:safe', 'tag:unsafe', 'identifier',
                   'version', 'priority', 'start_date', 'finish_date', 'solution_wall_time', 'operator'
               ]

    @cached_property
    def all_columns_set(self):
        return set(self.all_columns)

    def __column_title(self, column):
        col_parts = column.split(':')
        column_starts = []
        for i in range(len(col_parts)):
            column_starts.append(':'.join(col_parts[:(i + 1)]))

        titles = list(TITLES.get(col_st, col_st) for col_st in column_starts)
        title_pattern = '/'.join(list('{%s}' % i for i in range(len(titles))))
        return title_pattern.format(*titles)

    def __selected(self):
        return list({'value': col, 'title': self.__column_title(col)}
                    for col in self.view['columns'] if col in self.all_columns_set)

    def __available(self):
        return list({'value': col, 'title': self.__column_title(col)} for col in self.all_columns)

    def __get_queryset(self):
        qs_filter = Q()

        if 'title' in self.view:
            qs_filter &= Q(**{'name__' + self.view['title'][0]: self.view['title'][1]})

        if 'change_author' in self.view:
            author_filter = Q(change_author_id=int(self.view['change_author'][1]))
            qs_filter &= author_filter if self.view['change_author'][0] == 'is' else ~author_filter

        if 'change_date' in self.view:
            limit_time = now() - timedelta(**{self.view['change_date'][2]: int(self.view['change_date'][1])})
            qs_filter &= Q(**{'change_date__' + self.view['change_date'][0]: limit_time})

        if 'status' in self.view:
            qs_filter &= Q(status__in=self.view['status'])

        if 'priority' in self.view:
            priority_filter = 'solvingprogress__priority'
            priority_value = self.view['priority'][1]
            if self.view['priority'][0] == 'me':
                priorities = []
                for pr in PRIORITY:
                    priorities.append(pr[0])
                    if pr[0] == self.view['priority'][1]:
                        priority_filter += '__in'
                        priority_value = priorities
                        break
            elif self.view['priority'][0] == 'le':
                priorities = []
                for pr in reversed(PRIORITY):
                    priorities.append(pr[0])
                    if pr[0] == self.view['priority'][1]:
                        priority_filter += '__in'
                        priority_value = priorities
                        break
            qs_filter &= Q(**{priority_filter: priority_value})

        if 'finish_date' in self.view:
            qs_filter &= Q(**{
                'solvingprogress__finish_date__month__' + self.view['finish_date'][0]: int(self.view['finish_date'][1]),
                'solvingprogress__finish_date__year__' + self.view['finish_date'][0]: int(self.view['finish_date'][2]),
            })

        if 'weight' in self.view:
            qs_filter &= Q(weight__in=self.view['weight'])

        return Job.objects.filter(qs_filter)

    @property
    def order(self):
        order_map = {'title': 'name', 'start': 'decision__start_date', 'finish': 'decision__finish_date'}
        if 'order' in self.view and len(self.view['order']) == 2 and self.view['order'][1] in order_map:
            jobs_order = order_map[self.view['order'][1]]
            if self.view['order'][0] == 'up':
                jobs_order = '-' + jobs_order
            return jobs_order, 'id'
        return 'id',

    def __get_jobs_tree(self):
        # Jobs tree structure
        tree_struct = dict(Job.objects.values_list('id', 'parent_id'))

        # Jobs' ids with view access
        accessed = JobAccess(self._user).can_view_jobs(self.__get_queryset())

        # Get roots' ids for querysets optimizations
        roots = dict(ReportRoot.objects.filter(job_id__in=accessed).values_list('id', 'job_id'))

        # Add parents without access to show the tree structure
        jobs_in_tree = set(accessed)
        for j_id in accessed:
            parent = tree_struct[j_id]
            while parent is not None:
                jobs_in_tree.add(parent)
                parent = tree_struct[parent]

        # Get ordered list of jobs
        jobs_list = list(Job.objects.filter(id__in=jobs_in_tree).order_by(*self.order).values_list('id', flat=True))

        # Function collects children tree for specified job id (p_id)
        def get_job_children(p_id):
            children = []
            for oj_id in jobs_list:
                if tree_struct[oj_id] == p_id:
                    children.append({'id': oj_id, 'parent': p_id})
                    children.extend(get_job_children(oj_id))
            return children

        return get_job_children(None), accessed, roots

    def __get_core_reports(self):
        cores = {}
        for report_id, root_id in ReportComponent.objects.filter(root_id__in=self._roots, parent=None)\
                .values_list('id', 'root_id'):
            cores[self._roots[root_id]] = report_id
        return cores

    def __get_columns(self):
        columns = ['checkbox', 'name']
        self._titles['checkbox'] = ''
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
            if col in self.all_columns_set:
                if col in extend_action:
                    columns.extend(extend_action[col]())
                else:
                    columns.append(col)
        return columns

    def __safe_tags_columns(self):
        all_tags = set()
        for s_tags in ReportSafeCache.objects.filter(report__root_id__in=self._roots).values_list('tags', flat=True):
            all_tags |= set(s_tags)

        columns = []
        for tag in sorted(all_tags):
            columns.append('tag:safe:{}'.format(self.slugify(tag)))
        return columns

    def __unsafe_tags_columns(self):
        all_tags = set()
        for s_tags in ReportUnsafeCache.objects.filter(report__root_id__in=self._roots).values_list('tags', flat=True):
            all_tags |= set(s_tags)

        columns = []
        for tag in sorted(all_tags):
            columns.append('tag:unsafe:{}'.format(self.slugify(tag)))
        return columns

    def __filter_component(self, component):
        if component == 'total':
            return False
        if 'resource_component' not in self.view:
            return True
        if self.view['resource_component'][0] == 'iexact':
            return self.view['resource_component'][1].lower() == component.lower()
        if self.view['resource_component'][0] == 'istartswith':
            return component.lower().startswith(self.view['resource_component'][1].lower())
        if self.view['resource_component'][0] == 'icontains':
            return self.view['resource_component'][1].lower() in component.lower()
        return True

    def __resource_columns(self):
        components = set()
        for root in ReportRoot.objects.filter(id__in=self._roots).only('resources'):
            components |= set(root.resources)
        resource_columns = []
        for c_name in sorted(list(c for c in components if self.__filter_component(c))):
            column = 'resource:{}'.format(self.slugify(c_name))
            self._titles[column] = c_name
            resource_columns.append(column)
        resource_columns.append('resource:total')
        return resource_columns

    def __unknowns_columns(self):
        component_problems = {}
        qs_filters = {'report__root_id__in': self._roots}
        if 'problem_component' in self.view:
            filter_key = 'report__component__{}'.format(self.view['problem_component'][0])
            qs_filters[filter_key] = self.view['problem_component'][1]
        for component, problems in ReportUnknownCache.objects.filter(**qs_filters).order_by('report__component')\
                .values_list('report__component', 'problems'):
            component_problems.setdefault(component, set())
            component_problems[component] |= set(problems)

        columns = []
        for component in sorted(component_problems):
            for problem in sorted(component_problems[component]):
                column = 'problem:{}:{}'.format(self.slugify(component), self.slugify(problem))
                self._titles[column] = problem
                columns.append(column)
            if len(component_problems[component]):
                column = 'problem:{}:no_mark'.format(self.slugify(component))
                self._titles[column] = self.no_mark
                columns.append(column)
            column = 'problem:{}:total'.format(self.slugify(component))
            self._titles[column] = self.total
            columns.append(column)
            self._titles['problem:{}'.format(self.slugify(component))] = component
        columns.append('problem:total')
        return columns

    def __get_values(self):
        self.__init_values_data()
        self.__collect_jobdata()
        self.__collect_verdicts()
        if any(x.startswith('problem:') for x in self._columns):
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

                if job['id'] in self._values_data and col in self._values_data[job['id']]:
                    cell_value = self._values_data[job['id']][col]
                elif job['id'] in self._job_ids:
                    cell_value = self.__get_cell('-')
                else:
                    cell_value = self.__get_cell('')

                cell_value['column'] = col if col == 'checkbox' else str(col_id)

                row_values.append(cell_value)
            table_rows.append({
                'id': job['id'], 'parent': job['parent'],
                'black': job['id'] not in self._job_ids,
                'values': row_values
            })
        return table_rows

    def __init_values_data(self):
        for j_id, name in Job.objects.values_list('id', 'name'):
            self._values_data[j_id] = {'name': self.__get_cell(name)}

    def __html_link(self, url, text):
        return '<a href="{0}">{1}</a>'.format(url, text)

    def __get_cell(self, value, url=None, **kwargs):
        data = {}
        if url:
            data['html'] = self.__html_link(url, value)
        elif value is not None:
            data['text'] = str(value)
        else:
            data['text'] = '-'
        data.update(kwargs)
        return data

    def __collect_jobdata(self):
        for job_version in JobHistory.objects.filter(version=F('job__version'), job_id__in=self._job_ids)\
                .select_related('job', 'change_author'):
            job_url = reverse('jobs:job', args=[job_version.job_id])
            status_url = None
            if job_version.job.weight == JOB_WEIGHT[1][0] and job_version.job_id in self._core:
                status_url = reverse('reports:component', args=[self._core[job_version.job_id]])

            author_val = author_url = None
            if job_version.change_author:
                author_val = job_version.change_author.get_full_name()
                author_url = reverse('users:show-profile', args=[job_version.change_author_id])

            self._values_data[job_version.job_id].update({
                'name': self.__get_cell(job_version.job.name, url=job_url),
                'identifier': self.__get_cell(job_version.job.identifier),
                'date': self.__get_cell(HumanizedValue(job_version.change_date, user=self._user).date),
                'author': self.__get_cell(author_val, url=author_url),
                'status': self.__get_cell(job_version.job.get_status_display(), url=status_url),
                'version': self.__get_cell(job_version.version)
            })

    def __get_safes_without_confirmed(self):
        total_safes = {}
        verdicts = SafeVerdicts()
        for r_id, v, number in ReportSafeCache.objects.filter(report__root_id__in=self._roots)\
                .values('report__root_id', 'verdict').annotate(number=Count('id'))\
                .values_list('report__root_id', 'verdict', 'number'):
            j_id = self._roots[r_id]

            safes_url = None
            if number > 0:
                safes_url = construct_url('reports:safes', self._core[j_id], verdict=v)
            self._values_data[j_id][verdicts.column(v)] = self.__get_cell(number, url=safes_url, number=number)

            # Collect total number
            total_safes.setdefault(j_id, 0)
            total_safes[j_id] += number

        # Add numbers of total safes of the job
        for j_id, number in total_safes.values():
            safes_url = None
            if number > 0:
                safes_url = construct_url('reports:safes', self._core[j_id])
            self._values_data[j_id]['safe:total'] = self.__get_cell(number, url=safes_url, number=number)

    def __get_unsafes_without_confirmed(self):
        total_unsafes = {}
        verdicts = UnsafeVerdicts()
        for r_id, v, number in ReportUnsafeCache.objects.filter(report__root_id__in=self._roots)\
                .values('report__root_id', 'verdict').annotate(number=Count('id'))\
                .values_list('report__root_id', 'verdict', 'number'):
            j_id = self._roots[r_id]

            unsafes_url = None
            if number > 0:
                unsafes_url = construct_url('reports:unsafes', self._core[j_id], verdict=v)
            self._values_data[j_id][verdicts.column(v)] = self.__get_cell(number, url=unsafes_url, number=number)

            # Collect total number
            total_unsafes.setdefault(j_id, 0)
            total_unsafes[j_id] += number

        # Add numbers of total unsafes of the job
        for j_id, number in total_unsafes.values():
            unsafes_url = None
            if number > 0:
                unsafes_url = construct_url('reports:unsafes', self._core[j_id])
            self._values_data[j_id]['unsafe:total'] = self.__get_cell(number, url=unsafes_url, number=number)

    def __get_safes_with_confirmed(self):
        total_safes = {}
        verdicts = SafeVerdicts()

        # Collect safes data
        for r_id, v, total, confirmed in ReportSafeCache.objects\
                .filter(report__root_id__in=self._roots).values('report__root_id', 'verdict')\
                .annotate(total=Count('id'), confirmed=Count(Case(When(marks_confirmed__gt=0, then=1))))\
                .values_list('report__root_id', 'verdict', 'total', 'confirmed'):
            j_id = self._roots[r_id]

            html_number = total
            # Collect total number
            total_safes.setdefault(j_id, {'total': 0, 'confirmed': 0})
            total_safes[j_id]['total'] += total
            total_safes[j_id]['confirmed'] += confirmed

            if total > 0:
                total = self.__html_link(construct_url('reports:safes', self._core[j_id], verdict=v), total)

            if v == verdicts.unassociated:
                html_value = str(total)

            elif confirmed > 0:
                confirmed_url = construct_url('reports:safes', self._core[j_id], verdict=v, confirmed=1)
                html_value = '{} ({})'.format(self.__html_link(confirmed_url, confirmed), total)
            else:
                html_value = '0 ({})'.format(total)
            self._values_data[j_id][verdicts.column(v)] = {'html': html_value, 'number': html_number}

        # Add numbers of total safes of the job
        for j_id, total_data in total_safes.items():
            total, confirmed = total_data['total'], total_data['confirmed']
            html_number = total
            if total > 0:
                total = self.__html_link(construct_url('reports:safes', self._core[j_id]), total)
            if confirmed > 0:
                confirmed = self.__html_link(construct_url('reports:safes', self._core[j_id], confirmed=1), confirmed)
            self._values_data[j_id]['safe:total'] = {
                'html': '{} ({})'.format(confirmed, total), 'number': html_number
            }

    def __get_unsafes_with_confirmed(self):
        total_unsafes = {}
        verdicts = UnsafeVerdicts()

        # Collect unsafes
        for r_id, v, total, confirmed in ReportUnsafeCache.objects\
                .filter(report__root_id__in=self._roots).values('report__root_id', 'verdict')\
                .annotate(total=Count('id'), confirmed=Count(Case(When(marks_confirmed__gt=0, then=1))))\
                .values_list('report__root_id', 'verdict', 'total', 'confirmed'):
            j_id = self._roots[r_id]
            html_number = total

            # Collect total number
            total_unsafes.setdefault(j_id, {'total': 0, 'confirmed': 0})
            total_unsafes[j_id]['total'] += total
            total_unsafes[j_id]['confirmed'] += confirmed

            if total > 0:
                total = self.__html_link(construct_url('reports:unsafes', self._core[j_id], verdict=v), total)

            if v == verdicts.unassociated:
                html_value = str(total)

            elif confirmed > 0:
                confirmed_url = construct_url('reports:unsafes', self._core[j_id], verdict=v, confirmed=1)
                html_value = '{} ({})'.format(self.__html_link(confirmed_url, confirmed), total)
            else:
                html_value = '0 ({})'.format(total)
            self._values_data[j_id][verdicts.column(v)] = {'html': html_value, 'number': html_number}

        # Add numbers of total safes of the job
        for j_id, total_data in total_unsafes.items():
            total, confirmed = total_data['total'], total_data['confirmed']
            html_number = total
            if total > 0:
                total = self.__html_link(construct_url('reports:unsafes', self._core[j_id]), total)
            if confirmed > 0:
                confirmed = self.__html_link(construct_url('reports:unsafes', self._core[j_id], confirmed=1), confirmed)
            self._values_data[j_id]['unsafe:total'] = {
                'html': '{} ({})'.format(confirmed, total), 'number': html_number
            }

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

    def __collect_unknowns(self):
        numbers = {}
        unmarked = {}
        totals = {}
        for r_id, component, problems in ReportUnknownCache.objects.filter(report__root_id__in=self._roots)\
                .values_list('report__root_id', 'report__component', 'problems'):
            j_id = self._roots[r_id]

            numbers.setdefault(j_id, {})
            for problem, number in problems.items():
                numbers[j_id].setdefault((component, problem), 0)
                numbers[j_id][(component, problem)] += 1

            if len(problems) == 0:
                unmarked.setdefault(j_id, {})
                unmarked[j_id].setdefault(component, 0)
                unmarked[j_id][component] += 1

            totals.setdefault(j_id, {})
            totals[j_id].setdefault(component, 0)
            totals[j_id][component] += 1

        # Get numbers of problems
        for j_id in numbers:
            for component, problem in numbers[j_id]:
                column = 'problem:{}:{}'.format(self.slugify(component), self.slugify(problem))
                url = construct_url('reports:unknowns', self._core[j_id], component=component, problem=problem)
                value = numbers[j_id][(component, problem)]
                self._values_data[j_id][column] = self.__get_cell(value, url=url, number=value)

        # Get numbers of unknowns without marks
        for j_id in unmarked:
            for component in unmarked[j_id]:
                column = 'problem:{}:no_mark'.format(self.slugify(component))
                url = construct_url('reports:unknowns', self._core[j_id], component=component, problem=0)
                value = unmarked[j_id][component]
                self._values_data[j_id][column] = self.__get_cell(value, url=url, number=value)

        # Get total numbers of unknowns
        for j_id in totals:
            total_number = 0
            for component, number in totals[j_id].items():
                column = 'problem:{}:total'.format(self.slugify(component))
                url = construct_url('reports:unknowns', self._core[j_id], component=component)
                self._values_data[j_id][column] = self.__get_cell(number, url=url)
                total_number += number
            self._values_data[j_id]['problem:total'] = self.__get_cell(
                total_number, url=reverse('reports:unknowns', args=[self._core[j_id]]), number=total_number
            )

    def __collect_safe_tags(self):
        numbers = {}
        for r_id, tags in ReportSafeCache.objects.filter(report__root_id__in=self._roots)\
                .values_list('report__root_id', 'tags'):
            j_id = self._roots[r_id]
            numbers.setdefault(j_id, {})
            for tag, number in tags.items():
                numbers[j_id].setdefault(tag, 0)
                numbers[j_id][tag] += 1

        for j_id in numbers:
            for tag, num in numbers[j_id].items():
                column = 'tag:safe:{}'.format(self.slugify(tag))
                url = construct_url('reports:safes', self._core[j_id], tag=tag)
                self._values_data[j_id][column] = self.__get_cell(num, url=url, number=num)

    def __collect_unsafe_tags(self):
        numbers = {}
        for r_id, tags in ReportUnsafeCache.objects.filter(report__root_id__in=self._roots) \
                .values_list('report__root_id', 'tags'):
            j_id = self._roots[r_id]
            numbers.setdefault(j_id, {})
            for tag, number in tags.items():
                numbers[j_id].setdefault(tag, 0)
                numbers[j_id][tag] += 1

        for j_id in numbers:
            for tag, num in numbers[j_id].items():
                column = 'tag:unsafe:{}'.format(self.slugify(tag))
                url = construct_url('reports:unsafes', self._core[j_id], tag=tag)
                self._values_data[j_id][column] = self.__get_cell(num, url=url, number=num)

    def __collect_resourses(self):
        for root in ReportRoot.objects.filter(id__in=self._roots).only('resources', 'job_id'):
            for component in root.resources:
                column = 'resource:{}'.format(self.slugify(component))
                value = "{} {} {}".format(
                    HumanizedValue(root.resources[component]['wall_time'], user=self._user).timedelta,
                    HumanizedValue(root.resources[component]['cpu_time'], user=self._user).timedelta,
                    HumanizedValue(root.resources[component]['memory'], user=self._user).memory,
                )
                self._values_data[root.job_id][column] = self.__get_cell(value)

    def __collect_roles(self):
        author_of = set(Job.objects.filter(id__in=self._job_ids, author=self._user).values_list('id', flat=True))

        global_roles = {}
        for fv in JobHistory.objects.filter(job_id__in=self._job_ids, version=F('job__version'))\
                .only('job_id', 'global_role'):
            global_roles[fv.job_id] = fv.get_global_role_display()

        user_role_filters = {
            'user': self._user,
            'job_version__job_id__in': self._job_ids,
            'job_version__version': F('job_version__job__version')
        }
        job_user_roles = {}
        for ur in UserRole.objects.filter(**user_role_filters).only('job_version__job_id', 'role'):
            job_user_roles[ur.job_version.job_id] = ur.get_role_display()

        for j_id in self._job_ids:
            if j_id in author_of:
                job_role = _('Author')
            elif self._user.role == USER_ROLES[2][0]:
                job_role = self._user.get_role_display()
            elif j_id in job_user_roles:
                job_role = job_user_roles[j_id]
            else:
                job_role = global_roles[j_id]
            self._values_data[j_id]['role'] = self.__get_cell(job_role)

    def __collect_progress_data(self):
        decisions_qs = Decision.objects.filter(job_id__in=self._job_ids)

        for progress in ProgressSerializerRO(instance=decisions_qs, many=True, context={'user': self._user}).data:
            if 'total_ts' in progress:
                self._values_data[progress['job']]['tasks:total_ts'] = self.__get_cell(
                    progress['total_ts'], number=progress['total_ts']
                )
            if 'total_sj' in progress:
                self._values_data[progress['job']]['subjobs:total_sj'] = self.__get_cell(
                    progress['total_sj'], number=progress['total_sj']
                )

            job_progress = {'start_date': progress['start_date'], 'finish_date': progress['finish_date']}
            if 'progress_ts' in progress:
                job_progress['tasks:progress_ts'] = progress['progress_ts']['progress']
                job_progress['tasks:start_ts'] = progress['progress_ts']['start']
                job_progress['tasks:finish_ts'] = progress['progress_ts']['finish']
                if 'expected_time' in progress['progress_ts']:
                    job_progress['tasks:expected_time_ts'] = progress['progress_ts']['expected_time']
            if 'progress_sj' in progress:
                job_progress['tasks:progress_sj'] = progress['progress_sj']['progress']
                job_progress['tasks:start_sj'] = progress['progress_sj']['start']
                job_progress['tasks:finish_sj'] = progress['progress_sj']['finish']
                if 'expected_time' in progress['progress_sj']:
                    job_progress['tasks:expected_time_sj'] = progress['progress_sj']['expected_time']

            for column, value in job_progress.items():
                self._values_data[progress['job']][column] = self.__get_cell(value)

        for decision in decisions_qs:
            countable_data = {
                'tasks:total': decision.tasks_total,
                'tasks:cancelled': decision.tasks_cancelled,
                'tasks:error': decision.tasks_error,
                'tasks:finished': decision.tasks_finished,
                'tasks:processing': decision.tasks_processing,
                'tasks:pending': decision.tasks_pending,
                'tasks:solutions': decision.solutions
            }
            for column, value in countable_data.items():
                self._values_data[decision.job_id][column] = self.__get_cell(value, number=value)

            self._values_data[decision.job_id]['priority'] = self.__get_cell(decision.get_priority_display())
            if decision.start_date is not None and decision.finish_date is not None:
                solution_wall = HumanizedValue(
                    int((decision.finish_date - decision.start_date).total_seconds() * 1000), user=self._user
                ).timedelta
                self._values_data[decision.job_id]['solution_wall_time'] = self.__get_cell(solution_wall)

        for root in ReportRoot.objects.filter(job_id__in=self._job_ids).exclude(user=None).select_related('user'):
            self._values_data[root.job_id]['operator'] = self.__get_cell(
                root.user.get_full_name(), url=reverse('users:show-profile', args=[root.user_id])
            )

    @cached_property
    def _countable(self):
        countable = {
            'tasks:pending', 'tasks:processing', 'tasks:finished', 'tasks:error',
            'tasks:cancelled', 'tasks:total', 'tasks:solutions', 'tasks:total_ts', 'subjobs:total_sj'
        }
        countable_prefexes = {'safe:', 'unsafe:', 'tag:', 'problem:'}

        countable_columns = set()
        for col in self._columns:
            if col in countable or any(col.startswith(prefix) for prefix in countable_prefexes):
                countable_columns.add(col)
        return countable_columns

    def __get_footer(self):
        # Footer title length
        foot_length = 0
        for col in self._columns:
            if col in self._countable:
                break
            foot_length += 1
        else:
            foot_length = None

        # Footer columns
        footer = []
        if foot_length is not None and len(self.values) > 0:
            for i in range(foot_length, len(self._columns)):
                footer.append(str(i) if self._columns[i] in self._countable else None)
        return foot_length, footer
