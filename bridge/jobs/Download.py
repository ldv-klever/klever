import os
import re
import json
import tarfile
import tempfile
from io import BytesIO
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.utils.translation import ugettext_lazy as _, override
from django.utils.timezone import datetime, pytz
from bridge.vars import JOB_CLASSES, FORMAT, JOB_STATUS, REPORT_FILES_ARCHIVE
from bridge.utils import logger, file_get_or_create
from jobs.models import JOBFILE_DIR, RunHistory
from jobs.utils import create_job, update_job, change_job_status
from reports.models import *
from reports.utils import AttrData

ET_FILE = 'unsafe-error-trace.graphml'


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
        self.tempfile = tempfile.TemporaryFile()
        self.error = None
        self.__create_tar()
        self.tempfile.flush()
        self.size = self.tempfile.tell()
        self.tempfile.seek(0)

    def __create_tar(self):

        files_in_tar = {}
        self.tarname = 'Job-%s-%s.tar.gz' % (self.job.identifier[:10], self.job.type)
        with tarfile.open(fileobj=self.tempfile, mode='w:gz') as jobtar_obj:

            def add_json(file_name, data):
                file_content = json.dumps(data, indent=4).encode('utf-8')
                t = tarfile.TarInfo(file_name)
                t.size = len(file_content)
                jobtar_obj.addfile(t, BytesIO(file_content))

            for jobversion in self.job.versions.all():
                filedata = []
                for f in jobversion.filesystem_set.all():
                    filedata_element = {
                        'pk': f.pk, 'parent': f.parent_id, 'name': f.name, 'file': None
                    }
                    if f.file is not None:
                        filedata_element['file'] = f.file.pk
                        if f.file.pk not in files_in_tar:
                            files_in_tar[f.file.pk] = f.file.file.name
                            jobtar_obj.add(os.path.join(settings.MEDIA_ROOT, f.file.file.name), f.file.file.name)
                    filedata.append(filedata_element)
                add_json('version-%s.json' % jobversion.version, {
                    'filedata': filedata,
                    'description': jobversion.description,
                    'name': jobversion.name,
                    'global_role': jobversion.global_role,
                    'comment': jobversion.comment,
                })

            add_json('job.json', {
                'format': self.job.format, 'identifier': self.job.identifier, 'type': self.job.type,
                'status': self.job.status, 'files_map': files_in_tar,
                'run_history': self.__add_run_history_files(jobtar_obj)
            })
            add_json('reports.json', ReportsData(self.job).reports)
            self.__add_reports_files(jobtar_obj)

    def __add_reports_files(self, jobtar):
        tables = [ReportSafe, ReportUnsafe, ReportUnknown, ReportComponent]
        for table in tables:
            for report in table.objects.filter(root__job=self.job):
                if report.archive is not None:
                    jobtar.add(
                        os.path.join(settings.MEDIA_ROOT, report.archive.file.name),
                        arcname=os.path.join(table.__name__, '%s.tar.gz' % report.pk)
                    )

    def __add_run_history_files(self, jobtar):
        data = []
        for rh in self.job.runhistory_set.order_by('date'):
            jobtar.add(
                os.path.join(settings.MEDIA_ROOT, rh.configuration.file.name),
                arcname=os.path.join('Configurations', "%s.json" % rh.pk)
            )
            data.append({
                'id': rh.pk, 'status': rh.status,
                'date': [
                    rh.date.year, rh.date.month, rh.date.day, rh.date.hour,
                    rh.date.minute, rh.date.second, rh.date.microsecond
                ]
            })
        return data


class ReportsData(object):
    def __init__(self, job):
        self.job = job
        self.reports = self.__reports_data()

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
            'attrs': list((ra.attr.name.name, ra.attr.value) for ra in report.attrs.order_by('id')),
            'log': report.log
        }

    def __report_leaf_data(self, report):
        self.ccc = 0
        data = {
            'pk': report.pk,
            'parent': report.parent_id,
            'identifier': report.identifier,
            'attrs': list((ra.attr.name.name, ra.attr.value) for ra in report.attrs.order_by('id'))
        }
        if isinstance(report, ReportSafe):
            data['proof'] = report.proof
        elif isinstance(report, ReportUnsafe):
            data['error_trace'] = report.error_trace
        elif isinstance(report, ReportUnknown):
            data['problem_description'] = report.problem_description
        return data

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
        reports.append(ReportSafe.__name__)
        for safe in ReportSafe.objects.filter(root__job=self.job):
            reports.append(self.__report_leaf_data(safe))
        reports.append(ReportUnsafe.__name__)
        for unsafe in ReportUnsafe.objects.filter(root__job=self.job):
            reports.append(self.__report_leaf_data(unsafe))
        reports.append(ReportUnknown.__name__)
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
        reports_data = None
        files_in_db = {}
        versions_data = {}
        report_files = {}
        run_history_files = {}
        for dir_path, dir_names, file_names in os.walk(self.job_dir):
            for file_name in file_names:
                if dir_path.endswith(JOBFILE_DIR):
                    try:
                        files_in_db['/'.join([JOBFILE_DIR, file_name])] = file_get_or_create(
                            open(os.path.join(dir_path, file_name), mode='rb'), file_name, True
                        )[1]
                    except Exception as e:
                        logger.exception("Can't save job files to DB: %s" % e)
                        return _("Creating job's file failed")
                elif file_name == 'job.json':
                    try:
                        with open(os.path.join(dir_path, file_name), encoding='utf8') as fp:
                            jobdata = json.load(fp)
                    except Exception as e:
                        logger.exception("Can't parse job data: %s" % e)
                        return _("The job archive is corrupted")
                elif file_name == 'reports.json':
                    try:
                        with open(os.path.join(dir_path, file_name), encoding='utf8') as fp:
                            reports_data = json.load(fp)
                    except Exception as e:
                        logger.exception("Can't parse reports data: %s" % e)
                        return _("The job archive is corrupted")

                elif file_name.startswith('version-'):
                    m = re.match('version-(\d+)\.json', file_name)
                    if m is None:
                        logger.error("Unknown file that startswith 'version-' was found in the archive")
                        return _("The job archive is corrupted")
                    with open(os.path.join(dir_path, file_name), encoding='utf8') as fp:
                        versions_data[int(m.group(1))] = json.load(fp)
                elif dir_path.endswith('Configurations'):
                    try:
                        run_history_files[int(file_name.replace('.json', ''))] = os.path.join(dir_path, file_name)
                    except ValueError:
                        logger.exception("Unknown file was found in 'Configurations' dir: %s" % file_name)
                        return _("The job archive is corrupted")
                else:
                    b_dir = os.path.basename(dir_path)
                    if b_dir in list(x.__name__ for x in [ReportSafe, ReportUnsafe, ReportUnknown, ReportComponent]):
                        m = re.match('(\d+)\.tar\.gz', file_name)
                        if m is not None:
                            report_files[(b_dir, int(m.group(1)))] = os.path.join(dir_path, file_name)

        # Check job data
        if any(x not in jobdata for x in ['format', 'type', 'status', 'files_map', 'run_history']):
            logger.error('Not enough data in job.json file')
            return _("The job archive is corrupted")
        if jobdata['format'] != FORMAT:
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
        for f_id in list(jobdata['files_map']):
            if jobdata['files_map'][f_id] in files_in_db:
                jobdata['files_map'][int(f_id)] = files_in_db[jobdata['files_map'][f_id]]
                del jobdata['files_map'][f_id]
            else:
                logger.error('Not enough files in "Files" directory')
                return _("The job archive is corrupted")

        # Check versions data
        if len(versions_data) == 0:
            logger.error("There are no job's versions in the archive")
            return _("The job archive is corrupted")
        for version in versions_data:
            if any(x not in versions_data[version] for x in
                   ['name', 'description', 'comment', 'global_role', 'filedata']):
                logger.exception("The job version data is corrupted")
                return _("The job archive is corrupted")

        # Update versions' files data
        try:
            version_list = list(versions_data[v] for v in sorted(versions_data))
            for i in range(0, len(version_list)):
                version_filedata = []
                for file in version_list[i]['filedata']:
                    fdata_elem = {
                        'title': file['name'],
                        'id': file['pk'],
                        'type': '0',
                        'parent': file['parent'],
                        'hash_sum': None
                    }
                    if file['file'] is not None:
                        fdata_elem['type'] = '1'
                        fdata_elem['hash_sum'] = jobdata['files_map'][file['file']]
                    version_filedata.append(fdata_elem)
                version_list[i]['filedata'] = version_filedata
        except Exception as e:
            logger.exception("The job version data is corrupted: %s" % e)
            return _("The job archive is corrupted")

        # Creating the job
        job = create_job({
            'name': version_list[0]['name'],
            'identifier': jobdata.get('identifier'),
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

        # Creating job's run history
        try:
            for rh in jobdata['run_history']:
                if rh['status'] not in list(x[0] for x in JOB_STATUS):
                    return _("The job archive is corrupted")
                with open(run_history_files[rh['id']], mode='rb') as fp:
                    RunHistory.objects.create(
                        job=job, status=rh['status'],
                        date=datetime(*rh['date'], tzinfo=pytz.timezone('UTC')),
                        configuration=file_get_or_create(fp, 'config.json')[0]
                    )
        except Exception as e:
            logger.exception("Run history data is corrupted: %s" % e)
            job.delete()
            return _("The job archive is corrupted")

        # Creating job's versions
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

        # Change job's status as it was in downloaded archive
        change_job_status(job, jobdata['status'])
        ReportRoot.objects.create(user=self.user, job=job)
        try:
            UploadReports(job, reports_data, report_files)
        except Exception as e:
            logger.exception("Uploading report failed: %s" % e, stack_info=True)
            job.delete()
            return _("Uploading reports failed")
        self.job = job
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
                report_id = curr_func(data)
                for attr in data['attrs']:
                    self._attrs.add(report_id, attr[0], attr[1])
            elif isinstance(data, str) and data == ReportSafe.__name__:
                curr_func = self.__create_report_safe
            elif isinstance(data, str) and data == ReportUnsafe.__name__:
                curr_func = self.__create_report_unsafe
            elif isinstance(data, str) and data == ReportUnknown.__name__:
                curr_func = self.__create_report_unknown
        self._attrs.upload()

        Verdict.objects.bulk_create(list(
            Verdict(report=self._pk_map[rep_id]) for rep_id in self._pk_map
        ))

        from tools.utils import Recalculation
        Recalculation('all', json.dumps([self.job.pk]))

    def __create_report_component(self, data):
        parent = None
        if data.get('parent') is not None:
            parent = self._pk_map[data['parent']]
        with open(self.files[(ReportComponent.__name__, data['pk'])], mode='rb') as fp:
            archive = file_get_or_create(fp, REPORT_FILES_ARCHIVE)[0]
        if data['log'] is None:
            raise ValueError('Component report without log was found')
        report_datafile = None
        if data['data'] is not None:
            report_datafile = file_get_or_create(BytesIO(data['data'].encode('utf8')), 'report-data.json')[0]

        self._pk_map[data['pk']] = ReportComponent.objects.create(
            root=self.job.reportroot, parent=parent, identifier=data['identifier'],
            computer=Computer.objects.get_or_create(description=data['computer'])[0],
            component=Component.objects.get_or_create(name=data['component'])[0],
            cpu_time=data['resource']['cpu_time'] if data['resource'] is not None else None,
            wall_time=data['resource']['wall_time'] if data['resource'] is not None else None,
            memory=data['resource']['memory'] if data['resource'] is not None else None,
            start_date=datetime(*data['start_date'], tzinfo=pytz.timezone('UTC')),
            finish_date=datetime(*data['finish_date'], tzinfo=pytz.timezone('UTC')),
            log=data['log'], data=report_datafile, archive=archive
        )
        return self._pk_map[data['pk']].pk

    def __create_report_safe(self, data):
        with open(self.files[(ReportSafe.__name__, data['pk'])], mode='rb') as fp:
            return ReportSafe.objects.create(
                root=self.job.reportroot, parent=self._pk_map[data['parent']],
                identifier=data['identifier'], proof=data['proof'],
                archive=file_get_or_create(fp, REPORT_FILES_ARCHIVE)[0]
            ).pk

    def __create_report_unknown(self, data):
        with open(self.files[(ReportUnknown.__name__, data['pk'])], mode='rb') as fp:
            return ReportUnknown.objects.create(
                root=self.job.reportroot, parent=self._pk_map[data['parent']], identifier=data['identifier'],
                problem_description=data['problem_description'],
                archive=file_get_or_create(fp, REPORT_FILES_ARCHIVE)[0],
                component=self._pk_map[data['parent']].component
            ).pk

    def __create_report_unsafe(self, data):
        with open(self.files[(ReportUnsafe.__name__, data['pk'])], mode='rb') as fp:
            return ReportUnsafe.objects.create(
                root=self.job.reportroot, parent=self._pk_map[data['parent']], identifier=data['identifier'],
                error_trace=data['error_trace'], archive=file_get_or_create(fp, REPORT_FILES_ARCHIVE)[0]
            ).pk
