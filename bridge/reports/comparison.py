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

import re
import json
from collections import OrderedDict

from django.contrib.contenttypes.models import ContentType
from django.db.models import Count
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from bridge.vars import COMPARE_VERDICT, DECISION_WEIGHT
from bridge.utils import BridgeException

from reports.models import (
    ReportAttr, CompareDecisionsInfo, ComparisonObject, ComparisonLink,
    ReportSafe, ReportUnsafe, ReportUnknown, ReportComponent
)
from marks.models import MarkUnsafeReport, MarkSafeReport, MarkUnknownReport

from reports.verdicts import safe_color, unsafe_color


class GetComparisonObjects:
    def __init__(self, decision, names):
        self._decision = decision
        self._names = names

    def __fill_leaf_objects(self, data, leaf_type):
        qs = ReportAttr.objects.filter(report__decision=self._decision, compare=True)\
            .exclude(**{'report__report{}'.format(leaf_type): None})
        for attr in qs:
            if attr.report_id not in data:
                data[attr.report_id] = {
                    'type': leaf_type,
                    'values': OrderedDict(list((attr_name, '-') for attr_name in self._names))
                }
            data[attr.report_id]['values'][attr.name] = attr.value

    def get_leaf_values(self):
        data = {}
        self.__fill_leaf_objects(data, 'safe')
        self.__fill_leaf_objects(data, 'unsafe')
        self.__fill_leaf_objects(data, 'unknown')

        attr_data = {}
        for r_id in data:
            values_tuple = tuple(data[r_id]['values'].values())
            attr_data.setdefault(values_tuple, [])
            attr_data[values_tuple].append({'id': r_id, 'type': data[r_id]['type']})
        return attr_data


class FillComparisonCache:
    def __init__(self, user, decision1, decision2):
        self._decision1 = decision1
        self._decision2 = decision2
        self._names = self.__get_attr_names()
        self.info = self.__create_info(user)
        self.__fill_data()

    def __get_attr_names(self):
        names1 = set(ReportAttr.objects.filter(report__decision=self._decision1, compare=True)
                     .values_list('name', flat=True))
        names2 = set(ReportAttr.objects.filter(report__decision=self._decision2, compare=True)
                     .values_list('name', flat=True))
        if names1 != names2:
            raise BridgeException(_("Jobs with different sets of attributes to compare can't be compared"))
        return list(sorted(names1))

    def __create_info(self, user):
        return CompareDecisionsInfo.objects.create(
            user=user, decision1=self._decision1, decision2=self._decision2, names=self._names
        )

    def __fill_data(self):
        ct_map = {
            'safe': ContentType.objects.get_for_model(ReportSafe),
            'unsafe': ContentType.objects.get_for_model(ReportUnsafe),
            'unknown': ContentType.objects.get_for_model(ReportUnknown),
        }
        data1 = GetComparisonObjects(self._decision1, self._names).get_leaf_values()
        data2 = GetComparisonObjects(self._decision2, self._names).get_leaf_values()

        # Calculate total verdicts for each batch of attributes values
        verdicts_data = {}
        for values_tuple in data1:
            verdicts_data[values_tuple] = {
                'verdict1': self.__calc_verdict(data1[values_tuple]),
                'verdict2': COMPARE_VERDICT[4][0]
            }
        for values_tuple in data2:
            verdict2 = self.__calc_verdict(data2[values_tuple])
            if values_tuple in verdicts_data:
                verdicts_data[values_tuple]['verdict2'] = verdict2
            else:
                verdicts_data[values_tuple] = {'verdict1': COMPARE_VERDICT[4][0], 'verdict2': verdict2}

        # Create new comparison objects
        res = ComparisonObject.objects.bulk_create(list(ComparisonObject(
            info=self.info, values=list(values_tuple),
            verdict1=verdicts_data[values_tuple]['verdict1'],
            verdict2=verdicts_data[values_tuple]['verdict2']
        ) for values_tuple in sorted(verdicts_data)))
        for new_obj in res:
            verdicts_data[tuple(new_obj.values)]['pk'] = new_obj.pk

        # Create new comparison links
        new_links = []
        for values_tuple in data1:
            for report in data1[values_tuple]:
                new_links.append(ComparisonLink(
                    object_id=report['id'], content_type=ct_map[report['type']],
                    comparison_id=verdicts_data[values_tuple]['pk']
                ))
        for values_tuple in data2:
            for report in data2[values_tuple]:
                new_links.append(ComparisonLink(
                    object_id=report['id'], content_type=ct_map[report['type']],
                    comparison_id=verdicts_data[values_tuple]['pk']
                ))
        ComparisonLink.objects.bulk_create(new_links)

    def __calc_verdict(self, reports):
        if len(reports) == 1:
            if reports[0]['type'] == 'safe':
                return COMPARE_VERDICT[0][0]
            elif reports[0]['type'] == 'unknown':
                return COMPARE_VERDICT[3][0]
            return COMPARE_VERDICT[1][0]
        has_unknown = False
        for rep in reports:
            if rep['type'] == 'safe':
                return COMPARE_VERDICT[5][0]
            elif rep['type'] == 'unknown':
                if has_unknown:
                    return COMPARE_VERDICT[5][0]
                has_unknown = True
        return COMPARE_VERDICT[2][0] if has_unknown else COMPARE_VERDICT[1][0]


class ComparisonTableData:
    def __init__(self, decision1, decision2, comparison_info=None):
        if comparison_info:
            self.info = comparison_info
        else:
            try:
                self.info = CompareDecisionsInfo.objects.get(decision1=decision1, decision2=decision2)
            except CompareDecisionsInfo.DoesNotExist:
                raise BridgeException(_('The comparison cache was not found'))
        self.table_rows = self.__get_table_data()
        self.attrs = self.__get_attrs()
        self.lightweight = (decision1.weight == decision2.weight == DECISION_WEIGHT[1][0])

    def __get_table_data(self):
        numbers = {}
        for v1, v2, num in ComparisonObject.objects.filter(info=self.info)\
                .values('verdict1', 'verdict2').annotate(number=Count('id'))\
                .values_list('verdict1', 'verdict2', 'number'):
            numbers[(v1, v2)] = num

        head_row = [{'class': 'decision-th-0', 'value': ''}] + \
                   [{'class': 'decision-th-2', 'value': v[1]} for v in COMPARE_VERDICT]
        table_data = [head_row]

        for v1 in COMPARE_VERDICT:
            row_data = [{'class': 'decision-th-1 right aligned', 'value': v1[1]}]
            for v2 in COMPARE_VERDICT:
                verdict_tuple = (v1[0], v2[0])
                row_data.append({
                    'value': numbers.get(verdict_tuple, '-'),
                    'verdict': '{0}_{1}'.format(*verdict_tuple)
                })
            table_data.append(row_data)
        return table_data

    def __get_attrs(self):
        all_attrs = OrderedDict((attr_name, set()) for attr_name in self.info.names)
        for cmp_obj in ComparisonObject.objects.filter(info=self.info):
            i = 0
            for attr_name in all_attrs:
                if cmp_obj.values[i] != '-':
                    all_attrs[attr_name].add(cmp_obj.values[i])
                i += 1

        i = 0
        attrs_values = []
        for attr_name in all_attrs:
            attrs_values.append({'name': attr_name, 'id': i, 'values': list(sorted(all_attrs[attr_name]))})
            i += 1
        return attrs_values


class ComparisonData:
    def __init__(self, info, page_num, hide_attrs, hide_components, verdict=None, attrs=None):
        self.info = info

        # Never show components when both jobs are lightweight
        self.hide_components = bool(int(hide_components)) or self.lightweight
        self.hide_attrs = bool(int(hide_attrs))

        self.pages = {
            'backward': True,
            'forward': True,
            'page': page_num,
            'total': 0
        }
        self.comparison = self.__paginate(verdict, attrs)
        self.tree1, self.tree2 = self.__get_trees()

    @property
    def lightweight(self):
        return self.info.decision1.weight == self.info.decision2.weight == DECISION_WEIGHT[1][0]

    def __get_verdicts(self, verdict):
        m = re.match(r'^(\d)_(\d)$', verdict)
        if m is None:
            raise BridgeException()
        v1 = m.group(1)
        v2 = m.group(2)
        if any(v not in list(x[0] for x in COMPARE_VERDICT) for v in [v1, v2]):
            raise BridgeException()
        return v1, v2

    def __paginate(self, verdict=None, search_attrs=None):
        # Filter queryset
        qs_filters = {'info': self.info}
        if search_attrs:
            search_attr_values = json.loads(search_attrs)
            for i in range(len(self.info.names)):
                if search_attr_values[i] != '__ANY__':
                    qs_filters['values__{}'.format(i)] = search_attr_values[i]
        elif verdict is not None:
            qs_filters['verdict1'], qs_filters['verdict2'] = self.__get_verdicts(verdict)
        else:
            raise BridgeException()
        queryset = ComparisonObject.objects.filter(**qs_filters).order_by('id')

        # Get needed page and pages info
        self.pages['total'] = queryset.count()
        if self.pages['total'] < self.pages['page']:
            raise BridgeException(_('Required reports were not found'))
        self.pages['backward'] = (self.pages['page'] > 1)
        self.pages['forward'] = (self.pages['page'] < self.pages['total'])
        return queryset[self.pages['page'] - 1]

    def __get_trees(self):
        tree1 = ComparisonTree()
        tree2 = ComparisonTree()
        for link in ComparisonLink.objects.filter(comparison=self.comparison).order_by('object_id'):
            report = link.content_object
            if report.decision_id == self.info.decision1_id:
                tree1.update_tree(report, self.hide_components)
            else:
                tree2.update_tree(report, self.hide_components)

        blocks1 = tree1.blocks
        blocks2 = tree2.blocks

        # Compare attributes
        for b1 in blocks1:
            for b2 in blocks2:
                if b1.block_class != b2.block_class:
                    continue
                for attr in b1.attrs:
                    attr['type'] = 'unmatched'
                for attr in b2.attrs:
                    attr['type'] = 'unmatched'
                for attr1 in b1.attrs:
                    for attr2 in b2.attrs:
                        if attr1['name'] != attr2['name']:
                            continue
                        if attr1['value'] == attr2['value']:
                            attr1['type'] = attr2['type'] = 'compared' if attr1['compare'] else 'normal'
                        else:
                            attr1['type'] = attr2['type'] = 'different'

        # Hide normal attributes
        if self.hide_attrs:
            for block in blocks1 + blocks2:
                if not block.attrs:
                    continue
                block.attrs = list(attr for attr in block.attrs if attr['type'] != 'normal')

        return tree1, tree2


class CompareBlock:
    def __init__(self, block_id, block_class=None):
        self.id = block_id
        self.block_class = block_class or self.id

        self.parent = None
        self.children = []

        self.type = None
        self.title = ''
        self.subtitle = None
        self.href = None
        self.tags = None
        self.attrs = None

    def add_child(self, child):
        self.children.append(child)
        child.parent = self

    def get_attrs(self, report):
        attrs_list = list(ReportAttr.objects.filter(report=report).order_by('name').values('name', 'value', 'compare'))
        for attr in attrs_list:
            attr['type'] = 'compared' if attr['compare'] else 'normal'
        return attrs_list

    def get_tags(self, mark):
        return list(mark.versions.order_by('-version').first().tags.values_list('tag__name', flat=True))

    @property
    def ascendants(self):
        branch = []
        if self.parent:
            branch.extend(self.parent.ascendants)
        branch.append(self)
        return branch

    @property
    def root(self):
        if self.parent:
            return self.parent.root
        return self


class UnknownMarkBlock(CompareBlock):
    def __init__(self, mark_report):
        super().__init__("fm_{}".format(mark_report.mark_id))
        self.type = 'mark'
        self.title = _('Unknowns mark')
        self.href = reverse('marks:unknown', args=[mark_report.mark_id])
        self.subtitle = {'text': mark_report.problem}


class SafeMarkBlock(CompareBlock):
    def __init__(self, mark_report):
        super().__init__("sm_{}".format(mark_report.mark_id))
        self.type = 'mark'
        self.title = _('Safes mark')
        self.href = reverse('marks:safe', args=[mark_report.mark_id])
        self.subtitle = {
            'text': mark_report.mark.get_verdict_display(),
            'color': safe_color(mark_report.mark.verdict)
        }
        self.tags = self.get_tags(mark_report.mark)


class UnsafeMarkBlock(CompareBlock):
    def __init__(self, mark_report):
        super().__init__("um_{}".format(mark_report.mark_id))
        self.type = 'mark'
        self.title = _('Unsafes mark')
        self.href = reverse('marks:unsafe', args=[mark_report.mark_id])
        self.subtitle = {
            'text': mark_report.mark.get_verdict_display(),
            'color': unsafe_color(mark_report.mark.verdict)
        }
        self.tags = self.get_tags(mark_report.mark)


class UnknownBlock(CompareBlock):
    def __init__(self, report):
        super().__init__("f_{}".format(report.pk), block_class='unknown_{}'.format(report.component))
        self.type = 'unknown'
        self.title = _('Unknown')
        self.href = reverse('reports:unknown', args=[report.decision.identifier, report.identifier])
        self.subtitle = {'text': report.component}
        self.attrs = self.get_attrs(report)


class UnsafeBlock(CompareBlock):
    def __init__(self, report):
        super().__init__("u_{}".format(report.pk), block_class='unsafe')
        self.type = 'unsafe'
        self.title = _('Unsafe')
        self.href = reverse('reports:unsafe', args=[report.decision.identifier, report.identifier])
        self.subtitle = {
            'text': report.cache.get_verdict_display(),
            'color': unsafe_color(report.cache.verdict)
        }
        self.attrs = self.get_attrs(report)


class SafeBlock(CompareBlock):
    def __init__(self, report):
        super().__init__("s_{}".format(report.pk), block_class='safe')
        self.type = 'safe'
        self.title = _('Safe')
        self.href = reverse('reports:safe', args=[report.decision.identifier, report.identifier])
        self.subtitle = {
            'text': report.cache.get_verdict_display(),
            'color': safe_color(report.cache.verdict)
        }
        self.attrs = self.get_attrs(report)


class ComponentBlock(CompareBlock):
    def __init__(self, report):
        super().__init__("c_{}".format(report.pk), block_class=report.component)
        self.type = 'component'
        self.title = report.component
        self.href = reverse('reports:component', args=[report.decision.identifier, report.identifier])
        self.attrs = self.get_attrs(report)


class ComparisonTree:
    def __init__(self):
        self._blocks = {}
        self._leaves = []

    def __get_reports_branch(self, report):
        curr_parent = None
        parents_ids = list(r.pk for r in report.get_ancestors())
        for report in ReportComponent.objects.filter(id__in=parents_ids).order_by('id'):
            if report.pk not in self._blocks:
                self._blocks[report.pk] = ComponentBlock(report)
                if curr_parent:
                    curr_parent.add_child(self._blocks[report.pk])
            curr_parent = self._blocks[report.pk]
        return curr_parent

    def update_tree(self, report, hide_components):
        # Get parents branch if components are shown
        parent = None
        if not hide_components:
            parent = self.__get_reports_branch(report)

        # Create new leaf block with marks children
        if isinstance(report, ReportSafe):
            new_block = SafeBlock(report)
            mr_qs = MarkSafeReport.objects.filter(report=report, associated=True).select_related('mark')
            children = list(SafeMarkBlock(mr) for mr in mr_qs)
        elif isinstance(report, ReportUnsafe):
            new_block = UnsafeBlock(report)
            mr_qs = MarkUnsafeReport.objects.filter(report=report, associated=True).select_related('mark')
            children = list(UnsafeMarkBlock(mr) for mr in mr_qs)
        else:
            new_block = UnknownBlock(report)
            mr_qs = MarkUnknownReport.objects.filter(report=report, associated=True)
            children = list(UnknownMarkBlock(mr) for mr in mr_qs)

        # Link new block with parent and children
        if parent:
            parent.add_child(new_block)
        for child in children:
            new_block.add_child(child)

        self._leaves.append(new_block)

    @property
    def blocks(self):
        blocks_list = []
        for leaf in self._leaves:
            # Includes leaf
            for parent in leaf.ascendants:
                if parent not in blocks_list:
                    blocks_list.append(parent)
        return blocks_list

    def levels(self):
        # initialize first level (Core or leaves)
        current_level = []
        for leaf in self._leaves:
            leaf_root = leaf.root
            if leaf_root not in current_level:
                current_level.append(leaf_root)

        while len(current_level):
            yield current_level
            next_level = []
            for block in current_level:
                for child in block.children:
                    next_level.append(child)
            current_level = next_level
