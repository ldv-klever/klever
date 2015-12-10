import os
import json
import tarfile
import hashlib
from io import BytesIO
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.files import File as NewFile
from django.db.models import Q
from django.utils.translation import ugettext_lazy as _, override
from Omega.vars import JOB_CLASSES, FORMAT, JOB_STATUS, PRIORITY
from Omega.utils import print_err
from jobs.models import Job, File, JOBFILE_DIR
from jobs.utils import create_job, update_job
from reports.models import ReportComponent, ReportUnsafe, ReportSafe,\
    ReportUnknown, ReportRoot, ETVFiles
from reports.UploadReport import UploadReport
from service.models import SolvingProgress, Scheduler

ET_FILE = 'omega-error-trace.graphml'


class PSIDownloadJob(object):
    def __init__(self, job):
        self.error = None
        self.tarname = ''
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
                    src = os.path.join(
                        settings.MEDIA_ROOT, f.file.file.name)
                file_path = f.name
                file_parent = f.parent
                while file_parent is not None:
                    file_path = file_parent.name + '/' + file_path
                    file_parent = file_parent.parent
                files_for_tar.append({
                    'path': os.path.join('root', file_path),
                    'src': src
                })

        self.tarname = 'VJ__' + job.identifier + '.tar.gz'
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
        self.memory = BytesIO()
        self.error = None
        self.__create_tar(job)

    def __create_tar(self, job):

        files_in_tar = {}
        self.tarname = 'Job-' + job.identifier[:10] + '.tar.gz'
        jobtar_obj = tarfile.open(fileobj=self.memory, mode='w:gz')

        def write_file_str(file_name, file_content):
            file_content = file_content.encode('utf-8')
            t = tarfile.TarInfo(file_name)
            t.size = len(file_content)
            jobtar_obj.addfile(t, BytesIO(file_content))

        for jobversion in job.versions.all():
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
                        jobtar_obj.add(
                            os.path.join(settings.MEDIA_ROOT, f.file.file.name),
                            f.file.file.name
                        )
                filedata.append(filedata_element)
            version_data = {
                'filedata': filedata,
                'description': jobversion.description,
                'name': jobversion.name,
                'global_role': jobversion.global_role,
                'comment': jobversion.comment,
            }
            write_file_str('version-%s' % jobversion.version,
                           json.dumps(version_data))
        unsafes_tars = {}
        for unsafe in ReportUnsafe.objects.filter(root__job=job):
            unsafes_tars[unsafe] = {
                'memory': BytesIO(),
                'tarobj': None
            }
            unsafes_tars[unsafe]['tarobj'] = tarfile.open(fileobj=unsafes_tars[unsafe]['memory'], mode='w:gz')
        for f in ETVFiles.objects.filter(unsafe__root__job=job):
            if f.unsafe in unsafes_tars:
                unsafes_tars[f.unsafe]['tarobj'].add(
                    os.path.join(settings.MEDIA_ROOT, f.file.file.name), arcname=f.name
                )
        for u in unsafes_tars:
            tinfo = tarfile.TarInfo(ET_FILE)
            tinfo.size = len(u.error_trace)
            unsafes_tars[u]['tarobj'].addfile(tinfo, BytesIO(u.error_trace))
            unsafes_tars[u]['tarobj'].close()
            unsafes_tars[u]['memory'].seek(0)
            tarname = 'unsafe_files__%s.tar.gz' % u.pk
            tinfo = tarfile.TarInfo(tarname)
            tinfo.size = unsafes_tars[u]['memory'].getbuffer().nbytes
            jobtar_obj.addfile(tinfo, unsafes_tars[u]['memory'])

        common_data = {
            'format': str(job.format),
            'type': str(job.type),
            'status': job.status,
            'filedata': json.dumps(files_in_tar),
            'reports': ReportsData(job).reports
        }
        write_file_str('jobdata', json.dumps(common_data))
        jobtar_obj.close()


class ReportsData(object):
    def __init__(self, job):
        self.job = job
        self.reports = json.dumps(self.__reports_data())

    def __reports_data(self):
        reports = []
        try:
            root = self.job.reportroot
        except ObjectDoesNotExist:
            return reports
        try:
            main_report = ReportComponent.objects.get(
                Q(parent=None, root=root) & ~Q(finish_date=None))
        except ObjectDoesNotExist:
            return reports
        reports.append(ReverseReport(main_report).report_data)
        children = ReportComponent.objects.filter(parent_id=main_report.pk)
        while len(children) > 0:
            next_children = []
            for next_rep in children:
                if next_rep.finish_date is None:
                    continue
                reports.append(ReverseReport(next_rep).report_data)
                for child in ReportComponent.objects.filter(
                        parent_id=next_rep.pk):
                    next_children.append(child)
            children = next_children
        for unsafe in ReportUnsafe.objects.filter(root=root):
            reports.append(ReverseReport(unsafe).report_data)
        for safe in ReportSafe.objects.filter(root=root):
            reports.append(ReverseReport(safe).report_data)
        for unknown in ReportUnknown.objects.filter(root=root):
            reports.append(ReverseReport(unknown).report_data)
        reports.append(ReverseReport(job=self.job).report_data)
        return reports


class ReverseReport(object):
    def __init__(self, report=None, job=None):
        self.report = report
        self.job = job
        self.report_data = {}
        self.__revert_report()

    def __revert_report(self):
        if self.report is None and isinstance(self.job, Job):
            self.__revert_finish_component()
        elif isinstance(self.report, ReportComponent):
            self.__revert_report_component()
        else:
            self.__revert_leaf_report()

    def __revert_finish_component(self):
        try:
            report = ReportComponent.objects.get(root__job=self.job,
                                                 parent=None)
        except ObjectDoesNotExist:
            return
        self.report_data['id'] = '/'
        self.report_data['type'] = 'finish'
        self.report_data['resources'] = {
            'CPU time': report.resource.cpu_time,
            'max mem size': report.resource.memory,
            'wall time': report.resource.wall_time
        }
        if report.data is not None:
            self.report_data['data'] = report.data.decode('utf8')
        else:
            self.report_data['data'] = ''
        self.report_data['log'] = ''
        if report.log is not None:
            self.report_data['log'] = report.log.file.read().decode('utf8')
        if report.description is not None:
            self.report_data['desc'] = report.description.decode('utf8')

    def __revert_report_component(self):
        self.report_data['id'] = self.__get_report_id(self.report)
        self.report_data['attrs'] = self.__get_attrs()
        self.report_data['comp'] = json.loads(self.report.computer.description)
        if self.report.description is not None:
            self.report_data['desc'] = self.report.description.decode('utf8')
        if self.report_data['id'] == '/':
            self.report_data['type'] = 'start'
        else:
            try:
                parent = ReportComponent.objects.get(pk=self.report.parent_id)
            except ObjectDoesNotExist:
                parent = None
            if parent is not None:
                self.report_data['parent id'] = self.__get_report_id(parent)
            self.report_data['name'] = self.report.component.name
            self.report_data['type'] = 'verification'
            if self.report.data is not None:
                self.report_data['data'] = self.report.data.decode('utf8')
            else:
                self.report_data['data'] = ''
            self.report_data['resources'] = {
                'CPU time': self.report.resource.cpu_time,
                'max mem size': self.report.resource.memory,
                'wall time': self.report.resource.wall_time
            }
            self.report_data['log'] = ''
            if self.report.log is not None:
                self.report_data['log'] = self.report.log.file.read().decode('utf8')

    def __revert_leaf_report(self):
        if isinstance(self.report, ReportUnsafe):
            self.report_data['error trace'] = ET_FILE
            self.report_data['type'] = 'unsafe'
            self.report_data['omega_db_pk'] = self.report.pk
        elif isinstance(self.report, ReportSafe):
            self.report_data['proof'] = self.report.proof.decode('utf8')
            self.report_data['type'] = 'safe'
        elif isinstance(self.report, ReportUnknown):
            self.report_data['problem desc'] = self.report.problem_description\
                .decode('utf8')
            self.report_data['type'] = 'unknown'
        else:
            return
        if self.report.description is not None:
            self.report_data['desc'] = self.report.description.decode('utf8')
        self.report_data['id'] = self.__get_report_id(self.report)
        try:
            parent = ReportComponent.objects.get(pk=self.report.parent_id)
        except ObjectDoesNotExist:
            parent = None
        if parent is not None:
            self.report_data['parent id'] = self.__get_report_id(parent)
        self.report_data['attrs'] = self.__get_attrs()

    def __get_report_id(self, report):
        self.ccc = 0
        report_id = report.identifier.split('##')[-1]
        if report_id == report.root.job.identifier:
            return '/'
        else:
            return report_id

    def __get_attrs(self):
        attrs = []
        for attr_name in self.report.attrorder.order_by('id'):
            try:
                attr = self.report.attr.get(name__name=attr_name.name.name)
            except ObjectDoesNotExist:
                continue
            attrs.append((attr.name.name, attr.value))
        return {'values': attrs}


class UploadJob(object):
    def __init__(self, parent, user, zip_archive):
        self.parent = parent
        self.job = None
        self.user = user
        self.zip_file = zip_archive
        self.err_message = self.__create_job_from_tar()

    def __create_job_from_tar(self):
        inmemory = BytesIO(self.zip_file.read())
        jobzip_file = tarfile.open(fileobj=inmemory, mode='r')
        jobdata = None
        files_in_db = {}
        versions_data = {}
        unsafe_files = {}
        for f in jobzip_file.getmembers():
            file_name = f.name
            file_obj = jobzip_file.extractfile(f)
            if file_name == 'jobdata':
                try:
                    jobdata = json.loads(file_obj.read().decode('utf-8'))
                except Exception as e:
                    print_err(e)
                    return _("The job archive is corrupted")
            elif file_name.startswith(JOBFILE_DIR):
                if f.isreg():
                    file_content = BytesIO(file_obj.read())
                    check_sum = hashlib.md5(file_content.read()).hexdigest()
                    file_in_db = File.objects.filter(hash_sum=check_sum)
                    if len(file_in_db) == 0:
                        db_file = File()
                        db_file.file.save(
                            os.path.basename(file_name),
                            NewFile(file_content)
                        )
                        db_file.hash_sum = check_sum
                        db_file.save()
                    files_in_db[file_name] = check_sum
            elif file_name.startswith('version-'):
                version_id = int(file_name.replace('version-', ''))
                versions_data[version_id] = json.loads(file_obj.read().decode('utf8'))
            elif file_name.startswith('unsafe_files__'):
                import re
                m = re.match('unsafe_files__(\d+)\.tar\.gz', file_name)
                if m is not None:
                    unsafe_files[int(m.group(1))] = jobzip_file.extractfile(f)

        if any(x not in jobdata for x in
               ['format', 'type', 'status', 'filedata', 'reports']):
            return _("The job archive is corrupted")
        if int(jobdata['format']) != FORMAT:
            return _("The job format is not supported")
        if jobdata['type'] != self.parent.type:
            return _("The job class does not equal to the parent class")
        files_map = json.loads(jobdata['filedata'])
        for f_id in files_map:
            if files_map[f_id] in files_in_db:
                files_map[f_id] = \
                    files_in_db[files_map[f_id]]
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
                        fdata_elem['hash_sum'] = \
                            files_map[str(file['file'])]
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
        self.job = job
        ReportRoot.objects.create(user=self.user, job=self.job)
        SolvingProgress.objects.create(job=self.job, priority=PRIORITY[3][0],
                                       scheduler=Scheduler.objects.all()[0],
                                       configuration='{}'.encode('utf8'))
        self.job.status = JOB_STATUS[1][0]
        self.job.save()
        if not self.__upload_reports(json.loads(jobdata['reports']), unsafe_files):
            self.job.delete()
            self.job = None
            return _("One of the reports was not uploaded")
        if jobdata['status'] in list(JOB_STATUS[x][0] for x in [1, 2, 6]):
            self.job.status = JOB_STATUS[5][0]
        else:
            self.job.status = jobdata['status']
        self.job.save()
        self.job.solvingprogress.delete()
        return None

    def __upload_reports(self, reports, unsafe_files):
        for report in reports:
            archive = None
            if 'type' in report and report['type'] == 'unsafe' \
                    and 'omega_db_pk' in report and report['omega_db_pk'] in unsafe_files:
                archive = unsafe_files[report['omega_db_pk']]
            error = UploadReport(self.job, report, archive).error
            if error is not None:
                print_err(error)
                return False
        return True
