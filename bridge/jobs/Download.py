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

import re
import json
import tarfile
import tempfile
from io import BytesIO
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import ugettext_lazy as _, override
from django.utils.timezone import datetime, pytz
from bridge.vars import JOB_CLASSES, FORMAT, JOB_STATUS, REPORT_FILES_ARCHIVE
from bridge.utils import logger, file_get_or_create
from bridge.ZipGenerator import ZipStream, CHUNK_SIZE
from .models import RunHistory, JobFile
from .utils import create_job, update_job, change_job_status
from reports.models import *
from reports.utils import AttrData
from tools.utils import Recalculation

ET_FILE = 'unsafe-error-trace.graphml'


class KleverCoreArchiveGen:
    def __init__(self, job):
        self.arcname = 'VJ__' + job.identifier + '.zip'
        self.job = job
        self.stream = ZipStream()

    def __iter__(self):
        for f in self.__get_job_files():
            for data in self.stream.compress_file(f['src'], f['path']):
                yield data

        for data in self.stream.compress_string('format', str(self.job.format)):
            yield data

        for job_class in JOB_CLASSES:
            if job_class[0] == self.job.type:
                with override('en'):
                    for data in self.stream.compress_string('class', str(job_class[1])):
                        yield data
                break
        yield self.stream.close_stream()

    def __get_job_files(self):
        job_file_system = {}
        files_to_add = set()
        for f in self.job.versions.get(version=self.job.version).filesystem_set.all():
            job_file_system[f.id] = {
                'parent': f.parent_id,
                'name': f.name,
                'src': os.path.join(settings.MEDIA_ROOT, f.file.file.name) if f.file is not None else None
            }
            if job_file_system[f.id]['src'] is not None:
                files_to_add.add(f.id)
        job_files = []
        for f_id in files_to_add:
            file_path = job_file_system[f_id]['name']
            parent_id = job_file_system[f_id]['parent']
            while parent_id is not None:
                file_path = os.path.join(job_file_system[parent_id]['name'], file_path)
                parent_id = job_file_system[parent_id]['parent']
            job_files.append({
                'path': os.path.join('root', file_path),
                'src': job_file_system[f_id]['src']
            })
        return job_files


class KleverCoreDownloadJob(object):
    def __init__(self, job):
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

        jobtar_obj = tarfile.open(fileobj=self.memory, mode='w:gz', encoding='utf8')
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


class JobArchiveGenerator:
    def __init__(self, job):
        self.job = job
        self.arcname = 'Job-%s-%s.zip' % (self.job.identifier[:10], self.job.type)
        self.arch_files = {}
        self.files_to_add = []
        self.stream = ZipStream()

    def __iter__(self):
        for job_v in self.job.versions.all():
            for data in self.stream.compress_string('version-%s.json' % job_v.version, self.__version_data(job_v)):
                yield data
        for data in self.stream.compress_string('job.json', self.__job_data()):
            yield data
        for data in self.stream.compress_string('reports.json', json.dumps(
                ReportsData(self.job).reports, ensure_ascii=False, sort_keys=True, indent=4).encode('utf-8')):
            yield data
        for data in self.stream.compress_string('LightWeightCache.json', json.dumps(
                LightWeightCache(self.job).data, ensure_ascii=False, sort_keys=True, indent=4).encode('utf-8')):
            yield data
        self.__add_reports_files()
        for file_path, arcname in self.files_to_add:
            for data in self.stream.compress_file(file_path, arcname):
                yield data
        yield self.stream.close_stream()

    def __version_data(self, job_v):
        filedata = []
        for f in job_v.filesystem_set.all():
            filedata_element = {
                'pk': f.pk, 'parent': f.parent_id, 'name': f.name, 'file': f.file_id
            }
            if f.file is not None:
                if f.file.pk not in self.arch_files:
                    self.arch_files[f.file.pk] = f.file.file.name
                    self.files_to_add.append((os.path.join(settings.MEDIA_ROOT, f.file.file.name), f.file.file.name))
            filedata.append(filedata_element)
        return json.dumps({
            'filedata': filedata,
            'description': job_v.description,
            'name': job_v.name,
            'global_role': job_v.global_role,
            'comment': job_v.comment,
        }, ensure_ascii=False, sort_keys=True, indent=4).encode('utf-8')

    def __job_data(self):
        return json.dumps({
            'format': self.job.format, 'identifier': self.job.identifier, 'type': self.job.type,
            'status': self.job.status, 'files_map': self.arch_files,
            'run_history': self.__add_run_history_files()
        }, ensure_ascii=False, sort_keys=True, indent=4).encode('utf-8')

    def __add_run_history_files(self):
        data = []
        for rh in self.job.runhistory_set.order_by('date'):
            self.files_to_add.append((
                os.path.join(settings.MEDIA_ROOT, rh.configuration.file.name),
                os.path.join('Configurations', "%s.json" % rh.pk)
            ))
            data.append({
                'id': rh.pk, 'status': rh.status,
                'date': [
                    rh.date.year, rh.date.month, rh.date.day, rh.date.hour,
                    rh.date.minute, rh.date.second, rh.date.microsecond
                ]
            })
        return data

    def __add_reports_files(self):
        tables = [ReportSafe, ReportUnsafe, ReportUnknown, ReportComponent]
        for table in tables:
            for report in table.objects.filter(root__job=self.job):
                if report.archive:
                    self.files_to_add.append((
                        os.path.join(settings.MEDIA_ROOT, report.archive.name),
                        os.path.join(table.__name__, '%s.tar.gz' % report.pk)
                    ))


class JobsArchivesGen:
    def __init__(self, jobs):
        self.jobs = jobs
        self.stream = ZipStream()

    def __iter__(self):
        for job in self.jobs:
            jobgen = JobArchiveGenerator(job)
            buf = b''
            for data in self.stream.compress_stream(jobgen.arcname, jobgen):
                buf += data
                if len(buf) > CHUNK_SIZE:
                    yield buf
                    buf = b''
            yield buf
        yield self.stream.close_stream()


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
        with tarfile.open(fileobj=self.tempfile, mode='w:gz', encoding='utf8') as jobtar_obj:

            def add_json(file_name, data):
                file_content = json.dumps(data, ensure_ascii=False, sort_keys=True, indent=4).encode('utf-8')
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
            add_json('LightWeightCache.json', LightWeightCache(self.job).data)
            self.__add_reports_files(jobtar_obj)

    def __add_reports_files(self, jobtar):
        tables = [ReportSafe, ReportUnsafe, ReportUnknown, ReportComponent]
        for table in tables:
            for report in table.objects.filter(root__job=self.job):
                if report.archive:
                    jobtar.add(
                        os.path.join(settings.MEDIA_ROOT, report.archive.name),
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


class LightWeightCache(object):
    def __init__(self, job):
        self.data = {}
        try:
            self.root = ReportRoot.objects.get(job=job)
        except ObjectDoesNotExist:
            return
        self.data['safes'] = self.root.safes
        if job.light:
            self.data['resources'] = self.__get_light_resources()
            self.data['attrs_data'] = self.__get_attrs_statistic()

    def __get_light_resources(self):
        res_data = []
        for r in LightResource.objects.filter(report=self.root):
            res_data.append({
                'component': r.component.name if r.component is not None else None,
                'wall_time': r.wall_time, 'cpu_time': r.cpu_time, 'memory': r.memory
            })
        return res_data

    def __get_attrs_statistic(self):
        attrs_data = []
        for a_c in AttrStatistic.objects.filter(report__root=self.root, report__parent=None):
            if a_c.attr is None:
                attrs_data.append([a_c.name.name, None, a_c.safes, a_c.unsafes, a_c.unknowns])
            else:
                attrs_data.append([a_c.name.name, a_c.attr.value, a_c.safes, a_c.unsafes, a_c.unknowns])
        return attrs_data


class ReportsData(object):
    def __init__(self, job):
        try:
            self.root = ReportRoot.objects.get(job=job)
        except ObjectDoesNotExist:
            self.reports = []
        else:
            self.reports = self.__reports_data()

    def __report_component_data(self, report):
        self.__is_not_used()

        def get_date(d):
            return [d.year, d.month, d.day, d.hour, d.minute, d.second, d.microsecond] if d is not None else None

        data = None
        if report.data:
            with report.data as fp:
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
            'attrs': [],
            'log': report.log
        }

    def __report_leaf_data(self, report):
        self.__is_not_used()
        data = {
            'pk': report.pk,
            'parent': report.parent_id,
            'identifier': report.identifier,
            'attrs': []
        }
        if isinstance(report, ReportSafe):
            data['proof'] = report.proof
        elif isinstance(report, ReportUnsafe):
            data['error_trace'] = report.error_trace
        elif isinstance(report, ReportUnknown):
            data['problem_description'] = report.problem_description
            data['component'] = report.component.name
        return data

    def __reports_data(self):
        reports = []
        report_index = {}
        i = 0
        for rc in ReportComponent.objects.filter(root=self.root).select_related('computer', 'component').order_by('id'):
            report_index[rc.pk] = i
            reports.append(self.__report_component_data(rc))
            i += 1
        reports.append(ReportSafe.__name__)
        i += 1
        for safe in ReportSafe.objects.filter(root=self.root):
            report_index[safe.pk] = i
            reports.append(self.__report_leaf_data(safe))
            i += 1
        reports.append(ReportUnsafe.__name__)
        i += 1
        for unsafe in ReportUnsafe.objects.filter(root=self.root):
            report_index[unsafe.pk] = i
            reports.append(self.__report_leaf_data(unsafe))
            i += 1
        reports.append(ReportUnknown.__name__)
        i += 1
        for unknown in ReportUnknown.objects.filter(root=self.root).select_related('component'):
            report_index[unknown.pk] = i
            reports.append(self.__report_leaf_data(unknown))
            i += 1
        for ra in ReportAttr.objects.filter(report__root=self.root).select_related('attr', 'attr__name').order_by('id'):
            reports[report_index[ra.report_id]]['attrs'].append((ra.attr.name.name, ra.attr.value))
        return reports

    def __is_not_used(self):
        pass


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
        light_cache = {}
        for dir_path, dir_names, file_names in os.walk(self.job_dir):
            for file_name in file_names:
                if file_name == 'job.json':
                    try:
                        with open(os.path.join(dir_path, file_name), encoding='utf8') as fp:
                            jobdata = json.load(fp)
                    except Exception as e:
                        logger.exception("Can't parse job data: %s" % e)
                        return _("The job archive is corrupted")
                elif file_name == 'LightWeightCache.json':
                    try:
                        with open(os.path.join(dir_path, file_name), encoding='utf8') as fp:
                            light_cache = json.load(fp)
                    except Exception as e:
                        logger.exception("Can't parse lightweight results data: %s" % e)
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
                    else:
                        try:
                            files_in_db[b_dir + '/' + file_name] = file_get_or_create(
                                open(os.path.join(dir_path, file_name), mode='rb'), file_name, JobFile, True
                            )[1]
                        except Exception as e:
                            logger.exception("Can't save job files to DB: %s" % e)
                            return _("Creating job's file failed")

        if not isinstance(jobdata, dict):
            logger.error('job.json file was not found or contains wrong data')
            return _("The job archive is corrupted")
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
                        configuration=file_get_or_create(fp, 'config.json', JobFile)[0]
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
        self.__fill_lightweight_cache(light_cache)
        return None

    def __fill_lightweight_cache(self, light_cache):
        try:
            root = ReportRoot.objects.get(job=self.job)
        except ObjectDoesNotExist:
            return
        if 'safes' in light_cache:
            root.safes = int(light_cache['safes'])
            root.save()
        if 'resources' in light_cache:
            self.job.light = True
            self.job.save()
            LightResource.objects.bulk_create(list(LightResource(
                report=root, wall_time=int(d['wall_time']), cpu_time=int(d['cpu_time']), memory=int(d['memory']),
                component=Component.objects.get_or_create(name=d['component'])[0]
                if d['component'] is not None else None
            ) for d in light_cache['resources']))
        if 'attrs_data' in light_cache:
            root_report = ReportComponent.objects.get(root=root, parent=None)
            AttrStatistic.objects.filter(report=root_report).delete()
            AttrStatistic.objects.bulk_create(list(AttrStatistic(
                report=root_report,
                name=AttrName.objects.get_or_create(name=a_data[0])[0],
                attr=Attr.objects.get_or_create(
                    name=AttrName.objects.get_or_create(name=a_data[0])[0], value=a_data[1]
                )[0] if a_data[1] is not None else None,
                safes=a_data[2], unsafes=a_data[3], unknowns=a_data[4]
            ) for a_data in light_cache['attrs_data']))


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
        Verdict.objects.bulk_create(list(Verdict(report=self._pk_map[rep_id]) for rep_id in self._pk_map))
        Recalculation('all', json.dumps([self.job.pk], ensure_ascii=False, sort_keys=True, indent=4))

    def __create_report_component(self, data):
        parent = None
        if data.get('parent') is not None:
            parent = self._pk_map[data['parent']]
        create_data = {
            'root': self.job.reportroot, 'parent': parent, 'identifier': data['identifier'],
            'computer': Computer.objects.get_or_create(description=data['computer'])[0],
            'component': Component.objects.get_or_create(name=data['component'])[0],
            'cpu_time': data['resource']['cpu_time'] if data['resource'] is not None else None,
            'wall_time': data['resource']['wall_time'] if data['resource'] is not None else None,
            'memory': data['resource']['memory'] if data['resource'] is not None else None,
            'start_date': datetime(*data['start_date'], tzinfo=pytz.timezone('UTC')),
            'finish_date': datetime(*data['finish_date'], tzinfo=pytz.timezone('UTC')),
            'log': data.get('log')
        }
        self._pk_map[data['pk']] = ReportComponent(**create_data)
        if (ReportComponent.__name__, data['pk']) in self.files:
            with open(self.files[(ReportComponent.__name__, data['pk'])], mode='rb') as fp:
                self._pk_map[data['pk']].new_archive(REPORT_FILES_ARCHIVE, fp)
        if data['data'] is not None:
            self._pk_map[data['pk']].new_data('report-data.json', BytesIO(data['data'].encode('utf8')))
        self._pk_map[data['pk']].save()
        return self._pk_map[data['pk']].pk

    def __create_report_safe(self, data):
        report = ReportSafe(
            root=self.job.reportroot, parent=self._pk_map[data['parent']], identifier=data['identifier']
        )
        if (ReportSafe.__name__, data['pk']) in self.files:
            with open(self.files[(ReportSafe.__name__, data['pk'])], mode='rb') as fp:
                report.proof = data['proof']
                report.new_archive(REPORT_FILES_ARCHIVE, fp)
        report.save()
        return report.pk

    def __create_report_unknown(self, data):
        report = ReportUnknown.objects.create(
            root=self.job.reportroot, parent=self._pk_map[data['parent']], identifier=data['identifier'],
            problem_description=data['problem_description'],
            component=Component.objects.get_or_create(name=data['component'])[0]
        )
        with open(self.files[(ReportUnknown.__name__, data['pk'])], mode='rb') as fp:
            report.new_archive(REPORT_FILES_ARCHIVE, fp)
        report.save()
        return report.pk

    def __create_report_unsafe(self, data):
        report = ReportUnsafe.objects.create(
            root=self.job.reportroot, parent=self._pk_map[data['parent']],
            identifier=data['identifier'], error_trace=data['error_trace']
        )
        with open(self.files[(ReportUnsafe.__name__, data['pk'])], mode='rb') as fp:
            report.new_archive(REPORT_FILES_ARCHIVE, fp)
        report.save()
        return report.pk
