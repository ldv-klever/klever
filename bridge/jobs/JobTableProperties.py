#
# Copyright (c) 2019 ISP RAS (http://www.ispras.ru)
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

from collections import OrderedDict
from datetime import timedelta
from slugify import slugify

from django.db.models import Q, Case, When, Count
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _
from django.utils.timezone import now

from mptt.utils import tree_item_iterator

from bridge.vars import PRIORITY, SafeVerdicts, UnsafeVerdicts, JOB_ROLES, DECISION_STATUS, PRESET_JOB_TYPE
from bridge.utils import construct_url
from bridge.tableHead import ComplexHeaderMixin

from jobs.models import UserRole, PresetJob, Job, Decision
from reports.models import ReportComponent, DecisionCache
from caches.models import ReportSafeCache, ReportUnsafeCache, ReportUnknownCache

from users.utils import HumanizedValue
from jobs.utils import SAFES, UNSAFES, TITLES
from service.serializers import ProgressSerializerRO


TASKS_COLUMNS = [
    'tasks', 'tasks:pending', 'tasks:processing', 'tasks:finished', 'tasks:error', 'tasks:cancelled',
    'tasks:total', 'tasks:solutions', 'tasks:total_ts', 'tasks:start_ts', 'tasks:finish_ts',
    'tasks:progress_ts', 'tasks:expected_time_ts'
]

SUBJOBS_COLUMNS = [
    'subjobs', 'subjobs:total_sj', 'subjobs:start_sj', 'subjobs:finish_sj',
    'subjobs:progress_sj', 'subjobs:expected_time_sj'
]


def tree_supported_columns():
    return ['role', 'author', 'creation_date', 'status', 'unsafe'] + \
           list("unsafe:{0}".format(u) for u in UNSAFES) + \
           ['safe'] + list("safe:{0}".format(s) for s in SAFES) + \
           TASKS_COLUMNS + SUBJOBS_COLUMNS + [
               'problem', 'problem:total', 'resource', 'tag', 'tag:safe', 'tag:unsafe', 'identifier',
               'version', 'priority', 'start_date', 'finish_date', 'solution_wall_time', 'operator'
           ]


def html_link(url, text):
    return '<a href="{0}">{1}</a>'.format(url, text)


def cell_value(value, url=None):
    if url:
        return {'html': html_link(url, value)}
    return {'text': '-' if value is None else str(value)}


def jobs_view_queryset(view, qs_filter=None):
    if qs_filter is None:
        qs_filter = Q()

    if 'title' in view:
        qs_filter &= Q(**{'name__' + view['title'][0]: view['title'][1]})

    if 'author' in view:
        author_filter = Q(author_id=int(view['author'][1]))
        qs_filter &= author_filter if view['author'][0] == 'is' else ~author_filter

    if 'creation_date' in view:
        limit_time = now() - timedelta(**{view['creation_date'][2]: int(view['creation_date'][1])})
        qs_filter &= Q(**{'creation_date__' + view['creation_date'][0]: limit_time})

    if 'hidden' in view and 'without_decision' in view['hidden']:
        # Exclude jobs without decisions
        qs_filter &= Q(decision__isnull=False)

    # Filter by access to view jobs
    if not view.user.is_manager and not view.user.is_expert:
        custom_access_ids = set(UserRole.objects.filter(user=view.user)
                                .exclude(role=JOB_ROLES[0][0]).values_list('job_id', flat=True))
        qs_filter &= (Q(author=view.user) | ~Q(global_role=JOB_ROLES[0][0]) | Q(id__in=custom_access_ids))

    # Get queryset order
    qs_order = ('id',)
    if 'jobs_order' in view and len(view['jobs_order']) == 2 and view['jobs_order'][1]:
        order_value = view['jobs_order'][1]
        if view['jobs_order'][0] == 'up':
            order_value = '-' + order_value
        qs_order = (order_value, 'id')

    return Job.objects.filter(qs_filter).select_related('author').order_by(*qs_order)


def decisions_view_queryset(view, qs_filter=None):
    if qs_filter is None:
        qs_filter = Q()

    if 'title' in view:
        qs_filter &= Q(**{'job__name__' + view['title'][0]: view['title'][1]})

    if 'author' in view:
        author_filter = Q(job__author_id=int(view['author'][1]))
        qs_filter &= author_filter if view['author'][0] == 'is' else ~author_filter

    if 'creation_date' in view:
        limit_time = now() - timedelta(**{view['creation_date'][2]: int(view['creation_date'][1])})
        qs_filter &= Q(**{'job__creation_date__' + view['creation_date'][0]: limit_time})

    if 'status' in view:
        qs_filter &= Q(status__in=view['status'])
    else:
        # Exclude decisions with hidden statuses
        qs_filter &= ~Q(status=DECISION_STATUS[0][0])

    if 'priority' in view:
        priority_filter = 'priority'
        priority_value = view['priority'][1]
        if view['priority'][0] == 'me':
            priorities = []
            for pr in PRIORITY:
                priorities.append(pr[0])
                if pr[0] == view['priority'][1]:
                    priority_filter += '__in'
                    priority_value = priorities
                    break
        elif view['priority'][0] == 'le':
            priorities = []
            for pr in reversed(PRIORITY):
                priorities.append(pr[0])
                if pr[0] == view['priority'][1]:
                    priority_filter += '__in'
                    priority_value = priorities
                    break
        qs_filter &= Q(**{priority_filter: priority_value})

    if 'start_date' in view:
        qs_filter &= Q(**{
            'start_date__month__' + view['start_date'][0]: int(view['start_date'][1]),
            'start_date__year__' + view['start_date'][0]: int(view['start_date'][2]),
        })

    if 'finish_date' in view:
        qs_filter &= Q(**{
            'finish_date__month__' + view['finish_date'][0]: int(view['finish_date'][1]),
            'finish_date__year__' + view['finish_date'][0]: int(view['finish_date'][2]),
        })

    if 'weight' in view:
        qs_filter &= Q(weight__in=view['weight'])

    # Get queryset order
    qs_order = ('id',)
    if 'decisions_order' in view and len(view['decisions_order']) == 2 and view['decisions_order'][1]:
        order_value = view['decisions_order'][1]
        if view['decisions_order'][0] == 'up':
            order_value = '-' + order_value
        qs_order = (order_value, 'id')

    return Decision.objects.filter(qs_filter).select_related('operator', 'job').order_by(*qs_order)


class JobsTreeTable(ComplexHeaderMixin):
    def __init__(self, view):
        self.view = view
        self._jobs_qs = jobs_view_queryset(view)
        self._decisions_qs = decisions_view_queryset(view)
        self._values_collector = TableTree(view, self._decisions_qs, tree_supported_columns())
        self.columns_num_range = range(len(self._values_collector.columns))
        self.selected_columns = self._values_collector.selected_columns
        self.available_columns = self._values_collector.available_columns

        # Get table header
        self.header = self.head_struct(
            ['checkbox', 'name'] + self._values_collector.columns, self._values_collector.titles
        )
        self.content = self.__get_table_content()

    def __get_table_content(self):
        # Get presets tree in tree order
        presets_tree = OrderedDict()
        for preset_job, tree_info in tree_item_iterator(PresetJob.objects.all()):
            presets_tree[preset_job.id] = {'instance': preset_job, 'jobs': OrderedDict()}

        for job in self._jobs_qs:
            presets_tree[job.preset_id]['jobs'][job.id] = {
                'instance': job, 'decisions': [], 'values': self.__get_job_values_row(job)
            }

        # Initialize values dictionary
        for decision in self._decisions_qs:
            if decision.job_id not in presets_tree[decision.job.preset_id]['jobs']:
                continue
            values_row = self._values_collector.get_decision_values_row(decision)
            presets_tree[decision.job.preset_id]['jobs'][decision.job_id]['decisions'].append([decision, values_row])
        return presets_tree

    def __get_job_values_row(self, job):
        values_row = []
        for col in self._values_collector.columns:
            if col == 'identifier':
                value = cell_value(str(job.identifier))
            elif col == 'role':
                value = cell_value(self._job_roles[job.id])
            elif col == 'author':
                author_val = author_url = None
                if job.author:
                    author_val = job.author.get_full_name()
                    author_url = reverse('users:show-profile', args=[job.author_id])
                value = cell_value(author_val, url=author_url)
            elif col == 'creation_date':
                value = cell_value(HumanizedValue(job.creation_date, user=self.view.user).date)
            else:
                value = cell_value('')
            values_row.append(value)
        return values_row

    @cached_property
    def _job_roles(self):
        # Get specific user roles
        jobs_ids = set(job.id for job in self._jobs_qs)
        job_user_roles = {}
        for ur in UserRole.objects.filter(user=self.view.user, job_id__in=jobs_ids).only('job_id', 'role'):
            job_user_roles[ur.job_version.job_id] = ur.get_role_display()

        # Get role for each job for the self._user
        job_roles_data = {}
        for job in self._jobs_qs:
            if job.id in job_roles_data:
                # Already processed for another decision
                continue
            if job.author_id == self.view.user.id:
                job_roles_data[job.id] = _('Author')
            elif job.id in job_user_roles:
                job_roles_data[job.id] = job_user_roles[job.id]
            else:
                job_roles_data[job.id] = job.get_global_role_display()
        return job_roles_data


class PresetChildrenTree:
    def __init__(self, preset_job):
        self._preset_job = preset_job
        self._jobs_qs = self.__get_jobs_queryset()
        self.children = self.__get_jobs_tree()

    def __get_jobs_queryset(self):
        qs_filter = Q(preset_id=self._preset_job.id)
        if self._preset_job.type == PRESET_JOB_TYPE[1][0]:
            qs_filter |= Q(preset__parent_id=self._preset_job.id)
        return Job.objects.filter(qs_filter).order_by('name').only('id', 'name', 'preset_id')

    def __get_job_value(self, job):
        return {'name': job.name, 'url': reverse('jobs:job', args=[job.id])}

    def __get_preset_value(self, preset):
        jobs_list = []
        for job in self._jobs_qs:
            if job.preset_id != preset.id:
                continue
            jobs_list.append(self.__get_job_value(job))
        return {'name': preset.name, 'url': reverse('jobs:preset', args=[preset.id]), 'children': jobs_list}

    def __get_jobs_tree(self):
        jobs_tree = []
        if self._preset_job.type == PRESET_JOB_TYPE[1][0]:
            # Collect jobs without custom preset directory first
            for job in self._jobs_qs:
                if job.preset_id == self._preset_job.id:
                    jobs_tree.append(self.__get_job_value(job))

            # Collect jobs of custom preset directories
            for preset in PresetJob.objects.filter(parent=self._preset_job).order_by('name').only('id', 'name'):
                jobs_tree.append(self.__get_preset_value(preset))
        else:
            for job in self._jobs_qs:
                jobs_tree.append(self.__get_job_value(job))
        return jobs_tree


class TableTree:
    no_mark = _('Without marks')
    total = _('Total')

    def __init__(self, view, queryset, supported_columns):
        self.view = view
        self._decisions_qs = queryset
        self.all_columns = supported_columns

        self._slugs = {}

        # Get core reports
        self._core = self.__get_core_reports()

        # Some titles are collected during __get_columns()
        self.titles = TITLES.copy()
        self.titles['checkbox'] = ''
        self.columns = self.__get_columns()

        # Collecting values data
        self._values_data = {}
        self.__fill_values_data()

    def get_decision_values_row(self, decision):
        if decision.pk not in self._values_data:
            return list(cell_value('') for __ in range(len(self.columns)))
        values_row = []
        for col in self.columns:
            if col in self._job_columns:
                # Ignore specific job columns
                value = cell_value('')
            elif col == 'status':
                status_url = None
                if not decision.is_lightweight and decision.id in self._core:
                    status_url = reverse('reports:component', args=[self._core[decision.id]])
                value = cell_value(decision.get_status_display(), url=status_url)
            elif col == 'identifier':
                value = cell_value(decision.identifier)
            elif decision.pk in self._values_data and col in self._values_data[decision.pk]:
                value = self._values_data[decision.pk][col]
            else:
                value = cell_value('-')
            values_row.append(value)
        return values_row

    def slugify(self, source):
        if source not in self._slugs:
            self._slugs[source] = slugify(source)
        return self._slugs[source]

    @cached_property
    def _all_columns_set(self):
        return set(self.all_columns)

    @property
    def columns_num_range(self):
        return range(len(self.columns))

    @property
    def selected_columns(self):
        return list({'value': col, 'title': self.__column_title(col)}
                    for col in self.view['columns'] if col in self._all_columns_set)

    @property
    def available_columns(self):
        return list({'value': col, 'title': self.__column_title(col)} for col in self.all_columns)

    @cached_property
    def _job_columns(self):
        return {'role', 'author', 'creation_date'}

    @cached_property
    def _decisions_ids(self):
        return set(inst.id for inst in self._decisions_qs)

    def __column_title(self, column):
        col_parts = column.split(':')
        column_starts = []
        for i in range(len(col_parts)):
            column_starts.append(':'.join(col_parts[:(i + 1)]))

        titles = list(TITLES.get(col_st, col_st) for col_st in column_starts)
        title_pattern = '/'.join(list('{%s}' % i for i in range(len(titles))))
        return title_pattern.format(*titles)

    def __get_core_reports(self):
        cores_qs = ReportComponent.objects.filter(
            decision_id__in=self._decisions_ids, parent=None
        ).values_list('id', 'decision_id')
        return dict((decision_id, report_id) for report_id, decision_id in cores_qs)

    def __get_columns(self):
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
        columns = []
        for col in self.view['columns']:
            if col in self._all_columns_set:
                if col in extend_action:
                    columns.extend(extend_action[col]())
                else:
                    columns.append(col)
        return columns

    def __safe_tags_columns(self):
        all_tags = set()
        for s_tags in ReportSafeCache.objects.filter(report__decision_id__in=self._decisions_ids)\
                .values_list('tags', flat=True):
            all_tags |= set(s_tags)

        columns = []
        for tag in sorted(all_tags):
            columns.append('tag:safe:{}'.format(self.slugify(tag)))
        return columns

    def __unsafe_tags_columns(self):
        all_tags = set()
        for s_tags in ReportUnsafeCache.objects.filter(report__decision_id__in=self._decisions_ids)\
                .values_list('tags', flat=True):
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
        components = set(DecisionCache.objects.filter(decision_id__in=self._decisions_ids)
                         .values_list('component', flat=True))
        resource_columns = []
        for c_name in sorted(list(c for c in components if self.__filter_component(c))):
            column = 'resource:{}'.format(self.slugify(c_name))
            self.titles[column] = c_name
            resource_columns.append(column)
        resource_columns.append('resource:total')
        return resource_columns

    def __unknowns_columns(self):
        component_problems = {}
        qs_filters = {'report__decision_id__in': self._decisions_ids}
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
                self.titles[column] = problem
                columns.append(column)
            if len(component_problems[component]):
                column = 'problem:{}:no_mark'.format(self.slugify(component))
                self.titles[column] = self.no_mark
                columns.append(column)
            column = 'problem:{}:total'.format(self.slugify(component))
            self.titles[column] = self.total
            columns.append(column)
            self.titles['problem:{}'.format(self.slugify(component))] = component
        columns.append('problem:total')
        return columns

    def __fill_values_data(self):
        self._values_data = dict((decision.pk, {}) for decision in self._decisions_qs)

        self.__collect_verdicts()
        if any(x.startswith('problem:') for x in self.columns):
            self.__collect_unknowns()
        if any(x.startswith('tag:safe:') for x in self.columns):
            self.__collect_safe_tags()
        if any(x.startswith('tag:unsafe:') for x in self.columns):
            self.__collect_unsafe_tags()
        if any(x.startswith('resource:') for x in self.columns):
            self.__collect_resources()

        progress_columns = {'priority', 'solutions', 'start_date', 'finish_date', 'solution_wall_time', 'operator'} | \
            set(TASKS_COLUMNS) | set(SUBJOBS_COLUMNS)
        if any(x in progress_columns for x in self.columns):
            self.__collect_decision_data()

    def __get_safes_without_confirmed(self):
        total_safes = {}
        verdicts = SafeVerdicts()
        for d_id, v, number in ReportSafeCache.objects.filter(report__decision_id__in=self._decisions_ids)\
                .values('report__decision_id', 'verdict').annotate(number=Count('id'))\
                .values_list('report__decision_id', 'verdict', 'number'):

            safes_url = None
            if number > 0:
                safes_url = construct_url('reports:safes', self._core[d_id], verdict=v)
            self._values_data[d_id][verdicts.column(v)] = cell_value(number, url=safes_url)

            # Collect total number
            total_safes.setdefault(d_id, 0)
            total_safes[d_id] += number

        # Add numbers of total safes of the decision
        for d_id, number in total_safes.items():
            safes_url = None
            if number > 0:
                safes_url = construct_url('reports:safes', self._core[d_id])
            self._values_data[d_id]['safe:total'] = cell_value(number, url=safes_url)

    def __get_unsafes_without_confirmed(self):
        total_unsafes = {}
        verdicts = UnsafeVerdicts()
        for d_id, v, number in ReportUnsafeCache.objects.filter(report__decision_id__in=self._decisions_ids)\
                .values('report__decision_id', 'verdict').annotate(number=Count('id'))\
                .values_list('report__decision_id', 'verdict', 'number'):

            unsafes_url = None
            if number > 0:
                unsafes_url = construct_url('reports:unsafes', self._core[d_id], verdict=v)
            self._values_data[d_id][verdicts.column(v)] = cell_value(number, url=unsafes_url)

            # Collect total number
            total_unsafes.setdefault(d_id, 0)
            total_unsafes[d_id] += number

        # Add numbers of total unsafes of the decision
        for d_id, number in total_unsafes.items():
            unsafes_url = None
            if number > 0:
                unsafes_url = construct_url('reports:unsafes', self._core[d_id])
            self._values_data[d_id]['unsafe:total'] = cell_value(number, url=unsafes_url)

    def __get_safes_with_confirmed(self):
        total_safes = {}
        verdicts = SafeVerdicts()

        # Collect safes data
        for d_id, v, total, confirmed in ReportSafeCache.objects\
                .filter(report__decision_id__in=self._decisions_ids).values('report__decision_id', 'verdict')\
                .annotate(total=Count('id'), confirmed=Count(Case(When(marks_confirmed__gt=0, then=1))))\
                .values_list('report__decision_id', 'verdict', 'total', 'confirmed'):

            # Collect total number
            total_safes.setdefault(d_id, {'total': 0, 'confirmed': 0})
            total_safes[d_id]['total'] += total
            total_safes[d_id]['confirmed'] += confirmed

            if total > 0:
                total = html_link(construct_url('reports:safes', self._core[d_id], verdict=v), total)

            if v == verdicts.unassociated:
                html_value = str(total)
            elif confirmed > 0:
                confirmed_url = construct_url('reports:safes', self._core[d_id], verdict=v, confirmed=1)
                html_value = '{} ({})'.format(html_link(confirmed_url, confirmed), total)
            else:
                html_value = '0 ({})'.format(total)
            self._values_data[d_id][verdicts.column(v)] = {'html': html_value}

        # Add numbers of total safes of the deicision
        for d_id, total_data in total_safes.items():
            total, confirmed = total_data['total'], total_data['confirmed']
            if total > 0:
                total = html_link(construct_url('reports:safes', self._core[d_id]), total)
            if confirmed > 0:
                confirmed = html_link(construct_url('reports:safes', self._core[d_id], confirmed=1), confirmed)
            self._values_data[d_id]['safe:total'] = {'html': '{} ({})'.format(confirmed, total)}

    def __get_unsafes_with_confirmed(self):
        total_unsafes = {}
        verdicts = UnsafeVerdicts()

        # Collect unsafes
        for d_id, v, total, confirmed in ReportUnsafeCache.objects\
                .filter(report__decision_id__in=self._decisions_ids).values('report__decision_id', 'verdict')\
                .annotate(total=Count('id'), confirmed=Count(Case(When(marks_confirmed__gt=0, then=1))))\
                .values_list('report__decision_id', 'verdict', 'total', 'confirmed'):

            # Collect total number
            total_unsafes.setdefault(d_id, {'total': 0, 'confirmed': 0})
            total_unsafes[d_id]['total'] += total
            total_unsafes[d_id]['confirmed'] += confirmed

            if total > 0:
                total = html_link(construct_url('reports:unsafes', self._core[d_id], verdict=v), total)

            if v == verdicts.unassociated:
                html_value = str(total)
            elif confirmed > 0:
                confirmed_url = construct_url('reports:unsafes', self._core[d_id], verdict=v, confirmed=1)
                html_value = '{} ({})'.format(html_link(confirmed_url, confirmed), total)
            else:
                html_value = '0 ({})'.format(total)
            self._values_data[d_id][verdicts.column(v)] = {'html': html_value}

        # Add numbers of total safes of the decision
        for d_id, total_data in total_unsafes.items():
            total, confirmed = total_data['total'], total_data['confirmed']
            if total > 0:
                total = html_link(construct_url('reports:unsafes', self._core[d_id]), total)
            if confirmed > 0:
                confirmed = html_link(construct_url('reports:unsafes', self._core[d_id], confirmed=1), confirmed)
            self._values_data[d_id]['unsafe:total'] = {'html': '{} ({})'.format(confirmed, total)}

    def __collect_verdicts(self):
        if any(col.startswith('safe:') for col in self.columns):
            if 'hidden' in self.view and 'confirmed_marks' in self.view['hidden']:
                self.__get_safes_without_confirmed()
            else:
                self.__get_safes_with_confirmed()

        if any(col.startswith('unsafe:') for col in self.columns):
            if 'hidden' in self.view and 'confirmed_marks' in self.view['hidden']:
                self.__get_unsafes_without_confirmed()
            else:
                self.__get_unsafes_with_confirmed()

    def __collect_unknowns(self):
        numbers = {}
        unmarked = {}
        totals = {}
        for d_id, component, problems in ReportUnknownCache.objects\
                .filter(report__decision_id__in=self._decisions_ids)\
                .values_list('report__decision_id', 'report__component', 'problems'):

            numbers.setdefault(d_id, {})
            for problem, number in problems.items():
                numbers[d_id].setdefault((component, problem), 0)
                numbers[d_id][(component, problem)] += 1

            if len(problems) == 0:
                unmarked.setdefault(d_id, {})
                unmarked[d_id].setdefault(component, 0)
                unmarked[d_id][component] += 1

            totals.setdefault(d_id, {})
            totals[d_id].setdefault(component, 0)
            totals[d_id][component] += 1

        # Get numbers of problems
        for d_id in numbers:
            for component, problem in numbers[d_id]:
                column = 'problem:{}:{}'.format(self.slugify(component), self.slugify(problem))
                url = construct_url('reports:unknowns', self._core[d_id], component=component, problem=problem)
                value = numbers[d_id][(component, problem)]
                self._values_data[d_id][column] = cell_value(value, url=url)

        # Get numbers of unknowns without marks
        for d_id in unmarked:
            for component in unmarked[d_id]:
                column = 'problem:{}:no_mark'.format(self.slugify(component))
                url = construct_url('reports:unknowns', self._core[d_id], component=component, problem=0)
                value = unmarked[d_id][component]
                self._values_data[d_id][column] = cell_value(value, url=url)

        # Get total numbers of unknowns
        for d_id in totals:
            total_number = 0
            for component, number in totals[d_id].items():
                column = 'problem:{}:total'.format(self.slugify(component))
                url = construct_url('reports:unknowns', self._core[d_id], component=component)
                self._values_data[d_id][column] = cell_value(number, url=url)
                total_number += number
            self._values_data[d_id]['problem:total'] = cell_value(
                total_number, url=reverse('reports:unknowns', args=[self._core[d_id]])
            )

    def __collect_safe_tags(self):
        self.__collect_tags(ReportSafeCache, 'safe')

    def __collect_unsafe_tags(self):
        self.__collect_tags(ReportUnsafeCache, 'unsafe')

    def __collect_tags(self, cache_model, tags_type):
        """
        Collect tags data for decisions.
        :param cache_model: ReportSafeCache or ReportUnsafeCache
        :param tags_type: "safe" or "unsafe"
        :return: nothing
        """
        tags_qs = cache_model.objects\
            .filter(report__decision_id__in=self._decisions_ids)\
            .values_list('report__decision_id', 'tags')
        numbers = {}
        for d_id, tags in tags_qs:
            numbers.setdefault(d_id, {})
            for tag, number in tags.items():
                numbers[d_id].setdefault(tag, 0)
                numbers[d_id][tag] += 1

        for d_id in numbers:
            for tag, num in numbers[d_id].items():
                column = 'tag:{}:{}'.format(tags_type, self.slugify(tag))
                url = construct_url('reports:{}s'.format(tags_type), self._core[d_id], tag=tag)
                self._values_data[d_id][column] = cell_value(num, url=url)

    def __collect_resources(self):
        total_resources = {}
        for cache_obj in DecisionCache.objects.filter(decision_id__in=self._decisions_ids).select_related('decision'):
            value = "{} {} {}".format(
                HumanizedValue(cache_obj.wall_time, user=self.view.user).timedelta,
                HumanizedValue(cache_obj.cpu_time, user=self.view.user).timedelta,
                HumanizedValue(cache_obj.memory, user=self.view.user).memory,
            )
            column = 'resource:{}'.format(self.slugify(cache_obj.component))
            self._values_data[cache_obj.decision_id][column] = cell_value(value)
            total_resources.setdefault(cache_obj.decision_id, [0, 0, 0])
            total_resources[cache_obj.decision_id][0] += cache_obj.wall_time
            total_resources[cache_obj.decision_id][1] += cache_obj.cpu_time
            total_resources[cache_obj.decision_id][2] = max(total_resources[cache_obj.decision_id][2], cache_obj.memory)

        for d_id in total_resources:
            value = "{} {} {}".format(
                HumanizedValue(total_resources[d_id][0], user=self.view.user).timedelta,
                HumanizedValue(total_resources[d_id][1], user=self.view.user).timedelta,
                HumanizedValue(total_resources[d_id][2], user=self.view.user).memory,
            )
            self._values_data[d_id]['resource:total'] = cell_value(value)

    def __collect_decision_data(self):
        prodress_data = ProgressSerializerRO(
            instance=self._decisions_qs, many=True, context={'user': self.view.user}
        ).data
        for progress in prodress_data:
            if 'total_ts' in progress:
                self._values_data[progress['id']]['tasks:total_ts'] = cell_value(progress['total_ts'])
            if 'total_sj' in progress:
                self._values_data[progress['id']]['subjobs:total_sj'] = cell_value(progress['total_sj'])

            decision_progress = {'start_date': progress['start_date'], 'finish_date': progress['finish_date']}
            if 'progress_ts' in progress:
                decision_progress['tasks:progress_ts'] = progress['progress_ts']['progress']
                decision_progress['tasks:start_ts'] = progress['progress_ts']['start']
                decision_progress['tasks:finish_ts'] = progress['progress_ts']['finish']
                if 'expected_time' in progress['progress_ts']:
                    decision_progress['tasks:expected_time_ts'] = progress['progress_ts']['expected_time']
            if 'progress_sj' in progress:
                decision_progress['tasks:progress_sj'] = progress['progress_sj']['progress']
                decision_progress['tasks:start_sj'] = progress['progress_sj']['start']
                decision_progress['tasks:finish_sj'] = progress['progress_sj']['finish']
                if 'expected_time' in progress['progress_sj']:
                    decision_progress['tasks:expected_time_sj'] = progress['progress_sj']['expected_time']

            for column, value in decision_progress.items():
                self._values_data[progress['id']][column] = cell_value(value)

        for decision in self._decisions_qs:
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
                self._values_data[decision.id][column] = cell_value(value)

            self._values_data[decision.id]['priority'] = cell_value(decision.get_priority_display())
            if decision.start_date is not None and decision.finish_date is not None:
                solution_wall = HumanizedValue(
                    int((decision.finish_date - decision.start_date).total_seconds() * 1000), user=self.view.user
                ).timedelta
                self._values_data[decision.id]['solution_wall_time'] = cell_value(solution_wall)

            if decision.operator:
                self._values_data[decision.id]['operator'] = cell_value(
                    decision.operator.get_full_name(), url=reverse('users:show-profile', args=[decision.operator_id])
                )
