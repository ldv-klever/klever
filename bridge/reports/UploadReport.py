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
import uuid
import zipfile

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.files import File
from django.db import transaction
from django.db.models import Q, F
from django.utils.timezone import now
from django.utils.functional import cached_property

from rest_framework import exceptions, fields, serializers

from bridge.vars import JOB_WEIGHT, JOB_STATUS, ERROR_TRACE_FILE, REPORT_ARCHIVE
from bridge.utils import logger, extract_archive, CheckArchiveError

import marks.SafeUtils as SafeUtils
import marks.UnsafeUtils as UnsafeUtils
import marks.UnknownUtils as UnknownUtils

from reports.models import (
    ReportRoot, ReportComponent, ReportSafe, ReportUnsafe, ReportUnknown, ComponentResource, ReportAttr,
    ReportComponentLeaf, ComponentInstances, CoverageArchive, AttrFile, Computer, OriginalSources, AdditionalSources
)
from service.models import Task, Decision
from service.utils import FinishJobDecision
from caches.models import ReportSafeCache, ReportUnsafeCache, ReportUnknownCache

from reports.serializers import ReportAttrSerializer, ComputerSerializer

SUBJOB_NAME = 'Subjob'


class ReportParentField(serializers.SlugRelatedField):
    queryset = ReportComponent.objects

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('slug_field', 'identifier')
        super(ReportParentField, self).__init__(*args, **kwargs)

    def get_queryset(self):
        return super().get_queryset().filter(root=self.root.reportroot)


class ReportAttrsField(fields.ListField):
    default_error_messages = {
        'wrong_format': 'Attributes has wrong format',
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
        'light_subjob': "Subjobs aren't allowed for lightweight jobs"
    }
    parent = ReportParentField()
    attrs = ReportAttrsField(required=False)

    def __init__(self, *args, **kwargs):
        self.reportroot = kwargs.pop('reportroot')
        self._fullweight = kwargs.pop('fullweight', True)
        custom_fields = kwargs.pop('fields', None)
        super().__init__(*args, **kwargs)
        if custom_fields:
            for field_name in set(self.fields) - set(custom_fields):
                self.fields.pop(field_name)

    def validate_component(self, value):
        if value == SUBJOB_NAME and not self._fullweight:
            self.fail('light_subjob')
        return value

    def validate_data(self, value):
        # Do not save report data for lightweight jobs
        if not self._fullweight:
            return None
        if not isinstance(value, dict):
            self.fail('data_not_dict')

        # Update old report data
        if self.instance and self.instance.data:
            value = self.instance.data.update(value)
        return value

    def validate_log(self, value):
        # Do not save log for lightweight jobs
        return value if self._fullweight else None

    def __get_computer(self, value, parent=None):
        if value:
            return Computer.objects.get_or_create(identifier=value.pop('identifier'), defaults=value)[0]
        elif isinstance(parent, ReportComponent):
            # Inherit parent computer
            return parent.computer
        raise exceptions.ValidationError(detail={'computer': "Required"})

    def __parent_attributes(self, parent, select_fields=None):
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
            raise exceptions.ValidationError(detail={'attrs': 'Trying to redefine attributes'})

        if self.instance:
            parent = self.instance.parent
            old_attrs_set = set(ReportAttr.objects.filter(report=self.instance).values_list('name', flat=True))
            if old_attrs_set & new_attrs_set:
                raise exceptions.ValidationError(detail={'attrs': 'Trying to redefine attributes'})

        if parent:
            ancestors_attrs = self.__parent_attributes(parent, select_fields=['name'])
            ancestors_attrs_set = set(p_attr['name'] for p_attr in ancestors_attrs)
            if ancestors_attrs_set & new_attrs_set:
                raise exceptions.ValidationError(detail={'attrs': 'Trying to redefine parent attributes'})
        return attrs

    def validate(self, value):
        # Do not allow to change finished ReportComponent instances
        if isinstance(self.instance, ReportComponent) and self.instance.finish_date is not None:
            raise exceptions.ValidationError(detail={'finish_date': "The report is finished already"})

        # Validate attributes
        value['attrs'] = self.__validate_attrs(value.get('attrs'), parent=value.get('parent'))

        # Validate computer
        if 'computer' in self.fields:
            value['computer'] = self.__get_computer(value.get('computer'), parent=value.get('parent'))

        value['root'] = self.reportroot
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

    def validate(self, value):
        # Validate report parent
        if not value.get('parent'):
            if ReportComponent.objects.filter(root=self.reportroot, parent=None).exists():
                raise exceptions.ValidationError(detail={'parent': "The report parent is required"})
        elif value['parent'].parent is not None and value['component'] == SUBJOB_NAME:
            raise exceptions.ValidationError(detail={'parent': "Subjob parent is not Core"})

        return super().validate(value)

    class Meta:
        model = ReportComponent
        fields = (
            'identifier', 'parent', 'component', 'computer', 'attrs', 'data',
            'finish_date', 'cpu_time', 'wall_time', 'memory', 'log'
        )
        extra_kwargs = {
            'cpu_time': {'allow_null': False, 'required': True},
            'wall_time': {'allow_null': False, 'required': True},
            'memory': {'allow_null': False, 'required': True},
            'finish_date': {'allow_null': False, 'required': True},
            'parent': {'allow_null': True, 'required': False}
        }


class ReportVerificationSerializer(UploadBaseSerializer):
    computer = ComputerSerializer(required=False)
    task = serializers.PrimaryKeyRelatedField(queryset=Task.objects, required=False)
    original = serializers.SlugRelatedField(slug_field='identifier', queryset=OriginalSources.objects)

    def validate(self, value):
        # If task is set then get verifier input archive from it
        if value.get('task'):
            with value['task'].archive.file as fp:
                value['verifier_input'] = File(fp, name=REPORT_ARCHIVE['verifier input'])
        value['verification'] = True
        return super().validate(value)

    class Meta:
        model = ReportComponent
        fields = (
            'identifier', 'parent', 'component', 'computer', 'attrs', 'data',
            'cpu_time', 'wall_time', 'memory', 'log', 'verifier_input', 'original'
        )
        extra_kwargs = {
            'cpu_time': {'allow_null': False, 'required': True},
            'wall_time': {'allow_null': False, 'required': True},
            'memory': {'allow_null': False, 'required': True}
        }


class ReportUnknownSerializer(UploadBaseSerializer):
    def create(self, validated_data):
        cache_obj = ReportUnknownCache(job_id=validated_data['root'].job_id)
        validated_data['attrs'] = self.__parent_attributes(validated_data['parent']) + validated_data['attrs']
        cache_obj.attrs = dict((attr['name'], attr['value']) for attr in validated_data['attrs'])
        validated_data['component'] = validated_data['parent'].component
        if validated_data['parent'].verification:
            validated_data['cpu_time'] = validated_data['parent'].cpu_time
            validated_data['wall_time'] = validated_data['parent'].wall_time
            validated_data['memory'] = validated_data['parent'].memory
        instance = super().create(validated_data)
        cache_obj.report = instance
        cache_obj.save()
        return instance

    class Meta:
        model = ReportUnknown
        fields = ('identifier', 'parent', 'attrs', 'problem_description')


class ReportSafeSerializer(UploadBaseSerializer):
    def validate(self, value):
        if not value['parent'].verification:
            raise exceptions.ValidationError(detail={'parent': "The safe parent must be a verification report"})
        return super().validate(value)

    def create(self, validated_data):
        cache_obj = ReportSafeCache(job_id=validated_data['root'].job_id)
        validated_data['attrs'] = self.__parent_attributes(validated_data['parent']) + validated_data['attrs']
        cache_obj.attrs = dict((attr['name'], attr['value']) for attr in validated_data['attrs'])
        validated_data['cpu_time'] = validated_data['parent'].cpu_time
        validated_data['wall_time'] = validated_data['parent'].wall_time
        validated_data['memory'] = validated_data['parent'].memory
        instance = super().create(validated_data)
        cache_obj.report = instance
        cache_obj.save()
        return instance

    class Meta:
        model = ReportSafe
        fields = ('identifier', 'parent', 'attrs', 'proof')


class ReportUnsafeSerializer(UploadBaseSerializer):
    default_error_messages = {
        'wrong_format': 'Error trace has wrong format'
    }

    def __check_node(self, node):
        if not isinstance(node, dict):
            self.fail('wrong_format')
        if node.get('type') not in {'function call', 'statement', 'action', 'thread'}:
            self.fail('wrong_format')
        if node['type'] == 'function call':
            required_fields = ['line', 'file', 'source', 'children', 'display']
        elif node['type'] == 'statement':
            required_fields = ['line', 'file', 'source']
        elif node['type'] == 'action':
            required_fields = ['line', 'file', 'display']
        else:
            required_fields = ['thread']
        for field_name in required_fields:
            if field_name not in node or node[required_fields] is None:
                self.fail('wrong_format')
        if node.get('children'):
            for child in node['children']:
                self.__check_node(child)

    def validate_error_trace(self, archive):
        try:
            with zipfile.ZipFile(archive, mode='r') as zfp:
                error_trace = json.loads(zfp.read(ERROR_TRACE_FILE).decode('utf8'))
        except Exception as e:
            logger.exception(e)
            self.fail('wrong_format')
        archive.seek(0)
        if not isinstance(error_trace, dict) or 'trace' not in error_trace or \
                not isinstance(error_trace.get('files'), list):
            self.fail('wrong_format')
        self.__check_node(error_trace['trace'])
        if error_trace['trace']['type'] != 'thread':
            self.fail('wrong_format')
        return archive

    def create(self, validated_data):
        cache_obj = ReportUnsafeCache(job_id=validated_data['root'].job_id)
        # Random unique identifier
        validated_data['identifier'] = '{0}/unsafe/{1}'.format(validated_data['parent'].identifier, uuid.uuid4())[:255]
        validated_data['attrs'] = self.__parent_attributes(validated_data['parent']) + validated_data['attrs']
        cache_obj.attrs = dict((attr['name'], attr['value']) for attr in validated_data['attrs'])
        validated_data['cpu_time'] = validated_data['parent'].cpu_time
        validated_data['wall_time'] = validated_data['parent'].wall_time
        validated_data['memory'] = validated_data['parent'].memory
        instance = super().create(validated_data)
        cache_obj.report = instance
        cache_obj.save()
        return instance

    class Meta:
        model = ReportUnsafe
        fields = ('parent', 'error_trace', 'attrs')


class UploadReport:
    def __init__(self, job, archives=None):
        self.job = job
        self.archives = archives

    def upload_all(self, reports):
        # Check that all archives are valid ZIP files
        self.__check_archives()
        for report in reports:
            try:
                self.__upload(report)
            except Exception as e:
                self.__process_exception(e)

    def __process_exception(self, exc):
        if isinstance(exc, CheckArchiveError):
            raise exceptions.ValidationError(detail={'ZIP': 'Zip archive check has failed: {}'.format(exc)})
        if isinstance(exc, exceptions.ValidationError):
            err_detail = exc.detail
        else:
            err_detail = {settings.NON_FIELD_ERRORS_KEY: 'Unknown error: {}'.format(exc)}
        # TODO: process exceptions in FinishJobDecision
        FinishJobDecision(self.job, JOB_STATUS[5][0], self.__collapse_detail(err_detail))
        raise exceptions.ValidationError(detail=err_detail)

    def __collapse_detail(self, value):
        # TODO: collapse error structure to string
        return str(value)

    def __upload(self, data):
        assert isinstance(data, dict), 'Report data not a dict'

        # Check report type
        if 'type' not in data:
            raise exceptions.ValidationError(detail={'type': 'Required'})
        supported_actions = {
            'start': self.__create_report_component,
            'finish': self.__finish_report_component,
            'attrs': self.__update_attrs,
            'verification': self.__create_verification_report,
            'verification finish': self.__finish_verification_report,
            'unsafe': self.__create_report_unsafe,
            'safe': self.__create_report_safe,
            'unknown': self.__create_report_unknown,
            'data': self.__upload_report_data,
            'coverage': self.__upload_coverage,
            'sources': self.__upload_additional_sources
        }
        if data['type'] not in supported_actions:
            raise exceptions.ValidationError(detail={'type': 'Is not supported'})

        # Upload report
        supported_actions[data['type']](data)

    def __check_archives(self):
        if self.archives is None:
            self.archives = {}
        for arch in self.archives.values():
            if not zipfile.is_zipfile(arch) or zipfile.ZipFile(arch).testzip():
                raise CheckArchiveError('The archive "{}" is not a ZIP file'.format(arch.name))

    def __start_decision(self):
        try:
            progress = Decision.objects.get(job=self.job)
        except Decision.DoesNotExist:
            raise exceptions.ValidationError(detail={'job': "The decision wasn't successfully started"})
        if progress.start_date is not None:
            raise exceptions.ValidationError(detail={'job': "Decision start date is filled already"})
        elif progress.finish_date is not None:
            raise exceptions.ValidationError(detail={'job': "The job is not solving already"})
        progress.start_date = now()
        progress.save()

    def __get_archive(self, arch_name):
        if not arch_name:
            return None
        if arch_name not in self.archives:
            raise exceptions.ValidationError(detail={'archives': 'Archive "{}" was not attached'.format(arch_name)})
        self.archives[arch_name].seek(0)
        return self.archives[arch_name]

    @cached_property
    def root(self):
        try:
            return ReportRoot.objects.get(job=self.job)
        except ReportRoot.DoesNotExist:
            raise exceptions.ValidationError(detail={'job': 'The job was not started properly'})

    @cached_property
    def _is_fullweight(self):
        return self.job.weight == JOB_WEIGHT[0][0]

    def __get_report(self, identifier, model=ReportComponent):
        if not identifier:
            raise exceptions.ValidationError(detail={'identifier': "Required"})
        try:
            return model.objects.get(root=self.root, identifier=identifier)
        except model.DoesNotExist:
            raise exceptions.ValidationError(detail={'identifier': "The report wasn't found"})

    def __ancestors_for_cache(self, report):
        ancestors_qs = report.get_ancestors()
        if not self._is_fullweight:
            # Update cache just for Core and verification reports as other reports will be deleted
            ancestors_qs = ancestors_qs.filter(Q(parent=None) | Q(verification=True))
        return list(parent.pk for parent in ancestors_qs)

    def __create_report_component(self, data):
        data['attr_data'] = self.__upload_attrs_files(self.__get_archive(data.get('attr_data')))
        serializer = ReportComponentSerializer(
            data=data, fullweight=self._is_fullweight, reportroot=self.root,
            fields={'identifier', 'parent', 'component', 'attrs', 'data', 'computer', 'log'}
        )
        serializer.is_valid(raise_exception=True)
        report = serializer.save()
        self.__update_instances_cache(report, self.__ancestors_for_cache(report))

        if report.parent is None:
            self.__start_decision()

    def __create_verification_report(self, data):
        data['attr_data'] = self.__upload_attrs_files(self.__get_archive(data.get('attr_data')))
        data['log'] = self.__get_archive(data.get('log'))
        data['verifier_input'] = self.__get_archive(data.pop('input files of static verifiers', None))

        serializer = ReportVerificationSerializer(data=data, fullweight=self._is_fullweight, reportroot=self.root)
        serializer.is_valid(raise_exception=True)
        report = serializer.save()

        # Upload coverage for the report
        if 'coverage' in data:
            carch = CoverageArchive(report=report)
            carch.add_coverage(self.__get_archive(data['coverage']), save=True)

        ancestrors_ids = self.__ancestors_for_cache(report)
        self.__update_resources_cache(report, ancestrors_ids)
        self.__update_instances_cache(report, ancestrors_ids)

    def __upload_coverage(self, data):
        # Uploads global coverage
        report = self.__get_report(data.get('identifier'))
        if not self._is_fullweight:
            # Upload for Core for lightweight jobs
            report = report.get_ancestors().first()
        for cov_id in data['coverage']:
            carch = CoverageArchive(report=report, identifier=cov_id)
            carch.add_coverage(self.__get_archive(data['coverage'][cov_id]), save=True)

    def __upload_additional_sources(self, data):
        report = self.__get_report(data.get('identifier'))
        instance = AdditionalSources(root=self.root)
        instance.add_archive(self.__get_archive(data['sources']), save=True)
        report.additional = instance
        report.save()

    def __update_attrs(self, data):
        report = self.__get_report(data.get('identifier'))
        data['attr_data'] = self.__upload_attrs_files(self.__get_archive(data.get('attr_data')))
        serializer = ReportComponentSerializer(
            instance=report, data=data, reportroot=report.root,
            fullweight=self._is_fullweight, fields={'attrs'}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

    def __upload_report_data(self, data):
        if not self._is_fullweight:
            return
        report = self.__get_report(data.get('identifier'))
        serializer = ReportComponentSerializer(instance=report, data=data, reportroot=report.root, fields={'data'})
        serializer.is_valid(raise_exception=True)
        serializer.save()

    def __finish_report_component(self, data):
        report = self.__get_report(data.get('identifier'))
        data['finish_date'] = now()
        data['log'] = self.__get_archive(data.get('log'))
        data['attr_data'] = self.__upload_attrs_files(self.__get_archive(data.get('attr_data')))
        serializer = ReportComponentSerializer(
            instance=report, data=data, reportroot=report.root,
            fields={'finish_date', 'wall_time', 'cpu_time', 'memory', 'attrs', 'data', 'log'}
        )
        serializer.is_valid(raise_exception=True)
        report = serializer.save()

        # Get report ancestors before report might be deleted
        parents_ids = self.__ancestors_for_cache(report)
        if report.parent and not self._is_fullweight:
            # WARNING: If report has children it will be deleted!
            # It means verification reports (children) are not finished yet.
            report.delete()
        self.__update_resources_cache(report, parents_ids)

        if report.pk:
            # Include self for updating component instances cache
            parents_ids.append(report.pk)
        ComponentInstances.objects.filter(report_id__in=parents_ids, component=report.component, in_progress__gt=0)\
            .update(in_progress=(F('in_progress') - 1))

    def __finish_verification_report(self, data):
        report = self.__get_report(data.get('identifier'))
        if not report.verification:
            raise exceptions.ValidationError(detail={'identifier': "The report is not verification"})

        # Get report ancestors before report might be deleted
        ancestors_ids = self.__ancestors_for_cache(report)
        if not self._is_fullweight:
            # Set parent to Core for lightweight jobs
            report.parent_id = ancestors_ids[0]

        if not self._is_fullweight and report.is_leaf_node():
            # Remove verification report if it doesn't have children for lightweight jobs
            report.delete()
        else:
            # Save report with new data
            report.finish_date = now()
            report.save()
            # Update instances cache also for self
            ancestors_ids.append(report.pk)

        # Update instances cache
        ComponentInstances.objects.filter(report_id__in=ancestors_ids, component=report.component, in_progress__gt=0)\
            .update(in_progress=(F('in_progress') - 1))

    def __create_report_unknown(self, data):
        data['attr_data'] = self.__upload_attrs_files(self.__get_archive(data.get('attr_data')))
        data['problem_description'] = self.__get_archive(data['problem desc'])
        serializer = ReportUnknownSerializer(data=data, reportroot=self.root)
        serializer.is_valid(raise_exception=True)
        report = serializer.save()

        # Get ancestors before parent might me changed
        ancestors_ids = self.__ancestors_for_cache(report)

        if not self._is_fullweight and not report.parent.verification:
            # Change parent to Core
            report.parent_id = ancestors_ids[0]
            report.save()

        # Caching leaves for each tree branch node
        ReportComponentLeaf.objects.bulk_create(list(
            ReportComponentLeaf(report_id=parent_id, unknown=report) for parent_id in ancestors_ids
        ))

        # Connect report with marks
        UnknownUtils.ConnectReport(report)

    def __create_report_safe(self, data):
        data['attr_data'] = self.__upload_attrs_files(self.__get_archive(data.get('attr_data')))
        data['proof'] = self.__get_archive(data.get('proof'))
        serializer = ReportSafeSerializer(data=data, reportroot=self.root)
        serializer.is_valid(raise_exception=True)
        report = serializer.save()

        # Caching leaves for each tree branch node
        ReportComponentLeaf.objects.bulk_create(list(
            ReportComponentLeaf(report_id=parent_id, safe=report)
            for parent_id in self.__ancestors_for_cache(report)
        ))

        # Connect report with marks
        SafeUtils.ConnectReport(report)

    def __create_report_unsafe(self, data):
        data['attr_data'] = self.__upload_attrs_files(self.__get_archive(data.get('attr_data')))
        data['error_trace'] = self.__get_archive(data.get('error_trace'))
        serializer = ReportUnsafeSerializer(data=data, reportroot=self.root)
        serializer.is_valid(raise_exception=True)
        report = serializer.save()

        # Caching leaves for each tree branch node
        ReportComponentLeaf.objects.bulk_create(list(
            ReportComponentLeaf(report_id=parent_id, safe=report)
            for parent_id in self.__ancestors_for_cache(report)
        ))

        # Connect new unsafe with marks
        UnsafeUtils.ConnectReport(report)
        UnsafeUtils.RecalculateTags([report])

    @transaction.atomic
    def __update_instances_cache(self, report, ancestors_ids):
        for parent_id in ancestors_ids:
            try:
                comp_inst = ComponentInstances.objects.get(report_id=parent_id, component=report.component)
            except ObjectDoesNotExist:
                comp_inst = ComponentInstances(report_id=parent_id, component=report.component)
            comp_inst.in_progress += 1
            comp_inst.total += 1
            comp_inst.save()

        if self._is_fullweight or report.verification or report.parent is None:
            # Create component instances for the new report
            ComponentInstances.objects.create(report=report, component=report.component, in_progress=1, total=1)

    @transaction.atomic
    def __update_resources_cache(self, report, ancestors_ids):
        # Otherwise report is deleted already or not saved yet
        if report.pk:
            # Create component resources cache for the new report
            ComponentResource.objects.create(
                report_id=report.pk, component=report.component,
                memory=report.memory, cpu_time=report.cpu_time, wall_time=report.wall_time
            )
            if not report.verification:
                # Create total resources cache for the new report
                ComponentResource.objects.create(
                    report_id=report.pk, memory=report.memory, cpu_time=report.cpu_time, wall_time=report.wall_time
                )

        # Update component resources cache for each parent
        for parent_id in ancestors_ids:
            try:
                cr = ComponentResource.objects.get(report_id=parent_id, component=report.component)
            except ComponentResource.DoesNotExist:
                cr = ComponentResource(report_id=parent_id, component=report.component)
            cr.memory = max(report.memory, cr.memory)
            cr.cpu_time += report.cpu_time
            cr.wall_time += report.wall_time
            cr.save()

        # Update total resources cache for each parent
        for total_cr in ComponentResource.objects.filter(report_id__in=ancestors_ids, component=None):
            total_cr.memory = max(total_cr.memory, report.memory)
            total_cr.cpu_time += report.cpu_time
            total_cr.wall_time += report.wall_time
            total_cr.save()

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
                newfile = AttrFile(root=self.root)
                with open(full_path, mode='rb') as fp:
                    newfile.file.save(os.path.basename(rel_path), File(fp), save=True)
                db_files[rel_path] = newfile.pk
        return db_files


def collapse_reports(job):
    if job.weight == JOB_WEIGHT[1][0]:
        # The job is already lightweight
        return
    root = job.reportroot
    if ReportComponent.objects.filter(root=root, component=SUBJOB_NAME).exists():
        return
    core = ReportComponent.objects.get(root=root, parent=None)
    ReportComponent.objects.filter(root=root, verification=True).update(parent=core)
    ReportUnknown.objects.filter(root=root, parent__verification=False).udpate(parent=core)
    # Remove all non-verification reports except Core
    ReportComponent.objects.filter(root=root).exclude(Q(verification=True) | Q(parent=None)).delete()
    job.weight = JOB_WEIGHT[1][0]
    job.save()
