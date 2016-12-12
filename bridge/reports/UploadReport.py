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
from io import BytesIO
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.utils.timezone import now
from bridge.utils import logger
from bridge.vars import REPORT_FILES_ARCHIVE, ATTR_STATISTIC
from marks.utils import ConnectReportWithMarks
from service.utils import KleverCoreFinishDecision, KleverCoreStartDecision
from reports.utils import save_attrs
from reports.models import *
from tools.utils import RecalculateLeaves, RecalculateVerdicts, RecalculateResources


class UploadReport(object):

    def __init__(self, job, data, archive=None):
        self.job = job
        self.archive = archive
        self.data = {}
        self.ordered_attrs = []
        self.error = None
        try:
            self.__check_data(data)
            self.parent = self.__get_parent()
            self.root = self.__get_root_report()
            self.__upload()
        except Exception as e:
            logger.exception('Uploading report failed: %s' % str(e), stack_info=True)
            self.__job_failed(str(e))
            self.error = str(e)

    def __job_failed(self, error=None):
        if 'id' in self.data:
            error = 'The error occurred when uploading the report with id "%s": ' % self.data['id'] + str(error)
        KleverCoreFinishDecision(self.job, error)

    def __check_data(self, data):
        if not isinstance(data, dict):
            raise ValueError('report data is not a dictionary')
        if 'type' not in data or 'id' not in data or not isinstance(data['id'], str) or len(data['id']) == 0 \
                or not data['id'].startswith('/'):
            raise ValueError('type and id are required or have wrong format')
        if 'parent id' in data and not isinstance(data['parent id'], str):
            raise ValueError('parent id has wrong format')

        if 'resources' in data:
            if not isinstance(data['resources'], dict) \
                    or any(x not in data['resources'] for x in ['wall time', 'CPU time', 'memory size']):
                raise ValueError('resources have wrong format')

        self.data = {'type': data['type'], 'id': data['id']}
        if 'comp' in data:
            self.__check_comp(data['comp'])
        if 'name' in data and isinstance(data['name'], str) and len(data['name']) > 15:
            raise ValueError('component name is too long (max 15 symbols expected)')
        if 'data' in data:
            try:
                json.loads(data['data'])
            except ValueError:
                raise ValueError("component data must be represented in JSON")

        if data['type'] == 'start':
            if data['id'] == '/':
                KleverCoreStartDecision(self.job)
                try:
                    self.data.update({
                        'attrs': data['attrs'],
                        'comp': data['comp'],
                    })
                except KeyError as e:
                    raise ValueError("property '%s' is required." % e)
            else:
                try:
                    self.data.update({
                        'parent id': data['parent id'],
                        'name': data['name']
                    })
                except KeyError as e:
                    raise ValueError("property '%s' is required." % e)
                if 'attrs' in data:
                    self.data['attrs'] = data['attrs']
                if 'comp' in data:
                    self.data['comp'] = data['comp']
        elif data['type'] == 'finish':
            try:
                self.data['resources'] = data['resources']
            except KeyError as e:
                raise ValueError("property '%s' is required." % e)
            if 'data' in data:
                self.data.update({'data': data['data']})
            if 'log' in data:
                self.data['log'] = data['log']
        elif data['type'] == 'attrs':
            try:
                self.data['attrs'] = data['attrs']
            except KeyError as e:
                raise ValueError("property '%s' is required." % e)
        elif data['type'] == 'verification':
            try:
                self.data.update({
                    'parent id': data['parent id'],
                    'attrs': data['attrs'],
                    'name': data['name'],
                    'resources': data['resources']
                })
            except KeyError as e:
                raise ValueError("property '%s' is required." % e)
            if 'data' in data:
                self.data.update({'data': data['data']})
            if 'comp' in data:
                self.data['comp'] = data['comp']
            if 'log' in data:
                self.data['log'] = data['log']
        elif data['type'] == 'verification finish':
            pass
        elif data['type'] == 'safe':
            try:
                self.data.update({
                    'parent id': data['parent id'],
                    'proof': data['proof'],
                    'attrs': data['attrs'],
                })
            except KeyError as e:
                raise ValueError("property '%s' is required." % e)
        elif data['type'] == 'unknown':
            try:
                self.data.update({
                    'parent id': data['parent id'],
                    'problem desc': data['problem desc']
                })
            except KeyError as e:
                raise ValueError("property '%s' is required." % e)
            if 'attrs' in data:
                self.data['attrs'] = data['attrs']
        elif data['type'] == 'unsafe':
            try:
                self.data.update({
                    'parent id': data['parent id'],
                    'error trace': data['error trace'],
                    'attrs': data['attrs'],
                })
            except KeyError as e:
                raise ValueError("property '%s' is required." % e)
        elif data['type'] == 'data':
            try:
                self.data.update({
                    'data': data['data']
                })
            except KeyError as e:
                raise ValueError("property '%s' is required." % e)
        else:
            raise ValueError("report type is not supported")

    def __check_comp(self, descr):
        self.ccc = 0
        if not isinstance(descr, list):
            raise ValueError('wrong computer description format')
        for d in descr:
            if not isinstance(d, dict):
                raise ValueError('wrong computer description format')
            if len(d) != 1:
                raise ValueError('wrong computer description format')
            if not isinstance(d[next(iter(d))], str) and not isinstance(d[next(iter(d))], int):
                raise ValueError('wrong computer description format')

    def __get_root_report(self):
        try:
            return ReportRoot.objects.get(job=self.job)
        except ObjectDoesNotExist:
            raise ValueError("the job is corrupted: can't find report root")

    def __get_parent(self):
        if 'parent id' in self.data:
            try:
                return ReportComponent.objects.get(
                    root=self.job.reportroot,
                    identifier=self.job.identifier + self.data['parent id']
                )
            except ObjectDoesNotExist:
                raise ValueError('report parent was not found')
        elif self.data['id'] == '/':
            return None
        else:
            try:
                curr_report = ReportComponent.objects.get(identifier=self.job.identifier + self.data['id'])
                return ReportComponent.objects.get(pk=curr_report.parent_id)
            except ObjectDoesNotExist:
                raise ValueError('report parent was not found')

    def __upload(self):
        actions = {
            'start': self.__create_report_component,
            'finish': self.__finish_report_component,
            'attrs': self.__update_attrs,
            'verification': self.__create_report_component,
            'verification finish': self.__finish_verification_report,
            'unsafe': self.__create_report_unsafe,
            'safe': self.__create_report_safe,
            'unknown': self.__create_report_unknown,
            'data': self.__update_report_data
        }
        identifier = self.job.identifier + self.data['id']
        actions[self.data['type']](identifier)
        if len(self.ordered_attrs) != len(set(self.ordered_attrs)) \
                and self.data['type'] not in ['safe', 'unsafe', 'unknown']:
            raise ValueError("attributes are not unique")

    def __create_report_component(self, identifier):
        try:
            ReportComponent.objects.get(identifier=identifier)
            raise ValueError('the report with specified identifier already exists')
        except ObjectDoesNotExist:
            report = ReportComponent(
                identifier=identifier, parent=self.parent, root=self.root, start_date=now(),
                component=Component.objects.get_or_create(name=self.data['name'] if 'name' in self.data else 'Core')[0]
            )
            if 'data' in self.data:
                if self.job.light and self.data['id'] == '/' or not self.job.light:
                    report.new_data('report-data.json', BytesIO(self.data['data'].encode('utf8')))

        if self.data['type'] == 'verification':
            report.finish_date = report.start_date

        if 'comp' in self.data:
            report.computer = Computer.objects.get_or_create(
                description=json.dumps(self.data['comp'], ensure_ascii=False, sort_keys=True, indent=4)
            )[0]
        else:
            report.computer = self.parent.computer

        if 'resources' in self.data:
            report.cpu_time = int(self.data['resources']['CPU time'])
            report.memory = int(self.data['resources']['memory size'])
            report.wall_time = int(self.data['resources']['wall time'])

        if self.archive is not None:
            if not self.job.light or self.data['type'] == 'verification' or self.data['id'] == '/':
                report.new_archive(REPORT_FILES_ARCHIVE, self.archive)
                report.log = self.data.get('log')

        report.save()

        if 'attrs' in self.data:
            self.ordered_attrs = save_attrs(report, self.data['attrs'])

        if 'resources' in self.data:
            if self.job.light:
                self.__update_light_resources(report)
            else:
                self.__update_parent_resources(report)

    def __update_attrs(self, identifier):
        try:
            report = ReportComponent.objects.get(identifier=identifier)
            self.ordered_attrs = save_attrs(report, self.data['attrs'])
        except ObjectDoesNotExist:
            raise ValueError('updated report does not exist')

    def __update_report_data(self, identifier):
        if self.job.light and self.data['id'] != '/':
            return
        try:
            report = ReportComponent.objects.get(identifier=identifier)
            report.new_data('report-data.json', BytesIO(self.data['data'].encode('utf8')), True)
        except ObjectDoesNotExist:
            raise ValueError('updated report does not exist')

    def __finish_report_component(self, identifier):
        try:
            report = ReportComponent.objects.get(identifier=identifier)
        except ObjectDoesNotExist:
            raise ValueError('updated report does not exist')
        if report.finish_date is not None:
            raise ValueError('trying to finish the finished component')

        report.cpu_time = int(self.data['resources']['CPU time'])
        report.memory = int(self.data['resources']['memory size'])
        report.wall_time = int(self.data['resources']['wall time'])

        if self.archive is not None:
            if self.data['id'] == '/' or not self.job.light:
                report.new_archive(REPORT_FILES_ARCHIVE, self.archive)
                report.log = self.data.get('log')

        if 'data' in self.data:
            if not (self.job.light and self.data['id'] != '/'):
                report.new_data('report-data.json', BytesIO(self.data['data'].encode('utf8')))
        report.finish_date = now()
        report.save()

        if 'attrs' in self.data:
            self.ordered_attrs = save_attrs(report, self.data['attrs'])
        if self.job.light:
            self.__update_light_resources(report)
        else:
            self.__update_parent_resources(report)

        if self.data['id'] == '/':
            if len(ReportComponent.objects.filter(finish_date=None, root=self.root)) > 0:
                raise ValueError('there are unfinished reports')
            KleverCoreFinishDecision(self.job)
            if self.job.light:
                self.__collapse_reports()
        elif self.job.light and len(ReportComponent.objects.filter(parent=report)) == 0:
            report.delete()

    def __finish_verification_report(self, identifier):
        if not self.job.light:
            return
        try:
            report = ReportComponent.objects.get(identifier=identifier)
        except ObjectDoesNotExist:
            raise ValueError('verification report does not exist')
        if len(ReportUnsafe.objects.filter(parent=report)) == 0:
            report.delete()

    def __create_report_unknown(self, identifier):
        if self.job.light:
            self.__create_light_unknown_report(identifier)
            return
        try:
            ReportUnknown.objects.get(identifier=identifier)
            raise ValueError('the report with specified identifier already exists')
        except ObjectDoesNotExist:
            if self.archive is None:
                raise ValueError('unknown report must contain archive with problem description')
        report = ReportUnknown(
            identifier=identifier, parent=self.parent, root=self.root,
            component=self.parent.component, problem_description=self.data['problem desc']
        )
        report.new_archive(REPORT_FILES_ARCHIVE, self.archive)
        report.save()

        self.__collect_attrs(report)
        if 'attrs' in self.data:
            self.ordered_attrs += save_attrs(report, self.data['attrs'])
        report_attrs = self.__get_attrs(report)

        parent = self.parent
        while parent is not None:
            verdict = Verdict.objects.get_or_create(report=parent)[0]
            verdict.unknown += 1
            verdict.save()

            for a in report_attrs:
                attr_stat = AttrStatistic.objects.get_or_create(
                    report=parent, name=AttrName.objects.get(name=a), attr=report_attrs[a]
                )[0]
                attr_stat.unknowns += 1
                attr_stat.save()

            comp_unknown = ComponentUnknown.objects.get_or_create(report=parent, component=report.component)[0]
            comp_unknown.number += 1
            comp_unknown.save()

            ReportComponentLeaf.objects.create(report=parent, unknown=report)
            try:
                parent = ReportComponent.objects.get(pk=parent.parent_id)
            except ObjectDoesNotExist:
                parent = None
        ConnectReportWithMarks(report)

    def __create_light_unknown_report(self, identifier):
        try:
            ReportUnknown.objects.get(identifier=identifier)
            raise ValueError('the report with specified identifier already exists')
        except ObjectDoesNotExist:
            if self.archive is None:
                raise ValueError('unknown report must contain archive with problem description')
        report = ReportUnknown(
            identifier=identifier, parent=self.parent, root=self.root,
            component=self.parent.component, problem_description=self.data['problem desc']
        )
        report.new_archive(REPORT_FILES_ARCHIVE, self.archive)
        report.save()

        self.__collect_attrs(report)
        if 'attrs' in self.data:
            self.ordered_attrs += save_attrs(report, self.data['attrs'])
        report_attrs = self.__get_attrs(report)

        report.parent = ReportComponent.objects.get(parent=None, root=self.root)
        report.save()

        verdict = Verdict.objects.get_or_create(report=report.parent)[0]
        verdict.unknown += 1
        verdict.save()

        for a in report_attrs:
            attr_stat = AttrStatistic.objects.get_or_create(
                report=report.parent, name=AttrName.objects.get(name=a), attr=report_attrs[a]
            )[0]
            attr_stat.unknowns += 1
            attr_stat.save()

        comp_unknown = ComponentUnknown.objects.get_or_create(report=report.parent, component=report.component)[0]
        comp_unknown.number += 1
        comp_unknown.save()
        ReportComponentLeaf.objects.create(report=report.parent, unknown=report)
        ConnectReportWithMarks(report)

    def __create_report_safe(self, identifier):
        if self.job.light:
            self.__create_light_safe_report(identifier)
            return
        try:
            ReportSafe.objects.get(identifier=identifier)
            raise ValueError('the report with specified identifier already exists')
        except ObjectDoesNotExist:
            report = ReportSafe(identifier=identifier, parent=self.parent, root=self.root)
        if self.archive is not None:
            report.new_archive(REPORT_FILES_ARCHIVE, self.archive)
            report.proof = self.data['proof']
        report.save()

        self.root.safes += 1
        self.root.save()

        self.__collect_attrs(report)
        self.ordered_attrs += save_attrs(report, self.data['attrs'])
        report_attrs = self.__get_attrs(report)

        parent = self.parent
        while parent is not None:
            verdict = Verdict.objects.get_or_create(report=parent)[0]
            verdict.safe += 1
            verdict.safe_unassociated += 1
            verdict.save()

            for a in report_attrs:
                attr_stat = AttrStatistic.objects.get_or_create(
                    report=parent, name=AttrName.objects.get(name=a), attr=report_attrs[a]
                )[0]
                attr_stat.safes += 1
                attr_stat.save()

            ReportComponentLeaf.objects.create(report=parent, safe=report)
            try:
                parent = ReportComponent.objects.get(pk=parent.parent_id)
            except ObjectDoesNotExist:
                parent = None
        ConnectReportWithMarks(report)

    def __create_light_safe_report(self, identifier):
        report = ReportSafe.objects.create(identifier=identifier, parent=self.parent, root=self.root)
        self.root.safes += 1
        self.root.save()

        self.__collect_attrs(report)
        self.ordered_attrs += save_attrs(report, self.data['attrs'])
        report_attrs = self.__get_attrs(report)

        parent = self.parent
        while parent is not None:
            for a in report_attrs:
                attr_stat = AttrStatistic.objects.get_or_create(
                    report=parent, name=AttrName.objects.get(name=a), attr=report_attrs[a]
                )[0]
                attr_stat.safes += 1
                attr_stat.save()
            try:
                parent = ReportComponent.objects.get(pk=parent.parent_id)
            except ObjectDoesNotExist:
                parent = None
        report.delete()

    def __create_report_unsafe(self, identifier):
        if self.job.light:
            self.__create_light_unsafe_report(identifier)
            return
        try:
            ReportUnsafe.objects.get(identifier=identifier)
            raise ValueError('the report with specified identifier already exists')
        except ObjectDoesNotExist:
            if self.archive is None:
                raise ValueError('unsafe report must contain archive with error trace and source code files')
        report = ReportUnsafe(
            identifier=identifier, parent=self.parent, root=self.root, error_trace=self.data['error trace']
        )
        report.new_archive(REPORT_FILES_ARCHIVE, self.archive)
        report.save()

        self.__collect_attrs(report)
        self.ordered_attrs += save_attrs(report, self.data['attrs'])
        report_attrs = self.__get_attrs(report)

        parent = self.parent
        while parent is not None:
            verdict = Verdict.objects.get_or_create(report=parent)[0]
            verdict.unsafe += 1
            verdict.unsafe_unassociated += 1
            verdict.save()

            for a in report_attrs:
                attr_stat = AttrStatistic.objects.get_or_create(
                    report=parent, name=AttrName.objects.get(name=a), attr=report_attrs[a]
                )[0]
                attr_stat.unsafes += 1
                attr_stat.save()

            ReportComponentLeaf.objects.create(report=parent, unsafe=report)
            try:
                parent = ReportComponent.objects.get(pk=parent.parent_id)
            except ObjectDoesNotExist:
                parent = None
        ConnectReportWithMarks(report)

    def __create_light_unsafe_report(self, identifier):
        try:
            ReportUnsafe.objects.get(identifier=identifier)
            raise ValueError('the report with specified identifier already exists')
        except ObjectDoesNotExist:
            if self.archive is None:
                raise ValueError('unsafe report must contain archive with error trace and source code files')
        report = ReportUnsafe.objects.create(
            identifier=identifier, parent=self.parent, root=self.root, error_trace=self.data['error trace']
        )
        report.new_archive(REPORT_FILES_ARCHIVE, self.archive)
        report.save()

        # Each verification report must have only one unsafe child
        # In other cases unsafe reports will be without attributes
        self.__collect_attrs(report)
        self.ordered_attrs += save_attrs(report, self.data['attrs'])
        report_attrs = self.__get_attrs(report)

        root_report = ReportComponent.objects.get(parent=None, root=self.root)
        if self.parent.archive is None:
            report.parent = root_report
            report.save()
        else:
            self.parent.parent = root_report
            self.parent.save()
            verdict = Verdict.objects.get_or_create(report=self.parent)[0]
            verdict.unsafe += 1
            verdict.unsafe_unassociated += 1
            verdict.save()
            ReportComponentLeaf.objects.create(report=self.parent, unsafe=report)

        verdict = Verdict.objects.get_or_create(report=root_report)[0]
        verdict.unsafe += 1
        verdict.unsafe_unassociated += 1
        verdict.save()

        for a in report_attrs:
            attr_stat = AttrStatistic.objects.get_or_create(
                report=root_report, name=AttrName.objects.get(name=a), attr=report_attrs[a]
            )[0]
            attr_stat.unsafes += 1
            attr_stat.save()

        ReportComponentLeaf.objects.create(report=root_report, unsafe=report)
        ConnectReportWithMarks(report)

    def __collect_attrs(self, report):
        parent = self.parent
        attrs_ids = []
        while parent is not None:
            parent_attrs = []
            new_ids = []
            for rep_attr in parent.attrs.order_by('id'):
                parent_attrs.append(rep_attr.attr.name.name)
                try:
                    ReportAttr.objects.get(attr_id=rep_attr.attr_id, report=report)
                except ObjectDoesNotExist:
                    new_ids.append(rep_attr.attr_id)
            attrs_ids = new_ids + attrs_ids
            self.ordered_attrs = parent_attrs + self.ordered_attrs
            try:
                parent = ReportComponent.objects.get(pk=parent.parent_id)
            except ObjectDoesNotExist:
                parent = None
        ReportAttr.objects.bulk_create(list(ReportAttr(attr_id=a_id, report=report) for a_id in attrs_ids))

    def __update_parent_resources(self, report):

        def update_total_resources(rep):
            res_set = rep.resources_cache.filter(~Q(component=None))
            if len(res_set) > 0:
                try:
                    total_compres = rep.resources_cache.get(component=None)
                except ObjectDoesNotExist:
                    total_compres = ComponentResource()
                    total_compres.report = rep
                total_compres.cpu_time = sum(list(cr.cpu_time for cr in res_set))
                total_compres.wall_time = sum(list(cr.wall_time for cr in res_set))
                total_compres.memory = max(list(cr.memory for cr in res_set))
                total_compres.save()

        try:
            report.resources_cache.get(component=report.component)
        except ObjectDoesNotExist:
            report.resources_cache.create(
                component=report.component,
                wall_time=report.wall_time,
                cpu_time=report.cpu_time,
                memory=report.memory
            )
        if len(ReportComponent.objects.filter(parent_id=report.pk)) > 0:
            update_total_resources(report)

        parent = self.parent
        while parent is not None:
            wall_time = report.wall_time
            cpu_time = report.cpu_time
            memory = report.memory
            try:
                compres = parent.resources_cache.get(component=report.component)
                wall_time += compres.wall_time
                cpu_time += compres.cpu_time
                memory = max(compres.memory, memory)
            except ObjectDoesNotExist:
                compres = ComponentResource()
                compres.component = report.component
                compres.report = parent
            compres.cpu_time = cpu_time
            compres.wall_time = wall_time
            compres.memory = memory
            compres.save()
            update_total_resources(parent)
            try:
                parent = ReportComponent.objects.get(pk=parent.parent_id)
            except ObjectDoesNotExist:
                parent = None

    def __update_light_resources(self, report):
        try:
            comp_res = LightResource.objects.get(report=self.root, component=report.component)
        except ObjectDoesNotExist:
            comp_res = LightResource(report=self.root, component=report.component, wall_time=0, cpu_time=0, memory=0)
        comp_res.cpu_time += report.cpu_time
        comp_res.wall_time += report.wall_time
        comp_res.memory = max(report.memory, comp_res.memory)
        comp_res.save()

        try:
            total_res = LightResource.objects.get(report=self.root, component=None)
        except ObjectDoesNotExist:
            total_res = LightResource(report=self.root, component=None, wall_time=0, cpu_time=0, memory=0)
        total_res.cpu_time += report.cpu_time
        total_res.wall_time += report.wall_time
        total_res.memory = max(report.memory, total_res.memory)
        total_res.save()

    def __collapse_reports(self):
        root_report = ReportComponent.objects.get(parent=None, root=self.root)
        reports_to_save = []
        for u in ReportUnsafe.objects.filter(root=self.root):
            if u.parent_id != root_report.pk:
                reports_to_save.append(u.parent_id)
        ReportComponent.objects.filter(Q(parent=root_report) & ~Q(id__in=reports_to_save)).delete()

    def __get_attrs(self, report):
        report_attrs = {}
        if self.job.type in ATTR_STATISTIC:
            report_attr_names = {}
            for a in ReportAttr.objects.filter(report=report):
                report_attr_names[a.attr.name.name] = a.attr
            for a_name in ATTR_STATISTIC[self.job.type]:
                report_attrs[a_name] = None
                if a_name in report_attr_names:
                    report_attrs[a_name] = report_attr_names[a_name]
        return report_attrs


class CollapseReports(object):
    def __init__(self, job):
        self.job = job
        self.__collapse()
        self.job.light = True
        self.job.save()

    def __collapse(self):
        try:
            root_report = ReportComponent.objects.get(parent=None, root__job=self.job)
        except ObjectDoesNotExist:
            return
        reports_to_save = []
        for u in ReportUnsafe.objects.filter(root__job=self.job):
            parent = ReportComponent.objects.get(pk=u.parent_id)
            if parent.parent is None:
                continue
            if parent.archive is None:
                u.parent = root_report
                u.save()
            else:
                parent.parent = root_report
                parent.save()
                reports_to_save.append(parent.pk)
        for u in ReportUnknown.objects.filter(root__job=self.job):
            u.parent = root_report
            u.save()
        self.__fill_resources()
        ReportComponent.objects.filter(Q(parent=root_report) & ~Q(id__in=reports_to_save)).delete()
        AttrStatistic.objects.filter(Q(report__root__job=self.job) & ~Q(report=root_report)).delete()
        RecalculateLeaves([self.job])
        RecalculateVerdicts([self.job])
        RecalculateResources([self.job])

    def __fill_resources(self):
        if self.job.light:
            return
        self.job.reportroot.safes = len(ReportSafe.objects.filter(root__job=self.job))
        self.job.reportroot.save()
        LightResource.objects.filter(report=self.job.reportroot).delete()
        LightResource.objects.bulk_create(list(LightResource(
            report=self.job.reportroot, component=cres.component,
            cpu_time=cres.cpu_time, wall_time=cres.wall_time, memory=cres.memory
        ) for cres in ComponentResource.objects.filter(report__root__job=self.job, report__parent=None)))
