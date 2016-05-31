import os
import re
import json
import tarfile
from io import BytesIO
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.utils.translation import ugettext_lazy as _, override
from django.utils.timezone import datetime, pytz
from bridge.vars import JOB_CLASSES, FORMAT, JOB_STATUS
from bridge.utils import logger, file_get_or_create
from jobs.models import JOBFILE_DIR
from jobs.utils import create_job, update_job, change_job_status
from reports.UploadReport import UploadReportFiles
from reports.models import *
from reports.utils import AttrData

ET_FILE = 'unsafe-error-trace.graphml'
REPORT_LOG_FILE = 'report.log'


class KleverCoreDownloadJob(object):
    def __init__(self, job):
        self.error = None
        self.tarname = 'VJ__' + job.identifier + '.tar.gz'
        self.memory = BytesIO()
        self.__create_tar(job)

    def __create_tar(self, job):
        last_version = job.versions.get(version=job.version)

        def write_file_str(jobtar, file_name, file_content):
            file_content = file_content.encode('utf-8')
            t = tarfile.TarInfo(file_name)
            t.size = len(file_content)
            jobtar.addfile(t, BytesIO(file_content))

        files_for_tar = []
        for f in last_version.filesystem_set.all():
            if len(f.children.all()) == 0:
                src = None
                if f.file is not None:
                    src = os.path.join(settings.MEDIA_ROOT, f.file.file.name)
                file_path = f.name
                file_parent = f.parent
                while file_parent is not None:
                    file_path = os.path.join(file_parent.name, file_path)
                    file_parent = file_parent.parent
                files_for_tar.append({
                    'path': os.path.join('root', file_path),
                    'src': src
                })

        jobtar_obj = tarfile.open(fileobj=self.memory, mode='w:gz')
        write_file_str(jobtar_obj, 'format', str(job.format))
        for job_class in JOB_CLASSES:
            if job_class[0] == job.type:
                with override('en'):
                    write_file_str(jobtar_obj, 'class', job_class[1])
                break
        for f in files_for_tar:
            if f['src'] is None:
                folder = tarfile.TarInfo(f['path'])
                folder.type = tarfile.DIRTYPE
                jobtar_obj.addfile(folder)
            else:
                jobtar_obj.add(f['src'], f['path'])
        jobtar_obj.close()


class DownloadJob(object):

    def __init__(self, job):
        self.tarname = ''
        self.job = job
        self.memory = BytesIO()
        self.error = None
        self.__create_tar()

    def __create_tar(self):

        files_in_tar = {}
        self.tarname = 'Job-%s-%s.tar.gz' % (self.job.identifier[:10], self.job.type)
        jobtar_obj = tarfile.open(fileobj=self.memory, mode='w:gz')

        def write_file_str(file_name, file_content):
            file_content = file_content.encode('utf-8')
            t = tarfile.TarInfo(file_name)
            t.size = len(file_content)
            jobtar_obj.addfile(t, BytesIO(file_content))

        for jobversion in self.job.versions.all():
            filedata = []
            for f in jobversion.filesystem_set.all():
                filedata_element = {
                    'pk': f.pk,
                    'parent': f.parent_id,
                    'name': f.name,
                    'file': None
                }
                if f.file is not None:
                    filedata_element['file'] = f.file.pk
                    if f.file.pk not in files_in_tar:
                        files_in_tar[f.file.pk] = f.file.file.name
                        jobtar_obj.add(os.path.join(settings.MEDIA_ROOT, f.file.file.name), f.file.file.name)
                filedata.append(filedata_element)
            version_data = {
                'filedata': filedata,
                'description': jobversion.description,
                'name': jobversion.name,
                'global_role': jobversion.global_role,
                'comment': jobversion.comment,
            }
            write_file_str('version-%s' % jobversion.version, json.dumps(version_data))

        self.__add_safe_files(jobtar_obj)
        self.__add_unsafe_files(jobtar_obj)
        self.__add_unknown_files(jobtar_obj)
        self.__add_component_files(jobtar_obj)
        common_data = {
            'format': str(self.job.format),
            'type': str(self.job.type),
            'status': self.job.status,
            'filedata': json.dumps(files_in_tar),
            'reports': ReportsData(self.job).reports
        }
        write_file_str('jobdata', json.dumps(common_data))
        jobtar_obj.close()

    def __add_unsafe_files(self, jobtar):
        for unsafe in ReportUnsafe.objects.filter(root__job=self.job):
            memory = BytesIO()
            tarobj = tarfile.open(fileobj=memory, mode='w:gz')
            for f in unsafe.files.all():
                tarobj.add(os.path.join(settings.MEDIA_ROOT, f.file.file.name), arcname=f.name)
            tarobj.add(os.path.join(settings.MEDIA_ROOT, unsafe.error_trace.file.name), arcname=ET_FILE)
            tarobj.close()
            memory.seek(0)
            tarname = '%s.tar.gz' % unsafe.pk
            tinfo = tarfile.TarInfo(os.path.join('Unsafes', tarname))
            tinfo.size = memory.getbuffer().nbytes
            jobtar.addfile(tinfo, memory)

    def __add_safe_files(self, jobtar):
        for safe in ReportSafe.objects.filter(root__job=self.job):
            jobtar.add(
                os.path.join(settings.MEDIA_ROOT, safe.proof.file.name),
                arcname=os.path.join('Safes', str(safe.pk))
            )

    def __add_unknown_files(self, jobtar):
        for unknown in ReportUnknown.objects.filter(root__job=self.job):
            jobtar.add(
                os.path.join(settings.MEDIA_ROOT, unknown.problem_description.file.name),
                arcname=os.path.join('Unknowns', str(unknown.pk))
            )

    def __add_component_files(self, jobtar):
        for report in ReportComponent.objects.filter(Q(root__job=self.job) & ~Q(log=None)):
            memory = BytesIO()
            tarobj = tarfile.open(fileobj=memory, mode='w:gz')
            for f in report.files.all():
                tarobj.add(os.path.join(settings.MEDIA_ROOT, f.file.file.name), arcname=f.name)
            tarobj.add(os.path.join(settings.MEDIA_ROOT, report.log.file.name), arcname=REPORT_LOG_FILE)
            tarobj.close()
            memory.seek(0)
            tarname = '%s.tar.gz' % report.pk
            tinfo = tarfile.TarInfo(os.path.join('Components', tarname))
            tinfo.size = memory.getbuffer().nbytes
            jobtar.addfile(tinfo, memory)


class ReportsData(object):
    def __init__(self, job):
        self.job = job
        self.reports = json.dumps(self.__reports_data())

    def __report_component_data(self, report):
        self.ccc = 0

        def get_date(d):
            return [d.year, d.month, d.day, d.hour, d.minute, d.second, d.microsecond] if d is not None else None

        data = None
        if report.data is not None:
            with report.data.file as fp:
                data = fp.read().decode('utf8')
        return {
            'pk': report.pk,
            'parent': report.parent_id,
            'identifier': report.identifier,
            'computer': report.computer.description,
            'component': report.component.name,
            'resource': {
                'cpu_time': report.cpu_time,
                'wall_time': report.wall_time,
                'memory': report.memory,
            } if all(x is not None for x in [report.cpu_time, report.wall_time, report.memory]) else None,
            'start_date': get_date(report.start_date),
            'finish_date': get_date(report.finish_date),
            'data': data,
            'attrs': list((ra.attr.name.name, ra.attr.value) for ra in report.attrs.order_by('id'))
        }

    def __report_leaf_data(self, report):
        self.ccc = 0
        return {
            'pk': report.pk,
            'parent': report.parent_id,
            'identifier': report.identifier,
            'attrs': list((ra.attr.name.name, ra.attr.value) for ra in report.attrs.order_by('id'))
        }

    def __reports_data(self):
        reports = []
        try:
            main_report = ReportComponent.objects.get(Q(parent=None, root__job=self.job) & ~Q(finish_date=None))
        except ObjectDoesNotExist:
            return reports
        reports.append(self.__report_component_data(main_report))
        children = list(ReportComponent.objects.filter(parent_id=main_report.pk))
        while len(children) > 0:
            children_ids = []
            for ch in children:
                reports.append(self.__report_component_data(ch))
                children_ids.append(ch.pk)
            children = list(ReportComponent.objects.filter(parent_id__in=children_ids))
        reports.append('safes')
        for safe in ReportSafe.objects.filter(root__job=self.job):
            reports.append(self.__report_leaf_data(safe))
        reports.append('unsafes')
        for unsafe in ReportUnsafe.objects.filter(root__job=self.job):
            reports.append(self.__report_leaf_data(unsafe))
        reports.append('unknowns')
        for unknown in ReportUnknown.objects.filter(root__job=self.job):
            reports.append(self.__report_leaf_data(unknown))
        return reports


class UploadJob(object):
    def __init__(self, parent, user, job_dir):
        self.parent = parent
        self.job = None
        self.user = user
        self.job_dir = job_dir
        self.err_message = self.__create_job_from_tar()

    def __create_job_from_tar(self):
        jobdata = None
        files_in_db = {}
        versions_data = {}
        report_files = {}
        for dir_path, dir_names, file_names in os.walk(self.job_dir):
            for file_name in file_names:
                if file_name == 'jobdata':
                    try:
                        with open(os.path.join(dir_path, file_name), encoding='utf8') as fp:
                            jobdata = json.load(fp)
                    except Exception as e:
                        logger.exception("Can't parse jobdata: %s" % e, stack_info=True)
                        return _("The job archive is corrupted")
                elif dir_path.endswith(JOBFILE_DIR):
                    try:
                        files_in_db['/'.join([JOBFILE_DIR, file_name])] = file_get_or_create(
                            open(os.path.join(dir_path, file_name), mode='rb'),
                            file_name, True
                        )[1]
                    except Exception as e:
                        logger.exception("Can't save job files to DB: %s" % e, stack_info=True)
                        return _("Creating job's file failed")
                elif file_name.startswith('version-'):
                    version_id = int(file_name.replace('version-', ''))
                    with open(os.path.join(dir_path, file_name), encoding='utf8') as fp:
                        versions_data[version_id] = json.load(fp)
                elif dir_path.endswith('Unsafes'):
                    m = re.match('(\d+)\.tar\.gz', file_name)
                    if m is not None:
                        report_files[('unsafe', int(m.group(1)))] = os.path.join(dir_path, file_name)
                elif dir_path.endswith('Safes'):
                    report_files[('safe', int(file_name))] = os.path.join(dir_path, file_name)
                elif dir_path.endswith('Unknowns'):
                    report_files[('unknown', int(file_name))] = os.path.join(dir_path, file_name)
                elif dir_path.endswith('Components'):
                    m = re.match('(\d+)\.tar\.gz', file_name)
                    if m is not None:
                        report_files[('component', int(m.group(1)))] = os.path.join(dir_path, file_name)

        if any(x not in jobdata for x in ['format', 'type', 'status', 'filedata', 'reports']):
            return _("The job archive is corrupted")
        if int(jobdata['format']) != FORMAT:
            return _("The job format is not supported")

        if 'identifier' in jobdata:
            if isinstance(jobdata['identifier'], str) and len(jobdata['identifier']) > 0:
                if len(Job.objects.filter(identifier=jobdata['identifier'])) > 0:
                    return _("The job with identifier specified in the archive already exists")
            else:
                del jobdata['identifier']

        if jobdata['type'] != self.parent.type:
            return _("The job class does not equal to the parent class")
        if jobdata['status'] not in list(x[0] for x in JOB_STATUS):
            return _("The job status is wrong")
        files_map = json.loads(jobdata['filedata'])
        for f_id in files_map:
            if files_map[f_id] in files_in_db:
                files_map[f_id] = files_in_db[files_map[f_id]]
            else:
                return _("The job archive is corrupted")

        version_list = list(versions_data[v] for v in sorted(versions_data))
        for i in range(0, len(version_list)):
            filedata = []
            for file in version_list[i]['filedata']:
                fdata_elem = {
                    'title': file['name'],
                    'id': file['pk'],
                    'type': '0',
                    'parent': file['parent'],
                    'hash_sum': None
                }
                if file['file'] is not None:
                    if str(file['file']) in jobdata['filedata']:
                        fdata_elem['type'] = '1'
                        fdata_elem['hash_sum'] = files_map[str(file['file'])]
                    else:
                        return _("The job archive is corrupted")
                filedata.append(fdata_elem)
            version_list[i]['filedata'] = filedata

        job = create_job({
            'name': version_list[0]['name'],
            'author': self.user,
            'description': version_list[0]['description'],
            'parent': self.parent,
            'type': self.parent.type,
            'global_role': version_list[0]['global_role'],
            'filedata': version_list[0]['filedata'],
            'comment': version_list[0]['comment']
        })
        if not isinstance(job, Job):
            return job

        for version_data in version_list[1:]:
            updated_job = update_job({
                'job': job,
                'name': version_data['name'],
                'author': self.user,
                'description': version_data['description'],
                'parent': self.parent,
                'type': self.parent.type,
                'filedata': version_data['filedata'],
                'global_role': version_data['global_role'],
                'comment': version_data['comment']
            })
            if not isinstance(updated_job, Job):
                job.delete()
                return updated_job

        change_job_status(job, jobdata['status'])
        self.job = job
        ReportRoot.objects.create(user=self.user, job=self.job)
        try:
            UploadReports(self.job, json.loads(jobdata['reports']), report_files)
        except Exception as e:
            logger.exception("Uploading report failed: %s" % e, stack_info=True)
            self.job.delete()
            self.job = None
            return _("One of the reports was not uploaded")
        return None


class UploadReports(object):
    def __init__(self, job, data, files):
        self.error = None
        self.job = job
        self.data = data
        self.files = files
        self._pk_map = {}
        self._attrs = AttrData()
        self.__upload_all()

    def __fix_identifiers(self):
        ids_in_use = []
        for data in self.data:
            if isinstance(data, dict):
                if 'identifier' in data:
                    m = re.match('.*?(/.*)', data['identifier'])
                    if m is None:
                        data['identifier'] = self.job.identifier
                    else:
                        data['identifier'] = self.job.identifier + m.group(1)
                    if data['identifier'] in ids_in_use:
                        raise ValueError('Report identifier "%s" is not unique' % data['identifier'])
                    else:
                        ids_in_use.append(data['identifier'])

    def __upload_all(self):
        curr_func = self.__create_report_component
        self.__fix_identifiers()
        for data in self.data:
            if isinstance(data, dict):
                curr_func(data)
            elif isinstance(data, str) and data == 'safes':
                curr_func = self.__create_report_safe
            elif isinstance(data, str) and data == 'unsafes':
                curr_func = self.__create_report_unsafe
            elif isinstance(data, str) and data == 'unknowns':
                curr_func = self.__create_report_unknown
        self._attrs.upload()

        Verdict.objects.bulk_create(list(
            Verdict(report=self._pk_map[rep_id]) for rep_id in self._pk_map
        ))

        from tools.utils import Recalculation
        Recalculation('all', json.dumps([self.job.pk]))

    def __create_report_component(self, data):
        parent = None
        if 'parent' in data and data['parent'] is not None:
            if data['parent'] in self._pk_map:
                parent = self._pk_map[data['parent']]
            else:
                raise ValueError('Report component parent was not found')
        if ('component', data['pk']) not in self.files:
            raise ValueError('Component report files was not found')
        with open(self.files[('component', data['pk'])], mode='rb') as fp:
            uf = UploadReportFiles(fp, log=REPORT_LOG_FILE, need_other=True)
        if uf.log is None:
            raise ValueError('Component report without log was found')

        if data['data'] is not None:
            report_datafile = file_get_or_create(BytesIO(data['data'].encode('utf8')), 'report-data.json')[0]
        else:
            report_datafile = None
        self._pk_map[data['pk']] = ReportComponent.objects.create(
            root=self.job.reportroot,
            parent=parent,
            identifier=data['identifier'],
            computer=Computer.objects.get_or_create(description=data['computer'])[0],
            component=Component.objects.get_or_create(name=data['component'])[0],
            cpu_time=data['resource']['cpu_time'] if data['resource'] is not None else None,
            wall_time=data['resource']['wall_time'] if data['resource'] is not None else None,
            memory=data['resource']['memory'] if data['resource'] is not None else None,
            start_date=datetime(*data['start_date'], tzinfo=pytz.timezone('UTC')),
            finish_date=datetime(*data['finish_date'], tzinfo=pytz.timezone('UTC'))
            if data['finish_date'] is not None else None,
            log=uf.log,
            data=report_datafile
        )
        for attr in data['attrs']:
            self._attrs.add(self._pk_map[data['pk']].pk, attr[0], attr[1])
        for rep_f in uf.other_files:
            ReportFiles.objects.get_or_create(file=rep_f['file'], name=rep_f['name'], report=self._pk_map[data['pk']])

    def __create_report_safe(self, data):
        if ('safe', data['pk']) not in self.files:
            raise ValueError('Safe without proof was found')
        parent = None
        if 'parent' in data and data['parent'] in self._pk_map:
            parent = self._pk_map[data['parent']]
        with open(self.files[('safe', data['pk'])], mode='rb') as fp:
            report = ReportSafe.objects.create(
                root=self.job.reportroot,
                parent=parent,
                identifier=data['identifier'],
                proof=file_get_or_create(fp, 'safe-proof.txt')[0]
            )
        for attr in data['attrs']:
            self._attrs.add(report.pk, attr[0], attr[1])

    def __create_report_unknown(self, data):
        if ('unknown', data['pk']) not in self.files:
            raise ValueError('Unknown without problem description was found')
        parent = None
        if 'parent' in data and data['parent'] in self._pk_map:
            parent = self._pk_map[data['parent']]
        with open(self.files[('unknown', data['pk'])], mode='rb') as fp:
            report = ReportUnknown.objects.create(
                root=self.job.reportroot,
                parent=parent,
                identifier=data['identifier'],
                problem_description=file_get_or_create(fp, 'problem-description.txt')[0],
                component=parent.component
            )
        for attr in data['attrs']:
            self._attrs.add(report.pk, attr[0], attr[1])

    def __create_report_unsafe(self, data):
        if ('unsafe', data['pk']) not in self.files:
            raise ValueError('Unsafe without files was found')
        with open(self.files[('unsafe', data['pk'])], mode='rb') as fp:
            uf = UploadReportFiles(fp, file_name=ET_FILE, need_other=True)
        if uf.main_file is None:
            raise ValueError('Unsafe without error trace was found')
        if 'parent' in data and data['parent'] in self._pk_map:
            parent = self._pk_map[data['parent']]
        else:
            return
        report = ReportUnsafe.objects.create(
            root=self.job.reportroot,
            parent=parent,
            identifier=data['identifier'],
            error_trace=uf.main_file
        )
        for attr in data['attrs']:
            self._attrs.add(report.pk, attr[0], attr[1])
        for src_f in uf.other_files:
            ETVFiles.objects.get_or_create(file=src_f['file'], name=src_f['name'], unsafe=report)

    def __get_log(self, rep_id, component):
        if ('log', rep_id) in self.files:
            return file_get_or_create(open(self.files[('log', rep_id)], mode='rb'), '%s.log' % component)[0]
        return None
