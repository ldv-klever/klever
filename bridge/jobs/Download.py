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
import re
import json
import zipfile
import tempfile
from io import BytesIO

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.files import File
from django.db import transaction
from django.utils.translation import ugettext_lazy as _
from django.utils.timezone import datetime, pytz

from bridge.vars import FORMAT, JOB_STATUS, REPORT_ARCHIVE, JOB_WEIGHT
from bridge.utils import logger, file_get_or_create, unique_id, BridgeException
from bridge.ZipGenerator import ZipStream, CHUNK_SIZE

from jobs.models import Job, RunHistory, JobFile
from reports.models import Report, ReportRoot, ReportSafe, ReportUnsafe, ReportUnknown, ReportComponent,\
    Component, Computer, ReportAttr, ComponentResource, CoverageArchive, AttrFile, ErrorTraceSource
from service.models import SolvingProgress, JobProgress, Scheduler
from jobs.utils import create_job, update_job, change_job_status, GetConfiguration, remove_jobs_by_id
from reports.utils import AttrData
from service.utils import StartJobDecision
from tools.utils import Recalculation

from reports.UploadReport import UploadReport

ARCHIVE_FORMAT = 10


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


class AttrDataArchive:
    def __init__(self, job):
        self._job = job
        self.stream = ZipStream()

    def __iter__(self):
        for afile in AttrFile.objects.filter(root__job=self._job):
            file_name = os.path.join(settings.MEDIA_ROOT, afile.file.name)
            arc_name = os.path.join('{0}{1}'.format(afile.id, os.path.splitext(afile.file.name)[-1]))
            buf = b''
            for data in self.stream.compress_file(file_name, arc_name):
                buf += data
                if len(buf) > CHUNK_SIZE:
                    yield buf
                    buf = b''
            if len(buf) > 0:
                yield buf
        yield self.stream.close_stream()


class JobArchiveGenerator:
    def __init__(self, job):
        self.job = job
        self.arcname = 'Job-%s.zip' % self.job.identifier[:10]
        self.arch_files = {}
        self.files_to_add = []
        self.stream = ZipStream()

    def __iter__(self):
        for job_v in self.job.versions.all():
            for data in self.stream.compress_string('version-%s.json' % job_v.version, self.__version_data(job_v)):
                yield data
        for data in self.stream.compress_string('job.json', self.__job_data()):
            yield data
        reportsdata = ReportsData(self.job)
        for data in self.stream.compress_string('reports.json', json.dumps(
                reportsdata.reports, ensure_ascii=False, sort_keys=True, indent=4).encode('utf-8')):
            yield data
        for data in self.stream.compress_string('computers.json', json.dumps(
                reportsdata.computers, ensure_ascii=False, sort_keys=True, indent=4).encode('utf-8')):
            yield data
        for data in self.stream.compress_string('coverage_archives.json', json.dumps(
                reportsdata.coverage, ensure_ascii=False, sort_keys=True, indent=4).encode('utf-8')):
            yield data
        for data in self.stream.compress_string('Resources.json', json.dumps(
                ResourcesCache(self.job).data, ensure_ascii=False, sort_keys=True, indent=4).encode('utf-8')):
            yield data
        self.__add_reports_files()
        self.__add_coverage_files(reportsdata.coverage_arch_names)
        for file_path, arcname in self.files_to_add:
            for data in self.stream.compress_file(file_path, arcname):
                yield data
        if AttrFile.objects.filter(root__job=self.job).count() > 0:
            for data in self.stream.compress_stream('AttrData.zip', AttrDataArchive(self.job)):
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
            'global_role': job_v.global_role,
            'comment': job_v.comment,
        }, ensure_ascii=False, sort_keys=True, indent=4).encode('utf-8')

    def __job_data(self):
        return json.dumps({
            'archive_format': ARCHIVE_FORMAT, 'format': self.job.format, 'identifier': self.job.identifier,
            'status': self.job.status, 'files_map': self.arch_files, 'name': self.job.name,
            'run_history': self.__add_run_history_files(), 'weight': self.job.weight, 'safe marks': self.job.safe_marks,
            'progress': self.__get_progress_data()
        }, ensure_ascii=False, sort_keys=True, indent=4).encode('utf-8')

    def __get_progress_data(self):
        data = {}
        try:
            sp = SolvingProgress.objects.get(job=self.job)
        except ObjectDoesNotExist:
            pass
        else:
            data.update({
                'priority': sp.priority, 'scheduler': sp.scheduler.type,
                'start_date': sp.start_date.timestamp() if sp.start_date is not None else None,
                'finish_date': sp.finish_date.timestamp() if sp.finish_date is not None else None,
                'tasks_total': sp.tasks_total, 'tasks_pending': sp.tasks_pending,
                'tasks_processing': sp.tasks_processing, 'tasks_finished': sp.tasks_finished,
                'tasks_error': sp.tasks_error, 'tasks_cancelled': sp.tasks_cancelled, 'solutions': sp.solutions,
                'error': sp.error, 'configuration': sp.configuration.decode('utf8')
            })
        try:
            jp = JobProgress.objects.get(job=self.job)
        except ObjectDoesNotExist:
            pass
        else:
            data.update({
                'total_sj': jp.total_sj, 'failed_sj': jp.failed_sj, 'solved_sj': jp.solved_sj,
                'start_sj': jp.start_sj.timestamp() if jp.start_sj is not None else None,
                'finish_sj': jp.finish_sj.timestamp() if jp.finish_sj is not None else None,
                'total_ts': jp.total_ts, 'failed_ts': jp.failed_ts, 'solved_ts': jp.solved_ts,
                'start_ts': jp.start_ts.timestamp() if jp.start_ts is not None else None,
                'finish_ts': jp.finish_ts.timestamp() if jp.finish_ts is not None else None,
                'expected_time_sj': jp.expected_time_sj, 'expected_time_ts': jp.expected_time_ts,
                'gag_text_sj': jp.gag_text_sj, 'gag_text_ts': jp.gag_text_ts
            })
        return data

    def __add_run_history_files(self):
        data = []
        for rh in self.job.runhistory_set.order_by('date'):
            self.files_to_add.append((
                os.path.join(settings.MEDIA_ROOT, rh.configuration.file.name),
                os.path.join('Configurations', "%s.json" % rh.pk)
            ))
            data.append({'id': rh.pk, 'status': rh.status, 'date': rh.date.timestamp()})
        return data

    def __add_reports_files(self):
        try:
            root_id = ReportRoot.objects.get(job=self.job).id
        except ObjectDoesNotExist:
            return
        for report in ReportSafe.objects.filter(root_id=root_id):
            if report.proof:
                self.files_to_add.append((
                    os.path.join(settings.MEDIA_ROOT, report.proof.name),
                    os.path.join('ReportSafe', 'proof_%s.zip' % report.pk)
                ))
        for report in ReportUnsafe.objects.filter(root_id=root_id):
            self.files_to_add.append((
                os.path.join(settings.MEDIA_ROOT, report.error_trace.name),
                os.path.join('ReportUnsafe', 'trace_%s.zip' % report.pk)
            ))
        for report in ReportUnknown.objects.filter(root_id=root_id):
            self.files_to_add.append((
                os.path.join(settings.MEDIA_ROOT, report.problem_description.name),
                os.path.join('ReportUnknown', 'problem_%s.zip' % report.pk)
            ))
        for report in ReportComponent.objects.filter(root_id=root_id):
            if report.log:
                self.files_to_add.append((
                    os.path.join(settings.MEDIA_ROOT, report.log.name),
                    os.path.join('ReportComponent', 'log_%s.zip' % report.pk)
                ))
            if report.verifier_input:
                self.files_to_add.append((
                    os.path.join(settings.MEDIA_ROOT, report.verifier_input.name),
                    os.path.join('ReportComponent', 'verifier_input_%s.zip' % report.pk)
                ))
        for source in ErrorTraceSource.objects.filter(root_id=root_id):
            self.files_to_add.append((
                os.path.join(settings.MEDIA_ROOT, source.archive.name),
                os.path.join('ErrorTraceSource', 'source_%s.zip' % source.id)
            ))

    def __add_coverage_files(self, archives):
        for i in range(len(archives)):
            self.files_to_add.append((
                os.path.join(settings.MEDIA_ROOT, archives[i]), os.path.join('Coverages', '%s.zip' % i)
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
            if len(buf) > 0:
                yield buf
        yield self.stream.close_stream()


class JobsTreesGen:
    def __init__(self, jobs_ids):
        self._tree = {}
        self.jobs = self.__get_jobs(jobs_ids)
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
            if len(buf) > 0:
                yield buf
        for data in self.stream.compress_string('tree.json', json.dumps(self._tree, sort_keys=True, indent=2)):
            yield data
        yield self.stream.close_stream()

    def __get_jobs(self, jobs_ids):
        jobs = []
        for j in Job.objects.filter(id__in=jobs_ids):
            jobs.append(j)
            self._tree[j.identifier] = None
        parent_ids = jobs_ids
        while len(parent_ids) > 0:
            new_parents = []
            for j in Job.objects.filter(parent_id__in=parent_ids).select_related('parent'):
                if j.identifier not in self._tree:
                    jobs.append(j)
                    new_parents.append(j.id)
                self._tree[j.identifier] = j.parent.identifier
            parent_ids = new_parents
        return jobs


class ResourcesCache:
    def __init__(self, job):
        self.data = {}
        try:
            self.root = ReportRoot.objects.get(job=job)
        except ObjectDoesNotExist:
            return
        self.data = self.__get_resources()

    def __get_resources(self):
        res_data = []
        for r in ComponentResource.objects.filter(report__root=self.root):
            res_data.append({
                'id': r.report_id, 'component': r.component.name if r.component is not None else None,
                'wall_time': r.wall_time, 'cpu_time': r.cpu_time, 'memory': r.memory
            })
        return res_data


class ReportsData:
    def __init__(self, job):
        self.computers = {}
        self.coverage = []
        self.coverage_arch_names = []
        self._parents = {None: None}
        try:
            self.root = ReportRoot.objects.get(job=job)
        except ObjectDoesNotExist:
            self.reports = []
        else:
            self.reports = self.__reports_data()
            self.__get_coverage_data()

    def __report_component_data(self, report):
        data = None
        if report.data:
            with report.data as fp:
                data = fp.read().decode('utf8')
        if report.computer_id not in self.computers:
            self.computers[str(report.computer_id)] = report.computer.description
        self._parents[report.id] = report.identifier
        return {
            'pk': report.pk,
            'parent': self._parents[report.parent_id],
            'identifier': report.identifier,
            'computer': str(report.computer_id),
            'component': report.component.name,
            'verification': report.verification,
            'resource': {
                'cpu_time': report.cpu_time,
                'wall_time': report.wall_time,
                'memory': report.memory,
            } if all(x is not None for x in [report.cpu_time, report.wall_time, report.memory]) else None,
            'start_date': report.start_date.timestamp(),
            'finish_date': report.finish_date.timestamp() if report.finish_date is not None else None,
            'data': data,
            'covnum': report.covnum,
            'attrs': []
        }

    def __report_leaf_data(self, report):
        data = {
            'pk': report.pk,
            'parent': self._parents[report.parent_id],
            'identifier': report.identifier,
            'cpu_time': report.cpu_time,
            'wall_time': report.wall_time,
            'memory': report.memory,
            'attrs': []
        }
        if isinstance(report, ReportUnknown):
            data['component'] = report.component.name
        elif isinstance(report, ReportUnsafe):
            data['trace_id'] = report.trace_id
            data['source'] = report.source_id
        return data

    def __reports_data(self):
        reports = []
        report_index = {}
        i = 0
        for rc in ReportComponent.objects.filter(root=self.root).select_related('component').order_by('id'):
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
        for ra in ReportAttr.objects.filter(report__root=self.root).select_related('attr', 'attr__name', 'data')\
                .order_by('id'):
            ra_data = None
            if ra.data is not None:
                ra_data = os.path.join('{0}{1}'.format(ra.data_id, os.path.splitext(ra.data.file.name)[-1]))
            reports[report_index[ra.report_id]]['attrs'].append([
                ra.attr.name.name, ra.attr.value, ra.compare, ra.associate, ra_data
            ])
        return reports

    def __get_coverage_data(self):
        for carch in CoverageArchive.objects.filter(report__root=self.root):
            self.coverage.append([carch.report_id, carch.identifier])
            self.coverage_arch_names.append(carch.archive.name)

    def __is_not_used(self):
        pass


class UploadTree:
    def __init__(self, parent_id, user, jobs_dir):
        self._parent = self.__get_parent(parent_id)
        self._user = user
        self._jobsdir = jobs_dir

        self._uploaded = {}
        self._tree = self.__get_tree()

        try:
            self.__upload_tree()
        except Exception:
            remove_jobs_by_id(self._user, list(j.id for j in self._uploaded.values()))
            raise

    def __get_tree(self):
        tree_fname = os.path.join(self._jobsdir, 'tree.json')
        if not os.path.exists(tree_fname):
            raise BridgeException(_('The file with tree structure was not found'))
        with open(tree_fname, mode='r', encoding='utf8') as fp:
            return json.loads(fp.read())

    def __get_jobs_order(self):
        jobs = []
        for j_id in self._tree:
            if self._tree[j_id] is None:
                jobs.append(j_id)
        while True:
            has_child = False
            for j_id in self._tree:
                if self._tree[j_id] in jobs and j_id not in jobs:
                    jobs.append(j_id)
                    has_child = True
            if not has_child:
                break
        return jobs

    def __upload_tree(self):
        for j_id in self.__get_jobs_order():
            jobzip_name = os.path.join(self._jobsdir, 'Job-%s.zip' % j_id[:10])
            if not os.path.exists(jobzip_name):
                raise BridgeException(_('One of the job archives was not found'))
            if self._tree[j_id] is None:
                parent = self._parent
            elif self._tree[j_id] in self._uploaded:
                parent = self._uploaded[self._tree[j_id]]
            else:
                raise BridgeException()
            self.__upload_job(jobzip_name, parent)

    def __upload_job(self, jobarch, parent):
        try:
            jobdir = self.__extract_archive(jobarch)
        except Exception as e:
            logger.exception("Archive extraction failed: %s" % e, stack_info=True)
            raise BridgeException(_('Extraction of the archive "%(arcname)s" has failed') % {
                'arcname': os.path.basename(jobarch)
            })
        try:
            res = UploadJob(parent, self._user, jobdir.name)
        except BridgeException as e:
            raise BridgeException(_('Creating the job from archive "%(arcname)s" failed: %(message)s') % {
                    'arcname': os.path.basename(jobarch), 'message': str(e)
                })
        except Exception as e:
            logger.exception(e)
            raise BridgeException(_('Creating the job from archive "%(arcname)s" failed: %(message)s') % {
                    'arcname': os.path.basename(jobarch), 'message': _('The job archive is corrupted')
                })
        self._uploaded[res.job.identifier] = res.job

    def __extract_archive(self, jobarch):
        self.__is_not_used()
        with open(jobarch, mode='rb') as fp:
            if os.path.splitext(jobarch)[-1] != '.zip':
                raise ValueError('Only zip archives are supported')
            with zipfile.ZipFile(fp, mode='r') as zfp:
                tmp_dir_name = tempfile.TemporaryDirectory()
                zfp.extractall(tmp_dir_name.name)
            return tmp_dir_name

    def __get_parent(self, parent_id):
        self.__is_not_used()
        if len(parent_id) == 0:
            return None
        parents = Job.objects.filter(identifier__startswith=parent_id)
        if len(parents) == 0:
            raise BridgeException(_("The parent with the specified identifier was not found"))
        elif len(parents) > 1:
            raise BridgeException(_("Too many jobs starts with the specified identifier"))
        return parents.first()

    def __is_not_used(self):
        pass


class UploadJob:
    def __init__(self, parent, user, job_dir):
        self.parent = parent
        self.job = None
        self.user = user
        self.job_dir = job_dir
        self.__create_job_from_tar()

    def __create_job_from_tar(self):
        jobdata = None
        reports_data = None
        computers = {}
        files_in_db = {}
        versions_data = {}
        report_files = {}
        run_history_files = {}
        resources = {}
        coverage_data = []
        coverage_files = {}
        attr_data = None
        for dir_path, dir_names, file_names in os.walk(self.job_dir):
            for file_name in file_names:
                rel_path = os.path.relpath(os.path.join(dir_path, file_name), self.job_dir)
                if rel_path == 'job.json':
                    with open(os.path.join(dir_path, file_name), encoding='utf8') as fp:
                        jobdata = json.load(fp)
                elif rel_path == 'Resources.json':
                    with open(os.path.join(dir_path, file_name), encoding='utf8') as fp:
                        resources = json.load(fp)
                elif rel_path == 'reports.json':
                    with open(os.path.join(dir_path, file_name), encoding='utf8') as fp:
                        reports_data = json.load(fp)
                elif rel_path == 'computers.json':
                    with open(os.path.join(dir_path, file_name), encoding='utf8') as fp:
                        computers = json.load(fp)
                elif rel_path == 'coverage_archives.json':
                    with open(os.path.join(dir_path, file_name), encoding='utf8') as fp:
                        coverage_data = json.load(fp)
                elif rel_path == 'AttrData.zip':
                    attr_data = File(open(os.path.join(dir_path, file_name), mode='rb'))
                elif rel_path.startswith('version-'):
                    m = re.match('version-(\d+)\.json', rel_path)
                    if m is None:
                        raise BridgeException(_('Unknown file in the archive: %(filename)s') % {'filename': rel_path})
                    with open(os.path.join(dir_path, file_name), encoding='utf8') as fp:
                        versions_data[int(m.group(1))] = json.load(fp)
                elif rel_path.startswith('Configurations'):
                    run_history_files[int(file_name.replace('.json', ''))] = os.path.join(dir_path, file_name)
                elif rel_path.startswith('Coverages'):
                    m = re.match('(\d+)\.zip', file_name)
                    if m is not None:
                        coverage_files[int(m.group(1))] = os.path.join(dir_path, file_name)
                else:
                    b_dir = os.path.basename(dir_path)
                    if not rel_path.startswith(b_dir):
                        raise BridgeException(_('Unknown file in the archive: %(filename)s') % {'filename': rel_path})
                    if b_dir in {'ReportSafe', 'ReportUnsafe', 'ReportUnknown', 'ReportComponent', 'ErrorTraceSource'}:
                        m = re.match('(.*)_(\d+)\.zip', file_name)
                        if m is not None:
                            report_files[(b_dir, m.group(1), int(m.group(2)))] = os.path.join(dir_path, file_name)
                    else:
                        try:
                            files_in_db[b_dir + '/' + file_name] = file_get_or_create(
                                open(os.path.join(dir_path, file_name), mode='rb'), file_name, JobFile, True
                            )[1]
                        except Exception as e:
                            logger.exception("Can't save job files to DB: %s" % e)
                            raise BridgeException(_("Creating job's file failed"))

        if not isinstance(jobdata, dict):
            raise ValueError('job.json file was not found or contains wrong data')
        # Check job data
        if any(x not in jobdata for x in ['format', 'name', 'status', 'files_map',
                                          'run_history', 'weight', 'safe marks', 'progress']):
            raise BridgeException(_("The job archive was corrupted"))
        if jobdata.get('archive_format', 0) != ARCHIVE_FORMAT:
            raise BridgeException(_("The job archive format is not supported"))
        if jobdata['format'] != FORMAT:
            raise BridgeException(_("The job format is not supported"))
        if 'identifier' in jobdata:
            if isinstance(jobdata['identifier'], str) and len(jobdata['identifier']) > 0:
                if len(Job.objects.filter(identifier=jobdata['identifier'])) > 0:
                    # del jobdata['identifier']
                    raise BridgeException(_("The job with identifier specified in the archive already exists"))
            else:
                del jobdata['identifier']
        if jobdata['weight'] not in set(w[0] for w in JOB_WEIGHT):
            raise ValueError('Wrong job weight: %s' % jobdata['weight'])
        if jobdata['status'] not in list(x[0] for x in JOB_STATUS):
            raise ValueError("The job status is wrong: %s" % jobdata['status'])
        for f_id in list(jobdata['files_map']):
            if jobdata['files_map'][f_id] in files_in_db:
                jobdata['files_map'][int(f_id)] = files_in_db[jobdata['files_map'][f_id]]
                del jobdata['files_map'][f_id]
            else:
                raise ValueError('Not enough files in "Files" directory')

        # Check versions data
        if len(versions_data) == 0:
            raise ValueError("There are no job's versions in the archive")
        for version in versions_data:
            if any(x not in versions_data[version] for x in ['description', 'comment', 'global_role', 'filedata']):
                raise ValueError("The job version data is corrupted")

        # Update versions' files data
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

        # Creating the job
        try:
            job = create_job({
                'name': jobdata['name'],
                'identifier': jobdata.get('identifier'),
                'author': self.user,
                'description': version_list[0]['description'],
                'parent': self.parent,
                'global_role': version_list[0]['global_role'],
                'filedata': version_list[0]['filedata'],
                'comment': version_list[0]['comment'],
                'safe marks': jobdata['safe marks']
            })
        except Exception as e:
            logger.exception(e, stack_info=True)
            raise BridgeException(_('Saving the job failed'))
        job.weight = jobdata['weight']
        job.save()

        # Creating job's run history
        try:
            for rh in jobdata['run_history']:
                if rh['status'] not in list(x[0] for x in JOB_STATUS):
                    raise BridgeException(_("The job archive is corrupted"))
                with open(run_history_files[rh['id']], mode='rb') as fp:
                    RunHistory.objects.create(
                        job=job, status=rh['status'],
                        date=datetime.fromtimestamp(rh['date'], pytz.timezone('UTC')),
                        configuration=file_get_or_create(fp, 'config.json', JobFile)[0]
                    )
        except Exception as e:
            job.delete()
            raise ValueError("Run history data is corrupted: %s" % e)

        # Creating job's versions
        for version_data in version_list[1:]:
            try:
                update_job({
                    'job': job,
                    'author': self.user,
                    'description': version_data['description'],
                    'parent': self.parent,
                    'filedata': version_data['filedata'],
                    'global_role': version_data['global_role'],
                    'comment': version_data['comment']
                })
            except Exception as e:
                logger.exception(e)
                job.delete()
                raise BridgeException(_('Updating the job failed'))

        # Change job's status as it was in downloaded archive
        change_job_status(job, jobdata['status'])
        self.__create_progress(job, jobdata['progress'])
        ReportRoot.objects.create(user=self.user, job=job)
        try:
            UploadReports(job, computers, reports_data, report_files,
                          resources, coverage_data, coverage_files, attr_data)
        except BridgeException:
            job.delete()
            raise
        except Exception as e:
            logger.exception("Uploading reports failed: %s" % e, stack_info=True)
            job.delete()
            raise BridgeException(_("Unknown error while uploading reports"))
        self.job = job

    def __create_progress(self, job, data):
        self.__is_not_used()
        if 'scheduler' in data:
            try:
                scheduler = Scheduler.objects.get(type=data['scheduler'])
            except ObjectDoesNotExist:
                raise BridgeException(_('Scheduler for the job was not found'))
            SolvingProgress.objects.create(
                job=job, scheduler=scheduler, fake=True, priority=data['priority'],
                start_date=datetime.fromtimestamp(data['start_date'], pytz.timezone('UTC'))
                if data['start_date'] is not None else None,
                finish_date=datetime.fromtimestamp(data['finish_date'], pytz.timezone('UTC'))
                if data['finish_date'] is not None else None,
                tasks_total=data['tasks_total'], tasks_pending=data['tasks_pending'],
                tasks_processing=data['tasks_processing'], tasks_finished=data['tasks_finished'],
                tasks_error=data['tasks_error'], tasks_cancelled=data['tasks_cancelled'],
                solutions=data['solutions'], error=data['error'], configuration=data['configuration'].encode('utf8')
            )
        if 'total_sj' in data:
            JobProgress.objects.create(
                job=job,
                total_sj=data['total_sj'], failed_sj=data['failed_sj'], solved_sj=data['solved_sj'],
                start_sj=datetime.fromtimestamp(data['start_sj'], pytz.timezone('UTC'))
                if data['start_sj'] is not None else None,
                finish_sj=datetime.fromtimestamp(data['finish_sj'], pytz.timezone('UTC'))
                if data['finish_sj'] is not None else None,
                total_ts=data['total_ts'], failed_ts=data['failed_ts'], solved_ts=data['solved_ts'],
                start_ts=datetime.fromtimestamp(data['start_ts'], pytz.timezone('UTC'))
                if data['start_ts'] is not None else None,
                finish_ts=datetime.fromtimestamp(data['finish_ts'], pytz.timezone('UTC'))
                if data['finish_ts'] is not None else None,
                expected_time_sj=data['expected_time_sj'], expected_time_ts=data['expected_time_ts'],
                gag_text_sj=data['gag_text_sj'], gag_text_ts=data['gag_text_ts']
            )

    def __is_not_used(self):
        pass


class UploadReports:
    def __init__(self, job, computers, data, files, resources, coverage, cov_archives, attr_data):
        self.job = job
        self.data = data
        self.files = files
        self._resources = resources
        self._coverage = coverage
        self._cov_archives = cov_archives
        self._parents = {None: None}
        self._indexes = {}
        self._tree = []
        self._unsafes = []
        self._safes = []
        self._unknowns = []
        self._computers = computers
        self.__upload_computers()
        self._components = {}
        self._attrs = AttrData(self.job.reportroot.id, attr_data)
        self._rc_id_map = {}
        self.__upload_all()
        self.__upload_coverage()
        self.__upload_resources_cache()
        Recalculation('for_uploaded', json.dumps([self.job.pk], ensure_ascii=False))

    def __fix_identifer(self, i):
        m = re.match('.*?(/.*)', self.data[i]['identifier'])
        if m is None:
            self.data[i]['identifier'] = self.job.identifier
        else:
            self.data[i]['identifier'] = self.job.identifier + m.group(1)
        if self.data[i]['parent'] is not None:
            m = re.match('.*?(/.*)', self.data[i]['parent'])
            if m is None:
                self.data[i]['parent'] = self.job.identifier
            else:
                self.data[i]['parent'] = self.job.identifier + m.group(1)

    def __upload_computers(self):
        for c_id in self._computers:
            computer = Computer.objects.get_or_create(description=self._computers[c_id])[0]
            self._computers[c_id] = computer.id

    def __upload_all(self):
        curr_func = self.__add_report_component
        for i in range(len(self.data)):
            if isinstance(self.data[i], dict):
                self.__fix_identifer(i)
                curr_func(i)
            elif isinstance(self.data[i], str) and self.data[i] == ReportSafe.__name__:
                def curr_func(x):
                    self._safes.append(x)
                    self._indexes[self.data[x]['identifier']] = x
            elif isinstance(self.data[i], str) and self.data[i] == ReportUnsafe.__name__:
                def curr_func(x):
                    self._unsafes.append(x)
                    self._indexes[self.data[x]['identifier']] = x
            elif isinstance(self.data[i], str) and self.data[i] == ReportUnknown.__name__:
                def curr_func(x):
                    self._unknowns.append(x)
                    self._indexes[self.data[x]['identifier']] = x
        for lvl in range(len(self._tree)):
            self.__upload_report_components(lvl)
            for report in ReportComponent.objects.filter(root=self.job.reportroot):
                self._parents[report.identifier] = report.id
        self.__upload_safe_reports()
        self.__upload_unsafe_reports()
        self.__upload_unknown_reports()
        for report in Report.objects.filter(root=self.job.reportroot).only('id', 'identifier'):
            i = self._indexes[report.identifier]
            for attr in self.data[i]['attrs']:
                self._attrs.add(report.id, *attr)
        self._attrs.upload()

    @transaction.atomic
    def __upload_report_components(self, lvl):
        for identifier in self._tree[lvl]:
            i = self._indexes[identifier]
            report = ReportComponent(
                identifier=identifier, root=self.job.reportroot, covnum=self.data[i]['covnum'],
                parent_id=self._parents[self.data[i].get('parent')],
                computer_id=self._computers[self.data[i]['computer']],
                component_id=self.__get_component(self.data[i]['component']),
                verification=self.data[i]['verification'],
                start_date=datetime.fromtimestamp(self.data[i]['start_date'], pytz.timezone('UTC')),
                finish_date=datetime.fromtimestamp(self.data[i]['finish_date'], pytz.timezone('UTC'))
                if self.data[i]['finish_date'] is not None else None
            )
            if self.data[i]['resource'] is not None:
                report.cpu_time = self.data[i]['resource']['cpu_time']
                report.wall_time = self.data[i]['resource']['wall_time']
                report.memory = self.data[i]['resource']['memory']

            log_id = (ReportComponent.__name__, 'log', self.data[i]['pk'])
            if log_id in self.files:
                with open(self.files[log_id], mode='rb') as fp:
                    report.add_log(REPORT_ARCHIVE['log'], fp)

            verifier_input_id = (ReportComponent.__name__, 'verifier_input', self.data[i]['pk'])
            if verifier_input_id in self.files:
                with open(self.files[verifier_input_id], mode='rb') as fp:
                    report.add_verifier_input(REPORT_ARCHIVE['verifier input'], fp)

            if self.data[i]['data'] is not None:
                report.new_data('report-data.json', BytesIO(self.data[i]['data'].encode('utf8')))

            report.save()
            self._rc_id_map[self.data[i]['pk']] = report.id

    @transaction.atomic
    def __upload_safe_reports(self):
        for i in self._safes:
            report = ReportSafe(
                root=self.job.reportroot, identifier=self.data[i]['identifier'],
                parent_id=self._parents[self.data[i]['parent']],
                cpu_time=self.data[i]['cpu_time'], wall_time=self.data[i]['wall_time'], memory=self.data[i]['memory']
            )
            proof_id = (ReportSafe.__name__, 'proof', self.data[i]['pk'])
            if proof_id in self.files:
                with open(self.files[proof_id], mode='rb') as fp:
                    report.add_proof(REPORT_ARCHIVE['proof'], fp)
            report.save()

    @transaction.atomic
    def __upload_unsafe_reports(self):
        sources = {}
        for i in self._unsafes:
            # Upload error trace sources if it was not uploaded for already created error traces
            if self.data[i]['source'] not in sources:
                source_arch_id = (ErrorTraceSource.__name__, 'source', self.data[i]['source'])
                new_source = ErrorTraceSource(root=self.job.reportroot)
                with open(self.files[source_arch_id], mode='rb') as fp:
                    new_source.add_sources(REPORT_ARCHIVE['sources'], fp, True)
                sources[self.data[i]['source']] = new_source.id

            # Check if error trace identifier exists and is unique
            if 'trace_id' not in self.data[i] or \
                    ReportUnsafe.objects.filter(trace_id=self.data[i]['trace_id']).count() > 0:
                self.data[i]['trace_id'] = unique_id()

            report = ReportUnsafe(
                root=self.job.reportroot, identifier=self.data[i]['identifier'], trace_id=self.data[i]['trace_id'],
                source_id=sources[self.data[i]['source']], parent_id=self._parents[self.data[i]['parent']],
                cpu_time=self.data[i]['cpu_time'], wall_time=self.data[i]['wall_time'], memory=self.data[i]['memory']
            )
            trace_id = (ReportUnsafe.__name__, 'trace', self.data[i]['pk'])
            with open(self.files[trace_id], mode='rb') as fp:
                report.add_trace(REPORT_ARCHIVE['error trace'], fp, True)

    @transaction.atomic
    def __upload_unknown_reports(self):
        for i in self._unknowns:
            report = ReportUnknown(
                root=self.job.reportroot, identifier=self.data[i]['identifier'],
                parent_id=self._parents[self.data[i]['parent']],
                component_id=self.__get_component(self.data[i]['component']),
                cpu_time=self.data[i]['cpu_time'], wall_time=self.data[i]['wall_time'], memory=self.data[i]['memory']
            )
            problem_id = (ReportUnknown.__name__, 'problem', self.data[i]['pk'])
            with open(self.files[problem_id], mode='rb') as fp:
                report.add_problem_desc(REPORT_ARCHIVE['problem desc'], fp)
            report.save()

    def __get_component(self, name):
        if name not in self._components:
            component = Component.objects.get_or_create(name=name)[0]
            self._components[name] = component.id
        return self._components[name]

    def __add_report_component(self, i):
        p_id = self.data[i].get('parent')
        if p_id is None:
            self.__add_to_tree(0, i)
        else:
            for j in range(len(self._tree)):
                if p_id in self._tree[j]:
                    self.__add_to_tree(j + 1, i)
                    break
            else:
                raise ValueError('The report parent was not found in data')

    def __add_to_tree(self, lvl, i):
        while len(self._tree) <= lvl:
            self._tree.append(set())
        self._tree[lvl].add(self.data[i]['identifier'])
        self._indexes[self.data[i]['identifier']] = i

    @transaction.atomic
    def __upload_coverage(self):
        for i in range(len(self._coverage)):
            if i in self._cov_archives and self._coverage[i][0] in self._rc_id_map:
                carch = CoverageArchive(
                    report_id=self._rc_id_map[self._coverage[i][0]], identifier=self._coverage[i][1]
                )
                with open(self._cov_archives[i], mode='rb') as fp:
                    carch.save_archive(REPORT_ARCHIVE['coverage'], fp)

    def __upload_resources_cache(self):
        components = {}
        res_cache = []
        for res_data in self._resources:
            old_id = res_data['id']
            if old_id not in self._rc_id_map:
                continue
            component = res_data['component']
            if component is not None:
                if component not in components:
                    components[component] = Component.objects.get_or_create(name=component)[0].id
                component = components[component]
            res_cache.append(ComponentResource(
                report_id=self._rc_id_map[old_id], component_id=component,
                cpu_time=res_data['cpu_time'], wall_time=res_data['wall_time'], memory=res_data['memory']
            ))
        ComponentResource.objects.bulk_create(res_cache)


def update_identifier(job_id):
    from bridge.utils import unique_id
    job = Job.objects.get(id=job_id)
    new_id = unique_id()
    len_old = len(job.identifier)
    job.identifier = new_id
    job.save()
    with transaction.atomic():
        for r in Report.objects.filter(root__job=job):
            r.identifier = job.identifier + r.identifier[len_old:]
            r.save()


class UploadReportsWithoutDecision:
    def __init__(self, job, user, reports_dir):
        self._job = job
        self._user = user
        self._reports_dir = reports_dir
        self._data = None
        self._files = {}
        self.__read_files()
        self._tree = {}
        self.__get_reports_tree()

        self.__prepare_job()
        self._job = Job.objects.get(id=self._job.id)
        try:
            self.__upload_children(None)
        except Exception:
            ReportRoot.objects.get(job=self._job).delete()
            self._job.status = JOB_STATUS[4][0]
            self._job.save()
            raise
        change_job_status(self._job, JOB_STATUS[3][0])

    def __read_files(self):
        for dir_path, dir_names, file_names in os.walk(self._reports_dir):
            for file_name in file_names:
                rel_path = os.path.relpath(os.path.join(dir_path, file_name), self._reports_dir)
                if rel_path == 'reports.json':
                    with open(os.path.join(dir_path, file_name), encoding='utf8') as fp:
                        self.data = json.load(fp)
                else:
                    self._files[rel_path] = os.path.join(dir_path, file_name)

    def __get_reports_tree(self):
        if not isinstance(self.data, list) or len(self.data) == 0:
            raise BridgeException(_('Wrong format of main reports file or it is not found'))
        indexes = {}
        for i in range(len(self.data)):
            self._tree[i] = indexes.get(self.data[i]['parent id'])
            indexes[self.data[i]['id']] = i

    def __prepare_job(self):
        configuration = GetConfiguration(conf_name=settings.DEF_KLEVER_CORE_MODE).configuration
        if configuration is None:
            raise ValueError("Can't get default configuration")
        StartJobDecision(self._user, self._job.id, configuration, fake=True)
        change_job_status(self._job, JOB_STATUS[2][0])

    def __upload_children(self, parent_id):
        actions = {
            'component': self.__upload_component,
            'verification': self.__upload_verification,
            'safe': self.__upload_safe,
            'unsafe': self.__upload_unsafe,
            'unknown': self.__upload_unknown
        }
        for report in self.data:
            if report['parent id'] == parent_id:
                actions[report['type']](report)

    def __upload_component(self, data):
        start_report = data.copy()
        self.__clear_report(['id', 'parent id', 'name', 'attrs', 'comp'], start_report)
        start_report['type'] = 'start'
        if start_report['id'] == '/':
            del start_report['parent id']

        res = UploadReport(self._job, start_report)
        if res.error is not None:
            raise ValueError(res.error)

        self.__upload_children(data['id'])

        finish_report = data.copy()
        self.__clear_report(['id', 'data', 'resources', 'log', 'coverage'], finish_report)
        finish_report['type'] = 'finish'
        if 'resources' not in finish_report:
            finish_report['resources'] = {'CPU time': 0, 'wall time': 0, 'memory size': 0}

        archives = {}
        for arch_type in ['log', 'coverage']:
            if arch_type in data:
                try:
                    archives[data[arch_type]] = open(self._files[data[arch_type]], mode='rb')
                except Exception:
                    for fp in archives.values():
                        fp.close()
                    raise

        res = UploadReport(self._job, finish_report, archives=archives)
        for fp in archives.values():
            fp.close()

        if res.error is not None:
            raise ValueError(res.error)

    def __upload_verification(self, data):
        start_report = data.copy()
        self.__clear_report(['id', 'parent id', 'name', 'attrs', 'comp', 'resources',
                             'log', 'coverage', 'input files of static verifiers'], start_report)
        start_report['type'] = 'verification'
        if 'resources' not in start_report:
            start_report['resources'] = {'CPU time': 0, 'wall time': 0, 'memory size': 0}

        archives = {}
        for arch_type in ['log', 'coverage', 'input files of static verifiers']:
            if arch_type in data:
                try:
                    archives[data[arch_type]] = open(self._files[data[arch_type]], mode='rb')
                except Exception:
                    for fp in archives.values():
                        fp.close()
                    raise

        res = UploadReport(self._job, start_report, archives=archives)
        for fp in archives.values():
            fp.close()
        if res.error is not None:
            raise ValueError(res.error)

        self.__upload_children(data['id'])

        res = UploadReport(self._job, {'id': data['id'], 'type': 'verification finish'})
        if res.error is not None:
            raise ValueError(res.error)

    def __upload_unsafe(self, data):
        unsafe_data = data.copy()
        self.__clear_report(['id', 'parent id', 'attrs', 'error trace'], unsafe_data)
        unsafe_data['type'] = 'unsafe'

        with open(self._files[data['error trace']], mode='rb') as fp:
            res = UploadReport(self._job, unsafe_data, archives={data['error trace']: fp})
        if res.error is not None:
            raise ValueError(res.error)

    def __upload_safe(self, data):
        safe_data = data.copy()
        self.__clear_report(['id', 'parent id', 'attrs', 'proof'], safe_data)
        safe_data['type'] = 'safe'

        if 'proof' in data:
            with open(self._files[data['proof']], mode='rb') as fp:
                res = UploadReport(self._job, safe_data, archives={data['proof']: fp})
        else:
            res = UploadReport(self._job, safe_data)
        if res.error is not None:
            raise ValueError(res.error)

    def __upload_unknown(self, data):
        unknown_data = data.copy()
        self.__clear_report(['id', 'parent id', 'attrs', 'problem desc'], unknown_data)
        unknown_data['type'] = 'unknown'

        with open(self._files[data['problem desc']], mode='rb') as fp:
            res = UploadReport(self._job, unknown_data, archives={data['problem desc']: fp})
        if res.error is not None:
            raise ValueError(res.error)

    def __clear_report(self, supported_data, report):
        self.__is_not_used()
        attrs = set(report)
        for attr in attrs:
            if attr not in supported_data:
                del report[attr]

    def __is_not_used(self):
        pass
