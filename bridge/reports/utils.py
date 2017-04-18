#
# Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
# Institute for System Programming of the Russian Academy of Sciences
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

import os
import json
import zipfile
import xml.etree.ElementTree as ETree
from xml.dom import minidom
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.db.models import Q, Count
from django.utils.translation import ugettext_lazy as _
from bridge.vars import REPORT_ATTRS_DEF_VIEW, UNSAFE_LIST_DEF_VIEW, \
    SAFE_LIST_DEF_VIEW, UNKNOWN_LIST_DEF_VIEW, UNSAFE_VERDICTS, SAFE_VERDICTS
from bridge.utils import logger
from bridge.ZipGenerator import ZipStream
from users.models import View
from jobs.utils import get_resource_data, get_user_time
from reports.models import ReportComponent, Attr, AttrName, ReportAttr, ReportUnsafe, ReportSafe, ReportUnknown,\
    ReportRoot
from marks.tables import SAFE_COLOR, UNSAFE_COLOR
from marks.models import UnknownProblem, MarkUnknown, UnsafeReportTag, SafeReportTag
from bridge.tableHead import Header


REP_MARK_TITLES = {
    'mark_num': _('Mark'),
    'mark_verdict': _("Verdict"),
    'mark_result': _('Similarity'),
    'mark_status': _('Status'),
    'number': '№',
    'component': _('Component'),
    'marks_number': _("Number of associated marks"),
    'report_verdict': _("Total verdict"),
    'tags': _('Tags'),
    'parent_cpu': _('Verifiers time')
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
    try:
        parent = ReportComponent.objects.get(id=report.parent_id)
    except ObjectDoesNotExist:
        parent = None
    while parent is not None:
        parent_attrs = []
        for rep_attr in parent.attrs.order_by('attr__name__name').values_list('attr__name__name', 'attr__value'):
            parent_attrs.append(rep_attr)
        parents_data.insert(0, {
            'title': parent.component.name,
            'href': reverse('reports:component', args=[report.root.job_id, parent.id]),
            'attrs': parent_attrs
        })
        try:
            parent = ReportComponent.objects.get(id=parent.parent_id)
        except ObjectDoesNotExist:
            parent = None
    return parents_data


def report_resources(report, user):
    if all(x is not None for x in [report.wall_time, report.cpu_time, report.memory]):
        rd = get_resource_data(user.extended.data_format, user.extended.accuracy, report)
        return {'wall_time': rd[0], 'cpu_time': rd[1], 'memory': rd[2]}
    return None


class ReportTable(object):

    def __init__(self, user, report, view=None, view_id=None, table_type='0',
                 component_id=None, verdict=None, tag=None, problem=None, mark=None, attr=None):
        self.component_id = component_id
        self.report = report
        self.user = user
        self.type = table_type
        self.verdict = verdict
        self.tag = tag
        self.problem = problem
        self.mark = mark
        self.attr = attr
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
            pref_view = self.user.preferableview_set.filter(view__type=self.type).first()
            if pref_view:
                return json.loads(pref_view.view.view), pref_view.view_id
        elif view_id == 'default':
            return def_views[self.type], 'default'
        else:
            user_view = View.objects.filter(
                Q(id=view_id, type=self.type) & (Q(shared=True) | Q(author=self.user))
            ).first()
            if user_view:
                return json.loads(user_view.view), user_view.id
        return def_views[self.type], 'default'

    def __views(self):
        return View.objects.filter(Q(type=self.type) & (Q(author=self.user) | Q(shared=True))).order_by('name')

    def __get_table_data(self):
        actions = {
            '0': self.__self_data,
            '3': self.__component_data,
            '4': self.__unsafes_data,
            '5': self.__safes_data,
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
        for rep_attr in self.report.attrs.order_by('id').values_list('attr__name__name', 'attr__value'):
            columns.append(rep_attr[0])
            values.append(rep_attr[1])
        return columns, values

    def __component_data(self):
        data = {}
        components = {}
        columns = []
        component_filters = {'parent': self.report}
        if 'component' in self.view['filters']:
            component_filters[
                'component__name__' + self.view['filters']['component']['type']
                ] = self.view['filters']['component']['value']

        finish_dates = {}
        report_ids = set()
        for report in ReportComponent.objects.filter(**component_filters).select_related('component'):
            report_ids.add(report.id)
            components[report.id] = report.component
            if self.view['order'][0] == 'date' and report.finish_date is not None:
                finish_dates[report.id] = report.finish_date

        for ra in ReportAttr.objects.filter(report_id__in=report_ids).order_by('id')\
                .values_list('report_id', 'attr__name__name', 'attr__value'):
            if ra[1] not in data:
                columns.append(ra[1])
                data[ra[1]] = {}
            data[ra[1]][ra[0]] = ra[2]

        comp_data = []
        for pk in components:
            if self.view['order'][0] == 'component':
                comp_data.append((components[pk].name, {
                    'pk': pk,
                    'component': components[pk]
                }))
            elif self.view['order'][0] == 'date':
                if pk in finish_dates:
                    comp_data.append((finish_dates[pk], {
                        'pk': pk,
                        'component': components[pk]
                    }))
            else:
                attr_val = '-'
                if self.view['order'][0] in data and pk in data[self.view['order'][0]]:
                    attr_val = data[self.view['order'][0]][pk]
                comp_data.append((attr_val, {
                    'pk': pk,
                    'component': components[pk]
                }))
        sorted_components = []
        for name, dt in sorted(comp_data, key=lambda x: x[0]):
            sorted_components.append(dt)
        if self.view['order'] is not None and self.view['order'][1] == 'up':
            sorted_components = list(reversed(sorted_components))

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

    def __safes_data(self):
        data = {}

        columns = ['number']
        for col in self.view['columns']:
            if self.verdict is not None and col == 'report_verdict':
                continue
            columns.append(col)
        if self.verdict is not None:
            leaves_set = self.report.leaves.filter(Q(safe__verdict=self.verdict) & ~Q(safe=None))\
                .annotate(marks_number=Count('safe__markreport_set')).select_related('safe')
        elif self.mark is not None:
            leaves_set = self.report.leaves.filter(safe__markreport_set__mark=self.mark).distinct()\
                .exclude(safe=None).annotate(marks_number=Count('safe__markreport_set')).select_related('safe')
        elif self.attr is not None:
            leaves_set = self.report.leaves.filter(safe__attrs__attr=self.attr).distinct()\
                .exclude(safe=None).annotate(marks_number=Count('safe__markreport_set')).select_related('safe')
        else:
            leaves_set = self.report.leaves.exclude(safe=None).annotate(marks_number=Count('safe__markreport_set'))\
                .select_related('safe')

        reports = {}
        for leaf in leaves_set:
            reports[leaf.safe_id] = {
                'marks_number': leaf.marks_number,
                'verdict': leaf.safe.verdict,
                'parent_id': leaf.safe.parent_id,
                'parent_cpu': leaf.safe.verifier_time,
                'tags': {}
            }
        for srt in SafeReportTag.objects.filter(report_id__in=list(reports)).select_related('tag'):
            if srt.tag.tag not in reports[srt.report_id]['tags']:
                reports[srt.report_id]['tags'][srt.tag.tag] = 0
            reports[srt.report_id]['tags'][srt.tag.tag] += 1
        for rep_attr in ReportAttr.objects.filter(report_id__in=list(reports)).order_by('id')\
                .values_list('report_id', 'attr__name__name', 'attr__value'):
            if rep_attr[1] not in data:
                columns.append(rep_attr[1])
                data[rep_attr[1]] = {}
            data[rep_attr[1]][rep_attr[0]] = rep_attr[2]

        reports_ordered = []
        if 'order' in self.view and self.view['order'][0] in data:
            for rep_id in data[self.view['order'][0]]:
                if self.__has_tag(reports[rep_id]['tags']):
                    reports_ordered.append(
                        (data[self.view['order'][0]][rep_id], rep_id)
                    )
            reports_ordered = [x[1] for x in sorted(reports_ordered, key=lambda x: x[0])]
        else:
            for attr in data:
                for rep_id in data[attr]:
                    if rep_id not in reports_ordered and self.__has_tag(reports[rep_id]['tags']):
                        reports_ordered.append(rep_id)
            reports_ordered = sorted(reports_ordered)
        if 'order' in self.view and self.view['order'][1] == 'up':
            reports_ordered = list(reversed(reports_ordered))

        for r_id in reports:
            tags_str = []
            for t_name in sorted(reports[r_id]['tags']):
                if reports[r_id]['tags'][t_name] == 1:
                    tags_str.append(t_name)
                else:
                    tags_str.append("%s (%s)" % (t_name, reports[r_id]['tags'][t_name]))
            reports[r_id]['tags'] = '; '.join(tags_str)

        cnt = 1
        values_data = []
        for rep_id in reports_ordered:
            values_row = []
            for col in columns:
                val = '-'
                href = None
                color = None
                if col in data:
                    if rep_id in data[col]:
                        val = data[col][rep_id]
                        if not self.__filter_attr(col, val):
                            break
                elif col == 'number':
                    val = cnt
                    href = reverse('reports:safe', args=[rep_id])
                elif col == 'marks_number':
                    val = reports[rep_id]['marks_number']
                elif col == 'report_verdict':
                    for s in SAFE_VERDICTS:
                        if s[0] == reports[rep_id]['verdict']:
                            val = s[1]
                            break
                    color = SAFE_COLOR[reports[rep_id]['verdict']]
                elif col == 'tags':
                    if len(reports[rep_id]['tags']) > 0:
                        val = reports[rep_id]['tags']
                elif col == 'parent_cpu':
                    val = get_user_time(self.user, reports[rep_id]['parent_cpu'])
                values_row.append({
                    'value': val,
                    'color': color,
                    'href': href
                })
            else:
                cnt += 1
                values_data.append(values_row)
        return columns, values_data

    def __unsafes_data(self):
        data = {}

        columns = ['number']
        for col in self.view['columns']:
            if self.verdict is not None and col == 'report_verdict':
                continue
            columns.append(col)

        if self.verdict is not None:
            leaves_set = self.report.leaves.filter(Q(unsafe__verdict=self.verdict) & ~Q(unsafe=None))\
                .annotate(marks_number=Count('unsafe__markreport_set')).select_related('unsafe')
        elif self.mark is not None:
            leaves_set = self.report.leaves.filter(unsafe__markreport_set__mark=self.mark).distinct()\
                .exclude(unsafe=None).annotate(marks_number=Count('unsafe__markreport_set')).select_related('unsafe')
        elif self.attr is not None:
            leaves_set = self.report.leaves.filter(unsafe__attrs__attr=self.attr).distinct()\
                .exclude(unsafe=None).annotate(marks_number=Count('unsafe__markreport_set')).select_related('unsafe')
        else:
            leaves_set = self.report.leaves.exclude(unsafe=None).annotate(marks_number=Count('unsafe__markreport_set'))\
                .select_related('unsafe')

        reports = {}
        for leaf in leaves_set:
            reports[leaf.unsafe_id] = {
                'marks_number': leaf.marks_number,
                'verdict': leaf.unsafe.verdict,
                'parent_id': leaf.unsafe.parent_id,
                'parent_cpu': leaf.unsafe.verifier_time,
                'tags': {}
            }
        for urt in UnsafeReportTag.objects.filter(report_id__in=list(reports)).select_related('tag'):
            if urt.tag.tag not in reports[urt.report_id]['tags']:
                reports[urt.report_id]['tags'][urt.tag.tag] = 0
            reports[urt.report_id]['tags'][urt.tag.tag] += 1
        for rep_attr in ReportAttr.objects.filter(report_id__in=list(reports)).order_by('id')\
                .values_list('report_id', 'attr__name__name', 'attr__value'):
            if rep_attr[1] not in data:
                columns.append(rep_attr[1])
                data[rep_attr[1]] = {}
            data[rep_attr[1]][rep_attr[0]] = rep_attr[2]

        reports_ordered = []
        if 'order' in self.view and self.view['order'][0] in data:
            for rep_id in data[self.view['order'][0]]:
                if self.__has_tag(reports[rep_id]['tags']):
                    reports_ordered.append(
                        (data[self.view['order'][0]][rep_id], rep_id)
                    )
            reports_ordered = [x[1] for x in sorted(reports_ordered, key=lambda x: x[0])]
        else:
            for attr in data:
                for rep_id in data[attr]:
                    if rep_id not in reports_ordered and self.__has_tag(reports[rep_id]['tags']):
                        reports_ordered.append(rep_id)
            reports_ordered = sorted(reports_ordered)
        if 'order' in self.view and self.view['order'][1] == 'up':
            reports_ordered = list(reversed(reports_ordered))

        for r_id in reports:
            tags_str = []
            for t_name in sorted(reports[r_id]['tags']):
                if reports[r_id]['tags'][t_name] == 1:
                    tags_str.append(t_name)
                else:
                    tags_str.append("%s (%s)" % (t_name, reports[r_id]['tags'][t_name]))
            reports[r_id]['tags'] = '; '.join(tags_str)

        cnt = 1
        values_data = []
        for rep_id in reports_ordered:
            values_row = []
            for col in columns:
                val = '-'
                href = None
                color = None
                if col in data:
                    if rep_id in data[col]:
                        val = data[col][rep_id]
                        if not self.__filter_attr(col, val):
                            break
                elif col == 'number':
                    val = cnt
                    href = reverse('reports:unsafe', args=[rep_id])
                elif col == 'marks_number':
                    val = reports[rep_id]['marks_number']
                elif col == 'report_verdict':
                    for u in UNSAFE_VERDICTS:
                        if u[0] == reports[rep_id]['verdict']:
                            val = u[1]
                            break
                    color = UNSAFE_COLOR[reports[rep_id]['verdict']]
                elif col == 'tags':
                    if len(reports[rep_id]['tags']) > 0:
                        val = reports[rep_id]['tags']
                elif col == 'parent_cpu':
                    val = get_user_time(self.user, reports[rep_id]['parent_cpu'])
                values_row.append({
                    'value': val,
                    'color': color,
                    'href': href
                })
            else:
                cnt += 1
                values_data.append(values_row)
        return columns, values_data

    def __has_tag(self, tags):
        return self.tag is None or self.tag in tags

    def __unknowns_data(self):
        data = {}
        components = {}
        filters = {}
        if self.component_id is not None:
            filters['unknown__component_id'] = int(self.component_id)
        if 'component' in self.view['filters'] \
                and self.view['filters']['component']['type'] in ['iexact', 'istartswith', 'icontains']:
            ftype = 'unknown__component__name__%s' % self.view['filters']['component']['type']
            filters[ftype] = self.view['filters']['component']['value']
        if isinstance(self.problem, UnknownProblem):
            leaf_set = self.report.leaves.filter(unknown__markreport_set__problem=self.problem).distinct()\
                .filter(~Q(unknown=None) & Q(**filters))
        elif isinstance(self.mark, MarkUnknown):
            leaf_set = self.report.leaves.filter(unknown__markreport_set__mark=self.mark).distinct()\
                .filter(~Q(unknown=None) & Q(**filters))
        elif self.attr is not None:
            leaf_set = self.report.leaves.filter(unknown__attrs__attr=self.attr).distinct()\
                .filter(~Q(unknown=None) & Q(**filters))
        else:
            if self.problem == 0:
                filters['mr_set_len'] = 0
            leaf_set = self.report.leaves.annotate(mr_set_len=Count('unknown__markreport_set'))\
                .filter(~Q(unknown=None) & Q(**filters))
        columns = ['component']
        for leaf in leaf_set:
            report = leaf.unknown
            for rep_attr in report.attrs.order_by('id'):
                if rep_attr.attr.name.name not in data:
                    columns.append(rep_attr.attr.name.name)
                    data[rep_attr.attr.name.name] = {}
                data[rep_attr.attr.name.name][report.pk] = rep_attr.attr.value
            components[report.pk] = report.component.name

        report_ids = []
        if 'order' in self.view and self.view['order'][0] in data:
            ids_ordered = []
            for rep_id in data[self.view['order'][0]]:
                ids_ordered.append((data[self.view['order'][0]][rep_id], rep_id))
            report_ids = [x[1] for x in sorted(ids_ordered, key=lambda x: x[0])]
        else:
            comp_data = []
            for pk in components:
                comp_data.append((components[pk], pk))
            for name, rep_id in sorted(comp_data, key=lambda x: x[0]):
                report_ids.append(rep_id)
        if 'order' in self.view and self.view['order'][1] == 'up':
            report_ids = list(reversed(report_ids))

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
                    href = reverse('reports:unknown', args=[rep_id])
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
                elif ftype == 'istartswith' and not value.lower().startswith(fvalue.lower()):
                    return False
        return True


class AttrData(object):
    def __init__(self):
        self._data = []
        self._name = {}
        self._attrs = {}

    def add(self, report_id, name, value):
        self._data.append((report_id, name, value))
        if name not in self._name:
            self._name[name] = None
        if (name, value) not in self._attrs:
            self._attrs[(name, value)] = None

    def upload(self):
        self.__upload_names()
        self.__upload_attrs()
        ReportAttr.objects.bulk_create(
            list(ReportAttr(report_id=d[0], attr_id=self._attrs[(d[1], d[2])]) for d in self._data)
        )
        self.__init__()

    def __upload_names(self):
        existing_names = set(n.name for n in AttrName.objects.filter(name__in=self._name))
        names_to_create = []
        for name in self._name:
            if name not in existing_names:
                names_to_create.append(AttrName(name=name))
        AttrName.objects.bulk_create(names_to_create)
        for n in AttrName.objects.filter(name__in=self._name):
            self._name[n.name] = n.id

    def __upload_attrs(self):
        for a in Attr.objects.filter(value__in=list(attr[1] for attr in self._attrs)).select_related('name'):
            if (a.name.name, a.value) in self._attrs:
                self._attrs[(a.name.name, a.value)] = a.id
        attrs_to_create = []
        for attr in self._attrs:
            if self._attrs[attr] is None and attr[0] in self._name:
                attrs_to_create.append(Attr(name_id=self._name[attr[0]], value=attr[1]))
        Attr.objects.bulk_create(attrs_to_create)
        for a in Attr.objects.filter(value__in=list(attr[1] for attr in self._attrs)).select_related('name'):
            if (a.name.name, a.value) in self._attrs:
                self._attrs[(a.name.name, a.value)] = a.id


class FilesForCompetitionArchive(object):
    def __init__(self, job, filters):
        self.name = 'svcomp.zip'
        self.benchmark_fname = 'benchmark.xml'
        self.prp_fname = 'unreach-call.prp'
        self.obj_attr = 'Verification object'
        self.rule_attr = 'Rule specification'
        try:
            self.root = ReportRoot.objects.get(job=job)
        except ObjectDoesNotExist:
            raise ValueError('The job is not decided')
        self._archives = self.__get_archives()
        self.filters = filters
        self.xml_root = None
        self.prp_file_added = False
        self.stream = ZipStream()

    def __iter__(self):
        for f_t in self.filters:
            if isinstance(f_t, str) and f_t in {'u', 's'}:
                for data in self.__reports_data(f_t):
                    yield data
            elif isinstance(f_t, list):
                for data in self.__reports_data('f', f_t):
                    yield data
        if self.xml_root is None:
            for data in self.stream.compress_string('NOFILES', ''):
                yield data
        else:
            benchmark_content = minidom.parseString(ETree.tostring(self.xml_root, 'utf-8')).toprettyxml(indent="  ")
            for data in self.stream.compress_string(self.benchmark_fname, benchmark_content):
                yield data
        yield self.stream.close_stream()

    def __get_archives(self):
        archives = {}
        for c in ReportComponent.objects.filter(root=self.root).only('id', 'archive'):
            if c.archive:
                archives[c.id] = c.archive
        return archives

    def __reports_data(self, f_type, problems=None):
        if f_type == 'u':
            table = ReportUnsafe
            cil_dir = 'Unsafes'
        elif f_type == 's':
            table = ReportSafe
            cil_dir = 'Safes'
        elif f_type == 'f':
            table = ReportUnknown
            cil_dir = 'Unknowns'
        else:
            raise ValueError('Wrong filter type')

        reports = {}
        if f_type == 'f' and problems is not None and len(problems) > 0:
            for problem in problems:
                comp_id, problem_id = problem.split('_')[0:2]
                if comp_id == problem_id == '0':
                    for r in ReportUnknown.objects.annotate(mr_len=Count('markreport_set'))\
                            .filter(root=self.root, mr_len=0).exclude(parent__parent=None).only('id', 'parent_id'):
                        if r.parent_id not in self._archives:
                            continue
                        reports[r.id] = r.parent_id
                else:
                    for r in ReportUnknown.objects\
                            .filter(root=self.root, markreport_set__problem_id=problem_id, component_id=comp_id)\
                            .exclude(parent__parent=None).only('id', 'parent_id'):
                        if r.parent_id not in self._archives:
                            continue
                        reports[r.id] = r.parent_id
        else:
            for r in table.objects.filter(root=self.root).exclude(parent__parent=None).only('id', 'parent_id'):
                if r.parent_id not in self._archives:
                    continue
                reports[r.id] = r.parent_id
        attrs_data = {}
        for ra in ReportAttr.objects\
                .filter(report_id__in=list(reports), attr__name__name__in=[self.obj_attr, self.rule_attr])\
                .select_related('attr', 'attr__name'):
            if ra.report_id not in attrs_data:
                attrs_data[ra.report_id] = {}
            attrs_data[ra.report_id][ra.attr.name.name] = ra.attr.value
        cnt = 1
        paths_in_use = []
        for r_id in reports:
            if r_id in attrs_data and self.obj_attr in attrs_data[r_id] and self.rule_attr in attrs_data[r_id]:
                ver_obj = attrs_data[r_id][self.obj_attr].replace('~', 'HOME').replace('/', '---')
                ver_rule = attrs_data[r_id][self.rule_attr].replace(':', '-')
                r_path = '%s/%s__%s__%s.cil.i' % (cil_dir, f_type, ver_rule, ver_obj)
                if r_path in paths_in_use:
                    ver_obj_path, ver_obj_name = r_path.split('/')
                    r_path = '/'.join([ver_obj_path, "%s__%s" % (cnt, ver_obj_name)])
                    cnt += 1
                try:
                    for data in self.__cil_data(reports[r_id], r_path):
                        yield data
                except Exception as e:
                    logger.exception(e)
                else:
                    new_elem = ETree.Element('include')
                    new_elem.text = r_path
                    self.xml_root.find('tasks').append(new_elem)
                    paths_in_use.append(r_path)

    def __cil_data(self, report_id, arcname):
        with self._archives[report_id] as fp:
            if os.path.splitext(fp.name)[-1] != '.zip':
                raise ValueError('Archive type is not supported')
            with zipfile.ZipFile(fp, 'r') as zfp:
                xml_root = ETree.fromstring(zfp.read(self.benchmark_fname))
                cil_content = zfp.read(xml_root.find('tasks').find('include').text)
                for data in self.stream.compress_string(arcname, cil_content):
                    yield data
                if not self.prp_file_added:
                    for data in self.stream.compress_string(self.prp_fname, zfp.read(self.prp_fname)):
                        yield data
                    self.prp_file_added = True
            if self.xml_root is None:
                self.xml_root = xml_root
                self.xml_root.find('tasks').clear()


def report_attibutes(report):
    return report.attrs.order_by('id').values_list('attr__name__name', 'attr__value')
