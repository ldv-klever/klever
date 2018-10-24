#
# Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
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

from django.db.models import Q, Count, Case, When, BooleanField, Value
from django.urls import reverse
from django.utils.translation import ugettext_lazy as _

from bridge.vars import SAFE_VERDICTS, UNSAFE_VERDICTS, ASSOCIATION_TYPE
from bridge.utils import logger, BridgeException

from reports.models import ReportAttr, ComponentInstances, ReportUnknown
from marks.models import MarkUnknownReport

from jobs.utils import SAFES, UNSAFES, TITLES, get_resource_data


COLORS = {
    'red': '#C70646',
    'orange': '#D05A00',
    'purple': '#930BBD',
}


class ViewJobData:
    def __init__(self, user, view, report):
        self.user = user
        self.report = report
        self.view = view

        if self.report is None:
            return

        self.totals = self.__get_totals()
        self.problems = self.__get_problems()
        self.data = self.__get_view_data()

    def __get_view_data(self):
        if 'data' not in self.view:
            return {}
        data = {}
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
                data[d] = actions[d]()
        return data

    def __get_totals(self):
        return self.report.leaves.aggregate(
            safes=Count(Case(When(~Q(safe=None), then=1))),
            safes_confirmed=Count(Case(When(safe__has_confirmed=True, then=1))),
            unsafes=Count(Case(When(~Q(unsafe=None), then=1))),
            unsafes_confirmed=Count(Case(When(unsafe__has_confirmed=True, then=1))),
            unknowns=Count(Case(When(~Q(unknown=None), then=1)))
        )

    def __get_problems(self):
        queryset = MarkUnknownReport.objects.filter(Q(report__root=self.report.root) & ~Q(type=ASSOCIATION_TYPE[2][0]))\
            .values_list('problem_id', 'problem__name', 'report__component_id', 'report__component__name')\
            .distinct().order_by('report__component__name', 'problem__name')

        problems = []
        for p_id, p_name, c_id, c_name in queryset:
            problems.append(('{0}/{1}'.format(c_name, p_name), '{0}_{1}'.format(c_id, p_id)))
        if len(problems) > 0:
            problems.append((_('Without marks'), '0_0'))
        return problems

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
        url = reverse('reports:unknowns', args=[self.report.pk])
        no_mark_hidden = 'hidden' in self.view and 'unknowns_nomark' in self.view['hidden']
        total_hidden = 'hidden' in self.view and 'unknowns_total' in self.view['hidden']

        # ==========================
        # Get querysets for unknowns
        queryset_fields = ['component_id', 'component__name', 'markreport_set__problem_id',
                           'markreport_set__problem__name', 'number', 'unconfirmed']
        order_by_fields = ['component__name', 'markreport_set__problem__name']
        queryset = ReportUnknown.objects.filter(leaves__report=self.report)
        if 'unknown_component' in self.view:
            queryset = queryset.filter(**{
                'component__name__' + self.view['unknown_component'][0]: self.view['unknown_component'][1]
            })
        queryset_total = queryset.values('component_id').annotate(number=Count('id'))\
            .values_list('component_id', 'component__name', 'number')

        if no_mark_hidden:
            queryset = queryset.filter(markreport_set__type__in=[ASSOCIATION_TYPE[0][0], ASSOCIATION_TYPE[1][0]])
            unconfirmed = Value(False, output_field=BooleanField())
        else:
            unconfirmed = Case(When(markreport_set__type=ASSOCIATION_TYPE[2][0], then=True),
                               default=False, output_field=BooleanField())

        queryset = queryset.values('component_id', 'markreport_set__problem_id')\
            .annotate(number=Count('id', distinct=True), unconfirmed=unconfirmed)

        if 'unknown_problem' in self.view:
            queryset = queryset.filter(**{
                'markreport_set__problem__name__' + self.view['unknown_problem'][0]: self.view['unknown_problem'][1]
            })
        queryset = queryset.values_list(*queryset_fields).order_by(*order_by_fields)
        # ==========================

        unknowns_data = {}
        unmarked = {}
        # Get marked unknowns
        for c_id, c_name, p_id, p_name, number, unconfirmed in queryset:
            if p_id is None or unconfirmed:
                if c_name not in unmarked:
                    unmarked[c_name] = [0, c_id]
                unmarked[c_name][0] += number
            else:
                if c_name not in unknowns_data:
                    unknowns_data[c_name] = []
                unknowns_data[c_name].append({'num': number, 'problem': p_name,
                                              'href': '{0}?component={1}&problem={2}'.format(url, c_id, p_id)})

        # Get unmarked unknowns
        for c_name in unmarked:
            if c_name not in unknowns_data:
                unknowns_data[c_name] = []
            unknowns_data[c_name].append({
                'num': unmarked[c_name][0], 'problem': _('Without marks'),
                'href': '{0}?component={1}&problem=0'.format(url, unmarked[c_name][1])
            })

        if not total_hidden:
            # Get total unknowns for each component
            for c_id, c_name, number in queryset_total:
                if c_name not in unknowns_data:
                    unknowns_data[c_name] = []
                unknowns_data[c_name].append({
                    'num': number, 'problem': 'total', 'href': '{0}?component={1}'.format(url, c_id)
                })
        return list({'component': c_name, 'problems': unknowns_data[c_name]} for c_name in sorted(unknowns_data))

    def __safes_info(self):
        safes_numbers = {}
        for verdict, confirmed, total in self.report.leaves.exclude(safe=None).values('safe__verdict').annotate(
                total=Count('id'), confirmed=Count(Case(When(safe__has_confirmed=True, then=1)))
        ).values_list('safe__verdict', 'confirmed', 'total'):
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
        return safes_data

    def __unsafes_info(self):
        unsafes_numbers = {}
        for verdict, confirmed, total in self.report.leaves.exclude(unsafe=None).values('unsafe__verdict').annotate(
                total=Count('id'), confirmed=Count(Case(When(unsafe__has_confirmed=True, then=1)))
        ).values_list('unsafe__verdict', 'confirmed', 'total'):
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
        if report_type not in {'safe', 'unsafe', 'unknown'}:
            return []
        leaf_column = '"cache_report_component_leaf"."{0}_id"'.format(report_type)
        queryset = ReportAttr.objects.raw("""
SELECT "report_attrs"."id", "report_attrs"."attr_id" as "a_id",
       "attr"."value" as "a_val", "attr_name"."name" as "a_name"
  FROM "report_attrs"
  INNER JOIN "cache_report_component_leaf" ON ("report_attrs"."report_id" = {0})
  INNER JOIN "attr" ON ("report_attrs"."attr_id" = "attr"."id")
  INNER JOIN "attr_name" ON ("attr"."name_id" = "attr_name"."id")
  WHERE "cache_report_component_leaf"."report_id" = {1};""".format(leaf_column, self.report.id))

        if 'attr_stat' not in self.view or len(self.view['attr_stat']) != 1 or len(self.view['attr_stat'][0]) == 0:
            return []
        attr_name = self.view['attr_stat'][0]

        a_tmpl = None
        if 'attr_stat_filter' in self.view:
            a_tmpl = self.view['attr_stat_filter'][1].lower()

        attr_stat_data = {}
        for ra in queryset:
            if ra.a_name != attr_name:
                continue
            if 'attr_stat_filter' in self.view:
                a_low = ra.a_val.lower()
                if self.view['attr_stat_filter'][0] == 'iexact' and a_low != a_tmpl \
                        or self.view['attr_stat_filter'][0] == 'istartswith' and not a_low.startswith(a_tmpl) \
                        or self.view['attr_stat_filter'][0] == 'icontains' and not a_low.__contains__(a_tmpl):
                    continue

            if ra.a_val not in attr_stat_data:
                attr_stat_data[ra.a_val] = {'num': 0, 'href': '{0}?attr={1}'.format(
                    reverse('reports:%ss' % report_type, args=[self.report.pk]), ra.a_id)}
            attr_stat_data[ra.a_val]['num'] += 1
        return list((val, attr_stat_data[val]['num'], attr_stat_data[val]['href']) for val in sorted(attr_stat_data))
