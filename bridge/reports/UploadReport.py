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
from io import BytesIO

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q, F
from django.utils.timezone import now

from bridge.vars import REPORT_ARCHIVE, JOB_WEIGHT, JOB_STATUS, USER_ROLES
from bridge.utils import logger, unique_id

import marks.SafeUtils as SafeUtils
import marks.UnsafeUtils as UnsafeUtils
import marks.UnknownUtils as UnknownUtils

from users.models import Extended
from reports.models import Report, ReportRoot, ReportComponent, ReportSafe, ReportUnsafe, ReportUnknown, Verdict,\
    Component, ComponentUnknown, ComponentResource, ReportAttr, ReportComponentLeaf, Computer, ComponentInstances,\
    CoverageArchive, ErrorTraceSource
from service.models import Task
from reports.utils import AttrData
from service.utils import FinishJobDecision, KleverCoreStartDecision
from tools.utils import RecalculateLeaves, RecalculateVerdicts

from reports.coverage import FillCoverageCache
from reports.etv import GetETV


AVTG_TOTAL_NAME = 'total number of abstract verification task descriptions to be generated in ideal'
AVTG_FAIL_NAME = 'faulty generated abstract verification task descriptions'
VTG_FAIL_NAME = 'faulty processed abstract verification task descriptions'
BT_TOTAL_NAME = 'the number of verification tasks prepared for abstract verification task'


class CheckArchiveError(Exception):
    pass


class UploadReport:
    def __init__(self, job, data, archives=None, attempt=0):
        self.error = None
        self.job = job
        self.archives = archives
        self.attempt = attempt
        self.data = {}
        self.ordered_attrs = []
        try:
            self.__check_data(data)
            self.__check_archives(self.data['id'])
            self.parent = self.__get_parent()
            self._parents_branch = self.__get_parents_branch()
            self.root = self.__get_root_report()
            self.__upload()
        except CheckArchiveError as e:
            logger.info(str(e))
            self.error = 'ZIP error'
        except Exception as e:
            logger.exception(e)
            self.__job_failed(str(e))
            self.error = str(e)

    def __job_failed(self, error=None):
        if 'id' in self.data:
            error = 'The error occurred when uploading the report with id "%s": ' % self.data['id'] + str(error)
        FinishJobDecision(self.job, JOB_STATUS[5][0], error)

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
        if 'name' in data and isinstance(data['name'], str) and len(data['name']) > 20:
            raise ValueError('component name {!r} is too long (max 20 symbols expected)'.format(data['name']))
        if 'data' in data and not isinstance(data['data'], dict):
            raise ValueError('report data must be a dictionary object')

        if data['type'] == 'start':
            if data['id'] == '/':
                if self.attempt == 0:
                    KleverCoreStartDecision(self.job)
                try:
                    self.data.update({
                        'attrs': data['attrs'],
                        'comp': data['comp'],
                    })
                except KeyError as e:
                    raise ValueError("property '%s' is required." % e)
                if 'attr data' in data:
                    self.data['attr data'] = data['attr data']
                    if self.data['attr data'] not in self.archives:
                        raise ValueError("Attr data archive wasn't found in the archives list")
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
                    if 'attr data' in data:
                        self.data['attr data'] = data['attr data']
                        if self.data['attr data'] not in self.archives:
                            raise ValueError("Attr data archive wasn't found in the archives list")
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
                if self.data['log'] not in self.archives:
                    raise ValueError("Log archive wasn't found in the archives list")
        elif data['type'] == 'attrs':
            try:
                self.data['attrs'] = data['attrs']
            except KeyError as e:
                raise ValueError("property '%s' is required." % e)
            if 'attr data' in data:
                self.data['attr data'] = data['attr data']
                if self.data['attr data'] not in self.archives:
                    raise ValueError("Attr data archive wasn't found in the archives list")
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
            if 'attr data' in data:
                self.data['attr data'] = data['attr data']
                if self.data['attr data'] not in self.archives:
                    raise ValueError("Attr data archive wasn't found in the archives list")
            if 'data' in data:
                self.data.update({'data': data['data']})
            if 'comp' in data:
                self.data['comp'] = data['comp']
            if 'log' in data:
                self.data['log'] = data['log']
                if self.data['log'] not in self.archives:
                    raise ValueError("Log archive wasn't found in the archives list")
            if 'coverage' in data:
                self.data['coverage'] = data['coverage']
                if not isinstance(self.data['coverage'], str):
                    raise ValueError("Coverage for verification report must be a string")
                if self.data['coverage'] not in self.archives:
                    raise ValueError("Coverage archive wasn't found in the archives list")
            if 'task identifier' in data:
                try:
                    self.data['task'] = Task.objects.get(id=data['task identifier'])
                except ObjectDoesNotExist:
                    raise ValueError('The task with id "%s" was not found' % data['task identifier'])
            elif 'input files of static verifiers' in data:
                self.data['verifier input'] = data['input files of static verifiers']
                if self.data['verifier input'] not in self.archives:
                    raise ValueError("Archive with input files of static verifiers wasn't found in the archives list")
        elif data['type'] == 'verification finish':
            pass
        elif data['type'] == 'safe':
            try:
                self.data.update({
                    'parent id': data['parent id'],
                    'attrs': data['attrs']
                })
            except KeyError as e:
                raise ValueError("property '%s' is required." % e)
            if 'attr data' in data:
                self.data['attr data'] = data['attr data']
                if self.data['attr data'] not in self.archives:
                    raise ValueError("Attr data archive wasn't found in the archives list")
            if 'proof' in data:
                self.data['proof'] = data['proof']
                if self.data['proof'] not in self.archives:
                    raise ValueError("Proof archive wasn't found in the archives list")
        elif data['type'] == 'unknown':
            try:
                self.data.update({
                    'parent id': data['parent id'],
                    'problem desc': data['problem desc']
                })
            except KeyError as e:
                raise ValueError("property '%s' is required." % e)
            if self.data['problem desc'] not in self.archives:
                raise ValueError("Problem description archive wasn't found in the archives list")
            if 'attrs' in data:
                self.data['attrs'] = data['attrs']
                if 'attr data' in data:
                    self.data['attr data'] = data['attr data']
                    if self.data['attr data'] not in self.archives:
                        raise ValueError("Attr data archive wasn't found in the archives list")
        elif data['type'] == 'unsafe':
            try:
                self.data.update({
                    'parent id': data['parent id'],
                    'error traces': data['error traces'],
                    'sources': data['sources'],
                    'attrs': data['attrs'],
                })
            except KeyError as e:
                raise ValueError("property '%s' is required." % e)
            if 'attr data' in data:
                self.data['attr data'] = data['attr data']
                if self.data['attr data'] not in self.archives:
                    raise ValueError("Attr data archive wasn't found in the archives list")
            if len(self.data['error traces']) == 0:
                raise ValueError("There are no error traces in report")
            if any(x not in self.archives for x in self.data['error traces']):
                raise ValueError("One of the error traces archives wasn't found in the archives list")
            if self.data['sources'] not in self.archives:
                raise ValueError("Error trace sources archive wasn't found in the archives list")
        elif data['type'] == 'data':
            try:
                self.data.update({'data': data['data']})
            except KeyError as e:
                raise ValueError("property '%s' is required." % e)
        elif data['type'] == 'job coverage':
            try:
                self.data['coverage'] = data['coverage']
            except KeyError as e:
                raise ValueError("property '%s' is required." % e)
            if not isinstance(self.data['coverage'], dict):
                raise ValueError("Coverage for component '%s' must be a dictionary" % self.data['id'])
            if any(x not in self.archives for x in self.data['coverage'].values()):
                raise ValueError("One of coverage archives wasn't found in the archives list")
        else:
            raise ValueError("report type is not supported")

    def __check_comp(self, descr):
        self.__is_not_used()
        if not isinstance(descr, list):
            raise ValueError('wrong computer description format')
        for d in descr:
            if not isinstance(d, dict) or len(d) != 1:
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
            'verification': self.__create_verification_report,
            'verification finish': self.__finish_verification_report,
            'unsafe': self.__create_unsafe_reports,
            'safe': self.__create_report_safe,
            'unknown': self.__create_report_unknown,
            'data': self.__update_report_data,
            'job coverage': self.__upload_job_coverage
        }
        identifier = self.job.identifier + self.data['id']
        actions[self.data['type']](identifier)
        if len(self.ordered_attrs) != len(set(self.ordered_attrs)):
            logger.error("Attributes were redefined. List of attributes that should be unique: %s" % self.ordered_attrs)
            raise ValueError("attributes were redefined")

    def __create_report_component(self, identifier):
        try:
            report = ReportComponent.objects.get(identifier=identifier)
            if self.attempt > 0:
                report.start_date = now()
                report.save()
                return
            else:
                raise ValueError('the report with specified identifier already exists')
        except ObjectDoesNotExist:
            report = ReportComponent(
                identifier=identifier, parent=self.parent, root=self.root, start_date=now(), verification=False,
                component=Component.objects.get_or_create(name=self.data['name'] if 'name' in self.data else 'Core')[0]
            )

        save_add_data = (self.job.weight == JOB_WEIGHT[0][0] or self.parent is None or self.parent.parent is None)

        if save_add_data and 'data' in self.data:
            report.new_data('report-data.json', BytesIO(
                json.dumps(self.data['data'], ensure_ascii=False, sort_keys=True, indent=4).encode('utf8')
            ))

        if 'comp' in self.data:
            report.computer = Computer.objects.get_or_create(
                description=json.dumps(self.data['comp'], ensure_ascii=False, sort_keys=True, indent=4)
            )[0]
        else:
            report.computer = self.parent.computer

        report.save()

        if 'attrs' in self.data:
            self.ordered_attrs = self.__save_attrs(report.id, self.data['attrs'])

        if self.job.weight == JOB_WEIGHT[1][0]:
            self.__cut_parents_branch()

        for parent in self._parents_branch:
            try:
                comp_inst = ComponentInstances.objects.get(report=parent, component=report.component)
            except ObjectDoesNotExist:
                comp_inst = ComponentInstances(report=parent, component=report.component)
            comp_inst.in_progress += 1
            comp_inst.total += 1
            comp_inst.save()

        # Reports for other components will be deleted for lightweight job
        if save_add_data:
            ComponentInstances.objects.create(report=report, component=report.component, in_progress=1, total=1)

    def __create_verification_report(self, identifier):
        try:
            ReportComponent.objects.get(identifier=identifier)
            raise ValueError('the report with specified identifier already exists')
        except ObjectDoesNotExist:
            report = ReportComponent(
                identifier=identifier, parent=self.parent, root=self.root, start_date=now(), verification=True,
                component=Component.objects.get_or_create(name=self.data['name'])[0],
                covnum=int('coverage' in self.data)
            )
        if 'data' in self.data and self.job.weight == JOB_WEIGHT[0][0]:
            report.new_data('report-data.json', BytesIO(json.dumps(
                self.data['data'], ensure_ascii=False, sort_keys=True, indent=4
            ).encode('utf8')))

        if 'comp' in self.data:
            report.computer = Computer.objects.get_or_create(
                description=json.dumps(self.data['comp'], ensure_ascii=False, sort_keys=True, indent=4)
            )[0]
        else:
            report.computer = self.parent.computer

        report.cpu_time = int(self.data['resources']['CPU time'])
        report.memory = int(self.data['resources']['memory size'])
        report.wall_time = int(self.data['resources']['wall time'])

        if 'log' in self.data and self.job.weight == JOB_WEIGHT[0][0]:
            report.add_log(REPORT_ARCHIVE['log'], self.archives[self.data['log']])

        if 'task' in self.data:
            with self.data['task'].archive.file as fp:
                report.add_verifier_input(REPORT_ARCHIVE['verifier input'], fp)
        elif 'verifier input' in self.data:
            report.add_verifier_input(REPORT_ARCHIVE['verifier input'], self.archives[self.data['verifier input']])

        report.save()

        if 'coverage' in self.data:
            carch = CoverageArchive(report=report)
            carch.save_archive(REPORT_ARCHIVE['coverage'], self.archives[self.data['coverage']])

        # Check that report archives were successfully saved on disk
        for field_name in ['log', 'verifier_input']:
            arch_name = report.__getattribute__(field_name).name
            if arch_name and not os.path.exists(os.path.join(settings.MEDIA_ROOT, arch_name)):
                report.delete()
                raise CheckArchiveError('Report archive "%s" was not saved' % field_name)

        self.ordered_attrs = self.__save_attrs(report.id, self.data['attrs'])

        if self.job.weight == JOB_WEIGHT[1][0]:
            self.__cut_parents_branch()
        self.__update_parent_resources(report)

        for parent in self._parents_branch:
            try:
                comp_inst = ComponentInstances.objects.get(report=parent, component=report.component)
            except ObjectDoesNotExist:
                comp_inst = ComponentInstances(report=parent, component=report.component)
            comp_inst.in_progress += 1
            comp_inst.total += 1
            comp_inst.save()

        # Other verification reports will be deleted
        if self.job.weight == JOB_WEIGHT[0][0] or report.covnum > 0 or report.verifier_input:
            ComponentInstances.objects.create(report=report, component=report.component, in_progress=1, total=1)
        if report.covnum > 0:
            FillCoverageCache(report)

    def __upload_job_coverage(self, identifier):
        try:
            report = ReportComponent.objects.get(identifier=identifier)
        except ObjectDoesNotExist:
            raise ValueError('updated report does not exist')
        if self.parent is None or self.parent.parent is None:
            report.covnum = len(self.data['coverage'])
            for cov_id in self.data['coverage']:
                carch = CoverageArchive(report=report, identifier=cov_id)
                carch.save_archive(REPORT_ARCHIVE['coverage'], self.archives[self.data['coverage'][cov_id]])
            report.save()
            FillCoverageCache(report)
        else:
            raise ValueError('coverage can be uploaded only for Core and first-level reports')

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

        self.__update_dict_data(report, self.data['data'])

    def __update_dict_data(self, report, new_data):
        if self.job.weight == JOB_WEIGHT[1][0] and report.parent is not None:
            report.save()
            return
        if not isinstance(new_data, dict):
            raise ValueError("report's data must be a dictionary")
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

        save_add_data = (self.job.weight == JOB_WEIGHT[0][0] or self.parent is None or self.parent.parent is None)
        if save_add_data and 'log' in self.data:
            report.add_log(REPORT_ARCHIVE['log'], self.archives[self.data['log']])

        report.finish_date = now()

        if save_add_data and 'data' in self.data:
            # Report is saved after the data is updated
            self.__update_dict_data(report, self.data['data'])
        else:
            report.save()

        if report.log.name and not os.path.exists(os.path.join(settings.MEDIA_ROOT, report.log.name)):
            report.delete()
            raise CheckArchiveError('Report archive "log" was not saved')

        if 'attrs' in self.data:
            self.ordered_attrs = self.__save_attrs(report.id, self.data['attrs'])

        if self.job.weight == JOB_WEIGHT[1][0]:
            self.__cut_parents_branch()
        self.__update_parent_resources(report)

        report_ids = set(r.id for r in self._parents_branch)
        component_id = report.component_id

        if not save_add_data and ReportComponent.objects.filter(parent=report).count() == 0:
            report.delete()
        else:
            report_ids.add(report.id)
        ComponentInstances.objects.filter(report_id__in=report_ids, component_id=component_id, in_progress__gt=0) \
            .update(in_progress=(F('in_progress') - 1))

    def __finish_verification_report(self, identifier):
        try:
            report = ReportComponent.objects.get(identifier=identifier)
        except ObjectDoesNotExist:
            raise ValueError('verification report does not exist')

        if self.job.weight == JOB_WEIGHT[1][0]:
            self.__cut_parents_branch()
            report.parent = self._parents_branch[-1]

        report_ids = set(r.id for r in self._parents_branch)
        component_id = report.component_id

        # I hope that verification reports can't have component reports as its children
        if self.job.weight == JOB_WEIGHT[1][0] and Report.objects.filter(parent=report).count() == 0:
            report.delete()
        else:
            report.finish_date = now()
            report.save()
            report_ids.add(report.id)
        ComponentInstances.objects.filter(report_id__in=report_ids, component_id=component_id, in_progress__gt=0) \
            .update(in_progress=(F('in_progress') - 1))

    def __create_report_unknown(self, identifier):
        try:
            ReportUnknown.objects.get(identifier=identifier)
            raise ValueError('the report with specified identifier already exists')
        except ObjectDoesNotExist:
            report = ReportUnknown(
                identifier=identifier, parent=self.parent, root=self.root,
                component=self.parent.component, problem_description=self.data['problem desc']
            )
        if self.parent.verification:
            report.cpu_time = self.parent.cpu_time
            report.wall_time = self.parent.wall_time
            report.memory = self.parent.memory
        report.add_problem_desc(REPORT_ARCHIVE['problem desc'], self.archives[self.data['problem desc']], True)
        if not os.path.exists(os.path.join(settings.MEDIA_ROOT, report.problem_description.name)):
            report.delete()
            raise CheckArchiveError('Report archive "problem desc" was not saved')
        self.__create_leaf_attrs(report)
        self.__fill_leaf_cache(report)

    def __create_report_safe(self, identifier):
        try:
            ReportSafe.objects.get(identifier=identifier)
            raise ValueError('the report with specified identifier already exists')
        except ObjectDoesNotExist:
            if self.parent.cpu_time is None:
                raise ValueError('safe parent need to be verification report and must have cpu_time')
            report = ReportSafe(
                identifier=identifier, parent=self.parent, root=self.root, cpu_time=self.parent.cpu_time,
                wall_time=self.parent.wall_time, memory=self.parent.memory
            )
        if 'proof' in self.data:
            report.add_proof(REPORT_ARCHIVE['proof'], self.archives[self.data['proof']], True)
            if not os.path.exists(os.path.join(settings.MEDIA_ROOT, report.proof.name)):
                report.delete()
                raise CheckArchiveError('Report archive "proof" was not saved')
        else:
            report.save()
        self.__create_leaf_attrs(report)
        self.__fill_leaf_cache(report)

    def __create_unsafe_reports(self, identifier):
        et_archs = {}
        for arch_name in self.data['error traces']:
            et_archs[arch_name] = self.archives[arch_name]
        res = CheckErrorTraces(et_archs, self.archives[self.data['sources']])

        source = ErrorTraceSource(root=self.root)
        source.add_sources(REPORT_ARCHIVE['sources'], self.archives[self.data['sources']], True)

        cnt = 1
        unsafes = []
        for arch_name in self.data['error traces']:
            try:
                ReportUnsafe.objects.get(identifier=identifier + '/{0}'.format(cnt))
                raise ValueError('the report with specified identifier already exists')
            except ObjectDoesNotExist:
                if self.parent.cpu_time is None:
                    raise ValueError('unsafe parent need to be verification report and must have cpu_time')
                report = ReportUnsafe(
                    identifier=identifier + '/{0}'.format(cnt), parent=self.parent, root=self.root,
                    trace_id=unique_id(), source=source,
                    cpu_time=self.parent.cpu_time, wall_time=self.parent.wall_time, memory=self.parent.memory
                )

            report.add_trace(REPORT_ARCHIVE['error trace'], self.archives[arch_name], True)
            if not os.path.exists(os.path.join(settings.MEDIA_ROOT, report.error_trace.name)):
                report.delete()
                raise CheckArchiveError('Report archive "error trace" was not saved')

            self.__create_leaf_attrs(report, res.add_attrs.get(arch_name))
            unsafes.append(report)
            cnt += 1
        self.__fill_unsafes_cache(unsafes)

    def __create_leaf_attrs(self, leaf, add_attrs=None):
        self.ordered_attrs = []
        parent_attrs = []
        for p in self._parents_branch:
            for ra in p.attrs.order_by('id').select_related('attr__name'):
                self.ordered_attrs.append(ra.attr.name.name)
                parent_attrs.append(ReportAttr(
                    attr_id=ra.attr_id, report=leaf, compare=ra.compare, associate=ra.associate, data_id=ra.data_id
                ))
        ReportAttr.objects.bulk_create(parent_attrs)

        if 'attrs' in self.data:
            self.ordered_attrs += self.__save_attrs(leaf.id, self.data['attrs'])
        if add_attrs is not None:
            self.ordered_attrs += self.__save_attrs(leaf.id, add_attrs)

    def __fill_unsafes_cache(self, reports):
        if self.job.weight == JOB_WEIGHT[1][0]:
            self.__cut_parents_branch()
            if self.parent.verifier_input or self.parent.covnum > 0:
                # After verification finish report self.parent.parent will be Core/first-level report
                self._parents_branch.append(self.parent)
            else:
                ReportUnsafe.objects.filter(id__in=list(r.id for r in reports)).update(parent=self._parents_branch[-1])

        leaves = []
        for p in self._parents_branch:
            verdict = Verdict.objects.get_or_create(report=p)[0]
            verdict.unsafe += len(reports)
            verdict.unsafe_unassociated += len(reports)
            verdict.save()
            leaves.extend(list(ReportComponentLeaf(report=p, unsafe=unsafe) for unsafe in reports))
        ReportComponentLeaf.objects.bulk_create(leaves)
        for leaf in reports:
            UnsafeUtils.ConnectReport(leaf)
        UnsafeUtils.RecalculateTags(reports)

    def __fill_leaf_cache(self, leaf):
        if self.job.weight == JOB_WEIGHT[1][0]:
            self.__cut_parents_branch()
            if self.parent.verifier_input or self.parent.covnum > 0:
                # After verification finish report self.parent.parent will be Core/first-level report
                self._parents_branch.append(self.parent)
            else:
                leaf.parent = self._parents_branch[-1]
                leaf.save()

        if self.data['type'] == 'unknown':
            self.__fill_unknown_cache(leaf)
            UnknownUtils.ConnectReport(leaf)
        elif self.data['type'] == 'safe':
            self.__fill_safe_cache(leaf)
            if self.job.safe_marks:
                SafeUtils.ConnectReport(leaf)
                SafeUtils.RecalculateTags([leaf])

    def __cut_parents_branch(self):
        if len(self._parents_branch) > 1:
            # Just Core and first-level report
            self._parents_branch = self._parents_branch[:2]
        elif len(self._parents_branch) > 0:
            # Just Core report
            self._parents_branch = self._parents_branch[:1]

    def __fill_unknown_cache(self, unknown):
        for p in self._parents_branch:
            verdict = Verdict.objects.get_or_create(report=p)[0]
            verdict.unknown += 1
            verdict.save()
            comp_unknown = ComponentUnknown.objects.get_or_create(report=p, component=unknown.component)[0]
            comp_unknown.number += 1
            comp_unknown.save()
            ReportComponentLeaf.objects.create(unknown=unknown, report=p)

    def __fill_safe_cache(self, safe):
        for p in self._parents_branch:
            verdict = Verdict.objects.get_or_create(report=p)[0]
            verdict.safe += 1
            verdict.safe_unassociated += 1
            verdict.save()
            ReportComponentLeaf.objects.create(report=p, safe=safe)

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

    def __attr_children(self, name, value, compare=False, associate=False, data=None):
        attr_data = []
        if isinstance(value, list):
            for v in value:
                if not isinstance(v, dict) or 'name' not in v or 'value' not in v:
                    raise ValueError('Wrong format of report attribute')
                for n in self.__attr_children(v['name'].replace(':', '_'), v['value'], v.get('compare', False),
                                              v.get('associate', False), v.get('data')):
                    attr_data.append(("%s:%s" % (name, n[0]) if len(name) > 0 else n[0], n[1], n[2], n[3], n[4]))
        elif isinstance(value, str):
            attr_data = [(name, value, compare, associate, data)]
        else:
            raise ValueError('Wrong format of report attributes')
        return attr_data

    def __save_attrs(self, report_id, attrs):
        if not isinstance(attrs, list):
            return []
        attr_archive = None
        if 'attr data' in self.data:
            attr_archive = self.archives[self.data['attr data']]
        attrdata = AttrData(self.root.id, attr_archive)
        attrorder = []
        for attr, value, compare, associate, data in self.__attr_children('', attrs):
            attrorder.append(attr)
            attrdata.add(report_id, attr, value, compare, associate, data)
        attrdata.upload()
        if isinstance(self.parent, ReportComponent) and self.data['type'] in {'start', 'attrs', 'verification'}:
            names = set(x[0] for x in ReportAttr.objects.filter(report_id=report_id).values_list('attr__name_id'))
            for parent in self._parents_branch:
                if parent.attrs.filter(attr__name_id__in=names).count() > 0:
                    raise ValueError("The report has redefined parent's attributes")
        return attrorder

    def __check_archives(self, report_id):
        if self.archives is None:
            self.archives = {}
        for arch in self.archives.values():
            if not zipfile.is_zipfile(arch) or zipfile.ZipFile(arch).testzip():
                raise CheckArchiveError('The archive "%s" of report "%s" is not a ZIP file' % (arch.name, report_id))

    def __is_not_used(self):
        pass


class CollapseReports:
    def __init__(self, job):
        self.job = job
        if self.job.weight != JOB_WEIGHT[0][0]:
            return
        self.__collapse()
        self.job.weight = JOB_WEIGHT[1][0]
        self.job.save()

    def __collapse(self):
        root = self.job.reportroot
        sub_jobs = {}
        sj_reports = set()
        rel_reports = [
            'safe__parent__reportcomponent', 'unsafe__parent__reportcomponent', 'unknown__parent__reportcomponent'
        ]

        for leaf in ReportComponentLeaf.objects.filter(report__root=root, report__parent__parent=None)\
                .exclude(report__parent=None).select_related(*rel_reports):
            if leaf.report_id not in sub_jobs:
                sub_jobs[leaf.report_id] = set()
            for fname in ['safe', 'unsafe', 'unknown']:
                report = getattr(leaf, fname)
                if report:
                    sj_reports.add(report.id)
                    if report.parent.reportcomponent.covnum > 0 or report.parent.reportcomponent.verifier_input:
                        sub_jobs[leaf.report_id].add(report.parent_id)
                    else:
                        sub_jobs[leaf.report_id].add(report.id)
                    break
        for sj_id in sub_jobs:
            Report.objects.filter(id__in=sub_jobs[sj_id]).update(parent_id=sj_id)

        core_id = ReportComponent.objects.get(root=root, parent=None).id
        core_reports = set()
        for leaf in ReportComponentLeaf.objects.filter(report__root=root, report_id=core_id)\
                .select_related(*rel_reports):
            for fname in ['safe', 'unsafe', 'unknown']:
                report = getattr(leaf, fname)
                if report:
                    if report.id in sj_reports:
                        break
                    if report.parent.reportcomponent.covnum > 0 or report.parent.reportcomponent.verifier_input:
                        core_reports.add(report.parent_id)
                    else:
                        core_reports.add(report.id)
                    break
        Report.objects.filter(id__in=core_reports).update(parent_id=core_id)

        ReportComponent.objects.filter(root=root, verifier_input='', covnum=0)\
            .exclude(id__in=set(sub_jobs) | {core_id}).delete()

        RecalculateLeaves([root])
        RecalculateVerdicts([root])


class CheckErrorTraces:
    def __init__(self, traces, sources):
        self._traces = traces
        self._sources = sources
        self.add_attrs = {}
        self.__check_traces()
        self.__exit()

    def __check_traces(self):
        manager = Extended.objects.filter(role=USER_ROLES[2][0]).first()
        if not manager:
            raise ValueError("Can't check error traces without manager in the system")

        files = self.__get_list_of_sources()
        for tr_name in self._traces:
            res = GetETV(self.__read_trace(tr_name), manager.user)

            if 'attrs' in res.data:
                self.add_attrs[tr_name] = res.data['attrs']
            if 'files' not in res.data:
                raise ValueError('Wrong format of error trace')

            trace_files = set(f[1:] if f.startswith('/') else f for f in res.data['files'])
            if any(x not in files for x in trace_files):
                raise ValueError("Sources doesn't have needed source for error trace")

    def __read_trace(self, trace_name):
        with zipfile.ZipFile(self._traces[trace_name], mode='r') as zfp:
            return zfp.read('error trace.json').decode('utf8')

    def __get_list_of_sources(self):
        with zipfile.ZipFile(self._sources, mode='r') as zfp:
            return zfp.namelist()

    def __exit(self):
        for arch in self._traces:
            self._traces[arch].seek(0)
        self._sources.seek(0)
