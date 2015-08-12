import json
import pytz
from datetime import datetime, timedelta
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.utils.translation import ugettext_lazy as _, string_concat
from jobs.job_model import Job, JobStatus
from jobs.models import MarkSafeTag, MarkUnsafeTag
import jobs.job_functions as job_f
from reports.models import Verdict, ComponentResource, ComponentUnknown,\
    ComponentMarkUnknownProblem, ReportComponent
from Omega.vars import JOB_DEF_VIEW, USER_ROLES, JOB_STATUS
from jobs.job_functions import SAFES, UNSAFES, TITLES, get_resource_data


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
    columns = ['role', 'author', 'date', 'status', 'unsafe']
    for unsafe in UNSAFES:
        columns.append("unsafe:%s" % unsafe)
    columns.append('safe')
    for safe in SAFES:
        columns.append("safe:%s" % safe)
    columns.extend(['problem', 'resource', 'tag', 'tag:safe', 'tag:unsafe',
                    'identifier', 'format', 'version', 'type', 'parent_id'])
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

    def __count_footer(self):
        foot_length = 0
        for col in self.header[0]:
            if col['column'] in ['name', 'author', 'date', 'status', '',
                                 'resource', 'format', 'version', 'type',
                                 'identifier', 'parent_id', 'role']:
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

        for job in Job.objects.filter(
                **self.__view_filters()
        ).order_by(*orders):
            job_access = job_f.JobAccess(self.user, job)
            if job_access.can_view():
                rowdata.append(job)

        cnt = 0
        for job in rowdata:
            parent = job.parent
            row_job_data = {
                'job': job,
                'parent': parent,
                'parent_pk': None,
                'black': False,
                'pk': job.pk
            }
            if parent is not None:
                row_job_data['parent_id'] = parent.identifier
                row_job_data['parent_pk'] = parent.pk
            self.jobdata.append(row_job_data)
            while parent is not None and \
                    parent not in list(blackdata + rowdata):
                next_parent = parent.parent
                row_job_data = {
                    'job': parent,
                    'parent': next_parent,
                    'parent_pk': None,
                    'black': True,
                    'pk': parent.pk
                }
                if next_parent is not None:
                    row_job_data['parent_pk'] = next_parent.pk
                self.jobdata.append(row_job_data)
                blackdata.append(parent)
                parent = next_parent
            cnt += 1
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
            cr_set = ComponentResource.objects.filter(
                report__root__job=job['job'])
            if 'resource_component' in self.head_filters:
                compres_set = cr_set.filter(
                    **self.head_filters['resource_component']
                )
            else:
                compres_set = cr_set.all()
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
        cmup_filter = {'report__parent': None}
        if 'problem_component' in self.head_filters:
            cmup_filter.update(self.head_filters['problem_component'])
        if 'problem_problem' in self.head_filters:
            cmup_filter.update(self.head_filters['problem_problem'])

        for job in self.jobdata:
            cmup_filter['report__root__job'] = job['job']
            found_comp_ids = []
            for cmup in ComponentMarkUnknownProblem.objects.filter(
                    **cmup_filter):
                problem = cmup.problem
                comp_id = 'pr_component_%s' % str(cmup.component.pk)
                comp_name = cmup.component.name
                found_comp_ids.append(cmup.component_id)
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
            for cmup in ComponentUnknown.objects.filter(
                    Q(**cmup_filter) & ~Q(component_id__in=found_comp_ids)):
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
                    self.titles[column] = problems[comp_id]['problems'][probl_id]
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
                values_data[job['pk']] = {
                    'parent_id': parent_id
                }

        job_pks = [job['pk'] for job in self.jobdata]

        def collect_authors():
            for j in self.jobdata:
                if j['pk'] in values_data:
                    author = j['job'].change_author
                    if author is not None:
                        name = author.extended.last_name + ' ' + \
                               author.extended.first_name
                        author_href = reverse('users:show_profile',
                                              args=[author.pk])
                        values_data[j['pk']]['author'] = (name, author_href)

        def collect_jobs_data():
            for j in self.jobdata:
                if j['pk'] in values_data:
                    values_data[j['pk']].update({
                        'identifier': j['job'].identifier,
                        'format': j['job'].format,
                        'version': j['job'].version,
                        'type': j['job'].get_type_display(),
                        'date': j['job'].change_date,
                    })
                names_data[j['pk']] = j['job'].name

        def collect_statuses():
            for status in JobStatus.objects.filter(job_id__in=job_pks):
                if status.job_id in values_data:
                    try:
                        report = ReportComponent.objects.get(
                            root__job=status.job, parent=None)
                        values_data[status.job_id]['status'] = (
                            status.get_status_display(),
                            reverse('reports:report_component',
                                    args=[status.job_id, report.pk])
                        )
                    except ObjectDoesNotExist:
                        values_data[status.job_id]['status'] = \
                            status.get_status_display()

        def collect_verdicts():
            for verdict in Verdict.objects.filter(
                    report__root__job_id__in=job_pks, report__parent=None):
                if verdict.report.root.job_id in values_data:
                    values_data[verdict.report.root.job_id].update({
                        'unsafe:total': (
                            verdict.unsafe,
                            reverse('reports:report_list',
                                    args=[verdict.report.pk, 'unsafes'])),
                        'unsafe:bug': verdict.unsafe_bug,
                        'unsafe:target_bug': verdict.unsafe_target_bug,
                        'unsafe:false_positive': verdict.unsafe_false_positive,
                        'unsafe:unknown': verdict.unsafe_unknown,
                        'unsafe:unassociated': verdict.unsafe_unassociated,
                        'unsafe:inconclusive': verdict.unsafe_inconclusive,
                        'safe:total': (
                            verdict.safe,
                            reverse('reports:report_list',
                                    args=[verdict.report.pk, 'safes'])),
                        'safe:missed_bug': verdict.safe_missed_bug,
                        'safe:unknown': verdict.safe_unknown,
                        'safe:inconclusive': verdict.safe_inconclusive,
                        'safe:unassociated': verdict.safe_unassociated,
                        'safe:incorrect': verdict.safe_incorrect_proof,
                        'problem:total': verdict.unknown
                    })

        def collect_roles():
            user_role = self.user.extended.role
            for j in self.jobdata:
                if j['pk'] in values_data:
                    try:
                        first_version = j['job'].jobhistory_set.get(version=1)
                        last_version = j['job'].jobhistory_set.get(
                            version=j['job'].version)
                    except ObjectDoesNotExist:
                        return
                    if first_version.change_author == self.user:
                        values_data[j['pk']]['role'] = _('Author')
                    elif user_role == USER_ROLES[2][0]:
                        values_data[j['pk']]['role'] = \
                            self.user.extended.get_role_display()
                    else:
                        job_user_role = last_version.userrole_set.filter(
                            user=self.user)
                        if len(job_user_role):
                            values_data[j['pk']]['role'] = \
                                job_user_role[0].get_role_display()
                        else:
                            values_data[j['pk']]['role'] = \
                                last_version.get_global_role_display()

        def collect_safe_tags():
            for st in MarkSafeTag.objects.filter(job_id__in=job_pks):
                if st.job_id in values_data:
                    values_data[st.job_id]['tag:safe:tag_' + str(st.tag_id)] = \
                        st.number

        def collect_unsafe_tags():
            for ut in MarkUnsafeTag.objects.filter(job_id__in=job_pks):
                if ut.job_id in values_data:
                    values_data[ut.job_id]['tag:unsafe:tag_' + str(ut.tag_id)] \
                        = ut.number

        def collect_resourses():
            for cr in ComponentResource.objects.filter(
                    report__root__job_id__in=job_pks, report__parent=None):
                job_pk = cr.report.root.job_id
                if job_pk in values_data:
                    rd = get_resource_data(self.user, cr.resource)
                    resourses_value = "%s %s %s" % (rd[0], rd[1], rd[2])
                    if cr.component_id is None:
                        values_data[job_pk]['resource:total'] = resourses_value
                    else:
                        values_data[job_pk][
                            'resource:component_' + str(cr.component_id)
                        ] = resourses_value

        def collect_unknowns():
            for cmup in ComponentMarkUnknownProblem.objects.filter(
                    report__root__job_id__in=job_pks, report__parent=None):
                job_pk = cmup.report.root.job_id
                if job_pk in values_data:
                    if cmup.problem is None:
                        values_data[job_pk][
                            'problem:pr_component_' + str(cmup.component_id) +
                            ':z_no_mark'
                        ] = cmup.number
                    else:
                        values_data[job_pk][
                            'problem:pr_component_' + str(cmup.component_id) +
                            ':problem_' + str(cmup.problem_id)
                        ] = cmup.number
            for cu in ComponentUnknown.objects.filter(
                    report__root__job_id__in=job_pks, report__parent=None):
                job_pk = cu.report.root.job_id
                if job_pk in values_data:
                    values_data[job_pk][
                        'problem:pr_component_' + str(cu.component_id) +
                        ':z_total'
                    ] = (
                        cu.number,
                        reverse('reports:report_unknowns',
                                args=[cu.report_id, cu.component_id])
                    )

        def get_href(job_pk, column, black):
            if job_pk in values_data and not black:
                if column == 'name':
                    return reverse('jobs:job', args=[job_pk])
            return None

        if 'author' in self.columns:
            collect_authors()
        if any(x in [
            'name', 'identifier', 'format', 'version', 'type', 'date'
        ] for x in self.columns):
            collect_jobs_data()
        if 'status' in self.columns:
            collect_statuses()
        if any(x.startswith('safe:') or x.startswith('unsafe:') or
                x == 'problem:total' for x in self.columns):
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
                    href = get_href(job['pk'], 'name', job['black'])
                elif job['pk'] in values_data:
                    if col in values_data[job['pk']]:
                        if isinstance(values_data[job['pk']][col], tuple):
                            cell_value = values_data[job['pk']][col][0]
                            href = values_data[job['pk']][col][1]
                        else:
                            cell_value = values_data[job['pk']][col]
                row_values.append({
                    'value': cell_value,
                    'id': '__'.join(col.split(':')) + ('__%d' % col_id),
                    'href': href,
                    # get_href(job['pk'], col, job['black']),
                })
            table_rows.append({
                'id': job['pk'],
                'parent': job['parent_pk'],
                'values': row_values,
                'black': job['black']
            })
        return table_rows
