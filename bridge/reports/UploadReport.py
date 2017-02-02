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
from bridge.vars import REPORT_FILES_ARCHIVE, ATTR_STATISTIC, JOB_WEIGHT
from marks.utils import ConnectReportWithMarks
from service.utils import KleverCoreFinishDecision, KleverCoreStartDecision
from reports.utils import AttrData
from reports.models import *
from tools.utils import RecalculateLeaves, RecalculateVerdicts, RecalculateResources


AVTG_TOTAL_NAME = 'total number of abstract verification task descriptions to be generated in ideal'
AVTG_FAIL_NAME = 'faulty generated abstract verification task descriptions'
VTG_FAIL_NAME = 'faulty processed abstract verification task descriptions'
BT_TOTAL_NAME = 'the number of verification tasks prepared for abstract verification task'


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
            self._parents_branch = self.__get_parents_branch()
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
        if 'data' in data and not isinstance(data['data'], dict):
            raise ValueError('report data must be a dictionary object')

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
                self.data.update({'data': data['data']})
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
                return ReportComponent.objects.get(id=curr_report.parent_id)
            except ObjectDoesNotExist:
                raise ValueError('report or its parent was not found')

    def __get_parents_branch(self):
        branch = []
        parent = self.parent
        while parent is not None:
            branch.insert(0, parent)
            if parent.parent_id is not None:
                parent = ReportComponent.objects.get(id=parent.parent_id)
            else:
                parent = None
        return branch

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
                if self.job.weight == JOB_WEIGHT[0][0] \
                        or self.job.weight != JOB_WEIGHT[0][0] and self.data['id'] == '/':
                    report.new_data('report-data.json', BytesIO(json.dumps(
                        self.data['data'], ensure_ascii=False, sort_keys=True, indent=4
                    ).encode('utf8')))

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

        if self.archive is not None and \
                (self.job.weight == JOB_WEIGHT[0][0] or self.data['type'] == 'verification' or self.data['id'] == '/'):
            report.new_archive(REPORT_FILES_ARCHIVE, self.archive)
            report.log = self.data.get('log')

        report.save()

        if 'attrs' in self.data:
            self.ordered_attrs = self.__save_attrs(report.id, self.data['attrs'])

        if 'resources' in self.data:
            if self.job.weight == JOB_WEIGHT[0][0]:
                self.__update_parent_resources(report)
            else:
                self.__update_light_resources(report)

    def __update_attrs(self, identifier):
        try:
            report = ReportComponent.objects.get(identifier=identifier)
        except ObjectDoesNotExist:
            raise ValueError('updated report does not exist')
        self.ordered_attrs = self.__save_attrs(report.id, self.data['attrs'])

    def __update_report_data(self, identifier):
        try:
            report = ReportComponent.objects.get(identifier=identifier)
        except ObjectDoesNotExist:
            raise ValueError('updated report does not exist')

        report_data = self.data['data']
        if report.component.name == 'AVTG' and (AVTG_FAIL_NAME in report_data or AVTG_TOTAL_NAME in report_data):
            tasks_nums = TasksNumbers.objects.get_or_create(root=self.root)[0]
            if AVTG_TOTAL_NAME in report_data:
                tasks_nums.avtg_total = int(report_data[AVTG_TOTAL_NAME])
            if AVTG_FAIL_NAME in report_data:
                tasks_nums.avtg_fail = int(report_data[AVTG_FAIL_NAME])
            tasks_nums.save()
            self.__save_total_tasks_number(tasks_nums)
        elif report.component.name == 'VTG' and VTG_FAIL_NAME in report_data:
            tasks_nums = TasksNumbers.objects.get_or_create(root=self.root)[0]
            tasks_nums.vtg_fail = int(report_data[VTG_FAIL_NAME])
            tasks_nums.save()
            self.__save_total_tasks_number(tasks_nums)
        elif report.component.name in {'SBT', 'MBT', 'RSB'} and BT_TOTAL_NAME in report_data:
            tasks_nums = TasksNumbers.objects.get_or_create(root=self.root)[0]
            tasks_nums.bt_total += int(report_data[BT_TOTAL_NAME])
            tasks_nums.bt_num += 1
            tasks_nums.save()
            self.__save_total_tasks_number(tasks_nums)
        else:
            self.__update_dict_data(report, report_data)

    def __update_dict_data(self, report, new_data):
        if self.job.weight != JOB_WEIGHT[0][0] and self.data['id'] != '/':
            report.save()
            return
        if not isinstance(new_data, dict):
            raise ValueError("report's data must be dictionary")
        if report.data:
            with report.data as fp:
                old_data = json.loads(fp.read().decode('utf8'))
                old_data.update(new_data)
                new_data = old_data
            report.data.storage.delete(report.data.path)
        report.new_data('report-data.json', BytesIO(json.dumps(new_data, indent=2).encode('utf8')), True)

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
            if self.data['id'] == '/' or self.job.weight == JOB_WEIGHT[0][0]:
                report.new_archive(REPORT_FILES_ARCHIVE, self.archive)
                report.log = self.data.get('log')

        report.finish_date = now()
        if 'data' in self.data and (self.job.weight == JOB_WEIGHT[0][0] or self.data['id'] == '/'):
            # Report is saved after the data is updated
            self.__update_dict_data(report, self.data['data'])
        else:
            report.save()

        if 'attrs' in self.data:
            self.ordered_attrs = self.__save_attrs(report.id, self.data['attrs'])
        if self.job.weight != JOB_WEIGHT[0][0]:
            self.__update_light_resources(report)
        else:
            self.__update_parent_resources(report)

        if self.data['id'] == '/':
            KleverCoreFinishDecision(self.job)
            if self.job.weight != JOB_WEIGHT[0][0]:
                self.__collapse_reports()
        elif self.job.weight != JOB_WEIGHT[0][0] and ReportComponent.objects.filter(parent=report).count() == 0:
            report.delete()

    def __finish_verification_report(self, identifier):
        if self.job.weight == JOB_WEIGHT[0][0]:
            return
        try:
            report = ReportComponent.objects.get(identifier=identifier)
        except ObjectDoesNotExist:
            raise ValueError('verification report does not exist')
        # I hope that verification reports can't have component reports as its children
        if Report.objects.filter(parent=report).count() == 0:
            report.delete()

    def __create_report_unknown(self, identifier):
        if self.job.weight != JOB_WEIGHT[0][0]:
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
            self.ordered_attrs += self.__save_attrs(report.id, self.data['attrs'])
        report_attrs = self.__get_attrs(report)

        for p in self._parents_branch:
            verdict = Verdict.objects.get_or_create(report=p)[0]
            verdict.unknown += 1
            verdict.save()

            for ra in report_attrs:
                attr_stat = AttrStatistic.objects.get_or_create(report=p, name_id=ra[0], attr_id=ra[1])[0]
                attr_stat.unknowns += 1
                attr_stat.save()

            comp_unknown = ComponentUnknown.objects.get_or_create(report=p, component=report.component)[0]
            comp_unknown.number += 1
            comp_unknown.save()

            ReportComponentLeaf.objects.create(report=p, unknown=report)
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
            self.ordered_attrs += self.__save_attrs(report.id, self.data['attrs'])
        report_attrs = self.__get_attrs(report)

        report.parent = ReportComponent.objects.get(parent=None, root=self.root)
        report.save()

        verdict = Verdict.objects.get_or_create(report=report.parent)[0]
        verdict.unknown += 1
        verdict.save()

        for ra in report_attrs:
            attr_stat = AttrStatistic.objects.get_or_create(report=report.parent, name_id=ra[0], attr_id=ra[1])[0]
            attr_stat.unknowns += 1
            attr_stat.save()

        comp_unknown = ComponentUnknown.objects.get_or_create(report=report.parent, component=report.component)[0]
        comp_unknown.number += 1
        comp_unknown.save()
        ReportComponentLeaf.objects.create(report=report.parent, unknown=report)
        ConnectReportWithMarks(report)

    def __create_report_safe(self, identifier):
        if self.job.weight == JOB_WEIGHT[1][0]:
            self.__create_medium_safe_report(identifier)
            return
        elif self.job.weight == JOB_WEIGHT[2][0]:
            self.__create_light_safe_report(identifier)
            return
        try:
            ReportSafe.objects.get(identifier=identifier)
            raise ValueError('the report with specified identifier already exists')
        except ObjectDoesNotExist:
            if self.parent.cpu_time is None:
                raise ValueError('safe parent need to be verification report and must have cpu_time')
            report = ReportSafe(
                identifier=identifier, parent=self.parent, root=self.root, verifier_time=self.parent.cpu_time
            )
        if self.archive is not None:
            report.new_archive(REPORT_FILES_ARCHIVE, self.archive)
            report.proof = self.data['proof']
        report.save()

        self.root.safes += 1
        self.root.save()

        self.__collect_attrs(report)
        self.ordered_attrs += self.__save_attrs(report.id, self.data['attrs'])
        report_attrs = self.__get_attrs(report)

        for p in self._parents_branch:
            verdict = Verdict.objects.get_or_create(report=p)[0]
            verdict.safe += 1
            verdict.safe_unassociated += 1
            verdict.save()

            for ra in report_attrs:
                attr_stat = AttrStatistic.objects.get_or_create(report=p, name_id=ra[0], attr_id=ra[1])[0]
                attr_stat.safes += 1
                attr_stat.save()

            ReportComponentLeaf.objects.create(report=p, safe=report)
        ConnectReportWithMarks(report)

    def __create_medium_safe_report(self, identifier):
        try:
            ReportSafe.objects.get(identifier=identifier)
            raise ValueError('the report with specified identifier already exists')
        except ObjectDoesNotExist:
            if self.parent.cpu_time is None:
                raise ValueError('safe parent need to be verification report and must have cpu_time')
            report = ReportSafe.objects.create(
                identifier=identifier, parent=self.parent, root=self.root, verifier_time=self.parent.cpu_time
            )
        if self.archive is not None:
            report.new_archive(REPORT_FILES_ARCHIVE, self.archive)
            report.proof = self.data['proof']
        report.save()

        self.root.safes += 1
        self.root.save()

        self.__collect_attrs(report)
        self.ordered_attrs += self.__save_attrs(report.id, self.data['attrs'])
        report_attrs = self.__get_attrs(report)

        root_report = ReportComponent.objects.get(parent=None, root=self.root)
        if not self.parent.archive:
            report.parent = root_report
            report.save()
        else:
            self.parent.parent = root_report
            self.parent.save()
            verdict = Verdict.objects.get_or_create(report=self.parent)[0]
            verdict.safe += 1
            verdict.safe_unassociated += 1
            verdict.save()
            ReportComponentLeaf.objects.create(report=self.parent, safe=report)

        verdict = Verdict.objects.get_or_create(report=root_report)[0]
        verdict.safe += 1
        verdict.safe_unassociated += 1
        verdict.save()

        for ra in report_attrs:
            attr_stat = AttrStatistic.objects.get_or_create(report=root_report, name_id=ra[0], attr_id=ra[1])[0]
            attr_stat.safes += 1
            attr_stat.save()

        ReportComponentLeaf.objects.create(report=root_report, safe=report)
        ConnectReportWithMarks(report)

    def __create_light_safe_report(self, identifier):
        report = ReportSafe.objects.create(identifier=identifier, parent=self.parent, root=self.root, verifier_time=0)
        self.root.safes += 1
        self.root.save()
        self.__collect_attrs(report)
        self.ordered_attrs += self.__save_attrs(report.id, self.data['attrs'])
        report_attrs = self.__get_attrs(report)
        root_report = ReportComponent.objects.get(parent=None, root=self.root)
        for ra in report_attrs:
            attr_stat = AttrStatistic.objects.get_or_create(report=root_report, name_id=ra[0], attr_id=ra[1])[0]
            attr_stat.safes += 1
            attr_stat.save()

        report.delete()

    def __create_report_unsafe(self, identifier):
        if self.job.weight != JOB_WEIGHT[0][0]:
            self.__create_medium_unsafe_report(identifier)
            return
        try:
            ReportUnsafe.objects.get(identifier=identifier)
            raise ValueError('the report with specified identifier already exists')
        except ObjectDoesNotExist:
            if self.archive is None:
                raise ValueError('unsafe report must contain archive with error trace and source code files')
        if self.parent.cpu_time is None:
            raise ValueError('unsafe parent need to be verification report and must have cpu_time')
        report = ReportUnsafe(
            identifier=identifier, parent=self.parent, root=self.root,
            error_trace=self.data['error trace'], verifier_time=self.parent.cpu_time
        )
        report.new_archive(REPORT_FILES_ARCHIVE, self.archive, True)

        self.__collect_attrs(report)
        self.ordered_attrs += self.__save_attrs(report.id, self.data['attrs'])
        report_attrs = self.__get_attrs(report)

        for p in self._parents_branch:
            verdict = Verdict.objects.get_or_create(report=p)[0]
            verdict.unsafe += 1
            verdict.unsafe_unassociated += 1
            verdict.save()

            for ra in report_attrs:
                attr_stat = AttrStatistic.objects.get_or_create(report=p, name_id=ra[0], attr_id=ra[1])[0]
                attr_stat.unsafes += 1
                attr_stat.save()

            ReportComponentLeaf.objects.create(report=p, unsafe=report)
        ConnectReportWithMarks(report)

    def __create_medium_unsafe_report(self, identifier):
        try:
            ReportUnsafe.objects.get(identifier=identifier)
            raise ValueError('the report with specified identifier already exists')
        except ObjectDoesNotExist:
            if self.archive is None:
                raise ValueError('unsafe report must contain archive with error trace and source code files')
        if self.parent.cpu_time is None:
            raise ValueError('unsafe parent need to be verification report and must have cpu_time')
        report = ReportUnsafe.objects.create(
            identifier=identifier, parent=self.parent, root=self.root,
            error_trace=self.data['error trace'], verifier_time=self.parent.cpu_time
        )
        report.new_archive(REPORT_FILES_ARCHIVE, self.archive, True)

        # Each verification report must have only one unsafe child
        # In other cases unsafe reports will be without attributes
        self.__collect_attrs(report)
        self.ordered_attrs += self.__save_attrs(report.id, self.data['attrs'])
        report_attrs = self.__get_attrs(report)

        root_report = ReportComponent.objects.get(parent=None, root=self.root)
        if not self.parent.archive:
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

        for ra in report_attrs:
            attr_stat = AttrStatistic.objects.get_or_create(report=root_report, name_id=ra[0], attr_id=ra[1])[0]
            attr_stat.unsafes += 1
            attr_stat.save()

        ReportComponentLeaf.objects.create(report=root_report, unsafe=report)
        ConnectReportWithMarks(report)

    def __collect_attrs(self, report):
        attrs_ids = []
        for p in self._parents_branch:
            for ra in p.attrs.order_by('id').values('attr__name__name', 'attr_id'):
                self.ordered_attrs.append(ra['attr__name__name'])
                attrs_ids.append(ra['attr_id'])
        ReportAttr.objects.bulk_create(list(ReportAttr(attr_id=a_id, report=report) for a_id in attrs_ids))

    def __update_parent_resources(self, report):

        def update_total_resources(rep):
            res_set = rep.resources_cache.filter(~Q(component=None)).values_list('cpu_time', 'wall_time', 'memory')
            if len(res_set) > 0:
                try:
                    total_compres = rep.resources_cache.get(component=None)
                except ObjectDoesNotExist:
                    total_compres = ComponentResource()
                    total_compres.report = rep
                total_compres.cpu_time = sum(list(cr[0] for cr in res_set))
                total_compres.wall_time = sum(list(cr[1] for cr in res_set))
                total_compres.memory = max(list(cr[2] for cr in res_set))
                total_compres.save()

        report.resources_cache.get_or_create(component=report.component, defaults={
            'wall_time': report.wall_time, 'cpu_time': report.cpu_time, 'memory': report.memory
        })
        if ReportComponent.objects.filter(parent_id=report.id).count() > 0:
            update_total_resources(report)

        for p in self._parents_branch:
            try:
                compres = p.resources_cache.get(component=report.component)
            except ObjectDoesNotExist:
                compres = ComponentResource(component=report.component, report=p)
            compres.cpu_time += report.cpu_time
            compres.wall_time += report.wall_time
            compres.memory = max(report.memory, compres.memory)
            compres.save()
            update_total_resources(p)

    def __update_light_resources(self, report):
        comp_res = LightResource.objects.get_or_create(report=self.root, component=report.component)[0]
        comp_res.cpu_time += report.cpu_time
        comp_res.wall_time += report.wall_time
        comp_res.memory = max(report.memory, comp_res.memory)
        comp_res.save()

        total_res = LightResource.objects.get_or_create(report=self.root, component=None)[0]
        total_res.cpu_time += report.cpu_time
        total_res.wall_time += report.wall_time
        total_res.memory = max(report.memory, total_res.memory)
        total_res.save()

    def __collapse_reports(self):
        root_report = ReportComponent.objects.get(parent=None, root=self.root)
        reports_to_save = set()
        for u in ReportUnsafe.objects.filter(root=self.root).exclude(parent_id=root_report.id).values('parent_id'):
            reports_to_save.add(u['parent_id'])
        if self.job.weight != JOB_WEIGHT[2][0]:
            for u in ReportSafe.objects.filter(root=self.root).exclude(parent_id=root_report.id).values('parent_id'):
                reports_to_save.add(u['parent_id'])
        ReportComponent.objects.filter(Q(parent=root_report) & ~Q(id__in=reports_to_save)).delete()

    def __get_attrs(self, report):
        report_attrs = []
        if self.job.type in ATTR_STATISTIC:
            for a in ReportAttr.objects.filter(report=report).values('attr__name__name', 'attr__name_id', 'attr_id'):
                if a['attr__name__name'] in ATTR_STATISTIC[self.job.type]:
                    report_attrs.append((a['attr__name_id'], a['attr_id']))
        return report_attrs

    def __save_total_tasks_number(self, tnums):
        if tnums.bt_num == 0:
            tasks_total = (tnums.avtg_total - tnums.avtg_fail - tnums.vtg_fail)
        else:
            tasks_total = (tnums.avtg_total - tnums.avtg_fail - tnums.vtg_fail) * tnums.bt_total / tnums.bt_num
        if tasks_total < 0:
            tasks_total = 0
        self.root.tasks_total = tasks_total
        self.root.save()

    def __attr_children(self, name, val):
        attr_data = []
        if isinstance(val, list):
            for v in val:
                if isinstance(v, dict):
                    nextname = next(iter(v))
                    for n in self.__attr_children(nextname.replace(':', '_'), v[nextname]):
                        if len(name) == 0:
                            new_id = n[0]
                        else:
                            new_id = "%s:%s" % (name, n[0])
                        attr_data.append((new_id, n[1]))
        elif isinstance(val, str):
            attr_data = [(name, val)]
        return attr_data

    def __save_attrs(self, report_id, attrs):
        if not isinstance(attrs, list):
            return []
        attrdata = AttrData()
        attrorder = []
        for attr, value in self.__attr_children('', attrs):
            attrorder.append(attr)
            attrdata.add(report_id, attr, value)
        attrdata.upload()
        return attrorder

    def __is_not_used(self):
        pass


class CollapseReports(object):
    def __init__(self, job):
        self.job = job
        if self.job.weight == JOB_WEIGHT[0][0]:
            self.__collapse()
            self.job.weight = JOB_WEIGHT[1][0]
        elif self.job.weight == JOB_WEIGHT[1][0]:
            self.__collapse()
            self.job.weight = JOB_WEIGHT[2][0]
        else:
            return
        self.job.save()

    def __collapse(self):
        try:
            root_report = ReportComponent.objects.get(parent=None, root__job=self.job)
        except ObjectDoesNotExist:
            return
        reports_to_save = []
        for u in ReportUnsafe.objects.filter(root__job=self.job):
            parent = ReportComponent.objects.get(id=u.parent_id)
            if parent.parent is None:
                continue
            if parent.archive:
                parent.parent = root_report
                parent.save()
                reports_to_save.append(parent.id)
            else:
                u.parent = root_report
                u.save()
        if self.job.weight == JOB_WEIGHT[0][0]:
            for s in ReportSafe.objects.filter(root__job=self.job):
                parent = ReportComponent.objects.get(id=s.parent_id)
                if parent.parent is None:
                    continue
                if parent.archive:
                    parent.parent = root_report
                    parent.save()
                    reports_to_save.append(parent.id)
                else:
                    s.parent = root_report
                    s.save()
        elif self.job.weight == JOB_WEIGHT[1][0]:
            ReportSafe.objects.filter(root__job=self.job).delete()
        ReportUnknown.objects.filter(root__job=self.job).update(parent=root_report)
        if self.job.weight == JOB_WEIGHT[0][0]:
            self.__fill_resources()
        ReportComponent.objects.filter(Q(parent=root_report) & ~Q(id__in=reports_to_save)).delete()
        AttrStatistic.objects.filter(Q(report__root__job=self.job) & ~Q(report=root_report)).delete()
        RecalculateLeaves([self.job])
        RecalculateVerdicts([self.job])
        RecalculateResources([self.job])

    def __fill_resources(self):
        LightResource.objects.filter(report=self.job.reportroot).delete()
        LightResource.objects.bulk_create(list(LightResource(
            report=self.job.reportroot, component=cres.component,
            cpu_time=cres.cpu_time, wall_time=cres.wall_time, memory=cres.memory
        ) for cres in ComponentResource.objects.filter(report__root__job=self.job, report__parent=None)))
