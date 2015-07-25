import json
import re
import pytz
from datetime import datetime, timedelta
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.utils.translation import ugettext_lazy as _, string_concat
from jobs.job_model import Job
import jobs.job_functions as job_f
from Omega.vars import JOB_DEF_VIEW, USER_ROLES, JOB_STATUS
from jobs.job_functions import SAFES, UNSAFES, convert_memory, convert_time,\
    TITLES


ORDERS = [
    ('name', 'name'),
    ('change_author__extended__last_name', 'author'),
    ('change_date', 'date'),
    ('jobstatus__status', 'status')
]

ORDER_TITLES = {
    'name':  _('Title'),
    'author': string_concat(_('Author'), '/', _('Last name')),
    'date': _('Date'),
    'status': _('Decision status')
}

ALL_FILTERS = ['name', 'change_author', 'change_date', 'status',
               'resource_component', 'problem_component', 'problem_problem',
               'format']

FILTER_TITLES = {
    'name': _('Title'),
    'change_author': _('Author'),
    'change_date': _('Last change date'),
    'status': _('Decision status'),
    'resource_component': string_concat(
        _('Resources'), '/', _('Component name')),
    'problem_component': string_concat(_('Unknowns'), '/', _('Component name')),
    'problem_problem': _('Problem name'),
    'format': _('Format')
}


def all_user_columns():
    def_columns = ['name', 'role', 'author', 'date', 'status', 'unsafe', 'safe',
                   'problem', 'resource']
    add_columns = ['tag', 'tag:safe', 'tag:unsafe', 'identifier', 'format',
                   'version', 'type', 'parent_id']
    columns = []
    for col in def_columns:
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
    columns.extend(add_columns)
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
        self.cnt = 1
        (self.view, self.view_id) = get_view(user, view, view_id)
        self.selected_columns = self.__selected()
        self.available_columns = self.__available()
        self.selected_orders = self.__selected_orders()
        self.available_orders = self.__available_orders()
        self.available_filters = []
        self.selected_filters = self.__view_filters()
        self.user_views = self.__user_views(user)

    def __column_title(self, column):
        self.cnt = 1
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
        self.cnt += 1
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
                    f_val = {
                        'valtype': date_vals[0],
                        'valval': date_vals[1],
                    }
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


class TableHeader(object):

    def __init__(self, columns, titles):
        self.columns = columns
        self.titles = titles

    def header_struct(self):
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
                if column.startswith(col[0]) and col[0] != column:
                    nrows = 1
                    break
            columns_data.append({
                'column': col[0],
                'rows': nrows,
                'columns': col[1],
                'title': self.__title(col[0]),
            })
        return columns_data


class TableTree(object):
    def __init__(self, user, view=None, view_id=None):
        self.cnt = 1
        self.user = user
        self.columns = ['name']
        self.view = get_view(user, view, view_id)[0]
        self.titles = TITLES
        self.head_filters = self.__head_filters()
        self.jobdata = []
        self.__collect_jobdata()
        self.__table_columns()
        self.tableheader = TableHeader(
            self.columns, self.titles
        ).header_struct()

        # TODO: refactoring
        self.values = self.__values()

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

        for job in Job.objects.filter(
                **self.__view_filters()
        ).order_by(*orders):
            if job_f.JobAccess(self.user, job).can_view():
                rowdata.append(job)

        for job in rowdata:
            parent = job.parent
            self.jobdata.append({
                'job': job,
                'parent': parent,
                'black': False
            })
            while parent is not None and \
                    parent not in list(blackdata + rowdata):
                next_parent = parent.parent
                self.jobdata.append({
                    'job': parent,
                    'parent': next_parent,
                    'black': True
                })
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

        def __get_all_children(job):
            children = []
            for oj in other_jobs:
                if oj['parent'] == job['job']:
                    children.append(oj)
                    children.extend(__get_all_children(oj))
            return children

        for j in first_jobs:
            ordered_jobs.append(j)
            ordered_jobs.extend(__get_all_children(j))
        self.jobdata = ordered_jobs

    def __head_filters(self):
        head_filters = {}
        allowed_types = ['iexact', 'istartswith', 'icontains']
        for f in self.view['filters']:
            f_data = self.view['filters'][f]
            if f == 'resource_component':
                if f_data['type'] in allowed_types:
                    head_filters['resource_component'] = {
                        'component__name__' + f_data['type']: f_data['value']
                    }
            elif f == 'problem_component':
                if f_data['type'] in allowed_types:
                    head_filters['problem_component'] = {
                        'component__name__' + f_data['type']: f_data['value']
                    }
            elif f == 'problem_problem':
                if f_data['type'] in allowed_types:
                    head_filters['problem_problem'] = {
                        'problem__name__' + f_data['type']: f_data['value']
                    }
        return head_filters

    def __view_filters(self):

        def name_filter(fdata):
            if fdata['type'] in ['iexact', 'istartswith', 'icontains']:
                return {
                    'name__' + fdata['type']: fdata['value']
                }
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
                limit_time = pytz.timezone('UTC').localize(
                    datetime.now()
                ) - timedelta(**{measure: value})
                if fdata['type'] == 'older':
                    return {'change_date__lt': limit_time}
                elif fdata['type'] == 'younger':
                    return {'change_date__gt': limit_time}
            return {}

        def status_filter(fdata):
            if fdata['type'] == 'is':
                return {'jobstatus__status': fdata['value']}
            elif fdata['type'] == 'isnot':
                return {
                    'jobstatus__status__in': [
                        s[0] for s in JOB_STATUS if s[0] != fdata['value']
                        ]
                }
            return {}
        format_filter = lambda fdata: {
            'format': fdata['value']
        } if fdata['type'] == 'is' else {}

        action = {
            'name': name_filter,
            'change_author': author_filter,
            'change_date': date_filter,
            'status': status_filter,
            'format': format_filter
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
            'tag': lambda:
            self.__safe_tags_columns() + self.__unsafe_tags_columns(),
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
            for tag in job['job'].safe_tags.all():
                tag_name = tag.tag.tag
                tag_id = 'tag:safe:tag_%s' % tag.tag_id
                if tag_id not in tags_data:
                    tags_data[tag_id] = tag_name
                    self.titles[tag_id] = tag_name
        return list(sorted(tags_data, key=tags_data.get))

    def __unsafe_tags_columns(self):
        tags_data = {}
        for job in self.jobdata:
            for tag in job['job'].unsafe_tags.all():
                tag_name = tag.tag.tag
                tag_id = 'tag:unsafe:tag_%s' % tag.tag_id
                if tag_id not in tags_data:
                    tags_data[tag_id] = tag_name
                    self.titles[tag_id] = tag_name
        return list(sorted(tags_data, key=tags_data.get))

    def __resource_columns(self):
        components = {}
        for job in self.jobdata:
            if 'resource_component' in self.head_filters:
                compres_set = job['job'].componentresource_set.filter(
                    **self.head_filters['resource_component']
                )
            else:
                compres_set = job['job'].componentresource_set.all()
            for compres in compres_set:
                comp = compres.component
                if comp is not None:
                    comp_id = 'resource:component_' + str(comp.pk)
                    components[comp_id] = comp.name
        self.titles.update(components)
        components = list(sorted(components, key=components.get))
        components.append('resource:total')
        return components

    def __unknowns_columns(self):
        problems = {}
        cmup_filter = {}
        if 'problem_component' in self.head_filters:
            cmup_filter.update(self.head_filters['problem_component'])
        if 'problem_problem' in self.head_filters:
            cmup_filter.update(self.head_filters['problem_problem'])

        for job in self.jobdata:
            for cmup in job['job'].componentmarkunknownproblem_set.filter(
                    **cmup_filter):
                problem = cmup.problem
                comp_id = 'pr_component_%s' % str(cmup.component.pk)
                comp_name = cmup.component.name
                if problem is None:
                    if comp_id in problems:
                        if 'z_no_mark' not in problems[comp_id]['problems']:
                            problems[comp_id]['problems']['z_no_mark'] = \
                                _('Without marks')
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

        ordered_ids = list(x[0] for x in list(
            sorted(problems.items(), key=lambda x_y: x_y[1]['title'])
        ))

        new_columns = []
        for comp_id in ordered_ids:
            self.titles['problem:%s' % comp_id] = problems[comp_id]['title']
            # With sorting time is increased 4-6 times
            # for probl_id in problems[comp_id]['problems']:
            for probl_id in sorted(problems[comp_id]['problems'],
                                   key=problems[comp_id]['problems'].get):
                column = 'problem:%s:%s' % (comp_id, probl_id)
                new_columns.append(column)
                self.titles[column] = problems[comp_id]['problems'][probl_id]
        new_columns.append('problem:total')
        return new_columns

    def __values(self):
        table_rows = []
        for job in self.jobdata:
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
                return job.jobstatus.get_status_display()
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
        elif col == 'parent_id':
            if job.parent is None:
                return '-'
            else:
                return job.parent.identifier
        elif col == 'role':
            try:
                first_version = job.jobhistory_set.get(version=1)
            except ObjectDoesNotExist:
                return ''
            if first_version.change_author == self.user:
                return _('Author')
            if self.user.extended.role == USER_ROLES[2][0]:
                return self.user.extended.get_role_display()
            last_version = job.jobhistory_set.all().order_by('-change_date')[0]
            user_role = last_version.userrole_set.filter(user=self.user)
            if len(user_role):
                return user_role[0].get_role_display()
            else:
                return job.get_global_role_display()
        return ''

    def __get_href(self, job, col, black):
        self.cnt = 1
        if job:
            if black:
                return None
            elif col == 'name':
                return reverse('jobs:job', args=[job.pk])
        return None
