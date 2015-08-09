import json
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.utils.translation import ugettext_lazy as _
from reports.models import ReportComponent
import jobs.job_functions as job_f


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
                data.append("%s: %s" % (data_name, str(comp_data[data_name])))
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
            parent_attrs.append([attr.name.name, attr_value(attr.value)])
        title = pid.split('##')[-1]
        name = title
        if len(name) > 20:
            name = name[:20] + '...'
        if cnt == 1:
            href = reverse('reports:report_root', args=[report.root.job.pk])
        else:
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
        resources = {
            'wall_time': report.resource.wall_time,
            'cpu_time': report.resource.cpu_time,
            'memory': report.resource.memory,
        }
        if user.extended.data_format == 'hum':
            resources['wall_time'] = job_f.convert_time(
                resources['wall_time'], user.extended.accuracy)
            resources['cpu_time'] = job_f.convert_time(
                resources['cpu_time'], user.extended.accuracy)
            resources['memory'] = job_f.convert_memory(
                resources['memory'], user.extended.accuracy)
    return resources
