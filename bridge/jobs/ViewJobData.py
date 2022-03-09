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

from urllib.parse import quote

from django.db.models import Count, Case, When, F
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from bridge.vars import DECISION_WEIGHT

from reports.models import ReportSafe, ReportUnsafe, ReportUnknown, ReportComponent, Report, DecisionCache
from marks.models import MarkUnknownReport, Tag
from caches.models import ReportSafeCache, ReportUnsafeCache

from users.utils import HumanizedValue
from reports.verdicts import safe_color, unsafe_color, SafeColumns, UnsafeColumns


def get_leaves_totals(**qs_kwargs):
    data = {}
    data.update(ReportSafe.objects.filter(**qs_kwargs).aggregate(safes=Count('id', distinct=True)))
    data.update(ReportUnsafe.objects.filter(**qs_kwargs).aggregate(unsafes=Count('id', distinct=True)))
    data.update(ReportUnknown.objects.filter(**qs_kwargs).aggregate(unknowns=Count('id', distinct=True)))
    return data


class SafesInfo:
    def __init__(self, view, base_url):
        self._base_url = base_url
        self._detailed = 'hidden' not in view or 'detailed_verdicts' not in view['hidden']

    def __collect_detailed_info(self, **kwargs):
        columns = SafeColumns(detailed=True)
        queryset = ReportSafe.objects.filter(**kwargs).values('cache__verdict').annotate(
            total=Count('id', distinct=True),
            manual=Count(Case(When(cache__marks_confirmed__gt=0, then=F('id')), default=None), distinct=True)
        ).order_by('cache__verdict').values_list('cache__verdict', 'manual', 'total')

        info_data = []
        for verdict, manual_num, total_num in queryset:
            column = columns.get_verdict_column(verdict)
            verdict_url = "{}?verdict={}".format(self._base_url, verdict)
            verdict_data = {
                'title': columns.titles.get(column, column),
                'url': verdict_url,
                'color': safe_color(verdict),
                'value': total_num
            }

            is_detailed = columns.is_detailed(verdict)
            if is_detailed:
                manual_col = columns.get_verdict_column(verdict, manual=True)
                verdict_data['manual'] = {
                    'title': columns.titles.get(manual_col, manual_col),
                    'url': "{}&manual=1".format(verdict_url), 'value': manual_num
                }
                automatic_col = columns.get_verdict_column(verdict, manual=False)
                verdict_data['automatic'] = {
                    'title': columns.titles.get(automatic_col, automatic_col),
                    'url': "{}&manual=0".format(verdict_url),
                    'value': total_num - manual_num
                }
            info_data.append(verdict_data)
        return info_data

    def __collect_simple_info(self, **kwargs):
        columns = SafeColumns()
        queryset = ReportSafe.objects.filter(**kwargs).values('cache__verdict').annotate(
            total=Count('id', distinct=True)
        ).order_by('cache__verdict').values_list('cache__verdict', 'total')

        info_data = []
        for verdict, total_num in queryset:
            column = columns.get_verdict_column(verdict)
            info_data.append({
                'title': columns.titles.get(column, column),
                'url': "{}?verdict={}".format(self._base_url, verdict),
                'color': safe_color(verdict),
                'value': total_num
            })
        return info_data

    def collect_info(self, **kwargs):
        if self._detailed:
            return self.__collect_detailed_info(**kwargs)
        return self.__collect_simple_info(**kwargs)


class UnsafesInfo:
    def __init__(self, view, base_url):
        self._base_url = base_url
        self._detailed = 'hidden' not in view or 'detailed_verdicts' not in view['hidden']

    def __collect_detailed_info(self, **kwargs):
        columns = UnsafeColumns(detailed=True)
        queryset = ReportUnsafe.objects.filter(**kwargs).values('cache__verdict').annotate(
            total=Count('id', distinct=True),
            manual=Count(Case(When(cache__marks_confirmed__gt=0, then=F('id')), default=None), distinct=True)
        ).order_by('cache__verdict').values_list('cache__verdict', 'manual', 'total')

        info_data = []
        for verdict, manual_num, total_num in queryset:
            column = columns.get_verdict_column(verdict)
            verdict_url = "{}?verdict={}".format(self._base_url, verdict)
            verdict_data = {
                'title': columns.titles.get(column, column),
                'url': verdict_url,
                'color': unsafe_color(verdict),
                'value': total_num
            }

            is_detailed = columns.is_detailed(verdict)
            if is_detailed:
                manual_col = columns.get_verdict_column(verdict, manual=True)
                verdict_data['manual'] = {
                    'title': columns.titles.get(manual_col, manual_col),
                    'url': "{}&manual=1".format(verdict_url), 'value': manual_num
                }
                automatic_col = columns.get_verdict_column(verdict, manual=False)
                verdict_data['automatic'] = {
                    'title': columns.titles.get(automatic_col, automatic_col),
                    'url': "{}&manual=0".format(verdict_url),
                    'value': total_num - manual_num
                }
            info_data.append(verdict_data)
        return info_data

    def __collect_simple_info(self, **kwargs):
        columns = UnsafeColumns()
        queryset = ReportUnsafe.objects.filter(**kwargs).values('cache__verdict').annotate(
            total=Count('id', distinct=True)
        ).order_by('cache__verdict').values_list('cache__verdict', 'total')

        info_data = []
        for verdict, total_num in queryset:
            column = columns.get_verdict_column(verdict)
            info_data.append({
                'title': columns.titles.get(column, column),
                'url': "{}?verdict={}".format(self._base_url, verdict),
                'color': unsafe_color(verdict),
                'value': total_num
            })
        return info_data

    def collect_info(self, **kwargs):
        if self._detailed:
            return self.__collect_detailed_info(**kwargs)
        return self.__collect_simple_info(**kwargs)


class UnknownsInfo:
    def __init__(self, view, base_url, queryset):
        self._view = view

        # reverse('reports:unknowns', args=[self.report.id])
        self._base_url = base_url

        # ReportUnknown.objects.filter(decision=self.decision)
        # ReportUnknown.objects.filter(leaves__report=self.report)
        self._queryset = queryset

        self.info = self.__unknowns_info()

    @cached_property
    def _nomark_hidden(self):
        return 'hidden' in self._view and 'unknowns_nomark' in self._view['hidden']

    @cached_property
    def _total_hidden(self):
        return 'hidden' in self._view and 'unknowns_total' in self._view['hidden']

    @cached_property
    def _component_filter(self):
        if 'unknown_component' not in self._view:
            return {}
        return {'component__{}'.format(self._view['unknown_component'][0]): self._view['unknown_component'][1]}

    def __filter_problem(self, problem):
        if 'unknown_problem' not in self._view:
            return True
        if self._view['unknown_problem'][0] == 'iexact':
            return self._view['unknown_problem'][1].lower() == problem.lower()
        if self._view['unknown_problem'][0] == 'istartswith':
            return problem.lower().startswith(self._view['unknown_problem'][1].lower())
        if self._view['unknown_problem'][0] == 'icontains':
            return self._view['unknown_problem'][1].lower() in problem.lower()
        return True

    def __unknowns_info(self):
        unknowns_qs = self._queryset.filter(**self._component_filter)\
            .select_related('cache').only('component', 'cache__marks_total', 'cache__problems')

        # Collect unknowns data
        cache_data = {}
        unmarked = {}
        totals = {}
        skipped_problems = set()
        for unknown in unknowns_qs:
            cache_data.setdefault(unknown.component, {})
            if not self._total_hidden:
                totals.setdefault(unknown.component, 0)
                totals[unknown.component] += 1
            if not self._nomark_hidden and unknown.cache.marks_total == 0:
                unmarked.setdefault(unknown.component, 0)
                unmarked[unknown.component] += 1
            for problem in sorted(unknown.cache.problems):
                if problem in skipped_problems:
                    continue
                if not self.__filter_problem(problem):
                    skipped_problems.add(problem)
                    continue
                cache_data[unknown.component].setdefault(problem, 0)
                cache_data[unknown.component][problem] += 1

        # Sort unknowns data for html
        unknowns_data = []
        for c_name in sorted(cache_data):
            component_data = {'component': c_name, 'problems': []}
            has_data = False
            for problem in sorted(cache_data[c_name]):
                component_data['problems'].append({
                    'problem': problem, 'num': cache_data[c_name][problem],
                    'href': '{0}?component={1}&problem={2}'.format(self._base_url, quote(c_name), quote(problem))
                })
                has_data = True
            if not self._nomark_hidden and c_name in unmarked:
                component_data['problems'].append({
                    'problem': _('Without marks'), 'num': unmarked[c_name],
                    'href': '{0}?component={1}&problem=null'.format(self._base_url, quote(c_name))
                })
                has_data = True
            if not self._total_hidden and c_name in totals:
                component_data['total'] = {
                    'num': totals[c_name], 'href': '{0}?component={1}'.format(self._base_url, quote(c_name))
                }
                has_data = True
            if has_data:
                unknowns_data.append(component_data)
        return unknowns_data


class TagsInfo:
    def __init__(self, base_url, cache_qs, tags_filter):
        self._tags_filter = tags_filter

        # Values:
        # reverse('reports:unsafes', args=[self.report.id])
        # reverse('reports:safes', args=[self.report.id])
        self._base_url = base_url

        # Values:
        # ReportSafeCache.objects.filter(report__decision=self.decision)
        # ReportSafeCache.objects.filter(report__leaves__report=self.report)
        # ReportUnsafeCache.objects.filter(report__decision=self.decision)
        # ReportUnsafeCache.objects.filter(report__leaves__report=self.report)
        self._cache_qs = cache_qs

        self.info = self.__get_tags_info()

    @cached_property
    def _db_tags(self):
        """
        All DB tags
        :return: dict
        """
        qs_filter = {}
        if self._tags_filter:
            qs_filter['name__{}'.format(self._tags_filter[0])] = self._tags_filter[1]
        db_tags_qs = Tag.objects.filter(**qs_filter).order_by('level').only('id', 'parent_id', 'name', 'description')
        db_tags = {}
        for tag in db_tags_qs:
            if tag.parent_id and tag.parent_id not in db_tags:
                continue
            db_tags[tag.id] = {
                'parent': tag.parent_id,
                'name': tag.name,
                'shortname': tag.shortname,
                'description': tag.description
            }
        return db_tags

    @cached_property
    def _db_tags_names(self):
        return dict((self._db_tags[t_id]['name'], t_id) for t_id in self._db_tags)

    def __get_tags_info(self):
        tags_data = {}
        for cache_obj in self._cache_qs.only('tags'):
            for tag in cache_obj.tags:
                if tag not in self._db_tags_names:
                    continue
                tag_id = self._db_tags_names[tag]
                parent_id = tag_id
                while parent_id:
                    if parent_id in tags_data:
                        break
                    tags_data[parent_id] = {
                        'parent': self._db_tags[parent_id]['parent'],
                        'name': self._db_tags[parent_id]['shortname'],
                        'description': self._db_tags[parent_id]['description'],
                        'value': 0,
                        'url': '{}?tag={}'.format(self._base_url, quote(self._db_tags[parent_id]['name']))
                    }
                    parent_id = self._db_tags[parent_id]['parent']
                tags_data[tag_id]['value'] += 1
        return tags_data


class ResourcesInfo:
    def __init__(self, user, view, data):
        self.user = user
        self.view = view
        self._data = data
        self.info = self.__get_info()

    def __get_info(self):
        resource_data = []

        total_resources = {'wall_time': 0, 'cpu_time': 0, 'memory': 0}
        for component in sorted(self._data):
            component_data = {
                'component': component,
                'wall_time': '-',
                'cpu_time': '-',
                'memory': '-',
                'instances': '{}/{}'.format(self._data[component]['finished'], self._data[component]['total'])
            }
            if self._data[component]['finished'] and component in self._data:
                component_data['wall_time'] = HumanizedValue(
                    self._data[component]['wall_time'], user=self.user
                ).timedelta
                component_data['cpu_time'] = HumanizedValue(
                    self._data[component]['cpu_time'], user=self.user
                ).timedelta
                component_data['memory'] = HumanizedValue(
                    self._data[component]['memory'], user=self.user
                ).memory

                total_resources['wall_time'] += self._data[component]['wall_time']
                total_resources['cpu_time'] += self._data[component]['cpu_time']
                total_resources['memory'] = max(total_resources['memory'], self._data[component]['memory'])
            resource_data.append(component_data)

        if 'hidden' not in self.view or 'resource_total' not in self.view['hidden']:
            if total_resources['wall_time'] or total_resources['cpu_time'] or total_resources['memory']:
                resource_data.append({
                    'component': 'total', 'instances': '-',
                    'wall_time': HumanizedValue(total_resources['wall_time'], user=self.user).timedelta,
                    'cpu_time': HumanizedValue(total_resources['cpu_time'], user=self.user).timedelta,
                    'memory': HumanizedValue(total_resources['memory'], user=self.user).memory
                })
        return resource_data


class AttrStatisticsInfo:
    def __init__(self, view, **qs_kwargs):
        self.attr_name = self.__get_attr_name(view)
        self._qs_kwargs = qs_kwargs
        self._filtered_attrs = {}
        self._attr_filter = self.__get_qs_filters(view)
        self.info = self.__get_info()

    def __get_attr_name(self, view):
        if view['attr_stat'] and len(view['attr_stat']) == 1:
            return view['attr_stat'][0]
        return None

    def __get_qs_filters(self, view):
        if view['attr_stat_filter'] and len(view['attr_stat_filter']) == 2:
            return view['attr_stat_filter'][0], view['attr_stat_filter'][1].lower()
        return None

    def __filter_attr(self, value):
        if self._attr_filter is None:
            return True
        if value in self._filtered_attrs:
            return self._filtered_attrs[value]
        accepted = False
        if self._attr_filter[0] == 'iexact':
            accepted = self._attr_filter[1] == value.lower()
        elif self._attr_filter[0] == 'istartswith':
            accepted = value.lower().startswith(self._attr_filter[1])
        elif self._attr_filter[0] == 'icontains':
            accepted = self._attr_filter[1] in value.lower()
        self._filtered_attrs[value] = accepted
        return accepted

    def __get_info(self):
        if not self.attr_name:
            return None
        attr_name_q = quote(self.attr_name)

        data = {}
        for model, column in [(ReportSafe, 'safes'), (ReportUnsafe, 'unsafes'), (ReportUnknown, 'unknowns')]:
            queryset = model.objects.filter(
                cache__attrs__has_key=self.attr_name, **self._qs_kwargs
            ).values_list('cache__attrs', flat=True)
            for report_attrs in queryset:
                attr_value = report_attrs[self.attr_name]
                if not self.__filter_attr(attr_value):
                    continue
                if attr_value not in data:
                    data[attr_value] = {
                        'attr_value': attr_value, 'safes': 0, 'unsafes': 0, 'unknowns': 0,
                        'url_params': '?attr_name={}&attr_value={}'.format(attr_name_q, quote(attr_value))
                    }
                data[attr_value][column] += 1
        return list(data[a_val] for a_val in sorted(data))


class ViewJobData:
    def __init__(self, user, view, decision):
        self.user = user
        self.view = view
        self.decision = decision
        self.report = ReportComponent.objects.filter(decision=decision, parent=None)\
            .only('id', 'identifier', 'component').first()

    @cached_property
    def core_link(self):
        if self.report and self.decision.weight == DECISION_WEIGHT[0][0]:
            return reverse('reports:component', args=[self.decision.identifier, self.report.identifier])
        return None

    @cached_property
    def data(self):
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
            'attr_stat': self.__attr_statistic
        }
        for d in self.view['data']:
            if d in actions:
                data[d] = actions[d]()
        return data

    @cached_property
    def totals(self):
        return get_leaves_totals(decision=self.decision)

    @cached_property
    def problems(self):
        queryset = MarkUnknownReport.objects\
            .filter(report__decision=self.decision, associated=True)\
            .values_list('report__component', 'problem').distinct().order_by('report__component', 'problem')

        cnt = 0
        problems = []
        for c_name, p_name in queryset:
            problems.append({'id': cnt, 'component': c_name, 'problem': p_name})
            cnt += 1
        return problems

    @property
    def has_unmarked(self):
        return ReportUnknown.objects.filter(cache__marks_total=0, decision=self.decision).count() > 0

    def __safe_tags_info(self):
        if not self.report:
            return []
        return TagsInfo(
            reverse('reports:safes', args=[self.report.id]),
            ReportSafeCache.objects.filter(report__decision=self.decision),
            self.view['safe_tag']
        ).info

    def __unsafe_tags_info(self):
        if not self.report:
            return []
        return TagsInfo(
            reverse('reports:unsafes', args=[self.report.id]),
            ReportUnsafeCache.objects.filter(report__decision=self.decision),
            self.view['unsafe_tag']
        ).info

    def __resource_info(self):
        cache_data = {}
        for cache_obj in DecisionCache.objects.filter(decision=self.decision):
            cache_data[cache_obj.component] = {
                'cpu_time': cache_obj.cpu_time,
                'wall_time': cache_obj.wall_time,
                'memory': cache_obj.memory,
                'finished': cache_obj.finished,
                'total': cache_obj.total
            }
        return ResourcesInfo(self.user, self.view, cache_data).info

    def __unknowns_info(self):
        if not self.report:
            return []
        return UnknownsInfo(
            self.view, reverse('reports:unknowns', args=[self.report.id]),
            ReportUnknown.objects.filter(decision=self.decision)
        ).info

    def __safes_info(self):
        if not self.report:
            return []
        verdicts_collector = SafesInfo(self.view, reverse('reports:safes', args=[self.report.pk]))
        return verdicts_collector.collect_info(decision=self.decision)

    def __unsafes_info(self):
        if not self.report:
            return []
        verdicts_collector = UnsafesInfo(self.view, reverse('reports:unsafes', args=[self.report.pk]))
        return verdicts_collector.collect_info(decision=self.decision)

    def __attr_statistic(self):
        if not self.report:
            return None
        return AttrStatisticsInfo(self.view, decision=self.decision).info


class ViewReportData:
    def __init__(self, user, view, report):
        self.user = user
        self.report = report
        self.view = view
        self.totals = get_leaves_totals(leaves__report=report)
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
            'attr_stat': self.__attr_statistic
        }
        for d in self.view['data']:
            if d in actions:
                data[d] = actions[d]()
        return data

    def __safe_tags_info(self):
        return TagsInfo(
            reverse('reports:safes', args=[self.report.id]),
            ReportSafeCache.objects.filter(report__leaves__report=self.report),
            self.view['safe_tag']
        ).info

    def __unsafe_tags_info(self):
        return TagsInfo(
            reverse('reports:unsafes', args=[self.report.id]),
            ReportUnsafeCache.objects.filter(report__leaves__report=self.report),
            self.view['unsafe_tag']
        ).info

    def __resource_info(self):
        qs_filters = {}
        if 'resource_component' in self.view:
            filter_key = 'reportcomponent__component__{}'.format(self.view['resource_component'][0])
            qs_filters[filter_key] = self.view['resource_component'][1]
        report_base = Report.objects.get(id=self.report.id)
        reports_qs = report_base.get_descendants(include_self=True)\
            .exclude(reportcomponent=None).filter(**qs_filters).select_related('reportcomponent')\
            .annotate(component=F('reportcomponent__component'), finish_date=F('reportcomponent__finish_date'))\
            .only('reportcomponent__component', 'cpu_time', 'wall_time', 'memory', 'reportcomponent__finish_date')

        cache_data = {}
        for report in reports_qs:
            component = report.component
            if report.component not in cache_data:
                cache_data[component] = {'cpu_time': 0, 'wall_time': 0, 'memory': 0, 'finished': 0, 'total': 0}
            cache_data[component]['total'] += 1
            if report.reportcomponent.finish_date:
                cache_data[component]['finished'] += 1
            if report.cpu_time:
                cache_data[component]['cpu_time'] += report.cpu_time
            if report.wall_time:
                cache_data[component]['wall_time'] += report.wall_time
            if report.memory:
                cache_data[component]['memory'] = max(cache_data[component]['memory'], report.memory)

        return ResourcesInfo(self.user, self.view, cache_data).info

    def __unknowns_info(self):
        return UnknownsInfo(
            self.view, reverse('reports:unknowns', args=[self.report.id]),
            ReportUnknown.objects.filter(leaves__report=self.report)
        ).info

    def __safes_info(self):
        verdicts_collector = SafesInfo(self.view, reverse('reports:safes', args=[self.report.pk]))
        return verdicts_collector.collect_info(leaves__report=self.report)

    def __unsafes_info(self):
        verdicts_collector = UnsafesInfo(self.view, reverse('reports:unsafes', args=[self.report.pk]))
        return verdicts_collector.collect_info(leaves__report=self.report)

    def __attr_statistic(self):
        return AttrStatisticsInfo(self.view, leaves__report=self.report).info
