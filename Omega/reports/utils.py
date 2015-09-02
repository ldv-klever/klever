import json
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.utils.translation import ugettext_lazy as _
from Omega.vars import REPORT_ATTRS_DEF_VIEW, UNSAFE_LIST_DEF_VIEW, \
    SAFE_LIST_DEF_VIEW, UNKNOWN_LIST_DEF_VIEW, UNSAFE_VERDICTS, SAFE_VERDICTS
from jobs.utils import get_resource_data
from reports.models import ReportComponent, Attr, AttrName
from marks.tables import SAFE_COLOR, UNSAFE_COLOR
from Omega.tableHead import Header


REP_MARK_TITLES = {
    'mark_num': _('Mark'),
    'mark_verdict': _("Verdict"),
    'mark_result': _('Similarity'),
    'mark_status': _('Status'),
    'number': '№',
    'component': _('Component'),
    'marks_number': _("Number of associated marks"),
    'report_verdict': _("Total verdict"),
}

MARK_COLUMNS = ['mark_verdict', 'mark_result', 'mark_status']


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
                 component_id=None, verdict=None, tag=None):
        self.component_id = component_id
        self.report = report
        self.user = user
        self.type = table_type
        self.verdict = verdict
        self.tag = tag
        self.columns = []
        (self.view, self.view_id) = self.__get_view(view, view_id)
        self.views = self.__views()
        self.table_data = self.__get_table_data()

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
            '0': self.__self_data,
            '3': self.__component_data,
            '4': self.__verdict_data,
            '5': self.__verdict_data,
            '6': self.__unknowns_data,
        }
        if self.type in actions:
            self.columns, values = actions[self.type]()
        else:
            return {}
        return {
            'header': Header(self.columns, REP_MARK_TITLES).struct,
            'values': values
        }

    def __self_data(self):
        columns = []
        values = []
        for name in json.loads(self.report.attr_order):
            try:
                attr = self.report.attr.get(name__name=name)
            except ObjectDoesNotExist:
                continue
            columns.append(attr.name.name)
            values.append(attr.value)
        return columns, values

    def __component_data(self):
        data = {}
        components = {}
        component_filters = {
            'parent': self.report,
        }
        if 'component' in self.view['filters']:
            component_filters[
                'component__name__' + self.view['filters']['component']['type']
                ] = self.view['filters']['component']['value']
        attr_order = []
        for report in ReportComponent.objects.filter(**component_filters):
            for new_a in json.loads(report.attr_order):
                if new_a not in attr_order:
                    attr_order.append(new_a)
            for attr in report.attr.all():
                if attr.name.name not in data:
                    data[attr.name.name] = {}
                data[attr.name.name][report.pk] = attr.value
            components[report.pk] = report.component

        columns = []
        for name in attr_order:
            if name in data:
                columns.append(name)

        comp_data = []
        for pk in components:
            comp_data.append((components[pk].name, {
                'pk': pk,
                'component': components[pk]
            }))
        sorted_components = []
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
                    'pk': comp_data['pk'],
                    'component': comp_data['component'],
                    'attrs': values_row
                })
        columns.insert(0, 'component')
        return columns, values_data

    def __verdict_data(self):
        list_types = {
            '4': 'unsafe',
            '5': 'safe',
        }
        if self.type not in list_types:
            return None, None

        data = {}
        leaf_filter = {}
        if self.verdict is not None:
            leaf_filter[list_types[self.type] + '__verdict'] = self.verdict

        attr_order = []
        for leaf in self.report.leaves.filter(
                Q(**leaf_filter) & ~Q(**{list_types[self.type]: None})):
            report = getattr(leaf, list_types[self.type])
            if not self.__has_tag(report):
                continue
            for new_a in json.loads(report.attr_order):
                if new_a not in attr_order:
                    attr_order.append(new_a)
            for attr in report.attr.all():
                if attr.name.name not in data:
                    data[attr.name.name] = {}
                data[attr.name.name][report] = attr.value

        columns = ['number', 'marks_number']
        if self.verdict is None:
            columns.append('report_verdict')

        for name in attr_order:
            if name in data:
                columns.append(name)

        reports_ordered = []
        if 'order' in self.view and self.view['order'] in data:
            for report in data[self.view['order']]:
                reports_ordered.append(
                    (data[self.view['order']][report], report)
                )
            reports_ordered = \
                [x[1] for x in sorted(reports_ordered, key=lambda x: x[0])]
        else:
            for attr in data:
                for report in data[attr]:
                    if report not in reports_ordered:
                        reports_ordered.append(report)

        cnt = 1
        values_data = []
        for report in reports_ordered:
            values_row = []
            for col in columns:
                val = '-'
                href = None
                color = None
                if col in data and report in data[col]:
                    val = data[col][report]
                    if not self.__filter_attr(col, val):
                        break
                elif col == 'number':
                    val = cnt
                    href = reverse('reports:leaf',
                                   args=[list_types[self.type], report.pk])
                elif col == 'marks_number':
                    broken = 0
                    if list_types[self.type] == 'unsafe':
                        broken = \
                            len(report.markunsafereport_set.filter(broken=True))
                        num_of_connects = len(report.markunsafereport_set.all())
                    else:
                        num_of_connects = len(report.marksafereport_set.all())
                    if broken > 0:
                        val = _('%(all)s (%(broken)s are broken)') % {
                            'all': num_of_connects,
                            'broken': broken
                        }
                    else:
                        val = num_of_connects
                elif col == 'report_verdict':
                    if list_types[self.type] == 'unsafe':
                        for uns in UNSAFE_VERDICTS:
                            if uns[0] == report.verdict:
                                val = uns[1]
                                break
                        color = UNSAFE_COLOR[report.verdict]
                    else:
                        for s in SAFE_VERDICTS:
                            if s[0] == report.verdict:
                                val = s[1]
                                break
                        color = SAFE_COLOR[report.verdict]
                values_row.append({
                    'value': val,
                    'color': color,
                    'href': href
                })
            else:
                cnt += 1
                values_data.append(values_row)
        return columns, values_data

    def __has_tag(self, report):
        if self.tag is None:
            return True
        has_tag = False
        if self.type == '4':  # unsafe
            for mark_rep in report.markunsafereport_set.all():
                try:
                    mark_rep.mark.markunsafehistory_set\
                        .order_by('-version')[0].tags.get(tag=self.tag)
                    has_tag = True
                except ObjectDoesNotExist:
                    continue
        elif self.type == '5':  # safe
            for mark_rep in report.marksafereport_set.all():
                try:
                    mark_rep.mark.marksafehistory_set\
                        .order_by('-version')[0].tags.get(tag=self.tag)
                    has_tag = True
                except ObjectDoesNotExist:
                    continue
        return has_tag

    def __unknowns_data(self):

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
        attr_order = []
        for leaf in self.report.leaves.filter(~Q(unknown=None)):
            report = leaf.unknown
            for new_a in json.loads(report.attr_order):
                if new_a not in attr_order:
                    attr_order.append(new_a)
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
            components[report.pk] = parent.component.name

        columns = ['component']
        for name in attr_order:
            if name in data:
                columns.append(name)

        report_ids = []
        if 'order' in self.view and self.view['order'] in data:
            ids_ordered = []
            for rep_id in data[self.view['order']]:
                ids_ordered.append((data[self.view['order']][rep_id], rep_id))
            report_ids = [x[1] for x in sorted(ids_ordered, key=lambda x: x[0])]
        else:
            comp_data = []
            for pk in components:
                comp_data.append((components[pk], pk))
            for name, rep_id in sorted(comp_data, key=lambda x: x[0]):
                report_ids.append(rep_id)

        values_data = []
        for rep_id in report_ids:
            values_row = []
            for col in columns:
                val = '-'
                href = None
                if col in data and rep_id in data[col]:
                    val = data[col][rep_id]
                    if not self.__filter_attr(col, val):
                        break
                elif col == 'component':
                    val = components[rep_id]
                    href = reverse('reports:leaf', args=['unknown', rep_id])
                values_row.append({
                    'value': val,
                    'href': href
                })
            else:
                values_data.append(values_row)
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
        attr_data = []
        if isinstance(val, list):
            for v in val:
                if isinstance(v, dict):
                    nextname = next(iter(v))
                    for n in children(nextname.replace(':', '_'), v[nextname]):
                        if len(name) == 0:
                            new_id = n[0]
                        else:
                            new_id = "%s:%s" % (name, n[0])
                        attr_data.append((new_id, n[1]))
        elif isinstance(val, str):
            attr_data = [(name, val)]
        return attr_data

    created_attrs = []
    if isinstance(attrs, list):
        attrs_data = children('', attrs)
    elif isinstance(attrs, dict) and 'values' in attrs:
        attrs_data = attrs['values']
    else:
        return created_attrs
    for attr, value in attrs_data:
        new_attr_name, created = AttrName.objects.get_or_create(name=attr)
        new_attr, created = Attr.objects.get_or_create(
            name=new_attr_name, value=value)
        created_attrs.append(new_attr)
    return created_attrs
