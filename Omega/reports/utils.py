import json
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.utils.translation import ugettext_lazy as _
from Omega.vars import VIEW_REPORT_ATTRS_DEF_VIEW
from reports.models import ReportComponent
import jobs.job_functions as job_f
from reports.models import Attr, AttrName


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


def attr_value(value):
    value = json.loads(value)
    if isinstance(value, str):
        return value

    new_value = '-'
    if not isinstance(value, list):
        return new_value
    data = {}
    for v in value:
        if isinstance(v, dict):
            data_name = str(next(iter(v)))
            v_values = []
            if isinstance(v[data_name], list):
                for vv in v[data_name]:
                    if isinstance(vv, dict):
                        vv_name = next(iter(vv))
                        v_values.append('%s:%s' % (vv_name, str(vv[vv_name])))
            else:
                v_values.append(v[data_name])
            data[data_name] = str('; '.join(v_values))
    if len(data):
        new_value = ''
        for d in sorted(data):
            new_value += '%s: %s<br>' % (d, data[d])

    return new_value


def get_children_data(report):
    children = ReportComponent.objects.filter(parent=report)
    attr_names = []
    for child in children:
        for attr in child.attr.all().order_by('name__name'):
            if attr.name not in attr_names:
                attr_names.append(attr.name)

    children_values = []
    for child in children:
        attr_row = {
            'id': child.id,
            'component': child.component.name,
            'attrs': []
        }
        for attr in attr_names:
            child_attr = child.attr.all().filter(name=attr)
            if len(child_attr) == 1:
                attr_row['attrs'].append(attr_value(child_attr[0].value))
            else:
                attr_row['attrs'].append('-')
        children_values.append(attr_row)
    return {
        'attrs': attr_names,
        'values': children_values
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
        title = pid.split('##')[-1]
        name = title
        if len(name) > 20:
            name = name[:20] + '...'
        href = reverse('reports:report_component',
                       args=[report.root.job.pk, parent.pk])
        parents_data.append({
            'name': name,
            'title': title,
            'href': href,
            'attrs': parent_attrs
        })
    return parents_data


def report_resources(report, user):
    resources = None
    if report.resource is not None:
        rd = job_f.get_resource_data(user, report.resource)
        resources = {
            'wall_time': rd[0],
            'cpu_time': rd[1],
            'memory': rd[2],
        }
    return resources


class ReportAttrs(object):

    def __init__(self, user, report, view=None, view_id=None):
        self.report = report
        self.user = user
        (self.view, self.view_id) = self.__get_view(view, view_id)
        self.views = self.__views()

    class Header(object):

        def __init__(self, columns):
            self.columns = columns

        def head_struct(self, children=False):
            col_data = []
            depth = self.__max_depth()
            for d in range(1, depth + 1):
                col_data.append(self.__cellspan_level(d, depth))
            if children:
                if len(col_data) > 0:
                    col_data[0].insert(0, {
                        'column': _('Component'),
                        'rows': depth,
                        'columns': 1,
                    })
                else:
                    col_data = [{
                        'column': _('Component'),
                        'rows': depth,
                        'columns': 1,
                    }]
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
        if view is not None:
            return json.loads(view), None
        if view_id is None:
            pref_view = self.user.preferableview_set.filter(view__type='3')
            if len(pref_view):
                return json.loads(pref_view[0].view.view), pref_view[0].view_id
        elif view_id == 'default':
            return VIEW_REPORT_ATTRS_DEF_VIEW, 'default'
        else:
            user_view = self.user.view_set.filter(pk=int(view_id), type='3')
            if len(user_view):
                return json.loads(user_view[0].view), user_view[0].pk
        return VIEW_REPORT_ATTRS_DEF_VIEW, 'default'

    def __views(self):
        views = []
        for view in self.user.view_set.filter(type='3'):
            views.append({
                'id': view.pk,
                'name': view.name,
                'selected': lambda: (view.pk == self.view_id)
            })
        return views

    def get_table_data(self, children=False):
        if children:
            columns, values = self.__children_attrs()
        else:
            columns, values = self.__self_attrs()
        header = self.Header(columns).head_struct(children)
        return {'header': header, 'values': values}

    def __self_attrs(self):
        columns = []
        values = []
        for attr in self.report.attr.all().order_by('name__name'):
            columns.append(attr.name.name)
            values.append(attr.value)
        return columns, values

    def __children_attrs(self):
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

        ftype = None
        fvalue = None
        fattr = None
        if 'attr' in self.view['filters']:
            fattr = self.view['filters']['attr']['attr']
            fvalue = self.view['filters']['attr']['value']
            ftype = self.view['filters']['attr']['type']
        for comp_data in sorted_components:
            values_row = []
            passed = True
            for col in columns:
                cell_val = '-'
                if comp_data['pk'] in data[col]:
                    cell_val = data[col][comp_data['pk']]
                values_row.append(cell_val)
                if fattr is not None and fattr.lower() == col.lower():
                    if ftype == 'iexact' and fvalue.lower() != cell_val.lower():
                        passed = False
                    elif ftype == 'istartswith' and \
                            not cell_val.lower().startswith(fvalue.lower()):
                        passed = False
            if passed:
                values_data.append({
                    'pk': comp_data['pk'],
                    'component': comp_data['component'],
                    'attrs': values_row
                })
        return columns, values_data


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
