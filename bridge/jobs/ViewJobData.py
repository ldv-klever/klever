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

from urllib.parse import quote

from django.db.models import Count, Case, When, F
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _

from bridge.vars import ASSOCIATION_TYPE, SafeVerdicts, UnsafeVerdicts, JOB_WEIGHT
from bridge.utils import logger, BridgeException

from reports.models import ReportSafe, ReportUnsafe, ReportUnknown, ReportRoot, ReportComponent, Report
from marks.models import MarkUnknownReport, SafeTag, UnsafeTag

from users.utils import HumanizedValue
from jobs.utils import TITLES
from caches.models import ReportSafeCache, ReportUnsafeCache


class ViewJobData:
    def __init__(self, user, view, job):
        self.user = user
        self.view = view
        self.job = job
        self.root = ReportRoot.objects.filter(job=self.job).first()
        self.report = ReportComponent.objects.filter(root__job=self.job, parent=None)\
            .only('id', 'component').first()

    @cached_property
    def core_link(self):
        if self.report and self.job.weight == JOB_WEIGHT[0][0]:
            return reverse('reports:component', args=[self.report.id])
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
            'safes_attr_stat': self.__safes_attrs_statistic,
            'unsafes_attr_stat': self.__unsafes_attrs_statistic,
            'unknowns_attr_stat': self.__unknowns_attrs_statistic
        }
        for d in self.view['data']:
            if d in actions:
                data[d] = actions[d]()
        return data

    @cached_property
    def totals(self):
        data = {}
        if not self.root:
            return data
        data.update(ReportSafe.objects.filter(root=self.root).aggregate(
            safes=Count('id'),
            safes_confirmed=Count(Case(When(cache__marks_confirmed__gt=0, then=1))),
        ))
        data.update(ReportUnsafe.objects.filter(root=self.root).aggregate(
            unsafes=Count('id'),
            unsafes_confirmed=Count(Case(When(cache__marks_confirmed__gt=0, then=1))),
        ))
        data.update(ReportUnknown.objects.filter(root=self.root).aggregate(
            unknowns=Count('id'),
            unknowns_confirmed=Count(Case(When(cache__marks_confirmed__gt=0, then=1))),
        ))
        return data

    @cached_property
    def problems(self):
        if not self.root:
            return []
        queryset = MarkUnknownReport.objects\
            .filter(report__root=self.root).exclude(type=ASSOCIATION_TYPE[2][0])\
            .values_list('report__component', 'problem').distinct().order_by('report__component', 'problem')

        cnt = 0
        problems = []
        for c_name, p_name in queryset:
            problems.append({'id': cnt, 'component': c_name, 'problem': p_name})
            cnt += 1
        return problems

    def __safe_tags_info(self):
        if not self.report:
            return []
        # Get all db tags
        tags_qs = SafeTag.objects.all()
        if 'safe_tag' in self.view:
            tags_qs = tags_qs.filter(**{'name__{}'.format(self.view['safe_tag'][0]): self.view['safe_tag'][1]})
        db_tags = dict(tags_qs.values_list('name', 'description'))

        # Calculate tags numbers
        safes_url = reverse('reports:safes', args=[self.report.id])
        tags_data = {}
        for cache_obj in ReportSafeCache.objects.filter(report__root=self.root):
            for tag in cache_obj.tags:
                if tag not in db_tags:
                    continue
                if tag not in tags_data:
                    tags_data[tag] = {
                        'name': tag, 'value': 0, 'description': db_tags[tag],
                        'url': '{}?tag={}'.format(safes_url, quote(tag))
                    }
                tags_data[tag]['value'] += 1
        return list(tags_data[tag] for tag in sorted(tags_data))

    def __unsafe_tags_info(self):
        if not self.report:
            return []
        # Get all db tags
        tags_qs = UnsafeTag.objects.all()
        if 'unsafe_tag' in self.view:
            tags_qs = tags_qs.filter(**{'name__{}'.format(self.view['unsafe_tag'][0]): self.view['unsafe_tag'][1]})
        db_tags = dict(tags_qs.values_list('name', 'description'))

        # Calculate tags numbers
        unsafes_url = reverse('reports:unsafes', args=[self.report.id])
        tags_data = {}
        for cache_obj in ReportUnsafeCache.objects.filter(report__root=self.root):
            for tag in cache_obj.tags:
                if tag not in db_tags:
                    continue
                if tag not in tags_data:
                    tags_data[tag] = {
                        'name': tag, 'value': 0, 'description': db_tags[tag],
                        'url': '{}?tag={}'.format(unsafes_url, quote(tag))
                    }
                tags_data[tag]['value'] += 1
        return list(tags_data[tag] for tag in sorted(tags_data))

    def __resource_info(self):
        if not self.root:
            return []
        qs_filters = {}
        if 'resource_component' in self.view:
            qs_filters['component__{}'.format(self.view['resource_component'][0])] = self.view['resource_component'][1]
        report_qs = ReportComponent.objects.filter(root=self.root)\
            .filter(**qs_filters).only('component', 'cpu_time', 'wall_time', 'memory', 'finish_date')

        instances = {}
        res_data = {}
        res_total = {'cpu_time': 0, 'wall_time': 0, 'memory': 0}
        for report in report_qs:
            component = report.component

            instances.setdefault(component, {'finished': 0, 'total': 0})
            instances[component]['total'] += 1
            if report.finish_date:
                instances[component]['finished'] += 1

            if report.cpu_time or report.wall_time or report.memory:
                res_data.setdefault(component, {'cpu_time': 0, 'wall_time': 0, 'memory': 0})
            if report.cpu_time:
                res_data[component]['cpu_time'] += report.cpu_time
                res_total['cpu_time'] += report.cpu_time
            if report.wall_time:
                res_data[component]['wall_time'] += report.wall_time
                res_total['wall_time'] += report.wall_time
            if report.memory:
                res_data[component]['memory'] = max(report.memory, res_data[component]['memory'])
                res_total['memory'] = max(report.memory, res_total['memory'])

        resource_data = []
        for component in sorted(instances):
            resources_value = '-'
            if component in res_data:
                resources_value = "{} {} {}".format(
                    HumanizedValue(res_data[component]['wall_time'], user=self.user).timedelta,
                    HumanizedValue(res_data[component]['cpu_time'], user=self.user).timedelta,
                    HumanizedValue(res_data[component]['memory'], user=self.user).memory
                )
            instances_value = ' ({}/{})'.format(instances[component]['finished'], instances[component]['total'])
            resource_data.append({'component': component, 'val': resources_value, 'instances': instances_value})
        if 'hidden' not in self.view or 'resource_total' not in self.view['hidden']:
            if res_total['wall_time'] > 0 or res_total['cpu_time'] > 0 or res_total['memory'] > 0:
                resource_data.append({'component': _('Total'), 'instances': '', 'val': "{} {} {}".format(
                    HumanizedValue(res_total['wall_time'], user=self.user).timedelta,
                    HumanizedValue(res_total['cpu_time'], user=self.user).timedelta,
                    HumanizedValue(res_total['memory'], user=self.user).memory
                )})
        return resource_data

    def __filter_problem(self, problem):
        if 'unknown_problem' not in self.view:
            return True
        if self.view['unknown_problem'][0] == 'iexact':
            return self.view['unknown_problem'][1].lower() == problem.lower()
        if self.view['unknown_problem'][0] == 'istartswith':
            return problem.lower().startswith(self.view['unknown_problem'][1].lower())
        if self.view['unknown_problem'][0] == 'icontains':
            return self.view['unknown_problem'][1].lower() in problem.lower()
        return True

    def __unknowns_info(self):
        if not self.report:
            return []
        url = reverse('reports:unknowns', args=[self.report.id])
        nomark_hidden = 'hidden' in self.view and 'unknowns_nomark' in self.view['hidden']
        total_hidden = 'hidden' in self.view and 'unknowns_total' in self.view['hidden']

        # Get querysets for unknowns
        qs_filters = {'root': self.root}

        if 'unknown_component' in self.view:
            qs_filters['component__{}'.format(self.view['unknown_component'][0])] = self.view['unknown_component'][1]

        # 'unknown_problem' in self.view is not working anymore
        select_only = ('component', 'cache__marks_total', 'cache__problems')

        # Collect unknowns data
        cache_data = {}
        unmarked = {}
        totals = {}
        skipped_problems = set()
        for unknown in ReportUnknown.objects.select_related('cache').filter(**qs_filters).only(*select_only):
            cache_data.setdefault(unknown.component, {})
            if not total_hidden:
                totals.setdefault(unknown.component, 0)
                totals[unknown.component] += 1
            if not nomark_hidden and unknown.cache.marks_total == 0:
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
                    'href': '{0}?component={1}&problem={2}'.format(url, quote(c_name), quote(problem))
                })
                has_data = True
            if not nomark_hidden and c_name in unmarked:
                component_data['problems'].append({
                    'problem': _('Without marks'), 'num': unmarked[c_name],
                    'href': '{0}?component={1}&problem=null'.format(url, quote(c_name))
                })
                has_data = True
            if not total_hidden and c_name in totals:
                component_data['total'] = {
                    'num': totals[c_name], 'href': '{0}?component={1}'.format(url, quote(c_name))
                }
                has_data = True
            if has_data:
                unknowns_data.append(component_data)
        return unknowns_data

    def __safes_info(self):
        if not self.report:
            return []
        verdicts = SafeVerdicts()

        with_confirmed = 'hidden' not in self.view or 'confirmed_marks' not in self.view['hidden']
        base_url = reverse('reports:safes', args=[self.report.id])

        safes_qs = ReportSafe.objects.filter(root=self.root).values('cache__verdict').annotate(
            total=Count('id'), confirmed=Count(Case(When(cache__marks_confirmed__gt=0, then=1)))
        ).values_list('cache__verdict', 'confirmed', 'total')

        safes_numbers = {}
        for verdict, confirmed, total in safes_qs:
            if total == 0:
                continue
            column = verdicts.column(verdict)
            if column not in safes_numbers:
                safes_numbers[column] = {
                    'title': TITLES.get(column, column),
                    'verdict': verdict,
                    'url': base_url,
                    'total': 0
                }
                if with_confirmed:
                    safes_numbers[column]['confirmed'] = 0
            safes_numbers[column]['total'] += total
            if with_confirmed:
                safes_numbers[column]['confirmed'] += confirmed
        safes_data = []
        for column in verdicts.columns():
            if column in safes_numbers and safes_numbers[column]['total'] > 0:
                safes_data.append(safes_numbers[column])
        return safes_data

    def __unsafes_info(self):
        if not self.report:
            return []
        verdicts = UnsafeVerdicts()

        with_confirmed = 'hidden' not in self.view or 'confirmed_marks' not in self.view['hidden']
        base_url = reverse('reports:unsafes', args=[self.report.id])

        unsafes_qs = ReportUnsafe.objects.filter(root=self.root).values('cache__verdict').annotate(
            total=Count('id'), confirmed=Count(Case(When(cache__marks_confirmed__gt=0, then=1)))
        ).values_list('cache__verdict', 'confirmed', 'total')

        unsafes_numbers = {}
        for verdict, confirmed, total in unsafes_qs:
            if total == 0:
                continue
            column = verdicts.column(verdict)
            if column not in unsafes_numbers:
                unsafes_numbers[column] = {
                    'title': TITLES.get(column, column),
                    'verdict': verdict,
                    'url': base_url,
                    'total': 0
                }
                if with_confirmed:
                    unsafes_numbers[column]['confirmed'] = 0
            unsafes_numbers[column]['total'] += total
            if with_confirmed:
                unsafes_numbers[column]['confirmed'] += confirmed

        unsafes_data = []
        for column in verdicts.columns():
            if column in unsafes_numbers and unsafes_numbers[column]['total'] > 0:
                unsafes_data.append(unsafes_numbers[column])
        return unsafes_data

    def __safes_attrs_statistic(self):
        return self.__attr_statistic('reports:safes', ReportSafe)

    def __unsafes_attrs_statistic(self):
        return self.__attr_statistic('reports:unsafes', ReportUnsafe)

    def __unknowns_attrs_statistic(self):
        return self.__attr_statistic('reports:unknowns', ReportUnknown)

    def __attr_statistic(self, list_url_name, model):
        if not self.report:
            return []
        if 'attr_stat' not in self.view or len(self.view['attr_stat']) != 1 or len(self.view['attr_stat'][0]) == 0:
            return []
        attr_name = self.view['attr_stat'][0]

        base_url = reverse(list_url_name, args=[self.report.id])
        data = {}
        for report_attrs in model.objects.filter(root=self.root, cache__attrs__has_key=attr_name)\
                .values_list('cache__attrs', flat=True):
            attr_value = report_attrs[attr_name]
            if attr_value not in data:
                data[attr_value] = {
                    'url': '{}?attr_name={}&attr_value={}'.format(base_url, quote(attr_name), quote(attr_value)),
                    'name': attr_value, 'value': 0
                }
            data[report_attrs[attr_name]]['value'] += 1
        return list(data[attr_value] for attr_value in sorted(data))


class ViewReportData:
    def __init__(self, user, view, report):
        self.user = user
        self.report = report
        self.view = view
        self.totals = self.__get_totals()
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
        data = {}
        data.update(ReportSafe.objects.filter(leaves__report=self.report).aggregate(
            safes=Count('id'),
            safes_confirmed=Count(Case(When(cache__marks_confirmed__gt=0, then=1))),
        ))
        data.update(ReportUnsafe.objects.filter(leaves__report=self.report).aggregate(
            unsafes=Count('id'),
            unsafes_confirmed=Count(Case(When(cache__marks_confirmed__gt=0, then=1))),
        ))
        data.update(ReportUnknown.objects.filter(leaves__report=self.report).aggregate(
            unknowns=Count('id'),
            unknowns_confirmed=Count(Case(When(cache__marks_confirmed__gt=0, then=1))),
        ))
        return data

    def __safe_tags_info(self):
        # Get all db tags
        tags_qs = SafeTag.objects.all()
        if 'safe_tag' in self.view:
            tags_qs = tags_qs.filter(**{'name__{}'.format(self.view['safe_tag'][0]): self.view['safe_tag'][1]})
        db_tags = dict(tags_qs.values_list('name', 'description'))

        # Calculate tags numbers
        safes_url = reverse('reports:safes', args=[self.report.id])
        tags_data = {}
        for cache_obj in ReportSafeCache.objects.filter(report__leaves__report=self.report):
            for tag, number in cache_obj.tags.items():
                if tag not in db_tags:
                    continue
                if tag not in tags_data:
                    tags_data[tag] = {
                        'name': tag, 'value': 0, 'description': db_tags[tag],
                        'url': '{}?tag={}'.format(safes_url, quote(tag))
                    }
                tags_data[tag]['value'] += number
        return list(tags_data[tag] for tag in sorted(tags_data))

    def __unsafe_tags_info(self):
        # Get all db tags
        tags_qs = UnsafeTag.objects.all()
        if 'unsafe_tag' in self.view:
            tags_qs = tags_qs.filter(**{'name__{}'.format(self.view['unsafe_tag'][0]): self.view['unsafe_tag'][1]})
        db_tags = dict(tags_qs.values_list('name', 'description'))

        # Calculate tags numbers
        unsafes_url = reverse('reports:unsafes', args=[self.report.id])
        tags_data = {}
        for cache_obj in ReportUnsafeCache.objects.filter(report__leaves__report=self.report):
            for tag, number in cache_obj.tags.items():
                if tag not in db_tags:
                    continue
                if tag not in tags_data:
                    tags_data[tag] = {
                        'name': tag, 'value': 0, 'description': db_tags[tag],
                        'url': '{}?tag={}'.format(unsafes_url, quote(tag))
                    }
                tags_data[tag]['value'] += number
        return list(tags_data[tag] for tag in sorted(tags_data))

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

        instances = {}
        res_data = {}
        res_total = {'cpu_time': 0, 'wall_time': 0, 'memory': 0}
        for report in reports_qs:
            component = report.component

            instances.setdefault(component, {'finished': 0, 'total': 0})
            instances[component]['total'] += 1
            if report.reportcomponent.finish_date:
                instances[component]['finished'] += 1

            if report.cpu_time or report.wall_time or report.memory:
                res_data.setdefault(component, {'cpu_time': 0, 'wall_time': 0, 'memory': 0})
            if report.cpu_time:
                res_data[component]['cpu_time'] += report.cpu_time
                res_total['cpu_time'] += report.cpu_time
            if report.wall_time:
                res_data[component]['wall_time'] += report.wall_time
                res_total['wall_time'] += report.wall_time
            if report.memory:
                res_data[component]['memory'] = max(report.memory, res_data[component]['memory'])
                res_total['memory'] = max(report.memory, res_total['memory'])

        resource_data = []
        for component in sorted(instances):
            resources_value = '-'
            if component in res_data:
                resources_value = "{} {} {}".format(
                    HumanizedValue(res_data[component]['wall_time'], user=self.user).timedelta,
                    HumanizedValue(res_data[component]['cpu_time'], user=self.user).timedelta,
                    HumanizedValue(res_data[component]['memory'], user=self.user).memory
                )
            instances_value = ' ({}/{})'.format(instances[component]['finished'], instances[component]['total'])
            resource_data.append({'component': component, 'val': resources_value, 'instances': instances_value})
        if 'hidden' not in self.view or 'resource_total' not in self.view['hidden']:
            if res_total['wall_time'] > 0 or res_total['cpu_time'] > 0 or res_total['memory'] > 0:
                resource_data.append({'component': _('Total'), 'instances': '', 'val': "{} {} {}".format(
                    HumanizedValue(res_total['wall_time'], user=self.user).timedelta,
                    HumanizedValue(res_total['cpu_time'], user=self.user).timedelta,
                    HumanizedValue(res_total['memory'], user=self.user).memory
                )})
        return resource_data

    def __filter_problem(self, problem):
        if 'unknown_problem' not in self.view:
            return True
        if self.view['unknown_problem'][0] == 'iexact':
            return self.view['unknown_problem'][1].lower() == problem.lower()
        if self.view['unknown_problem'][0] == 'istartswith':
            return problem.lower().startswith(self.view['unknown_problem'][1].lower())
        if self.view['unknown_problem'][0] == 'icontains':
            return self.view['unknown_problem'][1].lower() in problem.lower()
        return True

    def __unknowns_info(self):
        url = reverse('reports:unknowns', args=[self.report.id])
        nomark_hidden = 'hidden' in self.view and 'unknowns_nomark' in self.view['hidden']
        total_hidden = 'hidden' in self.view and 'unknowns_total' in self.view['hidden']

        # Get querysets for unknowns
        qs_filters = {'leaves__report': self.report}

        if 'unknown_component' in self.view:
            qs_filters['component__{}'.format(self.view['unknown_component'][0])] = self.view['unknown_component'][1]

        # 'unknown_problem' in self.view is not working anymore
        select_only = ('component', 'cache__marks_total', 'cache__problems')

        # Collect unknowns data
        cache_data = {}
        unmarked = {}
        totals = {}
        skipped_problems = set()
        for unknown in ReportUnknown.objects.filter(**qs_filters).only(*select_only):
            cache_data.setdefault(unknown.component, {})
            if not total_hidden:
                totals.setdefault(unknown.component, 0)
                totals[unknown.component] += 1
            if not nomark_hidden and unknown.cache.marks_total == 0:
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
                    'href': '{0}?component={1}&problem={2}'.format(url, quote(c_name), quote(problem))
                })
                has_data = True
            if not nomark_hidden and c_name in unmarked:
                component_data['problems'].append({
                    'problem': _('Without marks'), 'num': unmarked[c_name],
                    'href': '{0}?component={1}&problem=null'.format(url, quote(c_name))
                })
                has_data = True
            if not total_hidden and c_name in totals:
                component_data['total'] = {
                    'num': totals[c_name], 'href': '{0}?component={1}'.format(url, quote(c_name))
                }
                has_data = True
            if has_data:
                unknowns_data.append(component_data)
        return unknowns_data

    def __safes_info(self):
        verdicts = SafeVerdicts()

        with_confirmed = 'hidden' not in self.view or 'confirmed_marks' not in self.view['hidden']
        base_url = reverse('reports:safes', args=[self.report.pk])

        safes_qs = ReportSafe.objects.filter(leaves__report=self.report).values('cache__verdict').annotate(
            total=Count('id'), confirmed=Count(Case(When(cache__marks_confirmed__gt=0, then=1)))
        ).values_list('cache__verdict', 'confirmed', 'total')

        safes_numbers = {}
        for verdict, confirmed, total in safes_qs:
            if total == 0:
                continue
            column = verdicts.column(verdict)
            if column not in safes_numbers:
                safes_numbers[column] = {
                    'title': TITLES.get(column, column),
                    'verdict': verdict,
                    'url': base_url,
                    'total': 0
                }
                if with_confirmed:
                    safes_numbers[column]['confirmed'] = 0
            safes_numbers[column]['total'] += total
            if with_confirmed:
                safes_numbers[column]['confirmed'] += confirmed
        safes_data = []
        for column in verdicts.columns():
            if column in safes_numbers and safes_numbers[column]['total'] > 0:
                safes_data.append(safes_numbers[column])
        return safes_data

    def __unsafes_info(self):
        verdicts = UnsafeVerdicts()

        with_confirmed = 'hidden' not in self.view or 'confirmed_marks' not in self.view['hidden']
        base_url = reverse('reports:unsafes', args=[self.report.pk])

        unsafes_qs = ReportUnsafe.objects.filter(leaves__report=self.report).values('cache__verdict').annotate(
            total=Count('id'), confirmed=Count(Case(When(cache__marks_confirmed__gt=0, then=1)))
        ).values_list('cache__verdict', 'confirmed', 'total')

        unsafes_numbers = {}
        for verdict, confirmed, total in unsafes_qs:
            if total == 0:
                continue
            column = verdicts.column(verdict)
            if column not in unsafes_numbers:
                unsafes_numbers[column] = {
                    'title': TITLES.get(column, column),
                    'verdict': verdict,
                    'url': base_url,
                    'total': 0
                }
                if with_confirmed:
                    unsafes_numbers[column]['confirmed'] = 0
            unsafes_numbers[column]['total'] += total
            if with_confirmed:
                unsafes_numbers[column]['confirmed'] += confirmed

        unsafes_data = []
        for column in verdicts.columns():
            if column in unsafes_numbers and unsafes_numbers[column]['total'] > 0:
                unsafes_data.append(unsafes_numbers[column])
        return unsafes_data

    def __safes_attrs_statistic(self):
        return self.__attr_statistic('safe')

    def __unsafes_attrs_statistic(self):
        return self.__attr_statistic('unsafe')

    def __unknowns_attrs_statistic(self):
        return self.__attr_statistic('unknown')

    def __attr_statistic(self, report_type):
        if 'attr_stat' not in self.view or len(self.view['attr_stat']) != 1 or len(self.view['attr_stat'][0]) == 0:
            return []
        attr_name = self.view['attr_stat'][0]

        if report_type == 'safe':
            model = ReportSafe
        elif report_type == 'unsafe':
            model = ReportUnsafe
        else:
            model = ReportUnknown
        base_url = reverse('reports:{}s'.format(report_type), args=[self.report.id])
        data = {}
        for report_attrs in model.objects.filter(leaves__report=self.report, cache__attrs__has_key=attr_name)\
                .values_list('cache__attrs', flat=True):
            attr_value = report_attrs[attr_name]
            if attr_value not in data:
                data[attr_value] = {
                    'url': '{}?attr_name={}&attr_value={}'.format(base_url, quote(attr_name), quote(attr_value)),
                    'name': attr_value, 'value': 0
                }
            data[report_attrs[attr_name]]['value'] += 1
        return list(data[attr_value] for attr_value in sorted(data))
