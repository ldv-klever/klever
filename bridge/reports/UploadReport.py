import os
import json
import tarfile
from io import BytesIO
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.core.files import File as NewFile
from django.db.models import Q
from django.utils.timezone import now
from bridge.vars import JOB_STATUS
from bridge.utils import file_checksum
from reports.models import *
from reports.utils import save_attrs
from marks.utils import ConnectReportWithMarks
from service.utils import KleverCoreFinishDecision, KleverCoreStartDecision


class UploadReport(object):

    def __init__(self, job, data, archive=None):
        self.job = job
        self.archive = archive
        self.data = {}
        self.ordered_attrs = []
        self.error = self.__check_data(data)
        if self.error is not None:
            self.__job_failed(self.error)
            return
        self.parent = self.__get_parent()
        if self.error is not None:
            self.__job_failed(self.error)
            return
        self.root = self.__get_root_report()
        if self.error is not None:
            self.__job_failed(self.error)
            return
        self.__upload()
        if self.error is not None:
            self.__job_failed(self.error)

    def __job_failed(self, error=None):
        if 'id' in self.data:
            error = 'Report with id "%s" has led to fail. ' + error
        KleverCoreFinishDecision(self.job, error)

    def __check_data(self, data):
        if not isinstance(data, dict):
            return 'Data is not a dictionary'
        if 'type' not in data or 'id' not in data or not isinstance(data['id'], str) or len(data['id']) == 0:
            return 'Type and id are required or have wrong format'
        if 'parent id' in data and not isinstance(data['parent id'], str):
            return 'Parent id has wrong format'

        if 'resources' in data:
            if not isinstance(data['resources'], dict) \
                    or any(x not in data['resources'] for x in ['wall time', 'CPU time', 'memory size']):
                return 'Resources has wrong format: %s' % json.dumps(data['resources'])

        self.data = {'type': data['type'], 'id': data['id']}
        if 'desc' in data:
            self.data['description'] = data['desc']
        if 'comp' in data:
            err = self.__check_comp(data['comp'])
            if err is not None:
                return err
        if 'name' in data and isinstance(data['name'], str) and len(data['name']) > 15:
            return 'Component name is too long (max 15 symbols expected)'

        if data['type'] == 'start':
            if data['id'] == '/':
                result = KleverCoreStartDecision(self.job)
                if result.error is not None:
                    return result.error
                try:
                    self.data.update({
                        'attrs': data['attrs'],
                        'comp': data['comp'],
                    })
                except KeyError as e:
                    return "Property '%s' is required." % e
            else:
                try:
                    self.data.update({
                        'parent id': data['parent id'],
                        'name': data['name']
                    })
                except KeyError as e:
                    return "Property '%s' is required." % e
                if 'attrs' in data:
                    self.data['attrs'] = data['attrs']
                if 'comp' in data:
                    self.data['comp'] = data['comp']
        elif data['type'] == 'finish':
            try:
                self.data.update({
                    'log': data['log'],
                    'data': data['data'],
                    'resources': data['resources'],
                })
            except KeyError as e:
                return "Property '%s' is required." % e
        elif data['type'] == 'attrs':
            try:
                self.data['attrs'] = data['attrs']
            except KeyError as e:
                return "Property '%s' is required." % e
        elif data['type'] == 'verification':
            try:
                self.data.update({
                    'parent id': data['parent id'],
                    'attrs': data['attrs'],
                    'name': data['name'],
                    'resources': data['resources'],
                    'log': data['log'],
                    'data': data['data'],
                })
            except KeyError as e:
                return "Property '%s' is required." % e
            if 'comp' in data:
                self.data['comp'] = data['comp']
        elif data['type'] == 'safe':
            try:
                self.data.update({
                    'parent id': data['parent id'],
                    'proof': data['proof'],
                    'attrs': data['attrs'],
                })
            except KeyError as e:
                return "Property '%s' is required." % e
        elif data['type'] == 'unknown':
            try:
                self.data.update({
                    'parent id': data['parent id'],
                    'problem desc': data['problem desc']
                })
            except KeyError as e:
                return "Property '%s' is required." % e
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
                return "Property '%s' is required." % e
        else:
            return "Report type is not supported"
        return None

    def __check_comp(self, descr):
        self.ccc = 0
        if not isinstance(descr, list):
            return 'Wrong computer description format'
        for d in descr:
            if not isinstance(d, dict):
                return 'Wrong computer description format'
            if len(d) != 1:
                return 'Wrong computer description format'
            if not isinstance(d[next(iter(d))], str) and not isinstance(d[next(iter(d))], int):
                return 'Wrong computer description format'
        return None

    def __get_root_report(self):
        try:
            return self.job.reportroot
        except ObjectDoesNotExist:
            self.error = "Can't find report root"
            return None

    def __get_parent(self):
        if 'parent id' in self.data:
            if self.data['parent id'] == '/':
                try:
                    return ReportComponent.objects.get(root=self.job.reportroot, identifier=self.job.identifier)
                except ObjectDoesNotExist:
                    self.error = 'Report parent was not found'
            else:
                try:
                    return ReportComponent.objects.get(
                        root=self.job.reportroot,
                        identifier__endswith=('##' + self.data['parent id'])
                    )
                except ObjectDoesNotExist:
                    self.error = 'Report parent was not found'
                except MultipleObjectsReturned:
                    self.error = 'Identifiers are not unique'
        elif self.data['id'] == '/':
            return None
        else:
            try:
                curr_report = ReportComponent.objects.get(
                    identifier__startswith=self.job.identifier,
                    identifier__endswith=("##%s" % self.data['id'])
                )
                return ReportComponent.objects.get(pk=curr_report.parent_id)
            except ObjectDoesNotExist:
                self.error = 'Report parent was not found'
        return None

    def __upload(self):
        actions = {
            'start': self.__create_report_component,
            'finish': self.__finish_report_component,
            'attrs': self.__update_attrs,
            'verification': self.__create_report_component,
            'unsafe': self.__create_report_unsafe,
            'safe': self.__create_report_safe,
            'unknown': self.__create_report_unknown
        }
        if self.parent is None:
            identifier = self.job.identifier
        else:
            identifier = "%s##%s" % (self.parent.identifier, self.data['id'])
        actions[self.data['type']](identifier)
        if self.error is None:
            if len(self.ordered_attrs) != len(set(self.ordered_attrs)) \
                    and self.data['type'] not in ['safe', 'unsafe', 'unknown']:
                self.__job_failed("Attributes for the component report with id '%s' are not unique" % self.data['id'])

    def __create_report_component(self, identifier):
        try:
            ReportComponent.objects.get(identifier=identifier)
            self.error = 'The report with specified identifier already exists'
            return
        except ObjectDoesNotExist:
            report = ReportComponent(
                identifier=identifier,
                parent=self.parent,
                root=self.root,
                start_date=now(),
                data=self.data['data'].encode('utf8') if 'data' in self.data else None,
                component=Component.objects.get_or_create(name=self.data['name'] if 'name' in self.data else 'Core')[0],
                description=self.data['description'].encode('utf8') if 'description' in self.data else None
            )

        if self.data['type'] == 'verification':
            report.finish_date = report.start_date

        if 'comp' in self.data:
            report.computer = Computer.objects.get_or_create(description=json.dumps(self.data['comp']))[0]
        else:
            report.computer = self.parent.computer

        if 'resources' in self.data:
            report.cpu_time = int(self.data['resources']['CPU time'])
            report.memory = int(self.data['resources']['memory size'])
            report.wall_time = int(self.data['resources']['wall time'])
        if 'log' in self.data:
            uf = UploadReportFiles(self.archive, log=self.data['log'])
            if uf.log is None:
                self.error = 'The report log was not found in archive'
                return
            report.log = uf.log

        report.save()

        if 'attrs' in self.data:
            self.ordered_attrs = save_attrs(report, self.data['attrs'])

        if 'resources' in self.data:
            self.__update_parent_resources(report)

    def __update_attrs(self, identifier):
        try:
            report = ReportComponent.objects.get(identifier=identifier)
            self.ordered_attrs = save_attrs(report, self.data['attrs'])
        except ObjectDoesNotExist:
            self.error = 'Updated report does not exist'

    def __finish_report_component(self, identifier):
        try:
            report = ReportComponent.objects.get(identifier=identifier)
        except ObjectDoesNotExist:
            self.error = 'Updated report does not exist'
            return
        if report.finish_date is not None:
            self.error = 'The component is finished already (there was finish report earlier)'

        report.cpu_time = int(self.data['resources']['CPU time'])
        report.memory = int(self.data['resources']['memory size'])
        report.wall_time = int(self.data['resources']['wall time'])
        if 'log' in self.data:
            uf = UploadReportFiles(self.archive, log=self.data['log'])
            if uf.log is None:
                self.error = 'The report log was not found in archive'
                return
            report.log = uf.log
        report.data = self.data['data'].encode('utf8')
        if 'description' in self.data:
            report.description = self.data['description'].encode('utf8')
        report.finish_date = now()
        report.save()

        if 'attrs' in self.data:
            self.ordered_attrs = save_attrs(report, self.data['attrs'])
        self.__update_parent_resources(report)

        if self.data['id'] == '/':
            for rep in ReportComponent.objects.filter(root__job=self.job):
                if len(ReportComponent.objects.filter(parent_id=rep.pk)) == 0:
                    rep.resources_cache.filter(component=None).delete()
            if len(ReportComponent.objects.filter(finish_date=None, root=self.root)):
                self.__job_failed("There are unfinished reports")
            elif self.job.status != JOB_STATUS[5][0]:
                KleverCoreFinishDecision(self.job)

    def __create_report_unknown(self, identifier):
        try:
            ReportUnknown.objects.get(identifier=identifier)
            self.error = 'The report with specified identifier already exists'
            return
        except ObjectDoesNotExist:
            report = ReportUnknown(
                identifier=identifier,
                parent=self.parent,
                root=self.root,
                description=self.data['description'].encode('utf8') if 'description' in self.data else None,
                component=self.parent.component
            )

        uf = UploadReportFiles(self.archive, file_name=self.data['problem desc'])
        if uf.file_content is None:
            self.error = 'The unknown report problem description was not found in the archive'
            return
        report.problem_description = uf.file_content
        report.save()

        self.__collect_attrs(report)

        parent = self.parent
        while parent is not None:
            verdict = Verdict.objects.get_or_create(report=parent)[0]
            verdict.unknown += 1
            verdict.save()

            comp_unknown = ComponentUnknown.objects.get_or_create(report=parent, component=report.component)[0]
            comp_unknown.number += 1
            comp_unknown.save()

            ReportComponentLeaf.objects.create(report=parent, unknown=report)
            try:
                parent = ReportComponent.objects.get(pk=parent.parent_id)
            except ObjectDoesNotExist:
                parent = None
        ConnectReportWithMarks(report)

    def __create_report_safe(self, identifier):
        try:
            ReportSafe.objects.get(identifier=identifier)
            self.error = 'The report with specified identifier already exists'
            return
        except ObjectDoesNotExist:
            report = ReportSafe(
                identifier=identifier,
                parent=self.parent,
                root=self.root,
                description=self.data['description'].encode('utf8') if 'description' in self.data else None
            )

        uf = UploadReportFiles(self.archive, file_name=self.data['proof'])
        if uf.file_content is None:
            self.error = 'The safe report proof was not found in teh archive'
            return
        report.proof = uf.file_content
        report.save()

        self.__collect_attrs(report)
        self.ordered_attrs += save_attrs(report, self.data['attrs'])

        parent = self.parent
        while parent is not None:
            verdict = Verdict.objects.get_or_create(report=parent)[0]
            verdict.safe += 1
            verdict.safe_unassociated += 1
            verdict.save()

            ReportComponentLeaf.objects.create(report=parent, safe=report)
            try:
                parent = ReportComponent.objects.get(pk=parent.parent_id)
            except ObjectDoesNotExist:
                parent = None
        ConnectReportWithMarks(report)

    def __create_report_unsafe(self, identifier):
        try:
            ReportUnsafe.objects.get(identifier=identifier)
            self.error = 'The report with specified identifier already exists'
            return
        except ObjectDoesNotExist:
            report = ReportUnsafe(
                identifier=identifier,
                parent=self.parent,
                root=self.root,
                description=self.data['description'].encode('utf8') if 'description' in self.data else None
            )

        uf = UploadReportFiles(self.archive, file_name=self.data['error trace'], need_other=True)
        if uf.file_content is None:
            self.error = 'The unsafe error trace was not found in the archive'
            return
        report.error_trace = uf.file_content
        report.save()

        for src_f in uf.other_files:
            ETVFiles.objects.get_or_create(file=src_f['file'], name=src_f['name'], unsafe=report)

        self.__collect_attrs(report)
        self.ordered_attrs += save_attrs(report, self.data['attrs'])

        parent = self.parent
        while parent is not None:
            verdict = Verdict.objects.get_or_create(report=parent)[0]
            verdict.unsafe += 1
            verdict.unsafe_unassociated += 1
            verdict.save()

            ReportComponentLeaf.objects.create(report=parent, unsafe=report)
            try:
                parent = ReportComponent.objects.get(pk=parent.parent_id)
            except ObjectDoesNotExist:
                parent = None
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


class UploadReportFiles(object):
    def __init__(self, archive, log=None, file_name=None, need_other=False):
        self.log = None
        self.file_content = None
        self.need_other = need_other
        self.other_files = []
        self.__read_archive(archive, log, file_name)

    def __read_archive(self, archive, logname, report_filename):
        if archive is None:
            return
        inmemory = BytesIO(archive.read())
        zipfile = tarfile.open(fileobj=inmemory, mode='r')
        for f in zipfile.getmembers():
            file_name = f.name
            if f.isreg():
                file_obj = zipfile.extractfile(f)
                if logname is not None and file_name == logname:
                    check_sum = file_checksum(file_obj)
                    try:
                        db_file = File.objects.get(hash_sum=check_sum)
                    except ObjectDoesNotExist:
                        db_file = File()
                        db_file.file.save(os.path.basename(file_name), NewFile(file_obj))
                        db_file.hash_sum = check_sum
                        db_file.save()
                    self.log = db_file
                elif report_filename is not None and file_name == report_filename:
                    self.file_content = file_obj.read()
                elif self.need_other:
                    check_sum = file_checksum(file_obj)
                    try:
                        db_file = File.objects.get(hash_sum=check_sum)
                    except ObjectDoesNotExist:
                        db_file = File()
                        db_file.file.save(os.path.basename(file_name), NewFile(file_obj))
                        db_file.hash_sum = check_sum
                        db_file.save()
                    self.other_files.append({'name': file_name, 'file': db_file})
