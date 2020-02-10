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

from django.core.files import File
from django.db import transaction
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _

from rest_framework import exceptions

from bridge.vars import REPORT_ARCHIVE, JOB_UPLOAD_STATUS, DECISION_STATUS, PRESET_JOB_TYPE
from bridge.utils import BridgeException, extract_archive

from jobs.models import JOBFILE_DIR, PresetJob
from reports.models import (
    DecisionCache, ReportSafe, ReportUnsafe, ReportUnknown, ReportComponent,
    ReportAttr, CoverageArchive, AttrFile, OriginalSources, AdditionalSources
)
from service.models import Decision
from caches.models import ReportSafeCache, ReportUnsafeCache, ReportUnknownCache

from tools.utils import Recalculation
from caches.utils import update_cache_atomic
from reports.coverage import FillCoverageStatistics
from jobs.serializers import JobFileSerializer
from jobs.DownloadSerializers import (
    DownloadJobSerializer, DownloadComputerSerializer, DownloadReportAttrSerializer,
    DownloadReportComponentSerializer, DownloadReportSafeSerializer, DownloadReportUnsafeSerializer,
    DownloadReportUnknownSerializer, DecisionCacheSerializer, DownloadDecisionSerializer
)


class JobArchiveUploader:
    def __init__(self, upload_obj):
        self._upload_obj = upload_obj
        self.job = None

    def __enter__(self):
        self.job = None
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val:
            if self.job:
                self.job.delete()
            self._upload_obj.error = str(exc_val)
            self._upload_obj.status = JOB_UPLOAD_STATUS[7][0]
        else:
            self._upload_obj.job = self.job
            self._upload_obj.status = JOB_UPLOAD_STATUS[6][0]
        self._upload_obj.finish_date = now()
        self._upload_obj.save()

    def upload(self):
        # Extract job archive
        self.__change_upload_status(JOB_UPLOAD_STATUS[1][0])
        with self._upload_obj.archive.file as fp:
            job_dir = extract_archive(fp)

        # Upload job files
        self.__change_upload_status(JOB_UPLOAD_STATUS[2][0])
        self.__upload_job_files(os.path.join(job_dir.name, JOBFILE_DIR))

        # Save job
        self.__change_upload_status(JOB_UPLOAD_STATUS[3][0])
        serializer_data = self.__parse_job_json(os.path.join(job_dir.name, 'job.json'))
        serializer = DownloadJobSerializer(data=serializer_data)
        serializer.is_valid(raise_exception=True)
        self.job = serializer.save(
            author=self._upload_obj.author, preset_id=self.__get_preset_id(serializer_data.get('preset_info'))
        )

        # Upload job reports
        self.__change_upload_status(JOB_UPLOAD_STATUS[4][0])
        res = UploadReports(self._upload_obj.author, self.job, job_dir.name)

        if res.decisions:
            # Recalculate cache if job has decisions
            self.__change_upload_status(JOB_UPLOAD_STATUS[5][0])
            Recalculation('all', res.decisions)

    def __change_upload_status(self, new_status):
        self._upload_obj.status = new_status
        self._upload_obj.save()

    def __get_preset_id(self, preset_info):
        if not isinstance(preset_info, dict) or 'identifier' not in preset_info:
            raise exceptions.ValidationError({'preset': _('Preset info has wrong format')})
        try:
            main_preset = PresetJob.objects.get(identifier=preset_info['identifier'], type=PRESET_JOB_TYPE[1][0])
        except PresetJob.DoesNotExist:
            raise exceptions.ValidationError({'preset': _('Preset job was not found')})
        if 'name' not in preset_info:
            return main_preset.id
        if not isinstance(preset_info['name'], str) or \
                len(preset_info['name']) > 150 or len(preset_info['name']) == 0:
            raise exceptions.ValidationError({'preset': _('Preset info is corrupted')})
        try:
            preset_dir = PresetJob.objects.get(name=preset_info['name'])
            if preset_dir.type != PRESET_JOB_TYPE[2][0]:
                raise exceptions.ValidationError({'preset': _('Preset info is corrupted')})
            return preset_dir.id
        except PresetJob.DoesNotExist:
            pass
        preset_dir, created = PresetJob.objects.get_or_create(
            name=preset_info['name'], type=PRESET_JOB_TYPE[2][0],
            defaults={'parent_id': main_preset.id, 'check_date': main_preset.check_date}
        )
        return preset_dir.id

    def __upload_job_files(self, files_dir):
        if not os.path.isdir(files_dir):
            # If 'JobFiles' doesn't exist then the job doesn't have files or archive is corrupted.
            # It'll be checked while files tree is uploading.
            return
        for dir_path, dir_names, file_names in os.walk(files_dir):
            for file_name in file_names:
                with open(os.path.join(dir_path, file_name), mode='rb') as fp:
                    serializer = JobFileSerializer(data={'file': File(fp, name=file_name)})
                    serializer.is_valid(raise_exception=True)
                    serializer.save()

    def __parse_job_json(self, file_path):
        if not os.path.exists(file_path):
            raise BridgeException('Required job.json file was not found in job archive')
        with open(file_path, encoding='utf8') as fp:
            return json.load(fp)


class UploadReports:
    def __init__(self, user, job, job_dir):
        self.opened_files = []
        self._user = user
        self._jobdir = job_dir
        self._final_statuses = {}
        self._uploaded_decisions = self.__upload_decisions(job)

        if not self._uploaded_decisions:
            # There are no decisions for the job
            return

        self._original_sources = self.__upload_original_sources()

        self._additional_sources = {}
        self.saved_reports = {}
        self._leaves_ids = set()
        self._computers = {}
        self._chunk = []
        self._attr_files = {}
        self.__upload_reports()
        self.__change_decision_statuses()

    @cached_property
    def decisions(self):
        return list(self._uploaded_decisions.values())

    def __upload_decisions(self, job):
        uploaded_map = {}
        decisions_data = self.__read_json_file('{}.json'.format(Decision.__name__))
        if not decisions_data:
            # The job is without reports
            return

        # Upload decisions
        for decision in decisions_data:
            if 'id' not in decision or not isinstance(decision['id'], int):
                raise exceptions.ValidationError({'decision': _('Decision data is corrupted')})
            serializer = DownloadDecisionSerializer(data=decision)
            serializer.is_valid(raise_exception=True)
            uploaded_map[decision['id']] = serializer.save(
                job=job, operator=self._user, status=DECISION_STATUS[0][0]
            ).id
            self._final_statuses[uploaded_map[decision['id']]] = serializer.validated_data['status']

        # Upload decision cache
        cache_data_list = self.__read_json_file('{}.json'.format(DecisionCache.__name__))
        new_cache_objects = []
        for dec_cache in cache_data_list:
            if 'decision' not in dec_cache or not uploaded_map.get(dec_cache['decision']):
                raise exceptions.ValidationError({'decision': _('Decision data is corrupted')})
            serializer = DecisionCacheSerializer(data=dec_cache)
            serializer.is_valid(raise_exception=True)
            new_cache_objects.append(DecisionCache(
                decision_id=uploaded_map[dec_cache['decision']], **serializer.validated_data
            ))
        DecisionCache.objects.bulk_create(new_cache_objects)

        return uploaded_map

    @transaction.atomic
    def __change_decision_statuses(self):
        for decision in Decision.objects.filter(id__in=self.decisions).select_for_update():
            decision.status = self._final_statuses[decision.id]
            decision.save()

    def __get_decision_id(self, old_id):
        if not isinstance(old_id, int) or old_id not in self._uploaded_decisions:
            raise exceptions.ValidationError({'decision': _('The job archive is corrupted')})
        return self._uploaded_decisions[old_id]

    def __upload_original_sources(self):
        original_sources = {}
        orig_data = self.__read_json_file('{}.json'.format(OriginalSources.__name__), required=True)
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
            raise exceptions.ValidationError({'computer': 'The report computer is required'})
        comp_id = comp_data['identifier']
        if comp_id not in self._computers:
            comp_serializer = DownloadComputerSerializer(data=comp_data)
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
            decision_id = report_data.pop('new_decision_id')
            save_kwargs = {
                'computer': self.__get_computer(report_data.get('computer')),
                'parent_id': self.saved_reports.get((decision_id, report_data['parent'])),
                'decision_id': decision_id
            }
            if report_data.get('additional_sources'):
                save_kwargs['additional_sources'] = self.__get_additional_sources(
                    decision_id, report_data['additional_sources']
                )
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

            serializer = DownloadReportComponentSerializer(data=report_data)
            serializer.is_valid(raise_exception=True)
            report = serializer.save(**save_kwargs)
            self.saved_reports[(decision_id, report.identifier)] = report.id

            while len(self.opened_files):
                fp = self.opened_files.pop()
                fp.close()

        self._chunk = []

    def __get_additional_sources(self, decision_id, rel_path):
        if rel_path not in self._additional_sources:
            add_inst = AdditionalSources(decision_id=decision_id)
            with open(self.__full_path(rel_path), mode='rb') as fp:
                add_inst.add_archive(fp, save=True)
            self._additional_sources[rel_path] = add_inst
        return self._additional_sources[rel_path]

    def __upload_reports(self):
        # Upload components tree
        for report_data in self.__read_json_file('{}.json'.format(ReportComponent.__name__), required=True):
            decision_id = self.__get_decision_id(report_data['decision'])
            if report_data['parent'] and (decision_id, report_data['parent']) not in self.saved_reports:
                self.__upload_reports_chunk()
                if (decision_id, report_data['parent']) not in self.saved_reports:
                    raise BridgeException(_('Reports data was corrupted'))
            report_data['new_decision_id'] = decision_id
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
            decision_id = self.__get_decision_id(report_data.get('decision'))
            save_kwargs = {
                'decision_id': decision_id, 'parent_id': self.saved_reports[(decision_id, report_data.pop('parent'))]
            }
            serializer = DownloadReportSafeSerializer(data=report_data)
            serializer.is_valid(raise_exception=True)
            report = serializer.save(**save_kwargs)
            self.saved_reports[(decision_id, report.identifier)] = report.id
            self._leaves_ids.add(report.id)
            safes_cache.append(ReportSafeCache(decision_id=decision_id, report_id=report.id))
        ReportSafeCache.objects.bulk_create(safes_cache)

    @transaction.atomic
    def __upload_unsafes(self):
        unsafes_data = self.__read_json_file('{}.json'.format(ReportUnsafe.__name__))
        if not unsafes_data:
            return
        unsafes_cache = []
        for report_data in unsafes_data:
            et_fp = None
            decision_id = self.__get_decision_id(report_data.get('decision'))
            save_kwargs = {
                'decision_id': decision_id, 'parent_id': self.saved_reports[(decision_id, report_data.pop('parent'))]
            }
            if report_data.get('error_trace'):
                et_fp = open(self.__full_path(report_data['error_trace']), mode='rb')
                report_data['error_trace'] = File(et_fp, name=REPORT_ARCHIVE['error_trace'])
            serializer = DownloadReportUnsafeSerializer(data=report_data)
            serializer.is_valid(raise_exception=True)
            report = serializer.save(**save_kwargs)
            self.saved_reports[(decision_id, report.identifier)] = report.id
            self._leaves_ids.add(report.id)
            if et_fp:
                et_fp.close()
            unsafes_cache.append(ReportUnsafeCache(decision_id=decision_id, report_id=report.id))
        ReportUnsafeCache.objects.bulk_create(unsafes_cache)

    @transaction.atomic
    def __upload_unknowns(self):
        unknowns_data = self.__read_json_file('{}.json'.format(ReportUnknown.__name__))
        if not unknowns_data:
            return
        unknowns_cache = []
        for report_data in unknowns_data:
            decision_id = self.__get_decision_id(report_data.get('decision'))
            save_kwargs = {
                'decision_id': decision_id, 'parent_id': self.saved_reports[(decision_id, report_data.pop('parent'))]
            }
            problem_fp = None
            if report_data.get('problem_description'):
                problem_fp = open(self.__full_path(report_data['problem_description']), mode='rb')
                report_data['problem_description'] = File(problem_fp, name=REPORT_ARCHIVE['problem_description'])
            serializer = DownloadReportUnknownSerializer(data=report_data)
            serializer.is_valid(raise_exception=True)
            save_kwargs['decision_id'] = self.__get_decision_id(report_data.get('decision'))
            report = serializer.save(**save_kwargs)
            self.saved_reports[(decision_id, report.identifier)] = report.id
            self._leaves_ids.add(report.id)
            if problem_fp:
                problem_fp.close()
            unknowns_cache.append(ReportUnknownCache(decision_id=decision_id, report_id=report.id))
        ReportUnknownCache.objects.bulk_create(unknowns_cache)

    def __upload_attrs(self):
        attrs_data = self.__read_json_file('{}.json'.format(ReportAttr.__name__), required=True)
        attrs_cache = {}
        new_attrs = []
        for old_d_id in attrs_data:
            decision_id = self.__get_decision_id(int(old_d_id))
            for r_id in attrs_data[old_d_id]:
                for adata in attrs_data[old_d_id][r_id]:
                    file_id = self.__get_attr_file_id(adata.pop('data_file', None), decision_id)
                    serializer = DownloadReportAttrSerializer(data=adata)
                    serializer.is_valid(raise_exception=True)
                    validated_data = serializer.validated_data

                    report_id = self.saved_reports[(decision_id, r_id)]
                    new_attrs.append(ReportAttr(data_id=file_id, report_id=report_id, **validated_data))
                    if report_id in self._leaves_ids:
                        attrs_cache.setdefault(report_id, {'attrs': {}})
                        attrs_cache[report_id]['attrs'][validated_data['name']] = validated_data['value']
        ReportAttr.objects.bulk_create(new_attrs)
        decisions_ids = list(self._uploaded_decisions.values())
        update_cache_atomic(ReportSafeCache.objects.filter(report__decision_id__in=decisions_ids), attrs_cache)
        update_cache_atomic(ReportUnsafeCache.objects.filter(report__decision_id__in=decisions_ids), attrs_cache)
        update_cache_atomic(ReportUnknownCache.objects.filter(report__decision_id__in=decisions_ids), attrs_cache)

    def __get_attr_file_id(self, rel_path, decision_id):
        if rel_path is None:
            return None
        if rel_path not in self._attr_files:
            instance = AttrFile(decision_id=decision_id)
            with open(self.__full_path(rel_path), mode='rb') as fp:
                instance.file.save(os.path.basename(rel_path), File(fp), save=True)
            self._attr_files[rel_path] = instance.id
        return self._attr_files[rel_path]

    def __upload_coverage(self):
        coverage_data = self.__read_json_file('{}.json'.format(CoverageArchive.__name__))
        if not coverage_data:
            return
        for coverage in coverage_data:
            decision_id = self.__get_decision_id(coverage['decision'])
            instance = CoverageArchive(
                report_id=self.saved_reports[(decision_id, coverage['report'])],
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
