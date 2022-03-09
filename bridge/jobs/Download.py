#
# Copyright (c) 2019 ISP RAS (http://www.ispras.ru)
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

from wsgiref.util import FileWrapper

from django.conf import settings
from django.core.files import File
from django.db.models import Q
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from bridge.utils import extract_archive, BridgeException
from bridge.ZipGenerator import ZipStream, CHUNK_SIZE

from jobs.models import Job, JobFile, FileSystem, Decision
from reports.models import (
    ReportSafe, ReportUnsafe, ReportUnknown, ReportComponent, ReportAttr,
    CoverageArchive, OriginalSources, AdditionalSources, DecisionCache
)

from jobs.serializers import UploadedJobArchiveSerializer
from jobs.tasks import upload_job_archive
from jobs.utils import JobAccess, DecisionAccess

from jobs.DownloadSerializers import (
    DownloadJobSerializer, DownloadReportAttrSerializer, DownloadReportComponentSerializer,
    DownloadReportSafeSerializer, DownloadReportUnsafeSerializer, DownloadReportUnknownSerializer,
    DecisionCacheSerializer, DownloadDecisionSerializer
)


def get_jobs_to_download(user, job_ids, decision_ids):
    jobs_qs_filter = Q()
    if job_ids:
        jobs_qs_filter |= Q(id__in=job_ids)
    if decision_ids:
        jobs_qs_filter |= Q(decision__id__in=decision_ids)
    if not jobs_qs_filter:
        raise BridgeException(_("Please select jobs or/and decisions you want to download"), back=reverse('jobs:tree'))

    # Collect selected jobs
    jobs_to_download = {}
    for job in Job.objects.filter(jobs_qs_filter):
        jobs_to_download[job.id] = {'instance': job, 'decisions': []}

    if not jobs_to_download:
        raise BridgeException(_("Jobs were not found"), back=reverse('jobs:tree'))

    # Collect selected decisions
    for decision in Decision.objects.filter(pk__in=decision_ids).select_related('job'):
        if decision.job_id not in jobs_to_download:
            # Unexpected behavior
            continue
        jobs_to_download[decision.job_id]['decisions'].append(decision.id)
        if not DecisionAccess(user, decision).can_download:
            raise BridgeException(
                _("You don't have an access to one of the selected decisions"), back=reverse('jobs:tree')
            )

    # Check access to jobs without any selected decision (all decisions will be downloaded)
    for job_id in jobs_to_download:
        if not jobs_to_download[job_id]['decisions']:
            if not JobAccess(user, jobs_to_download[job_id]['instance']).can_download:
                raise BridgeException(
                    _("You don't have an access to one of the selected jobs"), back=reverse('jobs:tree')
                )
    return jobs_to_download


class KleverCoreArchiveGen:
    def __init__(self, decision):
        self.decision = decision
        self.arcname = 'VJ__{}.zip'.format(decision.identifier)
        self.stream = ZipStream()

    def __iter__(self):
        for file_inst in FileSystem.objects.filter(decision=self.decision).select_related('file'):
            arch_name = '/'.join(['root', file_inst.name])
            file_src = '/'.join([settings.MEDIA_ROOT, file_inst.file.file.name])
            for data in self.stream.compress_file(file_src, arch_name):
                yield data
        yield self.stream.close_stream()


class JobArchiveGenerator:
    def __init__(self, job, decisions_ids=None):
        self.job = job
        self._decisions_ids = list(map(int, decisions_ids)) if decisions_ids else None
        self.name = 'Job-{}.zip'.format(self.job.identifier)
        self._arch_files = set()
        self.stream = ZipStream()

    def __iter__(self):
        # Job data
        yield from self.stream.compress_string('job.json', self.__get_job_data())
        yield from self.stream.compress_string('{}.json'.format(Decision.__name__), self.__add_decisions_data())
        yield from self.stream.compress_string('{}.json'.format(DecisionCache.__name__), self.__get_decision_cache())
        yield from self.stream.compress_string('{}.json'.format(OriginalSources.__name__), self.__get_original_src())
        yield from self.stream.compress_string('{}.json'.format(ReportComponent.__name__), self.__get_reports_data())
        yield from self.stream.compress_string('{}.json'.format(ReportSafe.__name__), self.__get_safes_data())
        yield from self.stream.compress_string('{}.json'.format(ReportUnsafe.__name__), self.__get_unsafes_data())
        yield from self.stream.compress_string('{}.json'.format(ReportUnknown.__name__), self.__get_unknowns_data())
        yield from self.stream.compress_string('{}.json'.format(ReportAttr.__name__), self.__get_attrs_data())
        yield from self.stream.compress_string('{}.json'.format(CoverageArchive.__name__), self.__get_coverage_data())

        self.__add_job_files()
        self.__add_additional_sources()

        for file_path, arcname in self._arch_files:
            yield from self.stream.compress_file(file_path, arcname)
        yield self.stream.close_stream()

    @cached_property
    def _decision_filter(self):
        if self._decisions_ids:
            return Q(decision_id__in=self._decisions_ids)
        return Q(decision__job_id=self.job.id)

    def __get_job_data(self):
        return self.__get_json(DownloadJobSerializer(instance=self.job).data)

    def __add_job_files(self):
        job_files = {}
        for fs in FileSystem.objects.filter(decision__job=self.job).select_related('file'):
            job_files[fs.file.hash_sum] = (fs.file.file.path, fs.file.file.name)
        for f_path, arcname in job_files.values():
            self._arch_files.add((f_path, arcname))

    def __add_decisions_data(self):
        if self._decisions_ids:
            qs_filter = Q(id__in=self._decisions_ids)
        else:
            qs_filter = Q(job_id=self.job.id)
        decisions_list = []
        for decision in Decision.objects.filter(qs_filter).select_related('scheduler', 'configuration'):
            decisions_list.append(DownloadDecisionSerializer(instance=decision).data)
            self._arch_files.add((decision.configuration.file.path, decision.configuration.file.name))
        return self.__get_json(decisions_list)

    def __get_decision_cache(self):
        return self.__get_json(DecisionCacheSerializer(
            instance=DecisionCache.objects.filter(self._decision_filter), many=True
        ).data)

    def __get_original_src(self):
        if self._decisions_ids:
            qs_filter = Q(reportcomponent__decision_id__in=self._decisions_ids)
        else:
            qs_filter = Q(reportcomponent__decision__job_id=self.job.id)
        sources = {}
        for src_arch in OriginalSources.objects.filter(qs_filter):
            sources[src_arch.identifier] = src_arch.archive.name
            self._arch_files.add((src_arch.archive.path, src_arch.archive.name))
        return self.__get_json(sources)

    def __get_reports_data(self):
        reports = []
        for report in ReportComponent.objects.filter(self._decision_filter)\
                .select_related('parent', 'computer', 'original_sources', 'additional_sources').order_by('level'):
            report_data = DownloadReportComponentSerializer(instance=report).data

            # Add report files
            if report_data['log']:
                self._arch_files.add((report.log.path, report_data['log']))
            if report_data['verifier_files']:
                self._arch_files.add((report.verifier_files.path, report_data['verifier_files']))
            reports.append(report_data)

        return self.__get_json(reports)

    def __get_safes_data(self):
        safes_queryset = ReportSafe.objects.filter(self._decision_filter).select_related('parent').order_by('id')
        return self.__get_json(DownloadReportSafeSerializer(instance=safes_queryset, many=True).data)

    def __get_unsafes_data(self):
        reports = []
        for report in ReportUnsafe.objects.filter(self._decision_filter).select_related('parent').order_by('id'):
            report_data = DownloadReportUnsafeSerializer(instance=report).data
            if report_data['error_trace']:
                self._arch_files.add((report.error_trace.path, report_data['error_trace']))
            reports.append(report_data)
        return self.__get_json(reports)

    def __get_unknowns_data(self):
        reports = []
        for report in ReportUnknown.objects.filter(self._decision_filter).select_related('parent').order_by('id'):
            report_data = DownloadReportUnknownSerializer(instance=report).data
            if report_data['problem_description']:
                self._arch_files.add((report.problem_description.path, report_data['problem_description']))
            reports.append(report_data)
        return self.__get_json(reports)

    def __get_attrs_data(self):
        if self._decisions_ids:
            qs_filter = Q(report__decision_id__in=self._decisions_ids)
        else:
            qs_filter = Q(report__decision__job_id=self.job.id)

        attrs_data = {}
        for ra in ReportAttr.objects.filter(qs_filter).select_related('data', 'report').order_by('id'):
            data = DownloadReportAttrSerializer(instance=ra).data
            if data['data_file']:
                self._arch_files.add((ra.data.file.path, data['data_file']))
            attrs_data.setdefault(ra.report.decision_id, {})
            attrs_data[ra.report.decision_id].setdefault(ra.report.identifier, [])
            attrs_data[ra.report.decision_id][ra.report.identifier].append(data)
        return self.__get_json(attrs_data)

    def __get_coverage_data(self):
        if self._decisions_ids:
            qs_filter = Q(report__decision_id__in=self._decisions_ids)
        else:
            qs_filter = Q(report__decision__job_id=self.job.id)

        coverage_data = []
        for carch in CoverageArchive.objects.filter(qs_filter).select_related('report').order_by('id'):
            coverage_data.append({
                'decision': carch.report.decision_id,
                'report': carch.report.identifier,
                'identifier': carch.identifier,
                'archive': carch.archive.name,
                'name': carch.name
            })
            self._arch_files.add((carch.archive.path, carch.archive.name))
        return self.__get_json(coverage_data)

    def __add_additional_sources(self):
        for src_arch in AdditionalSources.objects.filter(self._decision_filter):
            self._arch_files.add((src_arch.archive.path, src_arch.archive.name))

    def __get_json(self, data):
        return json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2)


class JobsArchivesGen:
    def __init__(self, jobs_to_download):
        self.jobs = jobs_to_download
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
        for job_id in self.jobs:
            jobgen = JobArchiveGenerator(self.jobs[job_id]['instance'], decisions_ids=self.jobs[job_id]['decisions'])
            yield from self.generate_job(jobgen)
        yield self.stream.close_stream()


class JobFileGenerator(FileWrapper):
    def __init__(self, jobfile):
        assert isinstance(jobfile, JobFile), 'Unknown error'
        self.size = len(jobfile.file)
        super().__init__(jobfile.file, 8192)


class DecisionConfGenerator(FileWrapper):
    def __init__(self, instance):
        assert isinstance(instance, Decision), 'Unknown error'
        self.name = "decision-{}.conf".format(instance.identifier)
        self.size = len(instance.configuration.file)
        super().__init__(instance.configuration.file, 8192)


class UploadJobsScheduler:
    def __init__(self, user, archive):
        self._author = user
        self._archive = archive

    @cached_property
    def _arch_files(self):
        with zipfile.ZipFile(self._archive, 'r') as zfp:
            return zfp.namelist()

    def upload_all(self):
        if all(os.path.splitext(file_path)[-1] == '.zip' for file_path in self._arch_files):
            # A list of jobs
            jobs_dir = extract_archive(self._archive)
            for arch_name in os.listdir(jobs_dir.name):
                with open(os.path.join(jobs_dir.name, arch_name), mode='rb') as fp:
                    self.__save_archive(File(fp, name=arch_name))
        else:
            # A single job
            self.__save_archive(self._archive)

    def __save_archive(self, arch_fp):
        serializer = UploadedJobArchiveSerializer(data={'archive': arch_fp})
        serializer.is_valid(raise_exception=True)
        upload_obj = serializer.save(author=self._author)
        upload_job_archive.delay(upload_obj.id)
        return upload_obj
