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

import os
import json
import zipfile
import uuid

from wsgiref.util import FileWrapper

from django.conf import settings
from django.core.files import File
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _

from rest_framework import exceptions

from bridge.vars import MPTT_FIELDS, TREE_LIST_JSON
from bridge.utils import logger, extract_archive, BridgeException
from bridge.ZipGenerator import ZipStream, CHUNK_SIZE

from jobs.models import Job, RunHistory, JobFile, FileSystem
from reports.models import (
    ReportRoot, ReportSafe, ReportUnsafe, ReportUnknown, ReportComponent,
    ReportAttr, CoverageArchive, AttrFile, OriginalSources, AdditionalSources
)

from jobs.serializers import UploadedJobArchiveSerializer
from jobs.DownloadSerializers import (
    DownloadJobSerializer, DownloadJobVersionSerializer,
    DownloadReportAttrSerializer, DownloadReportComponentSerializer,
    DownloadReportSafeSerializer, DownloadReportUnsafeSerializer, DownloadReportUnknownSerializer
)
from jobs.tasks import upload_job_archive, link_uploaded_job_parent


class KleverCoreArchiveGen:
    def __init__(self, job):
        self.job = job
        self.arcname = 'VJ__{}.zip'.format(job.identifier)
        self.stream = ZipStream()

    def __iter__(self):
        last_version = self.job.versions.get(version=self.job.version)
        for file_inst in last_version.files.select_related('file').all():
            arch_name = '/'.join(['root', file_inst.name])
            file_src = '/'.join([settings.MEDIA_ROOT, file_inst.file.file.name])
            for data in self.stream.compress_file(file_src, arch_name):
                yield data
        yield self.stream.close_stream()


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
        self.name = 'Job-{}.zip'.format(self.job.identifier)
        self._arch_files = set()
        self.stream = ZipStream()

    def __iter__(self):
        for job_v in self.job.versions.all():
            version_data = self.__get_json(DownloadJobVersionSerializer(instance=job_v).data)
            yield from self.stream.compress_string('version-%s.json' % job_v.version, version_data)
        self.__add_versions_files()

        # Job data
        job_data = self.__get_json(DownloadJobSerializer(instance=self.job).data)
        yield from self.stream.compress_string('job.json', job_data)
        self.__add_run_history_files()

        # Reports data
        try:
            root = ReportRoot.objects.get(job=self.job)
        except ReportRoot.DoesNotExist:
            pass
        else:
            yield from self.stream.compress_string(
                '{}.json'.format(OriginalSources.__name__), self.__get_original_sources(root)
            )
            yield from self.stream.compress_string(
                '{}.json'.format(ReportRoot.__name__), self.__get_root_data(root)
            )
            yield from self.stream.compress_string(
                '{}.json'.format(ReportComponent.__name__), self.__get_reports_data(root)
            )
            yield from self.stream.compress_string(
                '{}.json'.format(ReportSafe.__name__), self.__get_safes_data(root)
            )
            yield from self.stream.compress_string(
                '{}.json'.format(ReportUnsafe.__name__), self.__get_unsafes_data(root)
            )
            yield from self.stream.compress_string(
                '{}.json'.format(ReportUnknown.__name__), self.__get_unknowns_data(root)
            )
            yield from self.stream.compress_string(
                '{}.json'.format(ReportAttr.__name__), self.__get_attrs_data(root)
            )
            yield from self.stream.compress_string(
                '{}.json'.format(CoverageArchive.__name__), self.__get_coverage_data(root)
            )
            self.__add_additional_sources(root)

        for file_path, arcname in self._arch_files:
            yield from self.stream.compress_file(file_path, arcname)
        yield self.stream.close_stream()

    def __add_versions_files(self):
        job_files = {}
        for fs in FileSystem.objects.filter(job_version__job=self.job).select_related('file'):
            job_files[fs.file.hash_sum] = (fs.file.file.path, fs.file.file.name)
        for f_path, arcname in job_files.values():
            self._arch_files.add((f_path, arcname))

    def __add_run_history_files(self):
        for rh in self.job.run_history.order_by('date'):
            self._arch_files.add((rh.configuration.file.path, rh.configuration.file.name))

    def __get_root_data(self, root):
        return self.__get_json({'resources': root.resources, 'instances': root.instances})

    def __get_reports_data(self, root):
        reports = []
        for report in ReportComponent.objects.filter(root=root)\
                .select_related('parent', 'computer', 'original_sources', 'additional_sources').order_by('level'):
            report_data = DownloadReportComponentSerializer(instance=report).data

            # Add report files
            if report_data['log']:
                self._arch_files.add((report.log.path, report_data['log']))
            if report_data['verifier_files']:
                self._arch_files.add((report.verifier_files.path, report_data['verifier_files']))
            reports.append(report_data)

        return self.__get_json(reports)

    def __get_safes_data(self, root):
        reports = []
        for report in ReportSafe.objects.filter(root=root).select_related('parent').order_by('id'):
            reports.append(DownloadReportSafeSerializer(instance=report).data)
        return self.__get_json(reports)

    def __get_unsafes_data(self, root):
        reports = []
        for report in ReportUnsafe.objects.filter(root=root).select_related('parent').order_by('id'):
            report_data = DownloadReportUnsafeSerializer(instance=report).data
            if report_data['error_trace']:
                self._arch_files.add((report.error_trace.path, report_data['error_trace']))
            reports.append(report_data)
        return self.__get_json(reports)

    def __get_unknowns_data(self, root):
        reports = []
        for report in ReportUnknown.objects.filter(root=root).select_related('parent').order_by('id'):
            report_data = DownloadReportUnknownSerializer(instance=report).data
            if report_data['problem_description']:
                self._arch_files.add((report.problem_description.path, report_data['problem_description']))
            reports.append(report_data)
        return self.__get_json(reports)

    def __get_attrs_data(self, root):
        attrs_data = {}
        for ra in ReportAttr.objects.filter(report__root=root).select_related('data', 'report').order_by('id'):
            data = DownloadReportAttrSerializer(instance=ra).data
            if data['data_file']:
                self._arch_files.add((ra.data.file.path, data['data_file']))
            attrs_data.setdefault(ra.report.identifier, [])
            attrs_data[ra.report.identifier].append(data)
        return self.__get_json(attrs_data)

    def __get_coverage_data(self, root):
        coverage_data = []
        for carch in CoverageArchive.objects.filter(report__root=root).select_related('report').order_by('id'):
            coverage_data.append({
                'report': carch.report.identifier,
                'identifier': carch.identifier,
                'archive': carch.archive.name,
                'name': carch.name
            })
            self._arch_files.add((carch.archive.path, carch.archive.name))
        return self.__get_json(coverage_data)

    def __add_additional_sources(self, root):
        for src_arch in AdditionalSources.objects.filter(root=root):
            self._arch_files.add((src_arch.archive.path, src_arch.archive.name))

    def __get_original_sources(self, root):
        sources = {}
        for src_arch in OriginalSources.objects.filter(reportcomponent__root=root):
            sources[src_arch.identifier] = src_arch.archive.name
            self._arch_files.add((src_arch.archive.path, src_arch.archive.name))
        return self.__get_json(sources)

    def __get_json(self, data):
        return json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2)


class JobsArchivesGen:
    def __init__(self, jobs):
        self.jobs = jobs
        self.stream = ZipStream()
        self.name = 'KleverJobs.zip'

    def generate_job(self, jobgen):
        buf = b''
        for data in self.stream.compress_stream(jobgen.name, jobgen):
            buf += data
            if len(buf) > CHUNK_SIZE:
                yield buf
                buf = b''
        if len(buf) > 0:
            yield buf

    def __iter__(self):
        for job in self.jobs:
            jobgen = JobArchiveGenerator(job)
            yield from self.generate_job(jobgen)
        yield self.stream.close_stream()


class JobsTreesGen(JobsArchivesGen):
    def __init__(self, jobs_ids):
        self._root_ids = self.__get_root_ids(jobs_ids)
        super(JobsTreesGen, self).__init__([])

    def __iter__(self):
        tree_list = []
        for root_job in Job.objects.filter(id__in=self._root_ids).only(*MPTT_FIELDS):
            for job in root_job.get_descendants(include_self=True):
                jobgen = JobArchiveGenerator(job)
                yield from self.generate_job(jobgen)

                parent_uuid = None
                if job.id not in self._root_ids:
                    parent_id = self._all_jobs[job.id]['parent']
                    if parent_id:
                        parent_uuid = self._all_jobs[parent_id]['identifier']
                tree_list.append({'uuid': str(job.identifier), 'file': jobgen.name, 'parent': parent_uuid})
        yield from self.stream.compress_string(TREE_LIST_JSON, json.dumps(tree_list, sort_keys=True, indent=2))
        yield self.stream.close_stream()

    @property
    def jobs_queryset(self):
        ids_to_download = set()
        parents_ids = set(self._root_ids)
        while True:
            new_parents = set()
            for p_id in self._all_jobs:
                if self._all_jobs[p_id]['parent'] in parents_ids:
                    new_parents.add(p_id)
            if new_parents:
                ids_to_download |= new_parents
                parents_ids = new_parents
            else:
                # If children were not found then the lowest tree level is reached
                break
        return Job.objects.filter(id__in=ids_to_download)

    def __get_root_ids(self, jobs_ids):
        # Get selected root for each selected job
        jobs_ids = set(int(j_id) for j_id in jobs_ids)
        root_ids = set()
        for j_id in jobs_ids:
            root_id = j_id
            p_id = j_id
            while True:
                p_id = self._all_jobs[p_id]['parent']
                if not p_id:
                    break
                if p_id in jobs_ids:
                    root_id = p_id
            root_ids.add(root_id)
        return root_ids

    @cached_property
    def _all_jobs(self):
        total_tree = {}
        for j_id, p_id, j_uuid in Job.objects.values_list('id', 'parent_id', 'identifier'):
            total_tree[j_id] = {'parent': p_id, 'identifier': str(j_uuid)}
        return total_tree


class JobFileGenerator(FileWrapper):
    def __init__(self, jobfile):
        assert isinstance(jobfile, JobFile), 'Unknown error'
        self.size = len(jobfile.file)
        super().__init__(jobfile.file, 8192)


class JobConfGenerator(FileWrapper):
    def __init__(self, instance):
        assert isinstance(instance, RunHistory), 'Unknown error'
        self.name = "job-{}.conf".format(instance.job.identifier)
        self.size = len(instance.configuration.file)
        super().__init__(instance.configuration.file, 8192)


class UploadJobsScheduler:
    def __init__(self, user, archive, parent_uuid):
        self._author = user
        self._archive = archive
        self._parent_uuid = uuid.UUID(parent_uuid) if parent_uuid else None

    @cached_property
    def _arch_files(self):
        with zipfile.ZipFile(self._archive, 'r') as zfp:
            return zfp.namelist()

    def upload_all(self):
        if TREE_LIST_JSON in self._arch_files:
            # A tree of jobs
            self.__upload_tree()
        elif all(os.path.splitext(file_path)[-1] == '.zip' for file_path in self._arch_files):
            # A list of jobs
            jobs_dir = extract_archive(self._archive)
            for arch_name in os.listdir(jobs_dir.name):
                with open(os.path.join(jobs_dir.name, arch_name), mode='rb') as fp:
                    self.__save_archive(File(fp, name=arch_name))
        else:
            # A single job
            self.__save_archive(self._archive)

    def __upload_tree(self):
        # Extract archive to a temporary directory
        try:
            jobs_dir = extract_archive(self._archive)
        except Exception as e:
            logger.exception(e)
            raise exceptions.APIException(
                _('Extraction of the archive "%(arcname)s" has failed') % {'arcname': self._archive.name}
            )

        # Parse tree structure json
        tree_fname = os.path.join(jobs_dir.name, TREE_LIST_JSON)
        if not os.path.exists(tree_fname):
            raise BridgeException(_('The file with tree structure was not found'))
        with open(tree_fname, mode='r', encoding='utf8') as fp:
            tree_info = json.loads(fp.read())

        delayed_uploads = {}
        for job_info in tree_info:
            # Save each job archive
            with open(os.path.join(jobs_dir.name, job_info['file']), mode='rb') as fp:
                upload_obj = self.__save_archive(File(fp, name=job_info['file']))
            delayed_uploads[job_info['uuid']] = upload_obj.pk

            # Schedule task to link correct parent after upload is completed
            if job_info['parent'] and job_info['parent'] in delayed_uploads:
                link_uploaded_job_parent.delay(upload_obj.pk, delayed_uploads[job_info['parent']])

    def __save_archive(self, arch_fp):
        serializer = UploadedJobArchiveSerializer(data={'archive': arch_fp})
        serializer.is_valid(raise_exception=True)
        upload_obj = serializer.save(author=self._author)
        upload_job_archive.delay(upload_obj.id, self._parent_uuid)
        return upload_obj
