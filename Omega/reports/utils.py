import json
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.utils.translation import ugettext_lazy as _
from Omega.vars import REPORT_ATTRS_DEF_VIEW, UNSAFE_LIST_DEF_VIEW,\
    SAFE_LIST_DEF_VIEW, UNKNOWN_LIST_DEF_VIEW
from jobs.utils import get_resource_data
from reports.models import ReportComponent, Attr, AttrName, ReportComponentLeaf


def computer_description(computer):
    computer = json.loads(computer)
    data = []
    comp_name = _('Unknown')
    for comp_data in computer:
        if isinstance(comp_data, dict):
            data_name = str(next(iter(comp_data)))
            if data_name == 'node name':
                comp_name = str(comp_data[data_name])
            else:
                data.append([data_name, str(comp_data[data_name])])
    return {
        'name': comp_name,
        'data': data
    }


def get_parents(report):
    parents_data = []
    parents_ids = []
    ids_sep = report.identifier.split('##')
    for i in range(0, len(ids_sep)):
        parents_ids.append('##'.join(ids_sep[:(i + 1)]))

    parents = ReportComponent.objects.filter(identifier__startswith=ids_sep[0])
    cnt = 0
    for pid in parents_ids:
        cnt += 1
        try:
            parent = parents.get(identifier=pid)
        except ObjectDoesNotExist:
            continue
        parent_attrs = []
        for attr in parent.attr.all().order_by('name__name'):
            parent_attrs.append([attr.name.name, attr.value])

        title = parent.component.name
        href = reverse('reports:component',
                       args=[report.root.job.pk, parent.pk])
        parents_data.append({
            'title': title,
            'href': href,
            'attrs': parent_attrs
        })
    return parents_data


def report_resources(report, user):
    resources = None
    if report.resource is not None:
        rd = get_resource_data(user, report.resource)
        resources = {
            'wall_time': rd[0],
            'cpu_time': rd[1],
            'memory': rd[2],
        }
    return resources


class ReportTable(object):

    def __init__(self, user, report, view=None, view_id=None, table_type='0',
                 component_id=None, verdict=None):
        self.component_id = component_id
        self.report = report
        self.user = user
        self.type = table_type
        self.verdict = verdict
        self.columns = []
        (self.view, self.view_id) = self.__get_view(view, view_id)
        self.views = self.__views()
        self.table_data = self.__get_table_data()

    class Header(object):

        def __init__(self, columns):
            self.columns = columns

        def head_struct(self, table_type):
            col_data = []
            depth = self.__max_depth()
            for d in range(1, depth + 1):
                col_data.append(self.__cellspan_level(d, depth))

            if table_type != '0':
                title = '№'
                if table_type in ['3', '6']:
                    title = _('Component')
                if len(col_data) > 0:
                    col_data[0].insert(0, {
                        'column': title, 'rows': depth, 'columns': 1
                    })
                else:
                    col_data.append([{
                        'column': title, 'rows': depth, 'columns': 1
                    }])
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

        def __cellspan_level(self, lvl, max_depth):
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

            columns_data = []
            for col in columns_of_lvl:
                nrows = max_depth - lvl + 1
                for column in self.columns:
                    if column.startswith(col[0]) and col[0] != column:
                        nrows = 1
                        break
                columns_data.append({
                    'column': col[0].split(':')[-1],
                    'rows': nrows,
                    'columns': col[1],
                })
            return columns_data

    def __get_view(self, view, view_id):
        if self.type not in ['3', '4', '5', '6']:
            return None, None

        def_views = {
            '3': REPORT_ATTRS_DEF_VIEW,
            '4': UNSAFE_LIST_DEF_VIEW,
            '5': SAFE_LIST_DEF_VIEW,
            '6': UNKNOWN_LIST_DEF_VIEW,
        }

        if view is not None:
            return json.loads(view), None
        if view_id is None:
            pref_view = self.user.preferableview_set.filter(
                view__type=self.type)
            if len(pref_view):
                return json.loads(pref_view[0].view.view), pref_view[0].view_id
        elif view_id == 'default':
            return def_views[self.type], 'default'
        else:
            user_view = self.user.view_set.filter(
                pk=int(view_id), type=self.type)
            if len(user_view):
                return json.loads(user_view[0].view), user_view[0].pk
        return def_views[self.type], 'default'

    def __views(self):
        views = []
        for view in self.user.view_set.filter(type=self.type):
            views.append({
                'id': view.pk,
                'name': view.name,
                'selected': lambda: (view.pk == self.view_id)
            })
        return views

    def __get_table_data(self):
        actions = {
            '0': self.__self_attrs,
            '3': self.__component_attrs,
            '4': self.__verdict_attrs,
            '5': self.__verdict_attrs,
            '6': self.__unknowns_attrs,
        }
        if self.type in actions:
            self.columns, values = actions[self.type]()
        else:
            return {}
        return {
            'header': self.Header(self.columns).head_struct(self.type),
            'values': values
        }

    def __self_attrs(self):
        columns = []
        values = []
        for attr in self.report.attr.all().order_by('name__name'):
            columns.append(attr.name.name)
            values.append(attr.value)
        return columns, values

    def __component_attrs(self):
        data = {}
        components = {}
        component_filters = {
            'parent': self.report,
        }
        if 'component' in self.view['filters']:
            component_filters[
                'component__name__' + self.view['filters']['component']['type']
            ] = self.view['filters']['component']['value']
        for report in ReportComponent.objects.filter(**component_filters):
            for attr in report.attr.all():
                if attr.name.name not in data:
                    data[attr.name.name] = {}
                data[attr.name.name][report.pk] = attr.value
            components[report.pk] = report.component

        columns = []
        for name in sorted(data):
            columns.append(name)

        values_data = []

        comp_data = []
        for pk in components:
            comp_data.append((components[pk].name, {
                'pk': pk,
                'component': components[pk]
            }))
        sorted_components = []
        for name, dt in sorted(comp_data, key=lambda x: x[0]):
            sorted_components.append(dt)

        for comp_data in sorted_components:
            values_row = []
            for col in columns:
                cell_val = '-'
                if comp_data['pk'] in data[col]:
                    cell_val = data[col][comp_data['pk']]
                values_row.append(cell_val)
                if not self.__filter_attr(col, cell_val):
                    break
            else:
                values_data.append({
                    'pk': comp_data['pk'],
                    'component': comp_data['component'],
                    'attrs': values_row
                })
        return columns, values_data

    def __verdict_attrs(self):
        list_types = {
            '4': 'unsafe',
            '5': 'safe',
        }
        if self.type not in list_types:
            return None, None

        data = {}
        report_ids = []
        leaf_filter = {'report': self.report}
        if self.verdict is not None:
            leaf_filter[list_types[self.type] + '__verdict'] = self.verdict
        for leaf in ReportComponentLeaf.objects.filter(
                Q(**leaf_filter) & ~Q(**{list_types[self.type]: None})):
            report = getattr(leaf, list_types[self.type])
            for attr in report.attr.all():
                if attr.name.name not in data:
                    data[attr.name.name] = {}
                data[attr.name.name][report.pk] = attr.value
            report_ids.append(report.pk)

        columns = []
        for name in sorted(data):
            columns.append(name)

        ids_ordered = []
        if 'order' in self.view and self.view['order'] in data:
            for rep_id in data[self.view['order']]:
                ids_ordered.append((data[self.view['order']][rep_id], rep_id))
            report_ids = [x[1] for x in sorted(ids_ordered, key=lambda x: x[0])]

        cnt = 0
        values_data = []
        for rep_id in report_ids:
            values_row = []
            for col in columns:
                cell_val = '-'
                if rep_id in data[col]:
                    cell_val = data[col][rep_id]
                values_row.append(cell_val)
                if not self.__filter_attr(col, cell_val):
                    break
            else:
                cnt += 1
                values_data.append({
                    'href': reverse('reports:leaf',
                                    args=[list_types[self.type], rep_id]),
                    'value': cnt,
                    'attrs': values_row
                })
        return columns, values_data

    def __unknowns_attrs(self):

        def filter_component(component_name):
            if 'component' in self.view['filters']:
                filter_type = self.view['filters']['component']['type']
                filter_value = self.view['filters']['component']['value']
                if filter_type == 'iexact':
                    if component_name.lower() == filter_value.lower():
                        return True
                elif filter_type == 'istartswith':
                    if component_name.lower().startswith(filter_value.lower()):
                        return True
                elif filter_type == 'icontains':
                    if filter_value.lower() in component_name.lower():
                        return True
                return False
            return True

        data = {}
        components = {}
        for leaf in ReportComponentLeaf.objects.filter(
                Q(report=self.report) & ~Q(unknown=None)):
            report = leaf.unknown
            try:
                parent = ReportComponent.objects.get(pk=report.parent_id)
            except ObjectDoesNotExist:
                continue
            if self.component_id is not None and \
                    parent.component_id != int(self.component_id):
                continue
            if not filter_component(parent.component.name):
                continue
            for attr in report.attr.all():
                if attr.name.name not in data:
                    data[attr.name.name] = {}
                data[attr.name.name][report.pk] = attr.value
            components[report.pk] = parent.component

        columns = []
        for name in sorted(data):
            columns.append(name)

        sorted_components = []
        if 'order' in self.view and self.view['order'] in data:
            ids_ordered = []
            for rep_id in data[self.view['order']]:
                ids_ordered.append((data[self.view['order']][rep_id], rep_id))
            report_ids = [x[1] for x in sorted(ids_ordered, key=lambda x: x[0])]
            for rep_id in report_ids:
                sorted_components.append({
                    'pk': rep_id,
                    'component': components[rep_id]
                })
        else:
            comp_data = []
            for pk in components:
                comp_data.append((components[pk].name, {
                    'pk': pk,
                    'component': components[pk]
                }))
            for name, dt in sorted(comp_data, key=lambda x: x[0]):
                sorted_components.append(dt)

        values_data = []
        for comp_data in sorted_components:
            values_row = []
            for col in columns:
                cell_val = '-'
                if comp_data['pk'] in data[col]:
                    cell_val = data[col][comp_data['pk']]
                values_row.append(cell_val)
                if not self.__filter_attr(col, cell_val):
                    break
            else:
                values_data.append({
                    'attrs': values_row,
                    'value': comp_data['component'].name,
                    'href': reverse('reports:leaf',
                                    args=['unknown', comp_data['pk']])
                })
        return columns, values_data

    def __filter_attr(self, attribute, value):
        if 'attr' in self.view['filters']:

            fattr = self.view['filters']['attr']['attr']
            fvalue = self.view['filters']['attr']['value']
            ftype = self.view['filters']['attr']['type']
            if fattr is not None and fattr.lower() == attribute.lower():
                if ftype == 'iexact' and fvalue.lower() != value.lower():
                    return False
                elif ftype == 'istartswith' and \
                        not value.lower().startswith(fvalue.lower()):
                    return False
        return True


def save_attrs(attrs):

    def children(name, val):
        attr_data = {}
        if isinstance(val, list):
            for v in val:
                if isinstance(v, dict):
                    nextname = next(iter(v))
                    new_data = children(nextname.replace(':', '_'), v[nextname])
                    for n in new_data:
                        if len(name) == 0:
                            new_id = n
                        else:
                            new_id = "%s:%s" % (name, n)
                        attr_data[new_id] = new_data[n]
        elif isinstance(val, str):
            attr_data[name] = val
        return attr_data

    attrs_data = children('', attrs)
    created_attrs = []
    for attr in attrs_data:
        new_attr_name, created = AttrName.objects.get_or_create(name=attr)
        new_attr, created = Attr.objects.get_or_create(
            name=new_attr_name, value=attrs_data[attr])
        created_attrs.append(new_attr)
    return created_attrs
