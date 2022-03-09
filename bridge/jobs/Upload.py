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
import time

from django.conf import settings
from django.core.files import File
from django.db import transaction
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _

from rest_framework import exceptions

from bridge.vars import JOB_UPLOAD_STATUS, DECISION_STATUS, PRESET_JOB_TYPE
from bridge.utils import BridgeException, RequreLock, extract_archive

from jobs.models import JOBFILE_DIR, PresetJob, UploadedJobArchive
from reports.models import (
    DecisionCache, ReportSafe, ReportUnsafe, ReportUnknown, ReportComponent,
    ReportAttr, CoverageArchive, AttrFile, OriginalSources, AdditionalSources, Report
)
from service.models import Decision
from caches.models import ReportSafeCache, ReportUnsafeCache, ReportUnknownCache

from caches.utils import update_cache_atomic
from jobs.DownloadSerializers import (
    validate_report_identifier, DecisionCacheSerializer, DownloadDecisionSerializer,
    DownloadJobSerializer, DownloadComputerSerializer, DownloadReportAttrSerializer, UploadReportComponentSerializer,
    UploadReportSafeSerializer, UploadReportUnsafeSerializer, UploadReportUnknownSerializer
)
from jobs.serializers import JobFileSerializer
from reports.coverage import FillCoverageStatistics
from tools.utils import Recalculation


class JobArchiveUploader:
    reports_chunk_size = 500

    def __init__(self, upload_obj):
        self._upload_obj = upload_obj
        self._logger = UploadLogger(upload_obj)
        self.job = None

        self._jobdir = None
        self._decisions = {}
        self._final_statuses = {}
        self._identifiers_in_use = {}
        self._original_sources = {}
        self._additional_sources = {}
        self.saved_reports = {}
        self._leaves_ids = set()
        self._computers = {}
        self._reports_chunk = []

    def __enter__(self):
        self.job = None
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val:
            if self._decisions:
                Decision.objects.filter(id__in=self._decisions).delete()
            if self.job:
                self._upload_obj.job = self.job
            self._upload_obj.error = str(exc_val)
            self._upload_obj.status = JOB_UPLOAD_STATUS[14][0]

        else:
            self._upload_obj.job = self.job
            self._upload_obj.status = JOB_UPLOAD_STATUS[13][0]
        self._upload_obj.finish_date = now()
        self._upload_obj.step_progress = 0
        self._upload_obj.save()

    def upload(self):
        # Extract job archive
        self._logger.log('=' * 30)
        self._logger.start(JOB_UPLOAD_STATUS[1][0])
        with self._upload_obj.archive.file as fp:
            job_dir = extract_archive(fp)
        self._jobdir = job_dir.name

        # Upload job files
        self._logger.start(JOB_UPLOAD_STATUS[2][0])
        self.__upload_job_files(os.path.join(job_dir.name, JOBFILE_DIR))

        # Save job
        self._logger.start(JOB_UPLOAD_STATUS[3][0])
        serializer_data = self.__parse_job_json(os.path.join(job_dir.name, 'job.json'))
        serializer = DownloadJobSerializer(data=serializer_data)
        serializer.is_valid(raise_exception=True)
        self.job = serializer.save(
            author=self._upload_obj.author, preset_id=self.__get_preset_id(serializer_data.get('preset_info'))
        )

        # Upload job decisions objects with cache
        self._logger.start(JOB_UPLOAD_STATUS[4][0])
        self.__upload_decisions()

        if not self._decisions:
            self._logger.finish_all()
            return
        self._logger.start(JOB_UPLOAD_STATUS[5][0])
        self.__upload_original_sources()
        self._logger.end()

        self.__upload_reports()
        self.__change_decision_statuses()

        # Recalculate cache if job has decisions
        self._logger.start(JOB_UPLOAD_STATUS[12][0])
        Recalculation('all', list(self._decisions.values()))
        self._logger.finish_all()

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
            preset_dir = PresetJob.objects.get(name=preset_info['name'], parent_id=main_preset.id)
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
            # If 'JobFiles' doesn't exist then the job doesn't have decisions or archive is corrupted.
            # It'll be checked while files tree is uploading on decisions creation.
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

    def __upload_decisions(self):
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
            decision_obj = serializer.save(job=self.job, operator=self._upload_obj.author, status=DECISION_STATUS[0][0])
            self._decisions[decision['id']] = decision_obj.id
            self._identifiers_in_use[decision_obj.id] = set()
            self._final_statuses[decision_obj.id] = serializer.validated_data['status']

        if not self._decisions:
            # The job does not have decisions
            return

        # Upload decision cache
        cache_data_list = self.__read_json_file('{}.json'.format(DecisionCache.__name__))
        if not cache_data_list:
            # All decisions should have cache
            raise exceptions.ValidationError({'decision': _('Decision data is corrupted')})

        new_cache_objects = []
        for dec_cache in cache_data_list:
            if 'decision' not in dec_cache or not self._decisions.get(dec_cache['decision']):
                raise exceptions.ValidationError({'decision': _('Decision data is corrupted')})
            serializer = DecisionCacheSerializer(data=dec_cache)
            serializer.is_valid(raise_exception=True)
            new_cache_objects.append(DecisionCache(
                decision_id=self._decisions[dec_cache['decision']], **serializer.validated_data
            ))
        DecisionCache.objects.bulk_create(new_cache_objects)

    @transaction.atomic
    def __change_decision_statuses(self):
        for decision in Decision.objects.filter(id__in=list(self._decisions.values())).select_for_update():
            decision.status = self._final_statuses[decision.id]
            decision.save()

    def __upload_original_sources(self):
        orig_data = self.__read_json_file('{}.json'.format(OriginalSources.__name__), required=True)
        if not orig_data:
            return
        for src_id, src_path in orig_data.items():
            with RequreLock(OriginalSources):
                try:
                    src_obj = OriginalSources.objects.get(identifier=src_id)
                except OriginalSources.DoesNotExist:
                    src_obj = OriginalSources(identifier=src_id)
                    with open(self.__full_path(src_path), mode='rb') as fp:
                        src_obj.add_archive(fp, save=True)
            self._original_sources[src_id] = src_obj.id

    def __upload_reports(self):
        # Upload components tree
        reports_tree_data = self.__read_json_file('{}.json'.format(ReportComponent.__name__), required=True)
        self._logger.start(JOB_UPLOAD_STATUS[6][0], len(reports_tree_data))
        chunk_size = 0
        for report_data in reports_tree_data:
            decision_id = self.__get_decision_id(report_data['decision'])
            if report_data['parent'] and (decision_id, report_data['parent']) not in self.saved_reports:
                self.__upload_reports_chunk()
                self._logger.update(chunk_size)
                chunk_size = 0
                if (decision_id, report_data['parent']) not in self.saved_reports:
                    raise BridgeException(_('Reports data was corrupted'))
            elif chunk_size > self.reports_chunk_size:
                self.__upload_reports_chunk()
                self._logger.update(chunk_size)
                chunk_size = 0
            self._reports_chunk.append(
                self.__get_report_save_kwargs(decision_id, report_data)
            )
            chunk_size += 1
        self.__upload_reports_chunk()
        self._logger.update(chunk_size)
        self._logger.end()

        # Upload leaves
        self.__upload_safes()
        self.__upload_unsafes()
        self.__upload_unknowns()
        self.__upload_attrs()
        self.__upload_coverage()

    def __get_report_save_kwargs(self, decision_id, report_data):
        save_kwargs = {
            'decision_id': decision_id,
            'identifier': self.__validate_report_identifier(decision_id, report_data.get('identifier'))
        }

        serializer = UploadReportComponentSerializer(data=report_data)
        serializer.is_valid(raise_exception=True)
        save_kwargs.update(serializer.validated_data)

        computer_obj = self.__get_computer(report_data.get('computer'))
        save_kwargs.update({
            'computer_id': computer_obj.pk, 'parent_id': self.saved_reports.get((decision_id, report_data['parent']))
        })

        if report_data.get('additional_sources'):
            add_sources_obj = self.__get_additional_sources(decision_id, report_data['additional_sources'])
            save_kwargs['additional_sources_id'] = add_sources_obj.pk

        if report_data.get('original_sources'):
            save_kwargs['original_sources_id'] = self._original_sources[report_data['original_sources']]

        if report_data.get('log'):
            save_kwargs['log'] = self.__full_path(report_data['log'])

        if report_data.get('verifier_files'):
            save_kwargs['verifier_files'] = self.__full_path(report_data['verifier_files'])

        return save_kwargs

    def __upload_reports_chunk(self):
        with transaction.atomic():
            with Report.objects.delay_mptt_updates():
                for report_save_data in self._reports_chunk:
                    log_file = report_save_data.pop('log', None)
                    verifier_files_arch = report_save_data.pop('verifier_files', None)

                    report = ReportComponent(**report_save_data)
                    if log_file:
                        with open(log_file, mode='rb') as fp:
                            report.add_log(fp, save=False)
                    if verifier_files_arch:
                        with open(verifier_files_arch, mode='rb') as fp:
                            report.add_verifier_files(fp, save=False)
                    report.save()
                    self.saved_reports[(report.decision_id, report.identifier)] = report.id
        self._reports_chunk = []

    def __upload_safes(self):
        safes_data = self.__read_json_file('{}.json'.format(ReportSafe.__name__))
        if not safes_data:
            return

        self._logger.start(JOB_UPLOAD_STATUS[7][0])

        safes_cache = []
        new_reports = []
        for report_data in safes_data:
            decision_id = self.__get_decision_id(report_data.get('decision'))
            parent_id = self.saved_reports[(decision_id, report_data.pop('parent'))]
            identifier = self.__validate_report_identifier(decision_id, report_data.pop('identifier'))
            serializer = UploadReportSafeSerializer(data=report_data)
            serializer.is_valid(raise_exception=True)
            new_reports.append(ReportSafe(
                decision_id=decision_id, identifier=identifier, parent_id=parent_id, **serializer.validated_data
            ))

        with transaction.atomic():
            with Report.objects.delay_mptt_updates():
                for report in new_reports:
                    report.save()

        reports_qs = ReportSafe.objects.filter(decision_id__in=list(self._decisions.values()))\
            .only('id', 'identifier', 'decision_id')
        for report in reports_qs:
            self.saved_reports[(report.decision_id, report.identifier)] = report.id
            self._leaves_ids.add(report.id)
            safes_cache.append(ReportSafeCache(decision_id=report.decision_id, report_id=report.id))

        ReportSafeCache.objects.bulk_create(safes_cache)
        self._logger.end()

    def __upload_unsafes(self):
        unsafes_data = self.__read_json_file('{}.json'.format(ReportUnsafe.__name__))
        if not unsafes_data:
            return
        self._logger.start(JOB_UPLOAD_STATUS[8][0])

        unsafes_cache = []
        new_reports = []
        for report_data in unsafes_data:
            decision_id = self.__get_decision_id(report_data.get('decision'))
            parent_id = self.saved_reports[(decision_id, report_data.pop('parent'))]
            identifier = self.__validate_report_identifier(decision_id, report_data.pop('identifier'))
            error_trace = self.__full_path(report_data['error_trace'])
            serializer = UploadReportUnsafeSerializer(data=report_data)
            serializer.is_valid(raise_exception=True)

            report = ReportUnsafe(
                identifier=identifier, decision_id=decision_id, parent_id=parent_id, **serializer.validated_data
            )
            with open(error_trace, mode='rb') as fp:
                report.add_trace(fp, save=False)
            new_reports.append(report)

        with transaction.atomic():
            with Report.objects.delay_mptt_updates():
                for report in new_reports:
                    report.save()

        reports_qs = ReportUnsafe.objects.filter(decision_id__in=list(self._decisions.values()))\
            .only('id', 'identifier', 'decision_id')
        for report in reports_qs:
            self.saved_reports[(report.decision_id, report.identifier)] = report.id
            self._leaves_ids.add(report.id)
            unsafes_cache.append(ReportUnsafeCache(decision_id=report.decision_id, report_id=report.id))

        ReportUnsafeCache.objects.bulk_create(unsafes_cache)
        self._logger.end()

    def __upload_unknowns(self):
        unknowns_data = self.__read_json_file('{}.json'.format(ReportUnknown.__name__))
        if not unknowns_data:
            return
        self._logger.start(JOB_UPLOAD_STATUS[9][0])

        unknowns_cache = []
        new_reports = []
        for report_data in unknowns_data:
            decision_id = self.__get_decision_id(report_data.get('decision'))
            parent_id = self.saved_reports[(decision_id, report_data.pop('parent'))]
            identifier = self.__validate_report_identifier(decision_id, report_data.pop('identifier'))
            problem_description = self.__full_path(report_data['problem_description'])
            serializer = UploadReportUnknownSerializer(data=report_data)
            serializer.is_valid(raise_exception=True)

            report = ReportUnknown(
                decision_id=decision_id, parent_id=parent_id, identifier=identifier, **serializer.validated_data
            )
            with open(problem_description, mode='rb') as fp:
                report.add_problem_desc(fp, save=False)
            new_reports.append(report)

        with transaction.atomic():
            with Report.objects.delay_mptt_updates():
                for report in new_reports:
                    report.save()

        reports_qs = ReportUnknown.objects.filter(decision_id__in=list(self._decisions.values()))\
            .only('id', 'identifier', 'decision_id')
        for report in reports_qs:
            self.saved_reports[(report.decision_id, report.identifier)] = report.id
            self._leaves_ids.add(report.id)
            unknowns_cache.append(ReportUnknownCache(decision_id=report.decision_id, report_id=report.id))

        ReportUnknownCache.objects.bulk_create(unknowns_cache)
        self._logger.end()

    def __upload_attrs(self):
        attrs_data = self.__read_json_file('{}.json'.format(ReportAttr.__name__), required=True)
        attrs_cache = {}
        new_attrs = []
        new_attr_files = {}
        cnt = 0
        self._logger.start(JOB_UPLOAD_STATUS[10][0], total=100)
        for old_d_id in attrs_data:
            decision_id = self.__get_decision_id(int(old_d_id))
            for r_id in attrs_data[old_d_id]:
                for adata in attrs_data[old_d_id][r_id]:
                    report_id = self.saved_reports[(decision_id, r_id)]
                    data_file = adata.pop('data_file', None)

                    serializer = DownloadReportAttrSerializer(data=adata)
                    serializer.is_valid(raise_exception=True)
                    validated_data = serializer.validated_data

                    new_attrs.append(ReportAttr(report_id=report_id, **validated_data))
                    if data_file is not None:
                        file_key = (decision_id, data_file)
                        new_attr_files.setdefault(file_key, [])
                        new_attr_files[file_key].append(cnt)
                    cnt += 1

                    if report_id in self._leaves_ids:
                        attrs_cache.setdefault(report_id, {'attrs': {}})
                        attrs_cache[report_id]['attrs'][validated_data['name']] = validated_data['value']
        self._logger.update(10)

        attr_file_number = len(new_attr_files)
        if attr_file_number > 0:
            # Upload attributes' files
            with transaction.atomic():
                step_percent_number = int(attr_file_number / 70)
                attr_file_cnt = 0
                for decision_id, file_path in new_attr_files:
                    attr_file_obj = AttrFile(decision_id=decision_id)
                    with open(self.__full_path(file_path), mode='rb') as fp:
                        attr_file_obj.file.save(os.path.basename(file_path), File(fp), save=True)

                    for i in new_attr_files[(decision_id, file_path)]:
                        # Add link to file for attributes that have it
                        new_attrs[i].data_id = attr_file_obj.id
                    attr_file_cnt += 1
                    if attr_file_cnt > step_percent_number:
                        self._logger.update(int(70 * attr_file_cnt / attr_file_number))
                        attr_file_cnt = 0
        else:
            self._logger.update(70)

        ReportAttr.objects.bulk_create(new_attrs)
        self._logger.update(10)

        decisions_ids = list(self._decisions.values())
        update_cache_atomic(ReportSafeCache.objects.filter(report__decision_id__in=decisions_ids), attrs_cache)
        update_cache_atomic(ReportUnsafeCache.objects.filter(report__decision_id__in=decisions_ids), attrs_cache)
        update_cache_atomic(ReportUnknownCache.objects.filter(report__decision_id__in=decisions_ids), attrs_cache)
        self._logger.update(10)
        self._logger.end()

    def __upload_coverage(self):
        coverage_data = self.__read_json_file('{}.json'.format(CoverageArchive.__name__))
        if not coverage_data:
            return
        self._logger.start(JOB_UPLOAD_STATUS[11][0], len(coverage_data))

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
            self._logger.update()
        self._logger.end()

    def __get_decision_id(self, old_id):
        if not isinstance(old_id, int) or old_id not in self._decisions:
            raise exceptions.ValidationError({'decision': _('The job archive is corrupted')})
        return self._decisions[old_id]

    def __validate_report_identifier(self, decision_id, value):
        validate_report_identifier(value)
        if value in self._identifiers_in_use[decision_id]:
            raise exceptions.ValidationError({'report_identifier': 'Report identifier must be unique'})
        self._identifiers_in_use[decision_id].add(value)
        return value

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

    def __get_additional_sources(self, decision_id, rel_path):
        if rel_path not in self._additional_sources:
            add_inst = AdditionalSources(decision_id=decision_id)
            with open(self.__full_path(rel_path), mode='rb') as fp:
                add_inst.add_archive(fp, save=True)
            self._additional_sources[rel_path] = add_inst
        return self._additional_sources[rel_path]

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


class UploadLogger:
    def __init__(self, upload_obj: UploadedJobArchive):
        self._total_start = time.time()
        self._upload_obj = upload_obj
        self._log_file = os.path.join(settings.LOGS_DIR, settings.UPLOAD_LOG_FILE)
        self._start_time = None
        self._progress = None

    def start(self, status, total=None):
        if self._start_time:
            self.end()
        if total:
            self._progress = [0, total, 0]
        self._start_time = time.time()

        self._upload_obj.status = status
        self._upload_obj.step_progress = 0
        self._upload_obj.save()

    def update(self, count=1):
        if not self._progress:
            # Nothing is tracked
            return
        self._progress[0] += count
        new_progress = int(self._progress[0] / self._progress[1] * 100)
        if new_progress != self._progress[2]:
            self._progress[2] = new_progress
            self._upload_obj.step_progress = new_progress
            self._upload_obj.save()

    def end(self):
        if not self._start_time:
            # Nothing was started
            return
        self.log("{}: {:.5f}".format(self._upload_obj.get_status_display(), time.time() - self._start_time))
        self._start_time = None
        self._progress = None

    def log(self, message):
        with open(self._log_file, mode="a", encoding="utf-8") as fp:
            fp.write("{}\n".format(message))

    def finish_all(self):
        if self._start_time:
            self.end()
        self.log("Total: {:.5f}".format(time.time() - self._total_start))
