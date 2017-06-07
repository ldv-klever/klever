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
from django.db.models import Q, Count, Case, When
from django.utils.translation import ugettext_lazy as _

from bridge.vars import VIEWJOB_DEF_VIEW, JOB_WEIGHT, SAFE_VERDICTS, UNSAFE_VERDICTS
from bridge.utils import logger, BridgeException

from users.models import View
from reports.models import ReportComponentLeaf, ReportAttr

from jobs.utils import SAFES, UNSAFES, TITLES, get_resource_data


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
        self.attr_names = []
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
            user_view = View.objects.filter(Q(id=view_id, type='2') & (Q(shared=True) | Q(author=self.user))).first()
            if user_view:
                return json.loads(user_view.view), user_view.pk
        return VIEWJOB_DEF_VIEW, 'default'

    def __views(self):
        return View.objects.filter(Q(type='2') & (Q(author=self.user) | Q(shared=True))).order_by('name')

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
        safes_numbers = {}
        total_safes = 0
        for verdict, confirmed, total in self.report.leaves.exclude(safe=None).values('safe__verdict').annotate(
                total=Count('id'), confirmed=Count(Case(When(safe__has_confirmed=True, then=1)))
        ).values_list('safe__verdict', 'confirmed', 'total'):
            total_safes += total

            href = [None, None]
            if total > 0:
                href[1] = reverse('reports:list_verdict', args=[self.report.pk, 'safes', verdict])
            if confirmed > 0:
                href[0] = reverse('reports:list_verdict_confirmed', args=[self.report.pk, 'safes', verdict])

            color = None
            value = [confirmed, total]
            safe_name = 'safe:'
            if verdict == SAFE_VERDICTS[0][0]:
                safe_name += SAFES[2]
                color = COLORS['purple']
            elif verdict == SAFE_VERDICTS[1][0]:
                safe_name += SAFES[1]
                color = COLORS['orange']
            elif verdict == SAFE_VERDICTS[2][0]:
                safe_name += SAFES[0]
                color = COLORS['red']
            elif verdict == SAFE_VERDICTS[3][0]:
                safe_name += SAFES[3]
                color = COLORS['red']
            elif verdict == SAFE_VERDICTS[4][0]:
                safe_name += SAFES[4]
                value = [total]
                del href[0]

            if total > 0:
                safes_numbers[safe_name] = {
                    'title': TITLES[safe_name],
                    'value': value,
                    'color': color,
                    'href': href
                }

        safes_data = []
        for safe_name in SAFES:
            safe_name = 'safe:' + safe_name
            if safe_name in safes_numbers:
                safes_data.append(safes_numbers[safe_name])
        self.safes_total = (total_safes, reverse('reports:list', args=[self.report.pk, 'safes']))
        return safes_data

    def __unsafes_info(self):
        unsafes_numbers = {}
        total_unsafes = 0
        for verdict, confirmed, total in self.report.leaves.exclude(unsafe=None).values('unsafe__verdict').annotate(
                total=Count('id'), confirmed=Count(Case(When(unsafe__has_confirmed=True, then=1)))
        ).values_list('unsafe__verdict', 'confirmed', 'total'):
            total_unsafes += total

            href = [None, None]
            if total > 0:
                href[1] = reverse('reports:list_verdict', args=[self.report.pk, 'unsafes', verdict])
            if confirmed > 0:
                href[0] = reverse('reports:list_verdict_confirmed', args=[self.report.pk, 'unsafes', verdict])

            color = None
            value = [confirmed, total]
            unsafe_name = 'unsafe:'
            if verdict == UNSAFE_VERDICTS[0][0]:
                unsafe_name += UNSAFES[3]
                color = COLORS['purple']
            elif verdict == UNSAFE_VERDICTS[1][0]:
                unsafe_name += UNSAFES[0]
                color = COLORS['red']
            elif verdict == UNSAFE_VERDICTS[2][0]:
                unsafe_name += UNSAFES[1]
                color = COLORS['red']
            elif verdict == UNSAFE_VERDICTS[3][0]:
                unsafe_name += UNSAFES[2]
                color = COLORS['orange']
            elif verdict == UNSAFE_VERDICTS[4][0]:
                unsafe_name += UNSAFES[4]
                color = COLORS['red']
            elif verdict == UNSAFE_VERDICTS[5][0]:
                unsafe_name += UNSAFES[5]
                value = [total]
                del href[0]

            if total > 0:
                unsafes_numbers[unsafe_name] = {
                    'title': TITLES[unsafe_name],
                    'value': value,
                    'color': color,
                    'href': href
                }
        unsafes_data = []
        for unsafe_name in UNSAFES:
            unsafe_name = 'unsafe:' + unsafe_name
            if unsafe_name in unsafes_numbers:
                unsafes_data.append(unsafes_numbers[unsafe_name])
        self.unsafes_total = (total_unsafes, reverse('reports:list', args=[self.report.pk, 'unsafes']))
        return unsafes_data

    def __safes_attrs_statistic(self):
        try:
            return self.__attr_statistic('safe')
        except Exception as e:
            logger.exception(e)
            raise BridgeException()

    def __unsafes_attrs_statistic(self):
        try:
            return self.__attr_statistic('unsafe')
        except Exception as e:
            logger.exception(e)
            raise BridgeException()

    def __unknowns_attrs_statistic(self):
        try:
            return self.__attr_statistic('unknown')
        except Exception as e:
            logger.exception(e)
            raise BridgeException()

    def __attr_statistic(self, report_type):
        reports = set(rid for rid, in ReportComponentLeaf.objects.filter(report=self.report)
                      .exclude(**{report_type: None}).values_list('%s_id' % report_type))
        if 'stat_attr_name' in self.view['filters'] \
                and isinstance(self.view['filters']['stat_attr_name'].get('value'), str):
            attr_name = self.view['filters']['stat_attr_name'].get('value')
        else:
            return []

        if 'attr' in self.view['filters']:
            a_tmpl = self.view['filters']['attr']['value'].lower()

        attr_stat_data = {}
        attr_names = set()
        for a_id, ra_val, a_name in ReportAttr.objects.filter(report_id__in=list(reports))\
                .values_list('attr_id', 'attr__value', 'attr__name__name'):
            attr_names.add(a_name)
            if a_name != attr_name:
                continue
            if 'attr' in self.view['filters']:
                a_low = ra_val.lower()
                if self.view['filters']['attr']['type'] == 'iexact' and a_low != a_tmpl \
                        or self.view['filters']['attr']['type'] == 'istartswith' and not a_low.startswith(a_tmpl) \
                        or self.view['filters']['attr']['type'] == 'icontains' and not a_low.__contains__(a_tmpl):
                    continue

            if ra_val not in attr_stat_data:
                attr_stat_data[ra_val] = {
                    'num': 0, 'href': reverse('reports:list_attr', args=[self.report.id, report_type + 's', a_id])
                }
            attr_stat_data[ra_val]['num'] += 1
        self.attr_names = list(sorted(attr_names | set(self.attr_names)))
        return list((val, attr_stat_data[val]['num'], attr_stat_data[val]['href']) for val in sorted(attr_stat_data))
