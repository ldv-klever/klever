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
import re
import json
import zipfile
import tempfile
import uuid
from wsgiref.util import FileWrapper

from django.conf import settings
from django.core.files import File
from django.db import transaction
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _

from rest_framework import exceptions, serializers, fields

from bridge.vars import REPORT_ARCHIVE, MPTT_FIELDS
from bridge.utils import logger, BridgeException
from bridge.ZipGenerator import ZipStream, CHUNK_SIZE
from bridge.serializers import TimeStampField

from jobs.models import JOBFILE_DIR, Job, RunHistory, JobFile, JobHistory, FileSystem
from reports.models import (
    ReportRoot, ReportSafe, ReportUnsafe, ReportUnknown, ReportComponent,
    Computer, ReportAttr, CoverageArchive, AttrFile, OriginalSources, AdditionalSources
)
from service.models import Scheduler, Decision
from caches.models import ReportSafeCache, ReportUnsafeCache, ReportUnknownCache

from jobs.serializers import create_job_version, JobFileSerializer, JobFilesField
from jobs.utils import get_unique_name
from tools.utils import Recalculation
from caches.utils import update_cache_atomic
from reports.coverage import FillCoverageStatistics

ARCHIVE_FORMAT = 13


class RunHistorySerializer(serializers.ModelSerializer):
    date = TimeStampField()
    configuration = serializers.SlugRelatedField(slug_field='hash_sum', queryset=JobFile.objects)

    class Meta:
        model = RunHistory
        exclude = ('id', 'job', 'operator')


class UploadDecisionSerializer(serializers.ModelSerializer):
    scheduler = serializers.SlugRelatedField(slug_field='type', queryset=Scheduler.objects)
    start_date = TimeStampField(allow_null=True)
    finish_date = TimeStampField(allow_null=True)
    start_sj = TimeStampField(allow_null=True)
    finish_sj = TimeStampField(allow_null=True)
    start_ts = TimeStampField(allow_null=True)
    finish_ts = TimeStampField(allow_null=True)

    class Meta:
        model = Decision
        exclude = ('id', 'job', 'configuration', 'fake')


class UploadJobSerializer(serializers.ModelSerializer):
    identifier = fields.UUIDField()
    name = fields.CharField(max_length=150)
    archive_format = fields.IntegerField(write_only=True)
    run_history = RunHistorySerializer(many=True)
    decision = UploadDecisionSerializer(allow_null=True)
    parent = serializers.SlugRelatedField(slug_field='identifier', allow_null=True, queryset=Job.objects)

    def validate_identifier(self, value):
        if Job.objects.filter(identifier=value).exists():
            return uuid.uuid4()
        return value

    def validate_name(self, value):
        if Job.objects.filter(name=value).exists():
            return get_unique_name(value)
        return value

    def validate_archive_format(self, value):
        if value != ARCHIVE_FORMAT:
            raise exceptions.ValidationError(_("The job archive format is not supported"))
        return value

    def validate(self, attrs):
        attrs.pop('archive_format')
        return attrs

    def create(self, validated_data):
        # Run history and decision must be created outside with configuration file and job instance
        validated_data.pop('run_history')
        validated_data.pop('decision')

        instance = super().create(validated_data)
        return instance

    def to_representation(self, instance):
        value = super().to_representation(instance)
        value['archive_format'] = ARCHIVE_FORMAT
        if value['parent']:
            value['parent'] = str(value['parent'])
        return value

    class Meta:
        model = Job
        exclude = ('id', 'author', 'creation_date', 'preset_uuid', *MPTT_FIELDS)
        extra_kwargs = {'parent': {'write_only': True}}


class UploadJobVersionSerializer(serializers.ModelSerializer):
    change_date = TimeStampField()
    files = JobFilesField(source='files.all')

    def create(self, validated_data):
        job = validated_data.pop('job')
        job_files = validated_data.pop('files')['all']
        return create_job_version(job, job_files, [], **validated_data)

    class Meta:
        model = JobHistory
        exclude = ('id', 'job', 'change_author')


class UploadComputerSerializer(serializers.ModelSerializer):
    def create(self, validated_data):
        try:
            # Do not create the computer with the same identifier again
            return Computer.objects.get(identifier=validated_data['identifier'])
        except Computer.DoesNotExist:
            return super().create(validated_data)

    class Meta:
        model = Computer
        exclude = ('id',)


class UploadReportComponentSerializer(serializers.ModelSerializer):
    start_date = TimeStampField()
    finish_date = TimeStampField(allow_null=True)
    computer = UploadComputerSerializer(read_only=True)
    original_sources = serializers.SlugRelatedField(slug_field='identifier', read_only=True)
    additional_sources = serializers.FileField(source='additional_sources.archive', allow_null=True, read_only=True)
    parent = serializers.SlugRelatedField(slug_field='identifier', read_only=True)

    class Meta:
        model = ReportComponent
        exclude = ('id', 'root', *MPTT_FIELDS)


class UploadReportSafeSerializer(serializers.ModelSerializer):
    parent = serializers.SlugRelatedField(slug_field='identifier', read_only=True)

    class Meta:
        model = ReportSafe
        exclude = ('id', 'root', *MPTT_FIELDS)


class UploadReportUnsafeSerializer(serializers.ModelSerializer):
    parent = serializers.SlugRelatedField(slug_field='identifier', read_only=True)

    class Meta:
        model = ReportUnsafe
        exclude = ('id', 'root', 'trace_id', *MPTT_FIELDS)


class UploadReportUnknownSerializer(serializers.ModelSerializer):
    parent = serializers.SlugRelatedField(slug_field='identifier', read_only=True)

    class Meta:
        model = ReportUnknown
        exclude = ('id', 'root', *MPTT_FIELDS)


class UploadReportAttrSerializer(serializers.ModelSerializer):
    data_file = fields.FileField(source='data.file', allow_null=True, read_only=True)

    def get_attr_data(self, instance):
        if not instance.data:
            return None
        arch_name = '{}_{}'.format(instance.pk, os.path.basename(instance.data.file.name))
        return os.path.join(ReportAttr.__name__, arch_name)

    class Meta:
        model = ReportAttr
        exclude = ('id', 'report', 'data')


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
            version_data = self.__get_json(UploadJobVersionSerializer(instance=job_v).data)
            yield from self.stream.compress_string('version-%s.json' % job_v.version, version_data)
        self.__add_versions_files()

        # Job data
        job_data = self.__get_json(UploadJobSerializer(instance=self.job).data)
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
            report_data = UploadReportComponentSerializer(instance=report).data

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
            reports.append(UploadReportSafeSerializer(instance=report).data)
        return self.__get_json(reports)

    def __get_unsafes_data(self, root):
        reports = []
        for report in ReportUnsafe.objects.filter(root=root).select_related('parent').order_by('id'):
            report_data = UploadReportUnsafeSerializer(instance=report).data
            if report_data['error_trace']:
                self._arch_files.add((report.error_trace.path, report_data['error_trace']))
            reports.append(report_data)
        return self.__get_json(reports)

    def __get_unknowns_data(self, root):
        reports = []
        for report in ReportUnknown.objects.filter(root=root).select_related('parent').order_by('id'):
            report_data = UploadReportUnknownSerializer(instance=report).data
            if report_data['problem_description']:
                self._arch_files.add((report.problem_description.path, report_data['problem_description']))
            reports.append(report_data)
        return self.__get_json(reports)

    def __get_attrs_data(self, root):
        attrs_data = {}
        for ra in ReportAttr.objects.filter(report__root=root).select_related('data', 'report').order_by('id'):
            data = UploadReportAttrSerializer(instance=ra).data
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
        self._tree = {}
        jobs = self.__get_jobs(jobs_ids)
        super(JobsTreesGen, self).__init__(jobs)

    def __iter__(self):
        for job in self.jobs:
            jobgen = JobArchiveGenerator(job)
            yield from self.generate_job(jobgen)
            self._tree[str(job.identifier)]['path'] = jobgen.name
        yield from self.stream.compress_string('tree.json', json.dumps(self._tree, sort_keys=True, indent=2))
        yield self.stream.close_stream()

    def __get_jobs(self, jobs_ids):
        jobs = []
        for j in Job.objects.filter(id__in=jobs_ids):
            jobs.append(j)
            self._tree[str(j.identifier)] = {'parent': None}
        parent_ids = jobs_ids
        while len(parent_ids) > 0:
            new_parents = []
            for j in Job.objects.filter(parent_id__in=parent_ids).select_related('parent'):
                if str(j.identifier) not in self._tree:
                    jobs.append(j)
                    new_parents.append(j.id)
                self._tree[str(j.identifier)] = {'parent': str(j.parent.identifier)}
            parent_ids = new_parents
        return jobs


class UploadJob:
    def __init__(self, parent, user, job_dir):
        self.job = None
        self._user = user
        self._jobdir = job_dir

        self._jobdata = self.__read_json_file('job.json')
        self._jobdata['parent'] = parent or None
        self.__upload_job_files()
        try:
            self.__upload_job()
            UploadReports(self._user, self.job, job_dir)
        except Exception:
            if self.job:
                self.job.delete()
            raise

    def __upload_job_files(self):
        # If 'JobFiles' doesn't exist then the job doiesn't have files or archive is corrupted.
        # It'll be checked while files tree is uploading.
        for dir_path, dir_names, file_names in os.walk(os.path.join(self._jobdir, JOBFILE_DIR)):
            for file_name in file_names:
                with open(os.path.join(dir_path, file_name), mode='rb') as fp:
                    serializer = JobFileSerializer(data={'file': File(fp, name=file_name)})
                    serializer.is_valid(raise_exception=True)
                    serializer.save()

    def __upload_job_versions(self):
        versions_data = []
        for fname in os.listdir(self._jobdir):
            full_path = os.path.join(self._jobdir, fname)
            if not os.path.isfile(full_path) or not re.match(r'version-\d+\.json', fname):
                continue
            with open(full_path, encoding='utf8') as fp:
                versions_data.append(json.load(fp))
        if not versions_data:
            raise ValueError("There are no job's versions in the archive")
        versions_data.sort(key=lambda x: x['version'])

        serializer = UploadJobVersionSerializer(data=versions_data, many=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(job=self.job, change_author=self._user)
        try:
            # Check that last version has correct "version" value
            JobHistory.objects.get(job=self.job, version=self.job.version)
        except JobHistory.DoesNotExist:
            raise exceptions.ValidationError({'versions': _('Uploading job versions has failed')})

    def __upload_job(self):
        serializer = UploadJobSerializer(data=self._jobdata)
        serializer.is_valid(raise_exception=True)
        self.job = serializer.save(author=self._user)

        # Upload job's versions
        self.__upload_job_versions()

        # Upload job's run history (rh_data is already validated in job serializer)
        RunHistory.objects.bulk_create(list(
            RunHistory(job_id=self.job.id, **rh_data)
            for rh_data in serializer.validated_data['run_history']
        ))

        # Create job decision object if it is not None
        decision_data = serializer.validated_data['decision']
        if decision_data and len(serializer.validated_data['run_history']):
            last_conf = serializer.validated_data['run_history'][-1]['configuration']
            Decision.objects.create(job=self.job, configuration=last_conf, **decision_data)

    def __get_coverage_files(self):
        coverage_files = {}
        coverage_path = os.path.join(self._jobdir, 'Coverages')
        if os.path.isdir(coverage_path):
            for arcname in os.listdir(coverage_path):
                m = re.match(r'(\d+)\.zip', arcname)
                if m is not None:
                    coverage_files[int(m.group(1))] = os.path.join(coverage_path, arcname)
        return coverage_files

    def __read_json_file(self, rel_path):
        full_path = os.path.join(self._jobdir, rel_path)
        if not os.path.exists(full_path):
            raise BridgeException(
                _('Required file was not found in job archive: %(filename)s') % {'filename': rel_path}
            )
        with open(full_path, encoding='utf8') as fp:
            return json.load(fp)


class UploadReports:
    def __init__(self, user, job, job_dir, fake=False):
        self.opened_files = []
        self._user = user
        self._jobdir = job_dir
        self._fake = fake
        self.root = self.__create_root(job)
        if self.root is None:
            return
        self._original_sources = self.__upload_original_sources()

        self._additional_sources = {}
        self.saved_reports = {}
        self._leaves_ids = set()
        self._computers = {}
        self._chunk = []
        self._attr_files = {}
        self.__upload_reports()
        Recalculation('all', [self.root.job_id])

    def __create_root(self, job):
        # Create report root
        root_data = self.__read_json_file('{}.json'.format(ReportRoot.__name__))
        if not root_data:
            if not self._fake:
                # The job is without reports (for job uploading)
                return None
            # Manual reports uploading
            root_data = {'resources': {}, 'instances': {}}
        # TODO: validate root_data
        return ReportRoot.objects.create(user=self._user, job=job, **root_data)

    def __upload_original_sources(self):
        original_sources = {}
        orig_data = self.__read_json_file(
            '{}.json'.format(OriginalSources.__name__), required=not self._fake
        )
        if orig_data:
            for src_id, src_path in orig_data.items():
                try:
                    src_obj = OriginalSources.objects.get(identifier=src_id)
                except OriginalSources.DoesNotExist:
                    src_obj = OriginalSources(identifier=src_id)
                    with open(self.__full_path(src_path), mode='rb') as fp:
                        src_obj.add_archive(fp, save=True)
                original_sources[src_id] = src_obj.id
        return original_sources

    def __get_computer(self, comp_data):
        if not isinstance(comp_data, dict) or 'identifier' not in comp_data:
            if not self._fake:
                raise exceptions.ValidationError({'computer': 'The report computer is required'})
            comp_data = {'identifier': 'fake', 'display': '-', 'data': []}
        comp_id = comp_data['identifier']
        if comp_id not in self._computers:
            comp_serializer = UploadComputerSerializer(data=comp_data)
            comp_serializer.is_valid(raise_exception=True)
            comp_obj = comp_serializer.save()
            self._computers[comp_obj.identifier] = comp_obj
        return self._computers[comp_id]

    @cached_property
    def _current_date(self):
        return now().timestamp()

    @transaction.atomic
    def __upload_reports_chunk(self):
        if not self._chunk:
            return
        for report_data in self._chunk:
            save_kwargs = {
                'root': self.root,
                'computer': self.__get_computer(report_data.get('computer')),
                'parent_id': self.saved_reports.get(report_data['parent'])
            }
            if report_data.get('additional_sources'):
                save_kwargs['additional_sources'] = self.__get_additional_sources(report_data['additional_sources'])
            if report_data.get('original_sources'):
                save_kwargs['original_sources_id'] = self._original_sources[report_data['original_sources']]
            if report_data.get('log'):
                fp = open(self.__full_path(report_data['log']), mode='rb')
                report_data['log'] = File(fp, name=REPORT_ARCHIVE['log'])
                self.opened_files.append(fp)
            if report_data.get('verifier_files'):
                fp = open(self.__full_path(report_data['verifier_files']), mode='rb')
                report_data['verifier_files'] = File(fp, name=REPORT_ARCHIVE['verifier_files'])
                self.opened_files.append(fp)
            if self._fake:
                report_data['start_date'] = report_data.get('start_date', self._current_date)
                report_data['finish_date'] = report_data.get('finish_date', self._current_date)
                report_data['cpu_time'] = report_data.get('cpu_time', 0)
                report_data['wall_time'] = report_data.get('wall_time', 0)
                report_data['memory'] = report_data.get('memory', 0)

            serializer = UploadReportComponentSerializer(data=report_data)
            serializer.is_valid(raise_exception=True)
            report = serializer.save(**save_kwargs)
            self.saved_reports[report.identifier] = report.id

            while len(self.opened_files):
                fp = self.opened_files.pop()
                fp.close()

        self._chunk = []

    def __get_additional_sources(self, rel_path):
        if rel_path not in self._additional_sources:
            add_inst = AdditionalSources(root=self.root)
            with open(self.__full_path(rel_path), mode='rb') as fp:
                add_inst.add_archive(fp, save=True)
            self._additional_sources[rel_path] = add_inst
        return self._additional_sources[rel_path]

    def __upload_reports(self):
        # Upload components tree
        for report_data in self.__read_json_file('{}.json'.format(ReportComponent.__name__), required=True):
            if report_data['parent'] and report_data['parent'] not in self.saved_reports:
                self.__upload_reports_chunk()
                if report_data['parent'] not in self.saved_reports:
                    raise BridgeException(_('Reports data was corrupted'))
            self._chunk.append(report_data)
        self.__upload_reports_chunk()

        # Upload leaves
        self.__upload_safes()
        self.__upload_unsafes()
        self.__upload_unknowns()
        self.__upload_attrs()
        self.__upload_coverage()

    @transaction.atomic
    def __upload_safes(self):
        safes_data = self.__read_json_file('{}.json'.format(ReportSafe.__name__))
        if not safes_data:
            return
        safes_cache = []
        for report_data in safes_data:
            save_kwargs = {'root': self.root, 'parent_id': self.saved_reports[report_data.pop('parent')]}
            serializer = UploadReportSafeSerializer(data=report_data)
            serializer.is_valid(raise_exception=True)
            report = serializer.save(**save_kwargs)
            self.saved_reports[report.identifier] = report.id
            self._leaves_ids.add(report.id)
            safes_cache.append(ReportSafeCache(job_id=self.root.job_id, report_id=report.id))
        ReportSafeCache.objects.bulk_create(safes_cache)

    @transaction.atomic
    def __upload_unsafes(self):
        unsafes_data = self.__read_json_file('{}.json'.format(ReportUnsafe.__name__))
        if not unsafes_data:
            return
        unsafes_cache = []
        for report_data in unsafes_data:
            et_fp = None
            save_kwargs = {'root': self.root, 'parent_id': self.saved_reports[report_data.pop('parent')]}
            if report_data.get('error_trace'):
                et_fp = open(self.__full_path(report_data['error_trace']), mode='rb')
                report_data['error_trace'] = File(et_fp, name=REPORT_ARCHIVE['error_trace'])
            serializer = UploadReportUnsafeSerializer(data=report_data)
            serializer.is_valid(raise_exception=True)
            report = serializer.save(**save_kwargs)
            self.saved_reports[report.identifier] = report.id
            self._leaves_ids.add(report.id)
            if et_fp:
                et_fp.close()
            unsafes_cache.append(ReportUnsafeCache(job_id=self.root.job_id, report_id=report.id))
        ReportUnsafeCache.objects.bulk_create(unsafes_cache)

    @transaction.atomic
    def __upload_unknowns(self):
        unknowns_data = self.__read_json_file('{}.json'.format(ReportUnknown.__name__))
        if not unknowns_data:
            return
        unknowns_cache = []
        for report_data in unknowns_data:
            save_kwargs = {'root': self.root, 'parent_id': self.saved_reports[report_data.pop('parent')]}
            problem_fp = None
            if report_data.get('problem_description'):
                problem_fp = open(self.__full_path(report_data['problem_description']), mode='rb')
                report_data['problem_description'] = File(problem_fp, name=REPORT_ARCHIVE['problem_description'])
            serializer = UploadReportUnknownSerializer(data=report_data)
            serializer.is_valid(raise_exception=True)
            report = serializer.save(**save_kwargs)
            self.saved_reports[report.identifier] = report.id
            self._leaves_ids.add(report.id)
            if problem_fp:
                problem_fp.close()
            unknowns_cache.append(ReportUnknownCache(job_id=self.root.job_id, report_id=report.id))
        ReportUnknownCache.objects.bulk_create(unknowns_cache)

    def __upload_attrs(self):
        attrs_data = self.__read_json_file('{}.json'.format(ReportAttr.__name__), required=True)
        attrs_cache = {}
        new_attrs = []
        for r_id in attrs_data:
            for adata in attrs_data[r_id]:
                file_id = self.__get_attr_file_id(adata.pop('data_file', None))
                serializer = UploadReportAttrSerializer(data=adata)
                serializer.is_valid(raise_exception=True)
                validated_data = serializer.validated_data

                report_id = self.saved_reports[r_id]
                new_attrs.append(ReportAttr(data_id=file_id, report_id=report_id, **validated_data))
                if report_id in self._leaves_ids:
                    attrs_cache.setdefault(report_id, {'attrs': {}})
                    attrs_cache[report_id]['attrs'][validated_data['name']] = validated_data['value']
        ReportAttr.objects.bulk_create(new_attrs)
        update_cache_atomic(ReportSafeCache.objects.filter(report__root=self.root), attrs_cache)
        update_cache_atomic(ReportUnsafeCache.objects.filter(report__root=self.root), attrs_cache)
        update_cache_atomic(ReportUnknownCache.objects.filter(report__root=self.root), attrs_cache)

    def __get_attr_file_id(self, rel_path):
        if rel_path is None:
            return None
        if rel_path not in self._attr_files:
            instance = AttrFile(root=self.root)
            with open(self.__full_path(rel_path), mode='rb') as fp:
                instance.file.save(os.path.basename(rel_path), File(fp), save=True)
            self._attr_files[rel_path] = instance.id
        return self._attr_files[rel_path]

    def __upload_coverage(self):
        coverage_data = self.__read_json_file('{}.json'.format(CoverageArchive.__name__))
        if not coverage_data:
            return
        for coverage in coverage_data:
            instance = CoverageArchive(
                report_id=self.saved_reports[coverage['report']],
                identifier=coverage['identifier'], name=coverage.get('name', '...')
            )
            with open(self.__full_path(coverage['archive']), mode='rb') as fp:
                instance.add_coverage(fp, save=False)
            instance.save()
            res = FillCoverageStatistics(instance)
            instance.total = res.total_coverage
            instance.has_extra = res.has_extra
            instance.save()

    def __full_path(self, rel_path):
        full_path = os.path.join(self._jobdir, rel_path)
        if not os.path.exists(full_path):
            raise BridgeException(
                _('Required file was not found in job archive: %(filename)s') % {'filename': rel_path}
            )
        return full_path

    def __read_json_file(self, rel_path, required=False):
        full_path = os.path.join(self._jobdir, rel_path)
        if os.path.exists(full_path):
            with open(full_path, encoding='utf8') as fp:
                return json.load(fp)
        if required:
            raise BridgeException(
                _('Required file was not found in job archive: %(filename)s') % {'filename': rel_path}
            )
        return None


class UploadTree:
    def __init__(self, parent, user, jobs_dir):
        self._parent_id = parent or None
        self._user = user
        self._jobsdir = jobs_dir

        self._uploaded = set()
        self._tree = self.__get_tree()

        try:
            self.__upload_tree()
        except Exception:
            Job.objects.filter(identifier__in=self._uploaded).delete()
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
            if self._tree[j_id]['parent'] is None:
                jobs.append(j_id)
        while True:
            has_child = False
            for j_id in self._tree:
                if self._tree[j_id]['parent'] in jobs and j_id not in jobs:
                    jobs.append(j_id)
                    has_child = True
            if not has_child:
                break
        return jobs

    def __upload_tree(self):
        for j_id in self.__get_jobs_order():
            jobzip_name = os.path.join(self._jobsdir, self._tree[j_id]['path'])
            if not os.path.exists(jobzip_name):
                raise BridgeException(_('One of the job archives was not found'))
            if self._tree[j_id]['parent'] is None:
                parent_id = self._parent_id
            elif self._tree[j_id]['parent'] in self._uploaded:
                parent_id = self._tree[j_id]['parent']
            else:
                logger.error('The parent was not uploaded before the child')
                raise BridgeException()
            self.__upload_job(jobzip_name, parent_id)

    def __upload_job(self, jobarch, parent_id):
        try:
            jobdir = self.__extract_archive(jobarch)
        except Exception as e:
            logger.exception("Archive extraction failed: %s" % e, stack_info=True)
            raise BridgeException(_('Extraction of the archive "%(arcname)s" has failed') % {
                'arcname': os.path.basename(jobarch)
            })
        try:
            res = UploadJob(parent_id, self._user, jobdir.name)
        except BridgeException as e:
            raise BridgeException(_('Creating the job from archive "%(arcname)s" failed: %(message)s') % {
                    'arcname': os.path.basename(jobarch), 'message': str(e)
                })
        except Exception as e:
            logger.exception(e)
            raise BridgeException(_('Creating the job from archive "%(arcname)s" failed: %(message)s') % {
                    'arcname': os.path.basename(jobarch), 'message': _('The job archive is corrupted')
                })
        self._uploaded.add(str(res.job.identifier))

    def __extract_archive(self, jobarch):
        self.__is_not_used()
        with open(jobarch, mode='rb') as fp:
            if os.path.splitext(jobarch)[-1] != '.zip':
                raise ValueError('Only zip archives are supported')
            with zipfile.ZipFile(fp, mode='r') as zfp:
                tmp_dir_name = tempfile.TemporaryDirectory()
                zfp.extractall(tmp_dir_name.name)
            return tmp_dir_name

    def __is_not_used(self):
        pass


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
