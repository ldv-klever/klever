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
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _

from rest_framework import exceptions

from bridge.vars import JOB_UPLOAD_STATUS, DECISION_STATUS, PRESET_JOB_TYPE
from bridge.utils import BridgeException, extract_archive

from jobs.models import JOBFILE_DIR, PresetJob
from reports.models import (
    DecisionCache, ReportSafe, ReportUnsafe, ReportUnknown, ReportComponent,
    ReportAttr, CoverageArchive, AttrFile, OriginalSources, AdditionalSources
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
    def __init__(self, upload_obj):
        self._upload_obj = upload_obj
        self.job = None
        self._logger = UploadLogger()

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
        self._logger.log('=' * 20)
        self._logger.start('Total')
        # Extract job archive
        self.__change_upload_status(JOB_UPLOAD_STATUS[1][0])
        self._logger.start('Extract archive')
        with self._upload_obj.archive.file as fp:
            job_dir = extract_archive(fp)
        self._logger.end('Extract archive')

        # Upload job files
        self.__change_upload_status(JOB_UPLOAD_STATUS[2][0])
        self._logger.start('Upload files')
        self.__upload_job_files(os.path.join(job_dir.name, JOBFILE_DIR))
        self._logger.end('Upload files')

        # Save job
        self.__change_upload_status(JOB_UPLOAD_STATUS[3][0])
        self._logger.start('Create job')
        serializer_data = self.__parse_job_json(os.path.join(job_dir.name, 'job.json'))
        serializer = DownloadJobSerializer(data=serializer_data)
        serializer.is_valid(raise_exception=True)
        self.job = serializer.save(
            author=self._upload_obj.author, preset_id=self.__get_preset_id(serializer_data.get('preset_info'))
        )
        self._logger.end('Create job')

        # Upload job reports
        self.__change_upload_status(JOB_UPLOAD_STATUS[4][0])
        self._logger.start('Upload reports')
        res = UploadReports(self._upload_obj.author, self.job, job_dir.name)
        self._logger.end('Upload reports')

        if res.decisions:
            # Recalculate cache if job has decisions
            self.__change_upload_status(JOB_UPLOAD_STATUS[5][0])
            self._logger.start('Cache recalculation')
            Recalculation('all', res.decisions)
            self._logger.end('Cache recalculation')
        self._logger.end('Total')
        self._logger.log('=' * 20)

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


class UploadReports:
    def __init__(self, user, job, job_dir):
        self._user = user
        self._jobdir = job_dir
        self._final_statuses = {}
        self._logger = UploadLogger()
        self._uploaded_decisions = self.__upload_decisions(job)
        self._identifiers_in_use = dict((d_id, set()) for d_id in self._uploaded_decisions.values())

        if not self._uploaded_decisions:
            # There are no decisions for the job
            return

        self._original_sources = self.__upload_original_sources()

        self._additional_sources = {}
        self.saved_reports = {}
        self._leaves_ids = set()
        self._computers = {}
        self._chunk = []
        self.__upload_reports()
        self.__change_decision_statuses()
        self._logger.print_all_stat()

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
            self._logger.start_stat('Create decision')
            serializer = DownloadDecisionSerializer(data=decision)
            serializer.is_valid(raise_exception=True)
            uploaded_map[decision['id']] = serializer.save(
                job=job, operator=self._user, status=DECISION_STATUS[0][0]
            ).id
            self._final_statuses[uploaded_map[decision['id']]] = serializer.validated_data['status']
            self._logger.end_stat('Create decision')

        # Upload decision cache
        self._logger.start('Create decision cache')
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
        self._logger.end('Create decision cache')

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
                self._logger.start_stat('Upload original sources')
                try:
                    src_obj = OriginalSources.objects.get(identifier=src_id)
                except OriginalSources.DoesNotExist:
                    src_obj = OriginalSources(identifier=src_id)
                    with open(self.__full_path(src_path), mode='rb') as fp:
                        src_obj.add_archive(fp, save=True)
                original_sources[src_id] = src_obj.id
                self._logger.end_stat('Upload original sources')
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

    def __get_report_save_kwargs(self, decision_id, report_data):
        self._logger.start_stat('Validate report')

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

        self._logger.end_stat('Validate report')
        return save_kwargs

    @transaction.atomic
    def __upload_reports_chunk(self):
        if not self._chunk:
            return
        self._logger.start_stat('Upload reports chunk')
        for report_save_data in self._chunk:
            self._logger.start_stat('Create component report')
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
            self._logger.end_stat('Create component report')
        self._logger.end_stat('Upload reports chunk')
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
        self._logger.start('Upload reports')
        for report_data in self.__read_json_file('{}.json'.format(ReportComponent.__name__), required=True):
            decision_id = self.__get_decision_id(report_data['decision'])
            if report_data['parent'] and (decision_id, report_data['parent']) not in self.saved_reports:
                self.__upload_reports_chunk()
                if (decision_id, report_data['parent']) not in self.saved_reports:
                    raise BridgeException(_('Reports data was corrupted'))
            self._chunk.append(
                self.__get_report_save_kwargs(decision_id, report_data)
            )
        self.__upload_reports_chunk()

        self._logger.end('Upload reports')
        self._logger.print_stat('Validate report')
        self._logger.print_stat('Create component report')
        self._logger.print_stat('Upload reports chunk')

        # Upload leaves
        self._logger.start('Safes total')
        self.__upload_safes()
        self._logger.end('Safes total')
        self._logger.start('Unsafes total')
        self.__upload_unsafes()
        self._logger.end('Unsafes total')
        self._logger.start('Unknowns total')
        self.__upload_unknowns()
        self._logger.end('Unknowns total')
        self._logger.start('Attrs total')
        self.__upload_attrs()
        self._logger.end('Attrs total')
        self._logger.start('Coverage total')
        self.__upload_coverage()
        self._logger.end('Coverage total')

    def __upload_safes(self):
        safes_data = self.__read_json_file('{}.json'.format(ReportSafe.__name__))
        if not safes_data:
            return
        new_safes = []
        for report_data in safes_data:
            self._logger.start_stat('Validate safe')
            decision_id = self.__get_decision_id(report_data.get('decision'))

            save_kwargs = {
                'decision_id': decision_id,
                'identifier': self.__validate_report_identifier(decision_id, report_data.pop('identifier')),
                'parent_id': self.saved_reports[(decision_id, report_data.pop('parent'))]
            }
            serializer = UploadReportSafeSerializer(data=report_data)
            serializer.is_valid(raise_exception=True)

            new_safes.append(ReportSafe(**save_kwargs, **serializer.validated_data))
            self._logger.end_stat('Validate safe')
        self._logger.print_stat('Validate safe')

        self._logger.start('Create safes')
        with transaction.atomic():
            for new_safe in new_safes:
                new_safe.save()
        self._logger.end('Create safes')

        self._logger.start('Collect new safes')
        safes_cache = []
        new_safes_qs = ReportSafe.objects.filter(decision_id__in=list(self._identifiers_in_use))\
            .values_list('id', 'decision_id', 'identifier')
        for safe_id, decision_id, safe_identifier in new_safes_qs:
            self.saved_reports[(decision_id, safe_identifier)] = safe_id
            self._leaves_ids.add(safe_id)
            safes_cache.append(ReportSafeCache(decision_id=decision_id, report_id=safe_id))
        self._logger.end('Collect new safes')

        self._logger.start('Create safes cache')
        ReportSafeCache.objects.bulk_create(safes_cache)
        self._logger.end('Create safes cache')

    def __upload_unsafes(self):
        unsafes_data = self.__read_json_file('{}.json'.format(ReportUnsafe.__name__))
        if not unsafes_data:
            return

        unsafes_save_kwargs = []
        for report_data in unsafes_data:
            self._logger.start_stat('Validate unsafe')
            decision_id = self.__get_decision_id(report_data.get('decision'))
            parent_id = self.saved_reports[(decision_id, report_data.pop('parent'))]
            identifier = self.__validate_report_identifier(decision_id, report_data.pop('identifier'))
            save_kwargs = {
                'identifier': identifier, 'decision_id': decision_id, 'parent_id': parent_id,
                'error_trace': self.__full_path(report_data['error_trace'])
            }

            serializer = UploadReportUnsafeSerializer(data=report_data)
            serializer.is_valid(raise_exception=True)
            save_kwargs.update(serializer.validated_data)

            unsafes_save_kwargs.append(save_kwargs)
            self._logger.end_stat('Validate unsafe')
        self._logger.print_stat('Validate unsafe')

        with transaction.atomic():
            for unsafe_data in unsafes_save_kwargs:
                self._logger.start_stat('Create unsafe')
                error_trace = unsafe_data.pop('error_trace')
                report = ReportUnsafe(**unsafe_data)
                with open(error_trace, mode='rb') as fp:
                    report.add_trace(fp, save=True)
                self._logger.end_stat('Create unsafe')
        self._logger.print_stat('Create unsafe')

        self._logger.start('Collect new unsafes')
        unsafes_cache = []
        new_unsafes_qs = ReportUnsafe.objects.filter(decision_id__in=list(self._identifiers_in_use)) \
            .values_list('id', 'decision_id', 'identifier')
        for unsafe_id, decision_id, unsafe_identifier in new_unsafes_qs:
            self.saved_reports[(decision_id, unsafe_identifier)] = unsafe_id
            self._leaves_ids.add(unsafe_id)
            unsafes_cache.append(ReportUnsafeCache(decision_id=decision_id, report_id=unsafe_id))
        self._logger.end('Collect new unsafes')

        self._logger.start('Unsafes cache')
        ReportUnsafeCache.objects.bulk_create(unsafes_cache)
        self._logger.end('Unsafes cache')

    def __upload_unknowns(self):
        unknowns_data = self.__read_json_file('{}.json'.format(ReportUnknown.__name__))
        if not unknowns_data:
            return

        unknowns_save_kwargs = []
        for report_data in unknowns_data:
            self._logger.start_stat('Validate unknown')
            decision_id = self.__get_decision_id(report_data.get('decision'))
            parent_id = self.saved_reports[(decision_id, report_data.pop('parent'))]
            identifier = self.__validate_report_identifier(decision_id, report_data.pop('identifier'))
            save_kwargs = {
                'decision_id': decision_id, 'parent_id': parent_id, 'identifier': identifier,
                'problem_description': self.__full_path(report_data['problem_description'])
            }

            serializer = UploadReportUnknownSerializer(data=report_data)
            serializer.is_valid(raise_exception=True)
            save_kwargs.update(serializer.validated_data)

            unknowns_save_kwargs.append(save_kwargs)
            self._logger.end_stat('Validate unknown')
        self._logger.print_stat('Validate unknown')

        with transaction.atomic():
            for unknown_data in unknowns_save_kwargs:
                self._logger.start_stat('Create unknown')
                problem_description = unknown_data.pop('problem_description')
                report = ReportUnknown(**unknown_data)
                with open(problem_description, mode='rb') as fp:
                    report.add_problem_desc(fp, save=True)
                self._logger.end_stat('Create unknown')
        self._logger.print_stat('Create unknown')

        self._logger.start('Collect new unknowns')
        unknowns_cache = []
        new_unknowns_qs = ReportUnknown.objects.filter(decision_id__in=list(self._identifiers_in_use)) \
            .values_list('id', 'decision_id', 'identifier')
        for unknown_id, decision_id, unknown_identifier in new_unknowns_qs:
            self.saved_reports[(decision_id, unknown_identifier)] = unknown_id
            self._leaves_ids.add(unknown_id)
            unknowns_cache.append(ReportUnknownCache(decision_id=decision_id, report_id=unknown_id))
        self._logger.end('Collect new unknowns')

        self._logger.start('Unknowns cache')
        ReportUnknownCache.objects.bulk_create(unknowns_cache)
        self._logger.end('Unknowns cache')

    def __upload_attrs(self):
        attrs_data = self.__read_json_file('{}.json'.format(ReportAttr.__name__), required=True)
        attrs_cache = {}
        new_attrs = []
        new_attr_files = {}
        cnt = 0
        for old_d_id in attrs_data:
            decision_id = self.__get_decision_id(int(old_d_id))
            for r_id in attrs_data[old_d_id]:
                for adata in attrs_data[old_d_id][r_id]:
                    self._logger.start_stat('Parse attr')
                    report_id = self.saved_reports[(decision_id, r_id)]
                    data_file = adata.pop('data_file', None)

                    save_kwargs = {'report_id': report_id}

                    serializer = DownloadReportAttrSerializer(data=adata)
                    serializer.is_valid(raise_exception=True)
                    validated_data = serializer.validated_data
                    save_kwargs.update(validated_data)

                    new_attrs.append(ReportAttr(**save_kwargs))
                    if data_file is not None:
                        file_key = (decision_id, data_file)
                        new_attr_files.setdefault(file_key, [])
                        new_attr_files[file_key].append(cnt)
                    cnt += 1

                    if report_id in self._leaves_ids:
                        attrs_cache.setdefault(report_id, {'attrs': {}})
                        attrs_cache[report_id]['attrs'][validated_data['name']] = validated_data['value']
                    self._logger.end_stat('Parse attr')
        self._logger.print_stat('Parse attr')

        # Upload attributes' files
        with transaction.atomic():
            for decision_id, file_path in new_attr_files:
                self._logger.start_stat('Create attr file')
                attr_file_obj = AttrFile(decision_id=decision_id)
                with open(self.__full_path(file_path), mode='rb') as fp:
                    attr_file_obj.file.save(os.path.basename(file_path), File(fp), save=True)

                for i in new_attr_files[(decision_id, file_path)]:
                    # Add link to file for attributes that have it
                    new_attrs[i].data_id = attr_file_obj.id
                self._logger.end_stat('Create attr file')
        self._logger.print_stat('Create attr file')

        self._logger.start('Create attrs')
        ReportAttr.objects.bulk_create(new_attrs)
        self._logger.end('Create attrs')

        self._logger.start('Update attrs cache')
        decisions_ids = list(self._uploaded_decisions.values())
        update_cache_atomic(ReportSafeCache.objects.filter(report__decision_id__in=decisions_ids), attrs_cache)
        update_cache_atomic(ReportUnsafeCache.objects.filter(report__decision_id__in=decisions_ids), attrs_cache)
        update_cache_atomic(ReportUnknownCache.objects.filter(report__decision_id__in=decisions_ids), attrs_cache)
        self._logger.end('Update attrs cache')

    def __upload_coverage(self):
        coverage_data = self.__read_json_file('{}.json'.format(CoverageArchive.__name__))
        if not coverage_data:
            return
        for coverage in coverage_data:
            self._logger.start_stat('Upload coverage')
            decision_id = self.__get_decision_id(coverage['decision'])
            instance = CoverageArchive(
                report_id=self.saved_reports[(decision_id, coverage['report'])],
                identifier=coverage['identifier'], name=coverage.get('name', '...')
            )
            with open(self.__full_path(coverage['archive']), mode='rb') as fp:
                instance.add_coverage(fp, save=False)
            instance.save()
            self._logger.end_stat('Upload coverage')
            self._logger.start_stat('Fill coverage statistics')
            res = FillCoverageStatistics(instance)
            instance.total = res.total_coverage
            instance.has_extra = res.has_extra
            instance.save()
            self._logger.end_stat('Fill coverage statistics')
        self._logger.print_stat('Upload coverage')
        self._logger.print_stat('Fill coverage statistics')

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

    def __validate_report_identifier(self, decision_id, value):
        validate_report_identifier(value)
        if value in self._identifiers_in_use[decision_id]:
            raise exceptions.ValidationError({'report_identifier': 'Report identifier must be unique'})
        self._identifiers_in_use[decision_id].add(value)
        return value


class UploadLogger:
    def __init__(self):
        self._log_file = os.path.join(settings.LOGS_DIR, settings.UPLOAD_LOG_FILE)
        self._status = {}
        self._statistics = {}

    def start(self, name):
        self._status[name] = time.time()

    def end(self, name):
        if name not in self._status:
            return
        self.log("{}: {:.5f}".format(name, time.time() - self._status[name]))
        del self._status[name]

    def log(self, message):
        with open(self._log_file, mode="a", encoding="utf-8") as fp:
            fp.write("{}\n".format(message))

    def start_stat(self, name):
        self._statistics.setdefault(name, [])
        self._statistics[name].append(time.time())

    def end_stat(self, name):
        self._statistics[name][-1] = time.time() - self._statistics[name][-1]

    def __print_stat_row(self, name):
        total_time = sum(self._statistics[name])
        count = len(self._statistics[name])
        self.log("{}: min - {:.5f}, max - {:.5f}, avg - {:.5f}, total - {:.5f}, count - {}".format(
            name, min(self._statistics[name]),
            max(self._statistics[name]),
            total_time / count,
            total_time, count
        ))

    def print_stat(self, name):
        if name not in self._statistics:
            return
        self.__print_stat_row(name)
        del self._statistics[name]

    def print_all_stat(self):
        for name in self._statistics:
            self.__print_stat_row(name)
        self._statistics = {}
