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

import json
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.utils.translation import ugettext_lazy as _
from bridge.vars import VIEWJOB_DEF_VIEW, JOB_WEIGHT
from jobs.utils import SAFES, UNSAFES, TITLES, get_resource_data
from reports.models import AttrStatistic


COLORS = {
    'red': '#C70646',
    'orange': '#D05A00',
    'purple': '#930BBD',
}


class ViewJobData:
    def __init__(self, user, report, view=None, view_id=None):
        self.report = report
        self.user = user
        (self.view, self.view_id) = self.__get_view(view, view_id)
        self.views = self.__views()
        if self.report is None:
            return
        self.unknowns_total = None
        self.safes_total = None
        self.unsafes_total = None
        self.view_data = {}
        self.problems = []
        try:
            self.__get_view_data()
        except ObjectDoesNotExist:
            return
        if len(self.problems) > 0:
            self.problems.append((_('Without marks'), '0_0'))

    def __get_view(self, view, view_id):
        if view is not None:
            return json.loads(view), None
        if view_id is None:
            pref_view = self.user.preferableview_set.filter(view__type='2')
            if len(pref_view):
                return json.loads(pref_view[0].view.view), pref_view[0].view_id
        elif view_id == 'default':
            return VIEWJOB_DEF_VIEW, 'default'
        else:
            user_view = self.user.view_set.filter(pk=int(view_id), type='2')
            if len(user_view):
                return json.loads(user_view[0].view), user_view[0].pk
        return VIEWJOB_DEF_VIEW, 'default'

    def __views(self):
        views = []
        for view in self.user.view_set.filter(type='2'):
            views.append({
                'id': view.pk,
                'name': view.name
            })
        return views

    def __get_view_data(self):
        if 'data' not in self.view:
            return
        actions = {
            'safes': self.__safes_info,
            'unsafes': self.__unsafes_info,
            'unknowns': self.__unknowns_info,
            'resources': self.__resource_info,
            'tags_safe': self.__safe_tags_info,
            'tags_unsafe': self.__unsafe_tags_info,
            'safes_attr_stat': self.__safes_attrs_statistic,
            'unsafes_attr_stat': self.__unsafes_attrs_statistic,
            'unknowns_attr_stat': self.__unknowns_attrs_statistic
        }
        for d in self.view['data']:
            if d in actions:
                self.view_data[d] = actions[d]()

    def __safe_tags_info(self):
        safe_tag_filter = {}
        if 'safe_tag' in self.view['filters']:
            ft = 'tag__tag__' + self.view['filters']['safe_tag']['type']
            fv = self.view['filters']['safe_tag']['value']
            safe_tag_filter = {ft: fv}

        tree_data = []
        for st in self.report.safe_tags.filter(**safe_tag_filter).order_by('tag__tag').select_related('tag'):
            tree_data.append({
                'id': st.tag_id,
                'parent': st.tag.parent_id,
                'name': st.tag.tag,
                'number': st.number,
                'href': reverse('reports:list_tag', args=[self.report.pk, 'safes', st.tag_id]),
                'description': st.tag.description
            })

        def get_children(parent, padding):
            children = []
            if parent['id'] is not None:
                parent['padding'] = padding * 13
                children.append(parent)
            for t in tree_data:
                if t['parent'] == parent['id']:
                    children.extend(get_children(t, padding + 1))
            return children

        return get_children({'id': None}, -1)

    def __unsafe_tags_info(self):
        unsafe_tag_filter = {}
        if 'unsafe_tag' in self.view['filters']:
            ft = 'tag__tag__' + self.view['filters']['unsafe_tag']['type']
            fv = self.view['filters']['unsafe_tag']['value']
            unsafe_tag_filter = {ft: fv}

        tree_data = []
        for ut in self.report.unsafe_tags.filter(**unsafe_tag_filter).order_by('tag__tag').select_related('tag'):
            tree_data.append({
                'id': ut.tag_id,
                'parent': ut.tag.parent_id,
                'name': ut.tag.tag,
                'number': ut.number,
                'href': reverse('reports:list_tag', args=[self.report.pk, 'unsafes', ut.tag_id]),
                'description': ut.tag.description
            })

        def get_children(parent, padding):
            children = []
            if parent['id'] is not None:
                parent['padding'] = padding * 13
                children.append(parent)
            for t in tree_data:
                if t['parent'] == parent['id']:
                    children.extend(get_children(t, padding + 1))
            return children

        return get_children({'id': None}, -1)

    def __resource_info(self):
        res_data = {}
        resource_filters = {}
        resource_table = self.report.resources_cache
        if self.report.parent is None and self.report.root.job.weight == JOB_WEIGHT[1][0]:
            resource_table = self.report.root.lightresource_set

        if 'resource_component' in self.view['filters']:
            ft = 'component__name__' + self.view['filters']['resource_component']['type']
            fv = self.view['filters']['resource_component']['value']
            resource_filters = {ft: fv}

        for cr in resource_table.filter(~Q(component=None) & Q(**resource_filters)).select_related('component'):
            if cr.component.name not in res_data:
                res_data[cr.component.name] = {}
            rd = get_resource_data(self.user.extended.data_format, self.user.extended.accuracy, cr)
            res_data[cr.component.name] = "%s %s %s" % (rd[0], rd[1], rd[2])

        resource_data = [{'component': x, 'val': res_data[x]} for x in sorted(res_data)]

        if 'resource_total' not in self.view['filters'] or self.view['filters']['resource_total']['type'] == 'show':
            if self.report.root.job.weight == JOB_WEIGHT[1][0] and self.report.parent is None:
                res_total = resource_table.filter(component=None, report=self.report.root).first()
            else:
                res_total = resource_table.filter(component=None).first()
            if res_total is not None:
                rd = get_resource_data(self.user.extended.data_format, self.user.extended.accuracy, res_total)
                resource_data.append({'component': _('Total'), 'val': "%s %s %s" % (rd[0], rd[1], rd[2])})
        return resource_data

    def __unknowns_info(self):

        unknowns_filters = {}
        components_filters = {}
        if 'unknown_component' in self.view['filters']:
            ft = 'component__name__' + self.view['filters']['unknown_component']['type']
            fv = self.view['filters']['unknown_component']['value']
            components_filters[ft] = fv
            unknowns_filters.update(components_filters)

        if 'unknown_problem' in self.view['filters']:
            ft = 'problem__name__' + self.view['filters']['unknown_problem']['type']
            fv = self.view['filters']['unknown_problem']['value']
            unknowns_filters[ft] = fv

        unknowns_data = {}
        for cmup in self.report.mark_unknowns_cache.filter(~Q(problem=None) & Q(**unknowns_filters))\
                .select_related('component', 'problem'):
            if cmup.component.name not in unknowns_data:
                unknowns_data[cmup.component.name] = {}
            problem_tuple = (
                cmup.component.name + '/' + cmup.problem.name,
                "%s_%s" % (cmup.component_id, cmup.problem_id)
            )
            if problem_tuple not in self.problems:
                self.problems.append(problem_tuple)
            unknowns_data[cmup.component.name][cmup.problem.name] = (
                cmup.number,
                reverse('reports:unknowns_problem', args=[self.report.pk, cmup.component_id, cmup.problem_id])
            )

        unknowns_sorted = {}
        for comp in unknowns_data:
            problems_sorted = []
            for probl in sorted(unknowns_data[comp]):
                problems_sorted.append({
                    'num': unknowns_data[comp][probl][0],
                    'problem': probl,
                    'href': unknowns_data[comp][probl][1],
                })
            unknowns_sorted[comp] = problems_sorted

        if 'unknowns_nomark' not in self.view['filters'] or self.view['filters']['unknowns_nomark']['type'] == 'show':
            for cmup in self.report.mark_unknowns_cache.filter(Q(problem=None) & Q(**components_filters)):
                if cmup.component.name not in unknowns_sorted:
                    unknowns_sorted[cmup.component.name] = []
                unknowns_sorted[cmup.component.name].append({
                    'problem': _('Without marks'),
                    'num': cmup.number,
                    'href': reverse('reports:unknowns_problem', args=[self.report.pk, cmup.component.pk, 0])
                })

        if 'unknowns_total' not in self.view['filters'] or self.view['filters']['unknowns_total']['type'] == 'show':
            for cmup in self.report.unknowns_cache.filter(**components_filters):
                if cmup.component.name not in unknowns_sorted:
                    unknowns_sorted[cmup.component.name] = []
                unknowns_sorted[cmup.component.name].append({
                    'problem': 'total',
                    'num': cmup.number,
                    'href': reverse('reports:unknowns', args=[self.report.pk, cmup.component.pk])
                })
            try:
                self.unknowns_total = {
                    'num': self.report.verdict.unknown,
                    'href': reverse('reports:list', args=[self.report.pk, 'unknowns'])
                }
            except ObjectDoesNotExist:
                self.unknowns_total = None

        unknowns_sorted_by_comp = []
        for comp in sorted(unknowns_sorted):
            unknowns_sorted_by_comp.append({
                'component': comp,
                'problems': unknowns_sorted[comp]
            })
        self.problems.sort()
        return unknowns_sorted_by_comp

    def __safes_info(self):
        safes_data = []
        try:
            verdicts = self.report.verdict
        except ObjectDoesNotExist:
            return safes_data

        for s in SAFES:
            safe_name = 'safe:' + s
            color = None
            val = '-'
            href = None
            if s == 'missed_bug':
                val = verdicts.safe_missed_bug
                color = COLORS['red']
                href = reverse('reports:list_verdict', args=[self.report.pk, 'safes', '2'])
            elif s == 'incorrect':
                val = verdicts.safe_incorrect_proof
                color = COLORS['orange']
                href = reverse('reports:list_verdict', args=[self.report.pk, 'safes', '1'])
            elif s == 'unknown':
                val = verdicts.safe_unknown
                color = COLORS['purple']
                href = reverse('reports:list_verdict', args=[self.report.pk, 'safes', '0'])
            elif s == 'inconclusive':
                val = verdicts.safe_inconclusive
                color = COLORS['red']
                href = reverse('reports:list_verdict', args=[self.report.pk, 'safes', '3'])
            elif s == 'unassociated':
                val = verdicts.safe_unassociated
                href = reverse('reports:list_verdict', args=[self.report.pk, 'safes', '4'])
            elif s == 'total':
                if verdicts.safe > 0:
                    self.safes_total = (verdicts.safe, reverse('reports:list', args=[self.report.pk, 'safes']))
                continue
            if val != 0:
                safes_data.append({
                    'title': TITLES[safe_name],
                    'value': val,
                    'color': color,
                    'href': href
                })
        return safes_data

    def __safes_attrs_statistic(self):
        attr_stat_data = {}
        others_data = {}
        attr_names = []
        for a_s in AttrStatistic.objects.filter(report=self.report, safes__gt=0).order_by('attr__value')\
                .select_related('name', 'attr'):
            if a_s.name.name not in attr_names:
                attr_names.append(a_s.name.name)
            if a_s.attr is None:
                others_data[a_s.name.name] = a_s.safes
            else:
                if a_s.name.name not in attr_stat_data:
                    attr_stat_data[a_s.name.name] = []
                href = reverse('reports:list_attr', args=[self.report.pk, 'safes', a_s.attr_id])
                attr_stat_data[a_s.name.name].append((a_s.attr.value, a_s.safes, href))
        attrs_statistic = []
        for a_name in sorted(attr_names):
            a_n_s = []
            if a_name in attr_stat_data:
                a_n_s = attr_stat_data[a_name]
            if a_name in others_data:
                a_n_s.append((_('Others'), others_data[a_name]))
            attrs_statistic.append((a_name, a_n_s))
        return attrs_statistic

    def __unsafes_info(self):
        try:
            verdicts = self.report.verdict
        except ObjectDoesNotExist:
            return None

        unsafes_data = []
        for s in UNSAFES:
            unsafe_name = 'unsafe:' + s
            color = None
            val = '-'
            href = None
            if s == 'bug':
                val = verdicts.unsafe_bug
                color = COLORS['red']
                href = reverse('reports:list_verdict', args=[self.report.pk, 'unsafes', '1'])
            elif s == 'target_bug':
                val = verdicts.unsafe_target_bug
                color = COLORS['red']
                href = reverse('reports:list_verdict', args=[self.report.pk, 'unsafes', '2'])
            elif s == 'false_positive':
                val = verdicts.unsafe_false_positive
                color = COLORS['orange']
                href = reverse('reports:list_verdict', args=[self.report.pk, 'unsafes', '3'])
            elif s == 'unknown':
                val = verdicts.unsafe_unknown
                color = COLORS['purple']
                href = reverse('reports:list_verdict', args=[self.report.pk, 'unsafes', '0'])
            elif s == 'inconclusive':
                val = verdicts.unsafe_inconclusive
                color = COLORS['red']
                href = reverse('reports:list_verdict', args=[self.report.pk, 'unsafes', '4'])
            elif s == 'unassociated':
                val = verdicts.unsafe_unassociated
                href = reverse('reports:list_verdict', args=[self.report.pk, 'unsafes', '5'])
            elif s == 'total':
                if verdicts.unsafe > 0:
                    self.unsafes_total = (verdicts.unsafe, reverse('reports:list', args=[self.report.pk, 'unsafes']))
                continue
            if val != 0:
                unsafes_data.append({
                    'title': TITLES[unsafe_name],
                    'value': val,
                    'color': color,
                    'href': href
                })
        return unsafes_data

    def __unsafes_attrs_statistic(self):
        attr_stat_data = {}
        others_data = {}
        attr_names = []
        for a_s in AttrStatistic.objects.filter(report=self.report, unsafes__gt=0).order_by('attr__value')\
                .select_related('name', 'attr'):
            if a_s.name.name not in attr_names:
                attr_names.append(a_s.name.name)
            if a_s.attr is None:
                others_data[a_s.name.name] = a_s.unsafes
            else:
                if a_s.name.name not in attr_stat_data:
                    attr_stat_data[a_s.name.name] = []
                href = reverse('reports:list_attr', args=[self.report.pk, 'unsafes', a_s.attr_id])
                attr_stat_data[a_s.name.name].append((a_s.attr.value, a_s.unsafes, href))
        attrs_statistic = []
        for a_name in sorted(attr_names):
            a_n_s = []
            if a_name in attr_stat_data:
                a_n_s = attr_stat_data[a_name]
            if a_name in others_data:
                a_n_s.append((_('Others'), others_data[a_name]))
            attrs_statistic.append((a_name, a_n_s))
        return attrs_statistic

    def __unknowns_attrs_statistic(self):
        attr_stat_data = {}
        others_data = {}
        attr_names = []
        for a_s in AttrStatistic.objects.filter(report=self.report, unknowns__gt=0).order_by('attr__value')\
                .select_related('name', 'attr'):
            if a_s.name.name not in attr_names:
                attr_names.append(a_s.name.name)
            if a_s.attr is None:
                others_data[a_s.name.name] = a_s.unknowns
            else:
                if a_s.name.name not in attr_stat_data:
                    attr_stat_data[a_s.name.name] = []
                href = reverse('reports:list_attr', args=[self.report.pk, 'unknowns', a_s.attr_id])
                attr_stat_data[a_s.name.name].append((a_s.attr.value, a_s.unknowns, href))
        attrs_statistic = []
        for a_name in sorted(attr_names):
            a_n_s = []
            if a_name in attr_stat_data:
                a_n_s = attr_stat_data[a_name]
            if a_name in others_data:
                a_n_s.append((_('Others'), others_data[a_name]))
            attrs_statistic.append((a_name, a_n_s))
        return attrs_statistic
