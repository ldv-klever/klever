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
import time
import zipfile
from collections import OrderedDict

from django.core.files import File
from django.db import transaction
from django.db.models import Q
from django.utils.timezone import now

from rest_framework import exceptions, fields, serializers
from rest_framework.settings import api_settings

from bridge.vars import ERROR_TRACE_FILE, REPORT_ARCHIVE, DECISION_STATUS, SUBJOB_NAME, NAME_ATTR, MPTT_FIELDS
from bridge.utils import logger, extract_archive

from reports.models import (
    ReportComponent, ReportSafe, ReportUnsafe, ReportUnknown, ReportAttr, ReportComponentLeaf,
    CoverageArchive, AttrFile, Computer, OriginalSources, AdditionalSources, DecisionCache
)
from service.models import Task
from caches.models import ReportSafeCache, ReportUnsafeCache, ReportUnknownCache

from reports.serializers import ReportAttrSerializer, ComputerSerializer
from reports.tasks import fill_coverage_statistics
from marks.tasks import connect_safe_report, connect_unsafe_report, connect_unknown_report
from service.utils import FinishDecision

from reports.test import ReportsLogging


class ReportParentField(serializers.SlugRelatedField):
    queryset = ReportComponent.objects

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('slug_field', 'identifier')
        super(ReportParentField, self).__init__(*args, **kwargs)

    def get_queryset(self):
        return super().get_queryset().filter(decision=getattr(self.root, 'decision'))


class ReportAttrsField(fields.ListField):
    default_error_messages = {
        'wrong_format': 'Attributes have wrong format',
        'data_not_found': 'Attribute file was not found: {name}'
    }
    child = ReportAttrSerializer()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._files = None  # Attributes data

    def get_value(self, dictionary):
        # Get db files dictionary from parent serializer data
        self._files = dictionary.get('attr_data', {})
        return super().get_value(dictionary)

    def __attr_children(self, *args, children=None, compare=False, associate=False, data=None):
        attrs_data = []
        if isinstance(children, list):
            for child in children:
                if not isinstance(child, dict) or 'name' not in child or 'value' not in child:
                    self.fail('wrong_format')
                attrs_data.extend(self.__attr_children(
                    child['name'].replace(':', '_'), *args,
                    children=child['value'],
                    compare=child.get('compare', False),
                    associate=child.get('associate', False),
                    data=child.get('data')
                ))
        elif isinstance(children, str) and args:
            if data and data not in self._files:
                self.fail('data_not_found', name=data)
            return [{
                'name': ':'.join(reversed(args)), 'value': children,
                'compare': compare, 'associate': associate,
                'data_id': self._files[data] if data else None
            }]
        else:
            self.fail('wrong_format')
        return attrs_data

    def to_internal_value(self, data):
        if not isinstance(data, list):
            self.fail('not_a_list', input_type=type(data))
        return super().to_internal_value(self.__attr_children(children=data))


class UploadBaseSerializer(serializers.ModelSerializer):
    default_error_messages = {
        'data_not_dict': 'Dictionary expected.',
        'light_subjob': "Subjobs aren't allowed for lightweight jobs",
        'redefine': 'Trying to redefine attributes',
        'identifier_not_unique': 'Report with provided identifier already exists'
    }
    parent = ReportParentField()
    attrs = ReportAttrsField(required=False)

    def __init__(self, *args, **kwargs):
        self.decision = kwargs.pop('decision')
        self.allow_attrs_redefine = kwargs.pop('allow_attrs_redefine', False)
        custom_fields = kwargs.pop('fields', None)
        super().__init__(*args, **kwargs)
        if custom_fields:
            for field_name in set(self.fields) - set(custom_fields):
                self.fields.pop(field_name)

    def validate_identifier(self, value):
        if not self.instance:
            reports_model = getattr(self, 'Meta').model
            if reports_model.objects.filter(identifier=value, decision=self.decision).exists():
                self.fail('identifier_not_unique')
        return value

    def validate_component(self, value):
        if value == SUBJOB_NAME and self.decision.is_lightweight:
            self.fail('light_subjob')
        return value

    def validate_data(self, value):
        # Do not save report data for lightweight decisions
        if self.decision.is_lightweight:
            return None
        if not isinstance(value, dict):
            self.fail('data_not_dict')

        # Update old report data
        if self.instance and self.instance.data:
            self.instance.data.append(value)
            return self.instance.data

        return [value]

    def validate_log(self, value):
        # Do not save log for lightweight decisions
        return None if self.decision.is_lightweight else value

    def __get_computer(self, value, parent=None):
        if value:
            return Computer.objects.get_or_create(identifier=value.pop('identifier'), defaults=value)[0]
        elif isinstance(parent, ReportComponent):
            # Inherit parent computer
            return parent.computer
        raise exceptions.ValidationError('The computer is required')

    def parent_attributes(self, parent, select_fields=None):
        if not select_fields:
            select_fields = ['name', 'value', 'compare', 'associate', 'data_id']
        parents_ids = parent.get_ancestors(include_self=True).values_list('id', flat=True)
        return list(ReportAttr.objects.filter(report_id__in=parents_ids)
                    .order_by('report_id', 'id').values(*select_fields))

    def __validate_attrs(self, attrs, parent=None):
        if not attrs:
            return []

        new_attrs = list(attrdata['name'] for attrdata in attrs)
        new_attrs_set = set(new_attrs)
        if len(new_attrs_set) != len(new_attrs):
            self.fail('redefine')

        if self.instance:
            parent = self.instance.parent
            old_attrs_set = set(ReportAttr.objects.filter(report=self.instance).values_list('name', flat=True))
            if old_attrs_set & new_attrs_set:
                self.fail('redefine')

        if parent and not self.allow_attrs_redefine:
            ancestors_attrs = self.parent_attributes(parent, select_fields=['name'])
            ancestors_attrs_set = set(p_attr['name'] for p_attr in ancestors_attrs)
            if ancestors_attrs_set & new_attrs_set:
                self.fail('redefine')
        return attrs

    def validate(self, value):
        # Do not allow to change finished ReportComponent instances
        if isinstance(self.instance, ReportComponent) and self.instance.finish_date is not None:
            raise exceptions.ValidationError("Finished reports can't be updated!")

        # Validate attributes
        value['attrs'] = self.__validate_attrs(value.get('attrs'), parent=value.get('parent'))

        # Validate computer
        if 'computer' in self.fields:
            value['computer'] = self.__get_computer(value.get('computer'), parent=value.get('parent'))

        value['decision'] = self.decision
        return value

    def create(self, validated_data):
        attrs = validated_data.pop('attrs', [])
        instance = super().create(validated_data)
        ReportAttr.objects.bulk_create(list(ReportAttr(report=instance, **attrdata) for attrdata in attrs))
        return instance

    def update(self, instance, validated_data):
        attrs = validated_data.pop('attrs', [])
        instance = super().update(instance, validated_data)
        ReportAttr.objects.bulk_create(list(ReportAttr(report=instance, **attrdata) for attrdata in attrs))
        return instance


class ReportComponentSerializer(UploadBaseSerializer):
    computer = ComputerSerializer(required=False)
    parent = ReportParentField(allow_null=True)  # Allow null parent for Core
    original_sources = serializers.SlugRelatedField(
        slug_field='identifier', queryset=OriginalSources.objects.only('id'), required=False
    )

    def create(self, validated_data):
        # Validate report parent
        if not validated_data.get('parent'):
            if ReportComponent.objects.filter(decision=self.decision, parent=None).exists():
                raise exceptions.ValidationError(detail={'parent': "The report parent is required"})
        elif validated_data['parent'].parent is not None \
                and validated_data['component'] == SUBJOB_NAME:
            raise exceptions.ValidationError(detail={'parent': "Subjob parent is not Core"})
        return super().create(validated_data)

    class Meta:
        model = ReportComponent
        fields = (
            'identifier', 'parent', 'component', 'computer', 'attrs', 'data',
            'cpu_time', 'wall_time', 'memory', 'log', 'original_sources'
        )
        extra_kwargs = {
            'cpu_time': {'allow_null': False, 'required': True},
            'wall_time': {'allow_null': False, 'required': True},
            'memory': {'allow_null': False, 'required': True},
            'parent': {'allow_null': True, 'required': False}
        }


class ReportVerificationSerializer(UploadBaseSerializer):
    computer = ComputerSerializer(required=False)
    task = serializers.PrimaryKeyRelatedField(queryset=Task.objects.only('archive'), required=False)
    original_sources = serializers.SlugRelatedField(
        slug_field='identifier', queryset=OriginalSources.objects.only('id')
    )

    def validate(self, value):
        value['verification'] = True
        return super().validate(value)

    def create(self, validated_data):
        task = validated_data.pop('task', None)
        instance = super(ReportVerificationSerializer, self).create(validated_data)

        if task:
            # If task is set then get verifier input archive from it
            with task.archive.file as fp:
                verifier_files = File(fp, name=REPORT_ARCHIVE['verifier_files'])
                instance.add_verifier_files(verifier_files, save=True)
        return instance

    class Meta:
        model = ReportComponent
        fields = (
            'identifier', 'parent', 'component', 'computer', 'attrs', 'data',
            'cpu_time', 'wall_time', 'memory', 'log', 'original_sources', 'task'
        )
        extra_kwargs = {
            'cpu_time': {'allow_null': False, 'required': True},
            'wall_time': {'allow_null': False, 'required': True},
            'memory': {'allow_null': False, 'required': True}
        }


class UploadLeafBaseSerializer(UploadBaseSerializer):
    def __init__(self, *args, **kwargs):
        super(UploadLeafBaseSerializer, self).__init__(*args, allow_attrs_redefine=True, **kwargs)

    def get_cache_object(self, decision):
        raise NotImplementedError('Wrong serializer usage')

    def merge_attributes(self, parent, attrs):
        merged_attrs = OrderedDict()
        for attr in self.parent_attributes(parent):
            merged_attrs[attr['name']] = attr

        for attr in attrs:
            if attr['name'] in merged_attrs:
                if attr['value'] != merged_attrs[attr['name']]['value']:
                    self.fail('redefine')
                merged_attrs[attr['name']]['compare'] = attr['compare']
                merged_attrs[attr['name']]['associate'] = attr['associate']
            else:
                merged_attrs[attr['name']] = attr
        return list(merged_attrs.values())

    def validate(self, value):
        value = super().validate(value)
        value['attrs'] = self.merge_attributes(value['parent'], value['attrs'])
        return value

    def create(self, validated_data):
        cache_obj = self.get_cache_object(validated_data['decision'])
        cache_obj.attrs = dict((attr['name'], attr['value']) for attr in validated_data['attrs'])

        if validated_data['parent'].verification:
            validated_data['cpu_time'] = validated_data['parent'].cpu_time
            validated_data['wall_time'] = validated_data['parent'].wall_time
            validated_data['memory'] = validated_data['parent'].memory
        instance = super().create(validated_data)
        cache_obj.report = instance
        cache_obj.save()
        return instance


class ReportUnknownSerializer(UploadLeafBaseSerializer):
    def get_cache_object(self, decision):
        return ReportUnknownCache(decision=decision)

    def validate(self, value):
        value = super(ReportUnknownSerializer, self).validate(value)
        value['component'] = value['parent'].component
        return value

    class Meta:
        model = ReportUnknown
        fields = ('parent', 'identifier', 'attrs', 'problem_description')


class ReportSafeSerializer(UploadLeafBaseSerializer):
    def get_cache_object(self, decision):
        return ReportSafeCache(decision=decision)

    def validate(self, value):
        if not value['parent'].verification:
            raise exceptions.ValidationError(detail={'parent': "The safe parent must be a verification report"})
        return super(ReportSafeSerializer, self).validate(value)

    class Meta:
        model = ReportSafe
        fields = ('parent', 'identifier', 'attrs')


class ReportUnsafeSerializer(UploadLeafBaseSerializer):
    default_error_messages = {
        'wrong_format': 'Error trace has wrong format: {detail}.'
    }

    def get_cache_object(self, decision):
        return ReportUnsafeCache(decision=decision)

    def __check_node(self, node):
        if not isinstance(node, dict):
            self.fail('wrong_format', detail="node is not a dictionary")

        if node.get('type') not in {'function call', 'statement', 'action', 'thread', 'declaration', 'declarations'}:
            self.fail('wrong_format', detail='unsupported node type "{}"'.format(node.get('type')))
        if node['type'] == 'function call':
            required_fields = ['line', 'file', 'source', 'children', 'display']
        elif node['type'] == 'statement':
            required_fields = ['line', 'file', 'source']
        elif node['type'] == 'declaration':
            required_fields = ['line', 'file', 'source']
        elif node['type'] == 'action':
            required_fields = ['line', 'file', 'display']
        elif node['type'] == 'declarations':
            required_fields = ['children']
        else:
            required_fields = ['thread']
        for field_name in required_fields:
            if field_name not in node or node[field_name] is None:
                self.fail('wrong_format', detail='node field "{}" is required'.format(field_name))
        if node.get('notes'):
            if not isinstance(node['notes'], list):
                self.fail('wrong_format', detail='notes should be a list')
            for note in node['notes']:
                if not isinstance(note, dict):
                    self.fail('wrong_format', detail='note should be a dict')
                if 'text' not in note or not isinstance(note['text'], str) or not note['text']:
                    self.fail('wrong_format', detail='note should have a text')
                if 'level' not in note or not isinstance(note['level'], int) or note['level'] < 0:
                    self.fail('wrong_format', detail='note should have an unsigned int level')
        if node.get('children'):
            for child in node['children']:
                self.__check_node(child)
                if node['type'] == 'declarations' and child['type'] != 'declaration':
                    self.fail('wrong_format', detail='declarations child has type "{}"'.format(child['type']))

    def validate_error_trace(self, archive):
        try:
            with zipfile.ZipFile(archive, mode='r') as zfp:
                error_trace = json.loads(zfp.read(ERROR_TRACE_FILE).decode('utf8'))
        except Exception as e:
            logger.exception(e)
            self.fail('wrong_format', detail='file does not exist or it is wrong JSON')
        archive.seek(0)
        if not isinstance(error_trace, dict):
            self.fail('wrong_format', detail='error trace is not a dictionary')
        if not isinstance(error_trace.get('files'), list):
            self.fail('wrong_format', detail='error trace does not have files or it is not a list')
        if 'trace' not in error_trace:
            self.fail('wrong_format', detail='error trace does not have "trace"')
        if error_trace['trace']:
            self.__check_node(error_trace['trace'])
            if error_trace['trace']['type'] != 'thread':
                self.fail('wrong_format', detail='root error trace node type should be a "thread"')
        return archive

    class Meta:
        model = ReportUnsafe
        fields = ('parent', 'identifier', 'error_trace', 'attrs')


class UploadReports:
    def __init__(self, decision):
        self.decision = decision
        self.archives = {}
        self._logger = ReportsLogging(self.decision.id)

    def validate_archives(self, archives_list, archives):
        for arch_name in archives_list:
            if arch_name not in archives:
                raise exceptions.ValidationError(detail={
                    'archive': 'Archive "{}" was not attached'.format(arch_name)
                })
            arch = archives[arch_name]
            if not zipfile.is_zipfile(arch) or zipfile.ZipFile(arch).testzip():
                raise exceptions.ValidationError(detail={
                    'archive': 'The archive "{}" is not a ZIP file'.format(arch_name)
                })
            arch.seek(0)
            self.archives[arch_name] = arch

    def upload_all(self, reports):
        # Check that all archives are valid ZIP files
        for report in reports:
            try:
                self.__upload(report)
            except Exception as e:
                if str(e).__contains__('report_decision_id_identifier'):
                    logger.error('UniqueError')
                    logger.exception(e)
                self.__process_exception(e)

    def __process_exception(self, exc):
        if isinstance(exc, exceptions.ValidationError):
            err_detail = exc.detail
        else:
            logger.exception(exc)
            err_detail = 'Unknown error: {}'.format(exc)
        try:
            FinishDecision(self.decision, DECISION_STATUS[5][0], self.__collapse_detail(err_detail))
        except Exception as e:
            logger.exception(e)
            err_detail = 'Error while finishing decision with error'
        raise exceptions.ValidationError(detail=err_detail)

    def __collapse_detail(self, value):
        if isinstance(value, dict):
            error_list = []
            error_html = '<ul>'
            for name, val in value.items():
                if name == api_settings.NON_FIELD_ERRORS_KEY:
                    error_html += '<li>{}</li>'.format(self.__collapse_detail(val))
                else:
                    error_html += '<li>{}: {}</li>'.format(name, self.__collapse_detail(val))
                error_list.append('{}: {}'.format(name, self.__collapse_detail(val)))
            error_html += '</ul>'
            return error_html
        elif isinstance(value, list):
            if len(value) == 1:
                return self.__collapse_detail(value[0])
            error_html = '<ul>'
            for val in value:
                error_html += '<li>{}</li>'.format(self.__collapse_detail(val))
            error_html += '</ul>'
            return error_html
        return str(value)

    def __upload(self, data: dict):
        assert isinstance(data, dict), 'Report data not a dict'

        # Check report type
        if 'type' not in data:
            raise exceptions.ValidationError(detail={'type': 'Required'})
        supported_actions = {
            'start': self.__create_report_component,
            'patch': self.__patch_report_component,
            'finish': self.__finish_report_component,
            'verification': self.__create_verification_report,
            'verification finish': self.__finish_verification_report,
            'unsafe': self.__create_report_unsafe,
            'safe': self.__create_report_safe,
            'unknown': self.__create_report_unknown,
            'coverage': self.__upload_coverage,
        }
        if data['type'] not in supported_actions:
            raise exceptions.ValidationError(detail={
                'type': 'Report type "{}" is not supported'.format(data['type'])
            })

        # Upload report
        supported_actions[data['type']](data)

    def __get_archive(self, arch_name):
        """
        Get archive from attached files by name. Should be called before any DB changes.
        :param arch_name: Archive name
        :return: archive file pointer
        """
        if not arch_name:
            return None
        if arch_name not in self.archives:
            raise exceptions.ValidationError(detail={'archive': 'Archive "{}" was not provided'.format(arch_name)})
        self.archives[arch_name].seek(0)
        return self.archives[arch_name]

    def __get_report_for_update(self, identifier):
        """
        Get report by identifier for update. Must be used in atomic transaction block.
        :param identifier: report identifier
        :return: ReportComponent instance
        """
        if not identifier:
            raise exceptions.ValidationError(detail={'identifier': "Required"})
        try:
            return ReportComponent.objects.select_for_update().get(decision=self.decision, identifier=identifier)
        except ReportComponent.DoesNotExist:
            raise exceptions.ValidationError(detail={'identifier': "The report wasn't found"})

    def __ancestors_for_cache(self, report):
        ancestors_qs = report.get_ancestors()
        if self.decision.is_lightweight:
            # Update cache just for Core and verification reports as other reports will be deleted
            ancestors_qs = ancestors_qs.filter(Q(parent=None) | Q(reportcomponent__verification=True))
        return list(parent.pk for parent in ancestors_qs)

    def __create_report_component(self, data):
        self._logger.log("S0", data.get("identifier"))
        data['attr_data'] = self.__upload_attrs_files(self.__get_archive(data.get('attr_data')))

        self._logger.log("S1", data.get('component'), data.get("identifier"), data.get('parent'))
        serializer = ReportComponentSerializer(data=data, decision=self.decision, fields={
            'identifier', 'parent', 'component', 'attrs', 'data', 'computer', 'log'
        })
        serializer.is_valid(raise_exception=True)
        report = serializer.save()
        self._logger.log("S2", report.pk, report.identifier, report.parent_id)

        self.__update_decision_cache(report.component, started=True)
        self._logger.log("S3", report.pk)

    def __create_verification_report(self, data):
        self._logger.log("SV0", data.get("identifier"))
        data['log'] = self.__get_archive(data.get('log'))

        coverage_arch = None
        if 'coverage' in data:
            coverage_arch = self.__get_archive(data['coverage'])

        data['attr_data'] = self.__upload_attrs_files(self.__get_archive(data.get('attr_data')))
        save_kwargs = {}

        # Add additional sources if provided
        if 'additional_sources' in data:
            save_kwargs['additional_sources_id'] = self.__upload_additional_sources(data['additional_sources'])

        self._logger.log("SV1", data.get('component'), data.get("identifier"), data.get('parent'))
        serializer = ReportVerificationSerializer(data=data, decision=self.decision)
        serializer.is_valid(raise_exception=True)
        report = serializer.save(**save_kwargs)
        self._logger.log("SV2", report.pk, report.identifier, report.parent_id)

        # Upload coverage for the report
        if coverage_arch:
            self.__save_coverage(report, coverage_arch)

        self.__update_decision_cache(
            report.component, started=True,
            cpu_time=report.cpu_time, wall_time=report.wall_time, memory=report.memory
        )
        self._logger.log("SV3", report.pk)

    def __upload_coverage(self, data):
        self._logger.log("C0", data.get('identifier'))
        if not data.get('identifier'):
            raise exceptions.ValidationError(detail={'identifier': "Required"})

        coverages = {}
        for cov_id in data['coverage']:
            coverages[cov_id] = self.__get_archive(data['coverage'][cov_id])

        if self.decision.is_lightweight:
            # Upload for Core for lightweight decisions
            report = ReportComponent.objects.get(parent=None, decision=self.decision)
        else:
            # Get component report
            try:
                report = ReportComponent.objects.get(
                    decision=self.decision, identifier=data['identifier'], verification=False
                )
            except ReportComponent.DoesNotExist:
                raise exceptions.ValidationError(detail={'identifier': "The component report wasn't found"})
        self._logger.log("C1", report.pk, report.identifier)

        if not report.original_sources:
            raise exceptions.ValidationError(detail={
                'coverage': "The coverage can be uploaded only for reports with original sources"
            })

        for cov_id, cov_arch in coverages.items():
            # Save global coverage archive
            self.__save_coverage(report, cov_arch, identifier=cov_id)
        self._logger.log("C2", report.pk)

    def __patch_report_component(self, data):
        with transaction.atomic():
            self._logger.log("P0", data.get('identifier'))

            report = self.__get_report_for_update(data.get('identifier'))
            self._logger.log("P1", report.pk, report.identifier)

            save_kwargs = {}

            if 'attrs' in data:
                data['attr_data'] = self.__upload_attrs_files(self.__get_archive(data.get('attr_data')))

            if 'additional_sources' in data:
                save_kwargs['additional_sources_id'] = self.__upload_additional_sources(data['additional_sources'])

            serializer = ReportComponentSerializer(
                instance=report, data=data, partial=True, decision=self.decision,
                fields={'data', 'attrs', 'original_sources'}
            )
            serializer.is_valid(raise_exception=True)
            report = serializer.save(**save_kwargs)
            self._logger.log("P2", report.pk)

        if self.decision.is_lightweight and report.parent and (report.additional_sources or report.original_sources):
            with transaction.atomic():
                core_report = ReportComponent.objects.select_for_update().get(decision=self.decision, parent=None)
                if report.original_sources:
                    core_report.original_sources = report.original_sources
                if report.additional_sources:
                    core_report.additional_sources = report.additional_sources
                core_report.save()
                self._logger.log("P3", report.pk)

    def __finish_report_component(self, data):
        self._logger.log("F0", data.get('identifier'))

        data['log'] = self.__get_archive(data.get('log'))
        data['attr_data'] = self.__upload_attrs_files(self.__get_archive(data.get('attr_data')))

        # Update report atomicly
        with transaction.atomic():
            report = self.__get_report_for_update(data.get('identifier'))
            self._logger.log("F1", report.pk, report.identifier)

            serializer = ReportComponentSerializer(
                instance=report, data=data, decision=self.decision,
                fields={'wall_time', 'cpu_time', 'memory', 'attrs', 'data', 'log'}
            )
            serializer.is_valid(raise_exception=True)
            report = serializer.save(finish_date=now())
            self._logger.log("F2", report.pk)

        self.__update_decision_cache(
            report.component, finished=True,
            cpu_time=report.cpu_time, wall_time=report.wall_time, memory=report.memory
        )
        self._logger.log("F3", report.pk)

        # Get report ancestors before report might be deleted
        if report.parent and self.decision.is_lightweight:
            # WARNING: If report has children it will be deleted!
            # It means verification reports (children) are not finished yet.
            self._logger.log("F4", report.pk)
            if not self.__remove_report(report.pk):
                logger.error('Report deletion is failed!')

    def __finish_verification_report(self, data):
        update_data = {'finish_date': now()}

        self._logger.log("FV0", data.get('identifier'))

        # Get verification report by identifier
        if not data.get('identifier'):
            raise exceptions.ValidationError(detail={'identifier': "Required"})
        try:
            report = ReportComponent.objects.only('id', 'component', *MPTT_FIELDS)\
                .get(decision=self.decision, identifier=data['identifier'], verification=True)
        except ReportComponent.DoesNotExist:
            raise exceptions.ValidationError(detail={'identifier': "The report wasn't found"})
        self._logger.log("FV1", report.pk, report.identifier)

        if self.decision.is_lightweight:
            if report.is_leaf_node():
                # Remove verification report if it doesn't have children for lightweight decisions
                # But before update decision caches
                self.__update_decision_cache(report.component, finished=True)
                self._logger.log("FV2", report.pk)
                if not self.__remove_report(report.pk):
                    logger.error('Report deletion is failed!')
                return

            # Set parent to Core for lightweight decisions that will be preserved
            update_data['parent'] = ReportComponent.objects.only('id').get(decision=self.decision, parent=None)
            self._logger.log("FV3", report.pk, update_data['parent'].id)

        # Save report with new data
        with transaction.atomic():
            report = ReportComponent.objects.select_for_update().get(id=report.id)
            for k, v in update_data.items():
                setattr(report, k, v)
            report.save()
            self._logger.log("FV4", report.pk)

        self.__update_decision_cache(report.component, finished=True)
        self._logger.log("FV5", report.pk, report.parent_id)

    def __create_report_unknown(self, data):
        self._logger.log("UN0", data.get('parent'))

        data['problem_description'] = self.__get_archive(data['problem_description'])
        data['attr_data'] = self.__upload_attrs_files(self.__get_archive(data.get('attr_data')))
        serializer = ReportUnknownSerializer(data=data, decision=self.decision)
        serializer.is_valid(raise_exception=True)
        report = serializer.save()
        self._logger.log("UN1", report.pk, report.parent_id)

        # Get ancestors before parent might me changed
        ancestors_ids = self.__ancestors_for_cache(report)

        if self.decision.is_lightweight and not report.parent.verification:
            # Change parent to Core
            report.parent_id = ancestors_ids[0]
            report.save()
            self._logger.log("UN2", report.pk, report.parent_id)

        # Caching leaves for each tree branch node
        ReportComponentLeaf.objects.bulk_create(list(
            ReportComponentLeaf(report_id=parent_id, content_object=report) for parent_id in ancestors_ids
        ))

        # Connect report with marks
        connect_unknown_report.delay(report.id)

        self._logger.log("UN3", report.pk)

    def __create_report_safe(self, data):
        self._logger.log("SF0", data.get('parent'))

        data['attr_data'] = self.__upload_attrs_files(self.__get_archive(data.get('attr_data')))
        serializer = ReportSafeSerializer(data=data, decision=self.decision)
        serializer.is_valid(raise_exception=True)
        report = serializer.save()

        self._logger.log("SF1", report.pk, report.parent_id)

        # Caching leaves for each tree branch node
        ReportComponentLeaf.objects.bulk_create(list(
            ReportComponentLeaf(report_id=parent_id, content_object=report)
            for parent_id in self.__ancestors_for_cache(report)
        ))

        # Connect report with marks
        connect_safe_report.delay(report.id)

        self._logger.log("SF2", report.pk)

    def __create_report_unsafe(self, data):
        self._logger.log("UF0", data.get('parent'))

        data['error_trace'] = self.__get_archive(data.get('error_trace'))
        data['attr_data'] = self.__upload_attrs_files(self.__get_archive(data.get('attr_data')))
        serializer = ReportUnsafeSerializer(data=data, decision=self.decision)
        serializer.is_valid(raise_exception=True)
        report = serializer.save()

        self._logger.log("UF1", report.pk, report.parent_id)

        # Caching leaves for each tree branch node
        ReportComponentLeaf.objects.bulk_create(list(
            ReportComponentLeaf(report_id=parent_id, content_object=report)
            for parent_id in self.__ancestors_for_cache(report)
        ))

        # Connect new unsafe with marks
        connect_unsafe_report.delay(report.id)

        self._logger.log("UF2", report.pk)

    def __upload_additional_sources(self, arch_name):
        add_src = AdditionalSources(decision=self.decision)
        add_src.add_archive(self.__get_archive(arch_name), save=True)
        return add_src.id

    def __save_coverage(self, report, archive, identifier=''):
        # Get coverage name
        name = '-'
        if not report.verification:
            attr = ReportAttr.objects.filter(report=report, name=NAME_ATTR).only('value').first()
            name = attr.value if attr else '...'

        # Save coverage archive
        carch = CoverageArchive(report=report, identifier=identifier, name=name)
        carch.add_coverage(archive, save=True)

        # Fill coverage statistics in background
        fill_coverage_statistics.delay(carch.id)

    @transaction.atomic
    def __update_decision_cache(self, component, **kwargs):
        try:
            cache_obj = DecisionCache.objects.select_for_update().get(decision=self.decision, component=component)
        except DecisionCache.DoesNotExist:
            cache_obj = DecisionCache(decision=self.decision, component=component)
        if kwargs.get('cpu_time'):
            cache_obj.cpu_time += kwargs['cpu_time']
        if kwargs.get('wall_time'):
            cache_obj.wall_time += kwargs['wall_time']
        if kwargs.get('memory'):
            cache_obj.memory = max(cache_obj.memory, kwargs['memory'])
        if kwargs.get('started'):
            cache_obj.total += 1
        if kwargs.get('finished'):
            cache_obj.finished += 1
        cache_obj.save()

    def __upload_attrs_files(self, archive):
        if not archive:
            return {}
        try:
            files_dir = extract_archive(archive)
        except Exception as e:
            logger.exception("Archive extraction failed: %s" % e)
            raise exceptions.ValidationError(detail={'attr_data': 'Archive "{}" is corrupted'.format(archive.name)})
        db_files = {}
        for dir_path, dir_names, file_names in os.walk(files_dir.name):
            for file_name in file_names:
                full_path = os.path.join(dir_path, file_name)
                rel_path = os.path.relpath(full_path, files_dir.name).replace('\\', '/')
                newfile = AttrFile(decision=self.decision)
                with open(full_path, mode='rb') as fp:
                    newfile.file.save(os.path.basename(rel_path), File(fp), save=True)
                db_files[rel_path] = newfile.pk
        return db_files

    @transaction.atomic
    def __remove_report(self, report_id):
        cnt = 0
        while cnt < 5:
            try:
                report = ReportComponent.objects.select_for_update().get(id=report_id)
                report.delete()
                return True
            except Exception as e:
                logger.exception(e)
                time.sleep(0.1)
                cnt += 1
        return False
