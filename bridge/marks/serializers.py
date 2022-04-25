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

import re
import json

from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _

from rest_framework import fields, serializers, exceptions

from bridge.vars import MPTT_FIELDS, UNSAFE_VERDICTS, COMPARE_FUNCTIONS
from bridge.utils import logger
from bridge.serializers import DynamicFieldsModelSerializer

from marks.models import (
    MAX_TAG_LEN, Tag, MarkSafe, MarkSafeHistory, MarkSafeAttr, MarkSafeTag,
    MarkUnsafe, MarkUnsafeHistory, MarkUnsafeAttr, MarkUnsafeTag, ConvertedTrace, UnsafeConvertionCache,
    MarkUnknown, MarkUnknownHistory, MarkUnknownAttr, MarkUnsafeReport
)
from marks.tags import get_all_tags
from marks.UnsafeUtils import ErrorTraceConverter


def create_mark_version(mark, cache=True, **kwargs):
    """
    Creates mark version (MarkSafeHistory, MarkUnsafeHistory, MarkUnknownHistory) without any checks.
    :param mark: MarkSafe, MarkUnsafe, MarkUnknown instance
    :param cache: is caching needed?
    :param kwargs: mark version fields
    :return:
    """
    kwargs.setdefault('version', mark.version)
    kwargs.setdefault('author', mark.author)

    attrs = kwargs.pop('attrs')
    tags = kwargs.pop('tags', [])

    mark_version = None

    if isinstance(mark, MarkSafe):
        mark_version = MarkSafeHistory.objects.create(mark=mark, **kwargs)
        MarkSafeTag.objects.bulk_create(list(MarkSafeTag(tag_id=t, mark_version=mark_version) for t in tags))
        MarkSafeAttr.objects.bulk_create(list(MarkSafeAttr(mark_version=mark_version, **attr) for attr in attrs))

        if cache:
            mark.cache_tags = list(Tag.objects.filter(id__in=tags).order_by('name').values_list('name', flat=True))
            mark.cache_attrs = dict((attr['name'], attr['value']) for attr in attrs if attr['is_compare'])
            mark.save()
    elif isinstance(mark, MarkUnsafe):
        mark_version = MarkUnsafeHistory.objects.create(mark=mark, **kwargs)
        MarkUnsafeTag.objects.bulk_create(list(MarkUnsafeTag(tag_id=t, mark_version=mark_version) for t in tags))
        MarkUnsafeAttr.objects.bulk_create(list(MarkUnsafeAttr(mark_version=mark_version, **attr) for attr in attrs))

        if cache:
            mark.cache_tags = list(Tag.objects.filter(id__in=tags).order_by('name').values_list('name', flat=True))
            mark.cache_attrs = dict((attr['name'], attr['value']) for attr in attrs if attr['is_compare'])
            mark.save()
    elif isinstance(mark, MarkUnknown):
        mark_version = MarkUnknownHistory.objects.create(mark=mark, **kwargs)
        MarkUnknownAttr.objects.bulk_create(list(MarkUnknownAttr(mark_version=mark_version, **attr) for attr in attrs))

        if cache:
            mark.cache_attrs = dict((attr['name'], attr['value']) for attr in attrs if attr['is_compare'])
            mark.save()
    return mark_version


class TagSerializer(DynamicFieldsModelSerializer):
    default_error_messages = {
        'parent_required': 'Tag serializer parent field is required to validate short name',
        'name_unique': _('Tag name is not unique in the current branch level'),
        'name_invalid': _("Tag name can't contain ' - '")
    }
    shortname = fields.CharField(max_length=MAX_TAG_LEN)
    parents = serializers.SerializerMethodField()

    def get_parents(self, obj):
        unavailable = set(obj.get_descendants(include_self=True).values_list('id', flat=True))
        parents = [{'id': 0, 'name': str(_('Root'))}]
        for t in Tag.objects.order_by('name'):
            if t.id not in unavailable:
                parents.append({'id': t.id, 'name': t.name})
        return parents

    def __validate_shortname(self, value, parent):
        if value.__contains__(" - "):
            self.fail('name_invalid')
        if parent is not None:
            value = '{} - {}'.format(parent.name, value)

        qs_filter = Q(name=value)
        if self.instance:
            qs_filter &= ~Q(id=self.instance.id)
        if Tag.objects.filter(qs_filter).count():
            self.fail('name_unique')
        return value

    def validate(self, attrs):
        if 'shortname' in attrs:
            if 'parent' not in attrs:
                self.fail('parent_required')
            attrs['name'] = self.__validate_shortname(attrs.pop('shortname'), attrs['parent'])
        return attrs

    class Meta:
        model = Tag
        exclude = MPTT_FIELDS


class WithTagsMixin:
    def get_tags_ids(self, tags):
        if not hasattr(self, 'Meta'):
            raise RuntimeError('Incorrect mixin usage')

        if not tags:
            # Empty list
            return tags
        try:
            tags = list(int(t) for t in tags)
        except ValueError:
            pass

        context = getattr(self, 'context')
        if 'tags_tree' not in context or 'tags_names' not in context:
            tags_tree, tags_names = get_all_tags()
        else:
            tags_tree = context['tags_tree']
            tags_names = context['tags_names']

        # Collect tags with all ascendants
        mark_tags = set()
        for t_name in tags:
            if isinstance(t_name, int):
                parent = t_name
            elif t_name in tags_names:
                parent = tags_names[t_name]
            else:
                raise exceptions.ValidationError(_('One of tags was not found'))
            while parent:
                if parent in mark_tags:
                    break
                mark_tags.add(parent)
                parent = tags_tree[parent]
        return list(mark_tags)


class SafeMarkAttrSerializer(serializers.ModelSerializer):
    class Meta:
        model = MarkSafeAttr
        exclude = ('mark_version',)


class UnsafeMarkAttrSerializer(serializers.ModelSerializer):
    class Meta:
        model = MarkUnsafeAttr
        exclude = ('mark_version',)


class UnknownMarkAttrSerializer(serializers.ModelSerializer):
    class Meta:
        model = MarkUnknownAttr
        exclude = ('mark_version',)


class SafeMarkVersionSerializer(WithTagsMixin, serializers.ModelSerializer):
    tags = fields.ListField(child=fields.CharField(), allow_empty=True, write_only=True)
    attrs = fields.ListField(child=SafeMarkAttrSerializer(), allow_empty=True, write_only=True)

    def validate_tags(self, tags):
        return self.get_tags_ids(tags)

    def get_value(self, dictionary):
        return dictionary

    def create(self, validated_data):
        if 'mark' not in validated_data:
            raise exceptions.ValidationError(detail={'mark': 'Required'})
        return create_mark_version(validated_data.pop('mark'), **validated_data)

    def update(self, instance, validated_data):
        raise RuntimeError('Update of mark version object is not allowed')

    def to_representation(self, instance):
        value = super().to_representation(instance)
        if isinstance(instance, MarkSafeHistory):
            value['attrs'] = SafeMarkAttrSerializer(instance=instance.attrs.order_by('id'), many=True).data
            value['tags'] = list(instance.tags.values_list('tag__name', flat=True))
        return value

    class Meta:
        model = MarkSafeHistory
        fields = ('change_date', 'comment', 'description', 'verdict', 'tags', 'attrs')


class SafeMarkSerializer(DynamicFieldsModelSerializer):
    mark_version = SafeMarkVersionSerializer(write_only=True)

    def create(self, validated_data):
        # Save kwargs:
        # identifier - preset
        # job - GUI creation
        # author - upload and preset

        version_data = validated_data.pop('mark_version')

        # Get user from context (on GUI creation)
        if 'request' in self.context:
            validated_data['author'] = self.context['request'].user

        instance = super().create(validated_data)
        create_mark_version(instance, **version_data)
        return instance

    def update(self, instance, validated_data):
        assert isinstance(instance, MarkSafe)
        version_data = validated_data.pop('mark_version')
        if 'request' in self.context:
            version_data['author'] = self.context['request'].user
        validated_data['version'] = instance.version + 1

        instance = super().update(instance, validated_data)
        create_mark_version(instance, **version_data)
        return instance

    def to_representation(self, instance):
        value = super().to_representation(instance)
        if isinstance(instance, MarkSafe):
            last_version = MarkSafeHistory.objects.get(mark=instance, version=instance.version)
            value['mark_version'] = SafeMarkVersionSerializer(instance=last_version).data
        return value

    class Meta:
        model = MarkSafe
        fields = ('identifier', 'is_modifiable', 'verdict', 'mark_version')


class UnsafeMarkVersionSerializer(WithTagsMixin, serializers.ModelSerializer):
    default_error_messages = {
        'wrong_regexp': _('Regular expression is wrong.')
    }

    tags = fields.ListField(child=fields.CharField(), allow_empty=True, write_only=True)
    attrs = fields.ListField(child=UnsafeMarkAttrSerializer(), allow_empty=True, write_only=True)
    threshold = fields.IntegerField(min_value=0, max_value=100, write_only=True, default=0)
    regexp = fields.CharField(required=False)

    def validate_tags(self, tags):
        return self.get_tags_ids(tags)

    def validate_threshold(self, value):
        return value / 100

    def validate_regexp(self, value):
        try:
            re.compile(value)
        except Exception as e:
            logger.error(e)
            self.fail('wrong_regexp')
        return value

    def validate(self, attrs):
        res = super().validate(attrs)
        if res['verdict'] != UNSAFE_VERDICTS[1][0]:
            res['status'] = None
        elif not res.get('status'):
            raise exceptions.ValidationError(detail={'status': _('Wrong status value')})
        return res

    def get_value(self, dictionary):
        return dictionary

    def create(self, validated_data):
        raise RuntimeError('Use create_mark_version() instead')

    def update(self, instance, validated_data):
        raise RuntimeError('Update of mark version object is not allowed')

    def to_representation(self, instance):
        res = super().to_representation(instance)
        if isinstance(instance, MarkUnsafeHistory):
            res['tags'] = list(instance.tags.values_list('tag__name', flat=True))
            res['attrs'] = UnsafeMarkAttrSerializer(instance=instance.attrs.order_by('id'), many=True).data
            res['threshold'] = instance.threshold_percentage
        return res

    class Meta:
        model = MarkUnsafeHistory
        fields = ('change_date', 'comment', 'description', 'verdict', 'status', 'tags', 'attrs', 'regexp', 'threshold')


class UnsafeMarkSerializer(DynamicFieldsModelSerializer):
    default_error_messages = {
        'error_trace_for_raw_trace': _('Error trace was provided for mark with raw error trace extraction.')
    }

    mark_version = UnsafeMarkVersionSerializer(write_only=True)
    threshold = fields.IntegerField(min_value=0, max_value=100, write_only=True, default=0)
    regexp = fields.CharField(required=False)
    error_trace = fields.CharField(write_only=True, required=False, allow_null=True)

    def validate_threshold(self, value):
        return value / 100

    def validate(self, attrs):
        res = super().validate(attrs)

        error_trace = res.pop('error_trace', None)
        if self.instance:
            convert_func = COMPARE_FUNCTIONS[self.instance.function]['convert']
        else:
            convert_func = COMPARE_FUNCTIONS[res['function']]['convert']

        if error_trace is not None:
            if convert_func == 'raw_text_extraction':
                self.fail('error_trace_for_raw_trace')
            try:
                forests = json.loads(error_trace)
                res['error_trace'] = ErrorTraceConverter(convert_func).save_forests(forests)
            except Exception as e:
                logger.exception(e)
                raise exceptions.ValidationError(detail={
                    'error_trace': _('Wrong error trace is provided')
                })
        elif convert_func == 'raw_text_extraction':
            if 'regexp' not in res:
                raise exceptions.ValidationError(detail={'regexp': 'Required'})
            res['error_trace'] = None
        elif self.instance:
            # Error trace is not provided in case of lightweight edit
            res['error_trace'] = self.instance.error_trace

        return res

    def create(self, validated_data):
        # Save kwargs:
        # identifier - preset
        # job - GUI creation
        # author - upload and preset
        # error_trace - GUI creation (ConvertedTrace instance)

        version_data = validated_data.pop('mark_version')

        # ConvertedTrace instance from save kwargs (GUI creation, based on report)
        # or serializer data (population and upload). None for regexp marks.
        if 'error_trace' not in validated_data:
            raise exceptions.ValidationError(detail={'error_trace': 'Required'})
        version_data['error_trace'] = validated_data['error_trace']

        # Get user from context (on GUI creation)
        if 'request' in self.context:
            validated_data['author'] = self.context['request'].user

        validated_data['status'] = version_data['status']
        validated_data['threshold'] = version_data['threshold']

        instance = super().create(validated_data)
        create_mark_version(instance, **version_data)
        return instance

    def update(self, instance, validated_data):
        assert isinstance(instance, MarkUnsafe)
        version_data = validated_data.pop('mark_version')
        version_data['error_trace'] = validated_data['error_trace']
        if 'request' in self.context:
            version_data['author'] = self.context['request'].user
        validated_data['version'] = instance.version + 1
        validated_data['status'] = version_data['status']
        validated_data['threshold'] = version_data['threshold']

        instance = super().update(instance, validated_data)
        create_mark_version(instance, **version_data)
        return instance

    def to_representation(self, instance):
        value = super().to_representation(instance)
        if isinstance(instance, MarkUnsafe):
            if instance.error_trace:
                conv = ConvertedTrace.objects.get(id=instance.error_trace_id)
                with conv.file.file as fp:
                    value['error_trace'] = json.loads(fp.read().decode('utf-8'))

            last_version = MarkUnsafeHistory.objects.get(mark=instance, version=instance.version)
            value['mark_version'] = UnsafeMarkVersionSerializer(instance=last_version).data
            value['threshold'] = instance.threshold_percentage
        return value

    class Meta:
        model = MarkUnsafe
        fields = (
            'id', 'identifier', 'is_modifiable', 'verdict', 'status', 'function',
            'mark_version', 'threshold', 'error_trace', 'regexp'
        )


class UnknownMarkVersionSerializer(serializers.ModelSerializer):
    attrs = fields.ListField(child=UnsafeMarkAttrSerializer(), allow_empty=True, write_only=True)

    def validate(self, attrs):
        res = super().validate(attrs)
        if res.get('is_regexp'):
            try:
                re.search(res['function'], '')
            except Exception as e:
                logger.exception(e)
                raise exceptions.ValidationError(detail={
                    'function': _("The pattern is wrong, please refer to documentation on the standard "
                                  "Python library for processing reqular expressions")
                })
        return res

    def get_value(self, dictionary):
        return dictionary

    def create(self, validated_data):
        if 'mark' not in validated_data:
            raise exceptions.ValidationError(detail={'mark': 'Required'})
        return create_mark_version(validated_data.pop('mark'), **validated_data)

    def update(self, instance, validated_data):
        raise RuntimeError('Update of mark version object is not allowed')

    def to_representation(self, instance):
        res = super().to_representation(instance)
        if isinstance(instance, MarkUnknownHistory):
            res['attrs'] = UnknownMarkAttrSerializer(instance=instance.attrs.order_by('id'), many=True).data
        return res

    class Meta:
        model = MarkUnknownHistory
        fields = (
            'change_date', 'comment', 'description', 'attrs',
            'function', 'is_regexp', 'problem_pattern', 'link'
        )


class UnknownMarkSerializer(DynamicFieldsModelSerializer):
    mark_version = UnknownMarkVersionSerializer(write_only=True)

    def create(self, validated_data):
        # Save kwargs:
        # identifier - preset and upload
        # job - GUI creation
        # component - GUI creation
        # author - upload and preset

        version_data = validated_data.pop('mark_version')

        # Can be raised only on wrong serializer usage on GUI creation
        assert 'component' in validated_data, 'Component is requred'

        # Get user from context (on GUI creation)
        if 'request' in self.context:
            validated_data['author'] = self.context['request'].user

        instance = super().create(validated_data)
        create_mark_version(instance, **version_data)
        return instance

    def update(self, instance, validated_data):
        assert isinstance(instance, MarkUnknown)
        version_data = validated_data.pop('mark_version')
        if 'request' in self.context:
            version_data['author'] = self.context['request'].user
        validated_data['version'] = instance.version + 1

        instance = super().update(instance, validated_data)
        create_mark_version(instance, **version_data)
        return instance

    def to_representation(self, instance):
        value = super().to_representation(instance)
        if isinstance(instance, MarkUnknown):
            last_version = MarkUnknownHistory.objects.get(mark=instance, version=instance.version)
            value['mark_version'] = UnknownMarkVersionSerializer(instance=last_version).data
        return value

    class Meta:
        model = MarkUnknown
        fields = (
            'id', 'identifier', 'component',
            'is_modifiable', 'mark_version',
            'function', 'is_regexp', 'problem_pattern', 'link'
        )


class MVSerializerBase(serializers.ModelSerializer):
    title = serializers.SerializerMethodField()

    def __new__(cls, *args, **kwargs):
        if 'mark' in kwargs:
            mark = kwargs.pop('mark')
            kwargs['many'] = True
            kwargs['instance'] = mark.versions.select_related('mark', 'author').only(
                'version', 'comment', 'mark__version', 'change_date',
                'author__first_name', 'author__last_name', 'author__username'
            ).order_by('-version')
        return super(MVSerializerBase, cls).__new__(cls, *args, **kwargs)

    def get_title(self, instance):
        if instance.mark.version == instance.version:
            return _("Current version")
        title = serializers.DateTimeField(format="%d.%m.%Y %H:%M:%S").to_representation(instance.change_date)
        if instance.author:
            title += ' ({0})'.format(instance.author.get_full_name())
        if instance.comment:
            title += ': {0}'.format(instance.comment)
        return title


class SMVlistSerializerRO(MVSerializerBase):
    class Meta:
        model = MarkSafeHistory
        fields = ('version', 'title')


class UMVlistSerializerRO(MVSerializerBase):
    class Meta:
        model = MarkUnsafeHistory
        fields = ('version', 'title')


class FMVlistSerializerRO(MVSerializerBase):
    class Meta:
        model = MarkUnknownHistory
        fields = ('version', 'title')


class UpdatedPresetUnsafeMarkSerializer(serializers.ModelSerializer):
    attrs = serializers.SerializerMethodField()
    threshold = serializers.SerializerMethodField()
    tags = serializers.SerializerMethodField()
    error_trace = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()

    def get_attrs(self, instance):
        return list(MarkUnsafeAttr.objects.filter(
            is_compare=True, mark_version__mark=instance,
            mark_version__version=F('mark_version__mark__version')
        ).order_by('id').values('name', 'value', 'is_compare'))

    def get_threshold(self, instance):
        return instance.threshold_percentage

    def get_tags(self, instance):
        return list(MarkUnsafeTag.objects.filter(
            mark_version__mark=instance,
            mark_version__version=F('mark_version__mark__version')
        ).values_list('tag__name', flat=True))

    def get_error_trace(self, instance):
        convert_func = COMPARE_FUNCTIONS[instance.function]['convert']
        if convert_func == 'raw_text_extraction':
            return None

        report_id = self.context['request'].query_params.get('report')

        # Get the most relevant mark association
        if report_id:
            mark_report = MarkUnsafeReport.objects.filter(mark=instance, report_id=report_id).first()
        else:
            mark_report = MarkUnsafeReport.objects.filter(mark=instance).order_by('-result').first()
        if not mark_report:
            raise exceptions.APIException("The mark don't have any associations")

        # Trying to get converted report's error trace
        converted = ConvertedTrace.objects.filter(
            unsafeconvertioncache__unsafe=mark_report.report, function=convert_func
        ).first()

        if not converted:
            # If not found, convert error trace and save the convertion cache
            with open(mark_report.report.error_trace.path, mode='r', encoding='utf-8') as fp:
                error_trace = json.load(fp)
            converted = ErrorTraceConverter(convert_func).convert(error_trace)
            UnsafeConvertionCache.objects.create(unsafe_id=mark_report.report_id, converted_id=converted.id)

        with open(converted.file.path, mode='r', encoding='utf-8') as fp:
            # Return converted error trace
            return json.load(fp)

    def get_description(self, instance):
        last_version = MarkUnsafeHistory.objects.only('description').get(mark=instance, mark__version=F('version'))
        return last_version.description

    class Meta:
        model = MarkUnsafe
        fields = (
            'is_modifiable', 'description', 'attrs', 'verdict', 'status',
            'function', 'regexp', 'threshold', 'tags', 'error_trace'
        )
