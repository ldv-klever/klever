import json
import re
import pytz
from datetime import datetime, timedelta
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.utils.translation import ugettext_lazy as _
from django.utils.translation import string_concat
from jobs.job_model import Job
import jobs.job_functions as job_f
from Omega.vars import JOB_DEF_VIEW, USER_ROLES, JOB_STATUS
from jobs.job_functions import SAFES, UNSAFES, convert_memory, convert_time,\
    TITLES


# List of main classes of columns
MAIN_COLUMNS = [
    'name',
    'author',
    'date',
    'status',
    'unsafe',
    'safe',
    'problem',
    'resource',
]

ADDITIONAL_COLUMNS = [
    'identifier',
    'format',
    'version',
    'type',
    'parent_name',
    'parent_id',
    'role',
]


# List of available for user variables for sorting jobs
ORDERS = [
    ('name', 'name'),
    ('change_author__extended__last_name', 'author'),
    ('change_date', 'date'),
    ('reportroot__status', 'status'),
]

ORDER_TITLES = {
    'name':  _('Title'),
    'author': _('Author last name'),
    'date': _('Date'),
    'status': _('Status'),
}

FILTER_TYPE_TITLES = {
    'is': _('Is'),
    'isnot': _('Is not'),
    'iexact': _('Is'),
    'istartswith': _('Starts with'),
    'icontains': _('Contains'),
    'younger': _('Younger than'),
    'older': _('Older than'),
}

ALL_FILTERS = [
    'name',
    'change_author',
    'change_date',
    'status',
    'resource_component',
    'problem_component',
    'problem_problem',
    'format',
]

FILTER_NAME_TITLES = {
    'name': _('Title'),
    'change_author': _('Author'),
    'change_date': _('Last change'),
    'status': _('Status'),
    'resource_component': _('Resource/Component'),
    'problem_component': _('Problem/Component'),
    'problem_problem': _('Problem name'),
    'format': _('Format'),
}


def get_view(user, view=None, view_id=None):
    if view is None:
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
    else:
        return json.loads(view), None
    return JOB_DEF_VIEW, 'default'


class FilterForm(object):
    def __init__(self, user, view=None, view_id=None):
        self.cnt = 1
        self.available_filters = []
        (self.view, self.view_id) = get_view(user, view=view, view_id=view_id)
        self.selected_columns = self.__selected()
        self.available_columns = self.__available()
        self.available_orders = self.__available_orders()
        self.selected_orders = self.__selected_orders()
        self.filters = self.__view_filters()
        self.user_views = self.__user_views(user)

    def __selected(self):

        selected_columns = []
        for col in self.view['columns']:
            if col != 'name' and col in MAIN_COLUMNS + all_user_columns():
                selected_columns.append(col)

        columns = []
        for col in selected_columns:
            columns.append({
                'value': col,
                'title': self.__full_title(col),
            })
        return columns

    def __available(self):
        columns = []
        for col in all_user_columns():
            columns.append({
                'value': col,
                'title': self.__full_title(col),
            })
        return columns

    def __full_title(self, column):
        self.cnt += 1
        col_parts = column.split(':')
        column_starts = []
        for i in range(0, len(col_parts)):
            part = col_parts[0]
            for j in range(1, i + 1):
                part += ':' + col_parts[j]
            column_starts.append(part)
        titles = []
        for col_st in column_starts:
            titles.append(TITLES[col_st])

        concated_title = titles[0]
        for i in range(1, len(titles)):
            concated_title = string_concat(concated_title, '/', titles[i])
        return concated_title

    def __available_orders(self):
        new_orders = []
        user_orders = self.view['orders']
        for o in [x[1] for x in ORDERS]:
            if not(o in user_orders or ('-%s' % o) in user_orders):
                new_orders.append({
                    'value': o,
                    'title': ORDER_TITLES[o],
                })
        return new_orders

    def __selected_orders(self):
        new_orders = []
        user_orders = self.view['orders']
        for o in user_orders:
            if o in [x[1] for x in ORDERS]:
                new_orders.append({
                    'value': o,
                    'title': ORDER_TITLES[o],
                    'up': '0',
                })
            elif o.startswith('-') and o[1:] in [x[1] for x in ORDERS]:
                new_orders.append({
                    'value': o[1:],
                    'title': ORDER_TITLES[o[1:]],
                    'up': '1',
                })
        return new_orders

    def __user_views(self, user):
        self.cnt += 1
        view_data = []
        views = user.view_set.filter(type='1')
        for v in views:
            view_data.append({
                'title': v.name,
                'value': 'view_%d' % v.pk,
            })
        return view_data

    def __view_filters(self):
        view_filters = []
        selected_filters = []
        for f_name in sorted(self.view['filters']):
            if f_name in FILTER_NAME_TITLES:
                f = self.view['filters'][f_name]
                f_val = f['value']
                if f_name == 'change_date':
                    date_vals = f['value'].split(':', 1)
                    f_val = {
                        'valtype': date_vals[0],
                        'valval': date_vals[1],
                    }
                selected_filters.append(f_name)
                view_filters.append({
                    'name': f_name,
                    'name_title': FILTER_NAME_TITLES[f_name],
                    'type': f['type'],
                    'type_title': FILTER_TYPE_TITLES.get(f['type'],
                                                         'ERR404:type_title'),
                    'value': f_val,
                })
        for f_name in ALL_FILTERS:
            if f_name not in selected_filters:
                self.available_filters.append({
                    'name': f_name,
                    'name_title': FILTER_NAME_TITLES[f_name],
                })
        return view_filters


def all_user_columns():
    columns = []
    for col in MAIN_COLUMNS:
        if col == 'safe':
            columns.append('safe')
            for safe in SAFES:
                columns.append("%s:%s" % (col, safe))
        elif col == 'unsafe':
            columns.append('unsafe')
            for unsafe in UNSAFES:
                columns.append("%s:%s" % (col, unsafe))

        elif col != 'name':
            columns.append(col)
    columns.extend(['tag', 'tag:safe', 'tag:unsafe'])
    columns.extend(ADDITIONAL_COLUMNS)
    return columns


class TableHeader(object):
    def __init__(self, columns, titles):
        self.columns = columns
        self.titles = titles
        self.header_struct = self.__header_struct()

    def __header_struct(self):
        col_data = []
        depth = self.__max_depth()
        for d in range(1, depth + 1):
            col_data.append(self.__cellspan_level(d, depth))
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
        else:
            return column

    def __cellspan_level(self, lvl, max_depth):

        # Collecting first lvl identifiers of all table columns.
        # Example: 'a:b:c:d:e' (lvl=3) -> 'a:b:c'
        # Example: 'a:b' (lvl=3) -> ''
        all_columns_of_lvl = []
        for col in self.columns:
            col_parts = col.split(':')
            col_start = ''
            if len(col_parts) >= lvl:
                col_start = col.rsplit(':', len(col_parts) - lvl)[0]
            all_columns_of_lvl.append(col_start)

        # Colecting single identifiers and their amount without ''.
        # Example: [a, a, a, b, '', c, c, c, c, '', '', c, d, d] ->
        # [(a, 3), (b, 1), (c, 4), (c, 1), (d, 2)]
        columns_of_lvl = []
        prev_col = ''
        cnt = 0
        for col in all_columns_of_lvl:
            if col == '':
                if prev_col != '':
                    columns_of_lvl.append([prev_col, cnt])
                cnt = 0
            elif col == prev_col:
                cnt += 1
            else:
                if prev_col != '':
                    columns_of_lvl.append([prev_col, cnt])
                cnt = 1
            prev_col = col
        if prev_col != '' and cnt > 0:
            columns_of_lvl.append([prev_col, cnt])

        # Collecting data of cell span for columns.
        col_data = []
        for col in columns_of_lvl:
            nrows = max_depth - lvl + 1
            for column in self.columns:
                if column.startswith(col[0]) and col[0] != column:
                    nrows = 1
            col_data.append({
                'column': col[0],
                'rows': nrows,
                'columns': col[1],
                'title': self.__title(col[0]),
            })
        return col_data


class TableTree(object):
    def __init__(self, user, view=None, view_id=None):
        self.cnt = 0
        self.user = user
        self.columns = ['name']
        (self.view, self.view_id) = get_view(user, view=view, view_id=view_id)
        self.titles = TITLES
        self.head_filters = self.__get_head_filters()
        (self.rowdata, self.blackdata) = self.__get_rowdata()
        self.__get_table_columns_list()
        self.tableheader = TableHeader(self.columns, self.titles).header_struct
        self.values = self.__values()

    def __get_rowdata(self):
        orders = query_orders(self.view['orders'])
        filters = self.__view_filters()
        jobdata = Job.objects.filter(**filters).order_by(*orders)

        rowdata = []
        for job in jobdata:
            if job_f.has_job_access(self.user, job=job):
                rowdata.append(job)

        old_job_len = 0
        new_job_len = len(rowdata)
        blackdata = []
        while old_job_len < new_job_len:
            old_job_len = len(blackdata)
            for job in (rowdata + blackdata):
                if (job.parent is not None) and \
                        (job.parent not in (rowdata + blackdata)):
                    blackdata.append(job.parent)
            new_job_len = len(blackdata)
        return rowdata, blackdata

    def __get_head_filters(self):
        filters = [{}, {}, {}]
        for f in self.view['filters']:
            f_data = self.view['filters'][f]
            textfilters = ['iexact', 'istartswith', 'icontains']
            if f == 'resource_component':
                if f_data['type'] in textfilters:
                    filter_id = 'component__name__' + f_data['type']
                    filters[0] = {filter_id: f_data['value']}
            elif f == 'problem_component':
                if f_data['type'] in textfilters:
                    filter_id = 'component__name__' + f_data['type']
                    filters[1] = {filter_id: f_data['value']}
            elif f == 'problem_problem':
                if f_data['type'] in textfilters:
                    filter_id = 'problem__name__' + f_data['type']
                    filters[2] = {filter_id: f_data['value']}
        return filters

    def __view_filters(self):
        filters = {}
        for f in self.view['filters']:
            filters.update(query_filter(f, self.view['filters'][f]))
        return filters

    def __get_table_columns_list(self):
        for col in self.view['columns']:
            if col != 'name':
                if col in MAIN_COLUMNS:
                    self.columns.extend(self.__extend_column(col))
                elif col in all_user_columns():
                    self.columns.extend(self.__extend_column(col))

    def __extend_column(self, col):
        new_columns = []
        if col == 'safe':
            new_columns.extend([col + ':' + postfix for postfix in SAFES])
        elif col == 'unsafe':
            new_columns.extend([col + ':' + postfix for postfix in UNSAFES])
        elif col == 'resource':
            components = self.__component_resource()
            compres_new_cols = {}
            for component in components:
                compres_new_cols[component.pk] = component.name
            for c_id in sorted(compres_new_cols, key=compres_new_cols.get):
                component_id = "component_%s" % str(c_id)
                self.titles['resource:' + component_id] = compres_new_cols[c_id]
                new_columns.append(col + ':' + component_id)
            new_columns.append(col + ':total')
        elif col == 'problem':
            (probl_titles, probl_cols) = self.__component_problems()
            self.titles.update(probl_titles)
            new_columns.extend(probl_cols)
            new_columns.append('problem:total')
        elif col == 'tag':
            for tag in self.__safe_tags():
                st_id = 'tag:safe:tag_%s' % tag[1]
                new_columns.append(st_id)
                self.titles[st_id] = tag[0]
            for tag in self.__unsafe_tags():
                ut_id = 'tag:unsafe:tag_%s' % tag[1]
                new_columns.append(ut_id)
                self.titles[ut_id] = tag[0]
            return new_columns
        elif col == 'tag:safe':
            for tag in self.__safe_tags():
                st_id = 'tag:safe:tag_%s' % tag[1]
                new_columns.append(st_id)
                self.titles[st_id] = tag[0]
        elif col == 'tag:unsafe':
            for tag in self.__unsafe_tags():
                ut_id = 'tag:unsafe:tag_%s' % tag[1]
                new_columns.append(ut_id)
                self.titles[ut_id] = tag[0]
        else:
            new_columns.append(col)
        return new_columns

    def __safe_tags(self):
        tags = []
        for job in self.rowdata:
            tag_set = job.safe_tags.all().order_by('tag__tag')
            for tag in tag_set:
                st_name = tag.tag.tag
                st_id = tag.tag_id
                tags_elem = [st_name, st_id]
                if tags_elem not in tags:
                    tags.append(tags_elem)
        return sorted(tags)

    def __unsafe_tags(self):
        tags = []
        for job in self.rowdata:
            tag_set = job.unsafe_tags.all()
            for tag in tag_set:
                st_name = tag.tag.tag
                st_id = tag.tag_id
                tags_elem = [st_name, st_id]
                if tags_elem not in tags:
                    tags.append(tags_elem)
        return sorted(tags)

    def __component_resource(self):
        components = []
        for job in self.rowdata:
            if self.head_filters[0]:
                componentresource_set = job.componentresource_set.filter(
                    **self.head_filters[0]
                )
            else:
                componentresource_set = job.componentresource_set.all()
            for compres in componentresource_set:
                comp = compres.component
                if comp:
                    if comp not in components:
                        components.append(comp)
        return components

    def __component_problems(self):
        problems = {}
        for job in self.rowdata:
            if self.head_filters[1] and self.head_filters[2]:
                cmup_f = self.head_filters[1]
                cmup_f.update(self.head_filters[2])
            elif self.head_filters[1]:
                cmup_f = self.head_filters[1]
            elif self.head_filters[2]:
                cmup_f = self.head_filters[2]
            else:
                cmup_f = {}
            comp_mark_unknown_set = job.componentmarkunknownproblem_set.filter(
                **cmup_f
            )
            for compunk in comp_mark_unknown_set:
                comp = compunk.component
                problem = compunk.problem
                comp_id = 'pr_component_%s' % str(comp.pk)
                comp_name = comp.name
                if problem:
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
                else:
                    if comp_id in problems:
                        if 'z_no_mark' not in problems[comp_id]['problems']:
                            problems[comp_id]['problems']['z_no_mark'] = \
                                _('No EM')
                    else:
                        problems[comp_id] = {
                            'title': comp.name,
                            'problems': {
                                'z_no_mark': _('No EM'),
                                'z_total': _('Total')
                            }
                        }
        new_titles = {}
        new_columns = []
        for comp_id in sorted(problems):
            new_titles['problem:%s' % comp_id] = problems[comp_id]['title']
            for probl_id in sorted(problems[comp_id]['problems']):
                new_columns.append('problem:%s:%s' % (comp_id, probl_id))
                new_titles['problem:%s:%s' % (comp_id, probl_id)] = \
                    problems[comp_id]['problems'][probl_id]

        return new_titles, new_columns

    def __order_jobs(self):
        lvl = 1
        ordered_jobs = []
        for job in (self.rowdata + self.blackdata):
            if job.parent is None:
                lvljob = {'lvl': lvl, 'job': job, 'black': False}
                if job in self.blackdata:
                    lvljob['black'] = True
                ordered_jobs.append(lvljob)
        while len(ordered_jobs) < len(self.rowdata + self.blackdata):
            ordered_jobs = self.__insert_level(lvl, ordered_jobs)
            lvl += 1
            # maximum depth of jobs: 1000
            if lvl > 1000:
                return ordered_jobs
        return ordered_jobs

    def __insert_level(self, lvl, jobs):
        new_job_list = []
        for job in jobs:
            new_job_list.append(job)
            if job['lvl'] == lvl:
                for job_ch in (self.rowdata + self.blackdata):
                    if job_ch.parent == job['job']:
                        newjob = {'lvl': lvl + 1, 'job': job_ch, 'black': False}
                        if job_ch in self.blackdata:
                            newjob['black'] = True
                        new_job_list.append(newjob)
        return new_job_list

    def __values(self):
        table_rows = []
        jobs = self.__order_jobs()
        for job in jobs:
            row_values = []
            col_id = 0
            for col in self.columns:
                col_id += 1
                row_values.append({
                    'value': self.__get_value(job['job'], col, job['black']),
                    'id': '__'.join(col.split(':')) + ('__%d' % col_id),
                    'href': self.__get_href(job['job'], col, job['black']),
                })
            row_data = {
                'id': job['job'].pk,
                'parent': job['job'].parent_id,
                'values': row_values,
                'black': job['black'],
            }
            table_rows.append(row_data)
        return table_rows

    def __get_value(self, job, col, black):
        if col == 'name':
            if len(job.name) > 0:
                return job.name
            return '...'
        elif black:
            return ''
        elif col == 'author':
            author = job.change_author.extended
            return author.last_name + ' ' + author.first_name
        elif col == 'identifier':
            return job.identifier
        elif col == 'format':
            return job.format
        elif col == 'version':
            return job.version
        elif col == 'type':
            return job.get_type_display()
        elif col == 'date':
            return job.change_date
        elif col == 'status':
            try:
                return job.reportroot.get_status_display()
            except ObjectDoesNotExist:
                return '-'
        elif col.startswith('unsafe:'):
            try:
                verdicts = job.verdict
            except ObjectDoesNotExist:
                return '-'
            if col == 'unsafe:total':
                return verdicts.unsafe
            elif col == 'unsafe:bug':
                return verdicts.unsafe_bug
            elif col == 'unsafe:target_bug':
                return verdicts.unsafe_target_bug
            elif col == 'unsafe:false_positive':
                return verdicts.unsafe_false_positive
            elif col == 'unsafe:unknown':
                return verdicts.unsafe_unknown
            elif col == 'unsafe:unassociated':
                return verdicts.unsafe_unassociated
            elif col == 'unsafe:inconclusive':
                return verdicts.unsafe_inconclusive
            else:
                return 'E404:unsafe'
        elif col.startswith('safe:'):
            try:
                verdicts = job.verdict
            except ObjectDoesNotExist:
                return '-'
            if col == 'safe:total':
                return verdicts.safe
            elif col == 'safe:missed_bug':
                return verdicts.safe_missed_bug
            elif col == 'safe:unknown':
                return verdicts.safe_unknown
            elif col == 'safe:inconclusive':
                return verdicts.safe_inconclusive
            elif col == 'safe:unassociated':
                return verdicts.safe_unassociated
            elif col == 'safe:incorrect':
                return verdicts.safe_incorrect_proof
            else:
                return 'E404:safe'
        elif col == 'problem:total':
            try:
                verdicts = job.verdict
                return verdicts.unknown
            except ObjectDoesNotExist:
                return '-'
        elif col.startswith('problem:'):
            m = re.match(r'problem:pr_component_(\d+):problem_(\d+)', col)
            if m:
                comp_mark_unkn = job.componentmarkunknownproblem_set.filter(
                    component_id=int(m.group(1)), problem_id=int(m.group(2))
                )
                if len(comp_mark_unkn):
                    return comp_mark_unkn[0].number
                else:
                    return '-'
            m = re.match(r'problem:pr_component_(\d+):z_total', col)
            if m:
                try:
                    comp_unkn = job.componentunknown_set.get(
                        component_id=int(m.group(1)))
                    return comp_unkn.number
                except ObjectDoesNotExist:
                    return '-'
            m = re.match(r'problem:pr_component_(\d+):z_no_mark', col)
            if m:
                comp_mark_unkn_t = job.componentmarkunknownproblem_set.filter(
                    component_id=int(m.group(1)), problem=None
                )
                if len(comp_mark_unkn_t):
                    return comp_mark_unkn_t[0].number
                else:
                    return '-'
        elif col.startswith('resource:'):
            accuracy = self.user.extended.accuracy
            data_format = self.user.extended.data_format
            m = re.match(r'resource:component_(\d+)', col)
            if m:
                try:
                    comp_res = job.componentresource_set.get(
                        component_id=int(m.group(1))
                    )
                    wt = comp_res.wall_time
                    ct = comp_res.cpu_time
                    mem = comp_res.memory
                    if data_format == 'hum':
                        wt = convert_time(wt, accuracy)
                        ct = convert_time(ct, accuracy)
                        mem = convert_memory(mem, accuracy)
                    return "%s %s %s" % (wt, ct, mem)
                except ObjectDoesNotExist:
                    return '-'
            m = re.match(r'resource:total', col)
            if m:
                try:
                    comp_res = job.componentresource_set.get(component=None)
                    wt = comp_res.wall_time
                    ct = comp_res.cpu_time
                    mem = comp_res.memory
                    if data_format == 'hum':
                        wt = convert_time(wt, accuracy)
                        ct = convert_time(ct, accuracy)
                        mem = convert_memory(mem, accuracy)
                    return "%s %s %s" % (wt, ct, mem)
                except ObjectDoesNotExist:
                    return '-'
        elif col.startswith('tag:'):
            m = re.match(r'tag:safe:tag_(\d+)', col)
            if m:
                try:
                    mark_tag = job.safe_tags.get(
                        tag__pk=int(m.group(1))
                    )
                    return mark_tag.number
                except ObjectDoesNotExist:
                    return '-'
            m = re.match(r'tag:unsafe:tag_(\d+)', col)
            if m:
                try:
                    mark_tag = job.unsafe_tags.get(
                        tag__pk=int(m.group(1))
                    )
                    return mark_tag.number
                except ObjectDoesNotExist:
                    return '-'
        elif col == 'parent_name':
            if job.parent is None:
                return '-'
            else:
                return job.parent.name
        elif col == 'parent_id':
            if job.parent is None:
                return '-'
            else:
                return job.parent.identifier
        elif col == 'role':
            first_version = job.jobhistory_set.filter(version=1)
            if len(first_version):
                if first_version[0].change_author == self.user:
                    return _('Author')
            if self.user.extended.role == USER_ROLES[2][0]:
                return self.user.extended.get_role_display()
            user_role = job.userrole_set.filter(user=self.user)
            if len(user_role):
                return user_role[0].get_role_display()
            else:
                return job.get_global_role_display()
        return ''

    def __get_href(self, job, col, black):
        self.cnt += 1
        if job:
            if black:
                return None
            elif col == 'name':
                return reverse('jobs:job', args=[job.pk])
        return None


# Convert view order to accepted order that can be applied
def query_orders(orders):
    new_orders = []
    acceptable_orders = [x[1] for x in ORDERS]
    for order in orders:
        if order in acceptable_orders:
            new_orders.append(order)
        elif order.startswith('-') and order[1:] in acceptable_orders:
            new_orders.append(order)
    for i in range(len(new_orders)):
        for o in ORDERS:
            if o[1] == new_orders[i]:
                new_orders[i] = o[0]
            elif new_orders[i].startswith('-') and o[1] == new_orders[i][1:]:
                new_orders[i] = '-%s' % o[0]
    return new_orders


# Convert filter from view to django query
def query_filter(filter_name, filter_data):
    fil = {}
    textfilters = ['iexact', 'istartswith', 'icontains']
    if filter_name == 'name':
        if filter_data['type'] in textfilters:
            filter_id = filter_name + '__' + filter_data['type']
            fil[filter_id] = filter_data['value']
    elif filter_name == 'change_author':
        if filter_data['type'] == 'is':
            fil[filter_name + '__pk'] = int(filter_data['value'])
    elif filter_name == 'change_date':
        (measure, value) = filter_data['value'].split(':', 1)
        value = int(value)
        if measure == 'minutes':
            timed = timedelta(minutes=value)
        elif measure == 'hours':
            timed = timedelta(hours=value)
        elif measure == 'days':
            timed = timedelta(days=value)
        elif measure == 'weeks':
            timed = timedelta(weeks=value)
        else:
            timed = timedelta(seconds=1)
        limit_time = pytz.timezone('UTC').localize(datetime.now()) - timed
        if filter_data['type'] == 'older':
            fil[filter_name + '__' + 'lt'] = limit_time
        elif filter_data['type'] == 'younger':
            fil[filter_name + '__' + 'gt'] = limit_time
    elif filter_name == 'status':
        filter_name = 'reportroot__status'
        if filter_data['type'] == 'is':
            fil[filter_name] = filter_data['value']
        elif filter_data['type'] == 'isnot':
            other_vals = []
            for st_id in JOB_STATUS:
                if st_id[0] != filter_data['value']:
                    other_vals.append(st_id[0])
            fil[filter_name + '__in'] = other_vals
    elif filter_name == 'format':
        if filter_data['type'] == 'is':
            fil[filter_name] = filter_data['value']
    return fil
