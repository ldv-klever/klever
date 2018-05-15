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

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q, Count, Case, When
from django.urls import reverse
from django.utils.translation import ugettext_lazy as _

from bridge.vars import SAFE_VERDICTS, UNSAFE_VERDICTS
from bridge.utils import logger, BridgeException

from reports.models import ReportComponentLeaf, ReportAttr, ComponentInstances

from jobs.utils import SAFES, UNSAFES, TITLES, get_resource_data


COLORS = {
    'red': '#C70646',
    'orange': '#D05A00',
    'purple': '#930BBD',
}


class ViewJobData:
    def __init__(self, user, report, view):
        self.user = user
        self.report = report
        self.view = view

        self.safes_total = None
        self.unsafes_total = None
        self.unknowns_total = None
        self.data = {}
        self.problems = []

        if self.report is None:
            return
        try:
            self.__get_view_data()
        except ObjectDoesNotExist:
            return
        if len(self.problems) > 0:
            self.problems.append((_('Without marks'), '0_0'))

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
                self.data[d] = actions[d]()

    def __safe_tags_info(self):
        safe_tag_filter = {}
        if 'safe_tag' in self.view:
            safe_tag_filter['tag__tag__%s' % self.view['safe_tag'][0]] = self.view['safe_tag'][1]

        tree_data = []
        for st in self.report.safe_tags.filter(**safe_tag_filter).order_by('tag__tag').select_related('tag'):
            tree_data.append({
                'id': st.tag_id,
                'parent': st.tag.parent_id,
                'name': st.tag.tag,
                'number': st.number,
                'href': '%s?tag=%s' % (reverse('reports:safes', args=[st.report_id]), st.tag_id),
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
        if 'unsafe_tag' in self.view:
            unsafe_tag_filter['tag__tag__%s' % self.view['unsafe_tag'][0]] = self.view['unsafe_tag'][1]

        tree_data = []
        for ut in self.report.unsafe_tags.filter(**unsafe_tag_filter).order_by('tag__tag').select_related('tag'):
            tree_data.append({
                'id': ut.tag_id,
                'parent': ut.tag.parent_id,
                'name': ut.tag.tag,
                'number': ut.number,
                'href': '%s?tag=%s' % (reverse('reports:unsafes', args=[ut.report_id]), ut.tag_id),
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
        instances = {}
        for c_name, total, in_progress in ComponentInstances.objects.filter(report=self.report)\
                .order_by('component__name').values_list('component__name', 'total', 'in_progress'):
            instances[c_name] = ' (%s/%s)' % (total - in_progress, total)

        res_data = {}
        resource_filters = {}

        if 'resource_component' in self.view:
            resource_filters['component__name__%s' % self.view['resource_component'][0]] = \
                self.view['resource_component'][1]

        for cr in self.report.resources_cache.filter(~Q(component=None) & Q(**resource_filters))\
                .select_related('component'):
            if cr.component.name not in res_data:
                res_data[cr.component.name] = {}
            rd = get_resource_data(self.user.extended.data_format, self.user.extended.accuracy, cr)
            res_data[cr.component.name] = "%s %s %s" % (rd[0], rd[1], rd[2])

        resource_data = [
            {'component': x, 'val': res_data[x], 'instances': instances.get(x, '')} for x in sorted(res_data)
        ]
        resource_data.extend(list(
            {'component': x, 'val': '-', 'instances': instances[x]} for x in sorted(instances) if x not in res_data
        ))

        if 'hidden' not in self.view or 'resource_total' not in self.view['hidden']:
            res_total = self.report.resources_cache.filter(component=None).first()
            if res_total is not None:
                rd = get_resource_data(self.user.extended.data_format, self.user.extended.accuracy, res_total)
                resource_data.append({
                    'component': _('Total'), 'val': "%s %s %s" % (rd[0], rd[1], rd[2]), 'instances': ''
                })
        return resource_data

    def __unknowns_info(self):

        unknowns_filters = {}
        components_filters = {}
        if 'unknown_component' in self.view:
            components_filters['component__name__' + self.view['unknown_component'][0]] = \
                self.view['unknown_component'][1]
            unknowns_filters.update(components_filters)

        if 'unknown_problem' in self.view:
            unknowns_filters['problem__name__' + self.view['unknown_problem'][0]] = self.view['unknown_problem'][1]

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
                cmup.number, '%s?component=%s&problem=%s' % (
                    reverse('reports:unknowns', args=[self.report.pk]), cmup.component_id, cmup.problem_id
                )
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

        if 'hidden' not in self.view or 'unknowns_nomark' not in self.view['hidden']:
            for cmup in self.report.mark_unknowns_cache.filter(Q(problem=None) & Q(**components_filters))\
                    .select_related('component'):
                if cmup.component.name not in unknowns_sorted:
                    unknowns_sorted[cmup.component.name] = []
                unknowns_sorted[cmup.component.name].append({
                    'problem': _('Without marks'),
                    'num': cmup.number,
                    'href': '%s?component=%s&problem=%s' % (
                        reverse('reports:unknowns', args=[self.report.pk]), cmup.component_id, 0
                    )
                })

        if 'hidden' not in self.view or 'unknowns_total' not in self.view['hidden']:
            for cmup in self.report.unknowns_cache.filter(**components_filters).select_related('component'):
                if cmup.component.name not in unknowns_sorted:
                    unknowns_sorted[cmup.component.name] = []
                unknowns_sorted[cmup.component.name].append({
                    'problem': 'total',
                    'num': cmup.number,
                    'href': '%s?component=%s' % (reverse('reports:unknowns', args=[self.report.pk]), cmup.component_id)
                })
            try:
                self.unknowns_total = {
                    'num': self.report.verdict.unknown,
                    'href': reverse('reports:unknowns', args=[self.report.pk])
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
        total_confirmed = 0
        for verdict, confirmed, total in self.report.leaves.exclude(safe=None).values('safe__verdict').annotate(
                total=Count('id'), confirmed=Count(Case(When(safe__has_confirmed=True, then=1)))
        ).values_list('safe__verdict', 'confirmed', 'total'):
            total_safes += total
            total_confirmed += confirmed

            href = [None, None]
            if total > 0:
                href[1] = '%s?verdict=%s' % (reverse('reports:safes', args=[self.report.pk]), verdict)
            if confirmed > 0:
                href[0] = '%s?verdict=%s&confirmed=1' % (reverse('reports:safes', args=[self.report.pk]), verdict)

            if 'hidden' in self.view and 'confirmed_marks' in self.view['hidden']:
                value = [total]
                del href[0]
            else:
                value = [confirmed, total]

            color = None
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
                if len(href) == 2:
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
        if total_safes > 0:
            self.safes_total = (total_safes, reverse('reports:safes', args=[self.report.pk]))
            self.safes_total = {
                'total': (total_safes, reverse('reports:safes', args=[self.report.pk])),
                'confirmed': (total_confirmed, '%s?confirmed=1' % reverse('reports:safes', args=[self.report.pk]))
            }
        return safes_data

    def __unsafes_info(self):
        unsafes_numbers = {}
        total_unsafes = 0
        total_confirmed = 0
        for verdict, confirmed, total in self.report.leaves.exclude(unsafe=None).values('unsafe__verdict').annotate(
                total=Count('id'), confirmed=Count(Case(When(unsafe__has_confirmed=True, then=1)))
        ).values_list('unsafe__verdict', 'confirmed', 'total'):
            total_unsafes += total
            total_confirmed += confirmed

            href = [None, None]
            if total > 0:
                href[1] = '%s?verdict=%s' % (reverse('reports:unsafes', args=[self.report.pk]), verdict)
            if confirmed > 0:
                href[0] = '%s?verdict=%s&confirmed=1' % (reverse('reports:unsafes', args=[self.report.pk]), verdict)

            if 'hidden' in self.view and 'confirmed_marks' in self.view['hidden']:
                value = [total]
                del href[0]
            else:
                value = [confirmed, total]

            color = None
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
                if len(href) == 2:
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
        if total_unsafes > 0:
            self.unsafes_total = {
                'total': (total_unsafes, reverse('reports:unsafes', args=[self.report.pk])),
                'confirmed': (total_confirmed, '%s?confirmed=1' % reverse('reports:unsafes', args=[self.report.pk]))
            }
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
        if 'attr_stat' not in self.view or len(self.view['attr_stat']) != 1 or len(self.view['attr_stat'][0]) == 0:
            return []
        attr_name = self.view['attr_stat'][0]

        if 'attr_stat_filter' in self.view:
            a_tmpl = self.view['attr_stat_filter'][1].lower()

        attr_stat_data = {}
        for a_id, ra_val, a_name in ReportAttr.objects.filter(report_id__in=list(reports))\
                .values_list('attr_id', 'attr__value', 'attr__name__name'):
            if a_name != attr_name:
                continue
            if 'attr_stat_filter' in self.view:
                a_low = ra_val.lower()
                if self.view['attr_stat_filter'][0] == 'iexact' and a_low != a_tmpl \
                        or self.view['attr_stat_filter'][0] == 'istartswith' and not a_low.startswith(a_tmpl) \
                        or self.view['attr_stat_filter'][0] == 'icontains' and not a_low.__contains__(a_tmpl):
                    continue

            if ra_val not in attr_stat_data:
                attr_stat_data[ra_val] = {
                    'num': 0, 'href': '%s?attr=%s' % (reverse('reports:%ss' % report_type, args=[self.report.pk]), a_id)
                }
            attr_stat_data[ra_val]['num'] += 1
        return list((val, attr_stat_data[val]['num'], attr_stat_data[val]['href']) for val in sorted(attr_stat_data))
