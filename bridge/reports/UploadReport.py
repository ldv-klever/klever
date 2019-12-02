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

from django.core.files import File
from django.db.models import Q
from django.utils.functional import cached_property
from django.utils.timezone import now

from rest_framework import exceptions, fields, serializers
from rest_framework.settings import api_settings

from bridge.vars import (
    JOB_WEIGHT, JOB_STATUS, ERROR_TRACE_FILE, REPORT_ARCHIVE,
    SUBJOB_NAME, NAME_ATTR, UNKNOWN_ATTRS_NOT_ASSOCIATE
)
from bridge.utils import logger, extract_archive, CheckArchiveError

from reports.models import (
    ReportRoot, ReportComponent, ReportSafe, ReportUnsafe, ReportUnknown, ReportAttr,
    ReportComponentLeaf, CoverageArchive, AttrFile, Computer, OriginalSources, AdditionalSources
)
from service.models import Task, Decision
from service.utils import FinishJobDecision
from caches.models import ReportSafeCache, ReportUnsafeCache, ReportUnknownCache

from marks.SafeUtils import ConnectSafeReport
from marks.UnknownUtils import ConnectUnknownReport
from marks.tasks import connect_unsafe_report

from reports.serializers import ReportAttrSerializer, ComputerSerializer
from reports.coverage import FillCoverageStatistics


class ReportParentField(serializers.SlugRelatedField):
    queryset = ReportComponent.objects

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('slug_field', 'identifier')
        super(ReportParentField, self).__init__(*args, **kwargs)

    def get_queryset(self):
        return super().get_queryset().filter(root=getattr(self.root, 'reportroot'))


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
            self.instance.data.update(value)
            return self.instance.data

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

        if parent:
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
    parent = ReportParentField(allow_null=True)  # Allow null parent for Core
    original_sources = serializers.SlugRelatedField(
        slug_field='identifier', queryset=OriginalSources.objects, required=False
    )

    def create(self, validated_data):
        # Validate report parent
        if not validated_data.get('parent'):
            if ReportComponent.objects.filter(root=self.reportroot, parent=None).exists():
                raise exceptions.ValidationError(detail={'parent': "The report parent is required"})
        elif validated_data['parent'].parent is not None \
                and validated_data['component'] == SUBJOB_NAME:
            raise exceptions.ValidationError(detail={'parent': "Subjob parent is not Core"})
        return super().create(validated_data)

    class Meta:
        model = ReportComponent
        fields = (
            'identifier', 'parent', 'component', 'computer', 'attrs', 'data',
            'finish_date', 'cpu_time', 'wall_time', 'memory', 'log', 'original_sources'
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
    original_sources = serializers.SlugRelatedField(slug_field='identifier', queryset=OriginalSources.objects)

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
    def get_cache_object(self, reportroot):
        raise NotImplementedError('Wrong serialzier usage')

    def validate(self, value):
        value = super().validate(value)
        # Random identifier
        value['identifier'] = '{0}/leaf/{1}'.format(value['parent'].identifier, uuid.uuid4())[-255:]
        value['attrs'] = self.parent_attributes(value['parent']) + value['attrs']
        return value

    def create(self, validated_data):
        cache_obj = self.get_cache_object(validated_data['root'])
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
    def get_cache_object(self, reportroot):
        return ReportUnknownCache(job_id=reportroot.job_id)

    def parent_attributes(self, parent, select_fields=None):
        attrs_list = super().parent_attributes(parent, select_fields=select_fields)
        for adata in attrs_list:
            if adata['name'] in UNKNOWN_ATTRS_NOT_ASSOCIATE:
                adata['associate'] = False
        return attrs_list

    def validate(self, value):
        value = super(ReportUnknownSerializer, self).validate(value)
        value['component'] = value['parent'].component
        return value

    class Meta:
        model = ReportUnknown
        fields = ('parent', 'attrs', 'problem_description')


class ReportSafeSerializer(UploadLeafBaseSerializer):
    def get_cache_object(self, reportroot):
        return ReportSafeCache(job_id=reportroot.job_id)

    def validate(self, value):
        if not value['parent'].verification:
            raise exceptions.ValidationError(detail={'parent': "The safe parent must be a verification report"})
        return super(ReportSafeSerializer, self).validate(value)

    class Meta:
        model = ReportSafe
        fields = ('parent', 'attrs')


class ReportUnsafeSerializer(UploadLeafBaseSerializer):
    default_error_messages = {
        'wrong_format': 'Error trace has wrong format: {detail}.'
    }

    def get_cache_object(self, reportroot):
        return ReportUnsafeCache(job_id=reportroot.job_id)

    def __check_node(self, node):
        if not isinstance(node, dict):
            self.fail('wrong_format', detail="node is not a dictionary")
        if node.get('type') not in {'function call', 'statement', 'action', 'thread'}:
            self.fail('wrong_format', detail='unsupported node type')
        if node['type'] == 'function call':
            required_fields = ['line', 'file', 'source', 'children', 'display']
        elif node['type'] == 'statement':
            required_fields = ['line', 'file', 'source']
        elif node['type'] == 'action':
            required_fields = ['line', 'file', 'display']
        else:
            required_fields = ['thread']
        for field_name in required_fields:
            if field_name not in node or node[field_name] is None:
                self.fail('wrong_format', detail='node field "{}" is required'.format(field_name))
        if node.get('children'):
            for child in node['children']:
                self.__check_node(child)

    def validate_error_trace(self, archive):
        try:
            with zipfile.ZipFile(archive, mode='r') as zfp:
                error_trace = json.loads(zfp.read(ERROR_TRACE_FILE).decode('utf8'))
        except Exception as e:
            logger.exception(e)
            self.fail('wrong_format', detail='file does not exist or it is wrong json')
        archive.seek(0)
        if not isinstance(error_trace, dict):
            self.fail('wrong_format', detail='error trace is not a dictionary')
        if 'trace' not in error_trace:
            self.fail('wrong_format', detail='error trace does not have "trace"')
        if not isinstance(error_trace.get('files'), list):
            self.fail('wrong_format', detail='error trace does not have files or it is not a list')
        self.__check_node(error_trace['trace'])
        if error_trace['trace']['type'] != 'thread':
            self.fail('wrong_format', detail='root error trace node type should be a "thread"')
        return archive

    def validate(self, value):
        value = super(ReportUnsafeSerializer, self).validate(value)
        value['trace_id'] = uuid.uuid4()
        return value

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
            logger.exception(exc)
            err_detail = 'Unknown error: {}'.format(exc)
        try:
            FinishJobDecision(self.job, JOB_STATUS[5][0], self.__collapse_detail(err_detail))
        except Exception as e:
            logger.exception(e)
            err_detail = 'Error while finishing job decision with error'
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

    def __upload(self, data):
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

    def __get_report(self, identifier):
        if not identifier:
            raise exceptions.ValidationError(detail={'identifier': "Required"})
        try:
            return ReportComponent.objects.get(root=self.root, identifier=identifier)
        except ReportComponent.DoesNotExist:
            raise exceptions.ValidationError(detail={'identifier': "The report wasn't found"})

    def __ancestors_for_cache(self, report):
        ancestors_qs = report.get_ancestors()
        if not self._is_fullweight:
            # Update cache just for Core and verification reports as other reports will be deleted
            ancestors_qs = ancestors_qs.filter(Q(parent=None) | Q(reportcomponent__verification=True))
        return list(parent.pk for parent in ancestors_qs)

    def __create_report_component(self, data):
        data['attr_data'] = self.__upload_attrs_files(self.__get_archive(data.get('attr_data')))
        serializer = ReportComponentSerializer(
            data=data, fullweight=self._is_fullweight, reportroot=self.root,
            fields={'identifier', 'parent', 'component', 'attrs', 'data', 'computer', 'log'}
        )
        serializer.is_valid(raise_exception=True)
        report = serializer.save()

        self.__update_root_cache(report.component, started=True)

        if report.parent is None:
            self.__start_decision()

    def __create_verification_report(self, data):
        data['attr_data'] = self.__upload_attrs_files(self.__get_archive(data.get('attr_data')))
        data['log'] = self.__get_archive(data.get('log'))
        save_kwargs = {}

        # Add additional sources if provided
        if 'additional_sources' in data:
            save_kwargs['additional_sources_id'] = self.__upload_additional_sources(data['additional_sources'])

        serializer = ReportVerificationSerializer(data=data, fullweight=self._is_fullweight, reportroot=self.root)
        serializer.is_valid(raise_exception=True)
        report = serializer.save(**save_kwargs)

        # Upload coverage for the report
        if 'coverage' in data:
            self.__save_coverage(report, self.__get_archive(data['coverage']))

        self.__update_root_cache(
            report.component, started=True,
            cpu_time=report.cpu_time, wall_time=report.wall_time, memory=report.memory
        )

    def __upload_coverage(self, data):
        # Uploads global coverage
        report = self.__get_report(data.get('identifier'))
        if report.verification:
            raise exceptions.ValidationError(detail={
                'coverage': "The full coverage can be uploaded only for non-verification reports"
            })

        if not self._is_fullweight:
            # Upload for Core for lightweight jobs
            report = ReportComponent.objects.get(parent=None, root_id=report.root_id)

        if not report.original_sources:
            raise exceptions.ValidationError(detail={
                'coverage': "The coverage can be uploaded only for reports with original sources"
            })

        for cov_id in data['coverage']:
            self.__save_coverage(report, self.__get_archive(data['coverage'][cov_id]), identifier=cov_id)

    def __patch_report_component(self, data):
        report = self.__get_report(data.get('identifier'))
        save_kwargs = {}

        if 'attrs' in data:
            data['attr_data'] = self.__upload_attrs_files(self.__get_archive(data.get('attr_data')))

        if 'additional_sources' in data:
            save_kwargs['additional_sources_id'] = self.__upload_additional_sources(data['additional_sources'])

        serializer = ReportComponentSerializer(
            instance=report, data=data, partial=True,
            reportroot=report.root, fullweight=self._is_fullweight,
            fields={'data', 'attrs', 'original_sources'}
        )
        serializer.is_valid(raise_exception=True)
        report = serializer.save(**save_kwargs)

        if not self._is_fullweight and report.parent and (report.additional_sources or report.original_sources):
            core_report = ReportComponent.objects.get(root=self.root, parent=None)
            if report.original_sources:
                core_report.original_sources = report.original_sources
            if report.additional_sources:
                core_report.additional_sources = report.additional_sources
            core_report.save()

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

        self.__update_root_cache(
            report.component, finished=True,
            cpu_time=report.cpu_time, wall_time=report.wall_time, memory=report.memory
        )

        # Get report ancestors before report might be deleted
        if report.parent and not self._is_fullweight:
            # WARNING: If report has children it will be deleted!
            # It means verification reports (children) are not finished yet.
            report.delete()

    def __finish_verification_report(self, data):
        report = self.__get_report(data.get('identifier'))
        if not report.verification:
            raise exceptions.ValidationError(detail={'identifier': "The report is not verification"})

        if not self._is_fullweight:
            if report.is_leaf_node():
                # Remove verification report if it doesn't have children for lightweight jobs
                # But before update root caches
                self.__update_root_cache(report.component, finished=True)
                report.delete()
                return
            # Set parent to Core for lightweight jobs that will be preserved
            report.parent = ReportComponent.objects.get(root=self.root, parent=None)

        # Save report with new data
        report.finish_date = now()
        report.save()

        self.__update_root_cache(report.component, finished=True)

    def __create_report_unknown(self, data):
        data['attr_data'] = self.__upload_attrs_files(self.__get_archive(data.get('attr_data')))
        data['problem_description'] = self.__get_archive(data['problem_description'])
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
            ReportComponentLeaf(report_id=parent_id, content_object=report) for parent_id in ancestors_ids
        ))

        # Connect report with marks
        ConnectUnknownReport(report)

    def __create_report_safe(self, data):
        data['attr_data'] = self.__upload_attrs_files(self.__get_archive(data.get('attr_data')))
        serializer = ReportSafeSerializer(data=data, reportroot=self.root)
        serializer.is_valid(raise_exception=True)
        report = serializer.save()

        # Caching leaves for each tree branch node
        ReportComponentLeaf.objects.bulk_create(list(
            ReportComponentLeaf(report_id=parent_id, content_object=report)
            for parent_id in self.__ancestors_for_cache(report)
        ))

        # Connect report with marks
        ConnectSafeReport(report)

    def __create_report_unsafe(self, data):
        data['attr_data'] = self.__upload_attrs_files(self.__get_archive(data.get('attr_data')))
        data['error_trace'] = self.__get_archive(data.get('error_trace'))
        serializer = ReportUnsafeSerializer(data=data, reportroot=self.root)
        serializer.is_valid(raise_exception=True)
        report = serializer.save()

        # Caching leaves for each tree branch node
        ReportComponentLeaf.objects.bulk_create(list(
            ReportComponentLeaf(report_id=parent_id, content_object=report)
            for parent_id in self.__ancestors_for_cache(report)
        ))

        # Connect new unsafe with marks
        connect_unsafe_report.delay(report.id)

    def __upload_additional_sources(self, arch_name):
        add_src = AdditionalSources(root=self.root)
        add_src.add_archive(self.__get_archive(arch_name), save=True)
        return add_src.id

    def __save_coverage(self, report, archive, identifier=''):
        carch = CoverageArchive(
            report=report, identifier=identifier,
            name=self.__get_coverage_name(report)
        )
        carch.add_coverage(archive, save=True)
        try:
            res = FillCoverageStatistics(carch)
        except Exception as e:
            logger.exception(e)
            carch.delete()
            raise exceptions.ValidationError({
                'coverage': 'Error while parsing coverage statistics: {}'.format(e)
            })
        # Save again after statistics is calculated
        carch.total = res.total_coverage
        carch.has_extra = res.has_extra
        carch.save()

    def __update_root_cache(self, component, **kwargs):
        # Update resources cache
        self.root.resources.setdefault(component, {'cpu_time': 0, 'wall_time': 0, 'memory': 0})
        self.root.resources.setdefault('total', {'cpu_time': 0, 'wall_time': 0, 'memory': 0})
        if kwargs.get('cpu_time'):
            self.root.resources[component]['cpu_time'] += kwargs['cpu_time']
            self.root.resources['total']['cpu_time'] += kwargs['cpu_time']
        if kwargs.get('wall_time'):
            self.root.resources[component]['wall_time'] += kwargs['wall_time']
            self.root.resources['total']['wall_time'] += kwargs['wall_time']
        if kwargs.get('memory'):
            self.root.resources[component]['memory'] = max(kwargs['memory'], self.root.resources[component]['memory'])
            self.root.resources['total']['memory'] = max(kwargs['memory'], self.root.resources['total']['memory'])

        # Update instances cache
        self.root.instances.setdefault(component, {'finished': 0, 'total': 0})
        if kwargs.get('started'):
            self.root.instances[component]['total'] += 1
        if kwargs.get('finished'):
            self.root.instances[component]['finished'] += 1

        # Save
        self.root.save()

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

    def __get_coverage_name(self, report):
        if report.verification:
            return '-'
        attr = ReportAttr.objects.filter(report=report, name=NAME_ATTR).only('value').first()
        return attr.value if attr else '...'


def collapse_reports(job):
    if job.weight == JOB_WEIGHT[1][0]:
        # The job is already lightweight
        return
    root = job.reportroot
    if ReportComponent.objects.filter(root=root, component=SUBJOB_NAME).exists():
        return
    core = ReportComponent.objects.get(root=root, parent=None)
    ReportComponent.objects.filter(root=root, verification=True).update(parent=core)
    ReportUnknown.objects.filter(root=root, parent__reportcomponent__verification=False).update(parent=core)

    # Non-verification reports except Core
    reports_qs = ReportComponent.objects.filter(root=root).exclude(Q(verification=True) | Q(parent=None))

    # Update core original and additional sources
    report_with_original = reports_qs.exclude(original_sources=None).first()
    if report_with_original:
        core.original_sources = report_with_original.original_sources
    report_with_additional = reports_qs.exclude(additional_sources=None).first()
    if report_with_additional:
        core.additional_sources = report_with_additional.additional_sources
    core.save()

    # Move coverage to core
    CoverageArchive.objects.filter(report__root=root, report__verification=False).update(report=core)

    # Remove all non-verification reports except Core
    reports_qs.delete()

    job.weight = JOB_WEIGHT[1][0]
    job.save()
