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

import re
import json

from django.utils.translation import ugettext_lazy as _

from rest_framework import fields, serializers, exceptions

from bridge.vars import MPTT_FIELDS, UNSAFE_VERDICTS, CONVERT_FUNCTIONS, COMPARE_FUNCTIONS
from bridge.utils import logger
from bridge.serializers import DynamicFieldsModelSerializer

from marks.models import (
    MAX_TAG_LEN, SafeTag, MarkSafe, MarkSafeHistory, MarkSafeAttr, MarkSafeTag,
    UnsafeTag, MarkUnsafe, MarkUnsafeHistory, MarkUnsafeAttr, MarkUnsafeTag,
    ConvertedTrace, MarkUnknown, MarkUnknownHistory, MarkUnknownAttr
)
from marks.UnsafeUtils import save_converted_trace


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
            mark.cache_tags = list(SafeTag.objects.filter(id__in=tags).order_by('name').values_list('name', flat=True))
            mark.cache_attrs = dict((attr['name'], attr['value']) for attr in attrs if attr['is_compare'])
            mark.save()
    elif isinstance(mark, MarkUnsafe):
        if 'error_trace' not in kwargs:
            # Use old error trace if it wasn't provided (inline mark form)
            kwargs['error_trace_id'] = mark.error_trace_id
        mark_version = MarkUnsafeHistory.objects.create(mark=mark, **kwargs)
        MarkUnsafeTag.objects.bulk_create(list(MarkUnsafeTag(tag_id=t, mark_version=mark_version) for t in tags))
        MarkUnsafeAttr.objects.bulk_create(list(MarkUnsafeAttr(mark_version=mark_version, **attr) for attr in attrs))

        if cache:
            mark.error_trace = mark_version.error_trace
            mark.cache_tags = list(UnsafeTag.objects.filter(id__in=tags).order_by('name')
                                   .values_list('name', flat=True))
            mark.cache_attrs = dict((attr['name'], attr['value']) for attr in attrs if attr['is_compare'])
            mark.save()
    elif isinstance(mark, MarkUnknown):
        mark_version = MarkUnknownHistory.objects.create(mark=mark, **kwargs)
        MarkUnknownAttr.objects.bulk_create(list(MarkUnknownAttr(mark_version=mark_version, **attr) for attr in attrs))

        if cache:
            mark.cache_attrs = dict((attr['name'], attr['value']) for attr in attrs if attr['is_compare'])
            mark.save()
    return mark_version


class SafeTagSerializer(serializers.ModelSerializer):
    def to_representation(self, instance):
        data = super().to_representation(instance)
        if isinstance(instance, SafeTag):
            if data['parent'] is None:
                data['parent'] = 0

            unavailable = set(instance.get_descendants(include_self=True).values_list('id', flat=True))
            data['parents'] = [{'id': 0, 'name': str(_('Root'))}]
            for t in SafeTag.objects.order_by('name'):
                if t.id not in unavailable:
                    data['parents'].append({'id': t.id, 'name': t.name})
        return data

    class Meta:
        model = SafeTag
        exclude = MPTT_FIELDS


class UnsafeTagSerializer(serializers.ModelSerializer):
    def to_representation(self, instance):
        data = super().to_representation(instance)
        if isinstance(instance, UnsafeTag):
            if data['parent'] is None:
                data['parent'] = 0

            unavailable = set(instance.get_descendants(include_self=True).values_list('id', flat=True))
            data['parents'] = [{'id': 0, 'name': str(_('Root'))}]
            for t in UnsafeTag.objects.order_by('name'):
                if t.id not in unavailable:
                    data['parents'].append({'id': t.id, 'name': t.name})
        return data

    class Meta:
        model = UnsafeTag
        exclude = MPTT_FIELDS


class WithTagsMixin:
    def get_tags_ids(self, tags, tags_qs):
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
        if 'tags_tree' in context:
            tags_tree = context['tags_tree']
        else:
            tags_tree = dict((t.id, t.parent_id) for t in tags_qs)
        if 'tags_names' in context:
            tags_names = context['tags_names']
        else:
            tags_names = dict((t.name, t.id) for t in tags_qs)

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
    tags = fields.ListField(child=fields.CharField(max_length=MAX_TAG_LEN), allow_empty=True, write_only=True)
    attrs = fields.ListField(child=SafeMarkAttrSerializer(), allow_empty=True, write_only=True)

    def validate_tags(self, tags):
        return self.get_tags_ids(tags, SafeTag.objects.all())

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
    tags = fields.ListField(child=fields.CharField(max_length=MAX_TAG_LEN), allow_empty=True, write_only=True)
    attrs = fields.ListField(child=UnsafeMarkAttrSerializer(), allow_empty=True, write_only=True)
    error_trace = fields.CharField(write_only=True, required=False)
    threshold = fields.IntegerField(min_value=0, max_value=100, write_only=True, default=0)

    def validate_tags(self, tags):
        return self.get_tags_ids(tags, UnsafeTag.objects.all())

    def validate_threshold(self, value):
        return value / 100

    def __validate_error_trace(self, err_trace_str, compare_func):
        convert_func = COMPARE_FUNCTIONS[compare_func]['convert']
        assert convert_func in CONVERT_FUNCTIONS
        forests = json.loads(err_trace_str)
        return save_converted_trace(forests, convert_func)

    def validate(self, attrs):
        res = super().validate(attrs)
        if 'error_trace' in res:
            try:
                res['error_trace'] = self.__validate_error_trace(res.pop('error_trace'), res['function'])
            except Exception as e:
                logger.exception(e)
                raise exceptions.ValidationError(detail={
                    'error_trace': _('Wrong error trace json provided')
                })
        if res['verdict'] != UNSAFE_VERDICTS[1][0]:
            res['status'] = None
        elif not res.get('status'):
            raise exceptions.ValidationError(detail={'status': _('Wrong status value')})
        return res

    def get_value(self, dictionary):
        return dictionary

    def create(self, validated_data):
        if 'mark' not in validated_data:
            raise exceptions.ValidationError(detail={'mark': 'Required'})
        if 'error_trace' not in validated_data:
            raise exceptions.ValidationError(detail={'error_trace': 'Required'})
        return create_mark_version(validated_data.pop('mark'), **validated_data)

    def update(self, instance, validated_data):
        raise RuntimeError('Update of mark version object is not allowed')

    def to_representation(self, instance):
        res = super().to_representation(instance)
        if isinstance(instance, MarkUnsafeHistory):
            conv = ConvertedTrace.objects.get(id=instance.error_trace_id)
            with conv.file.file as fp:
                res['error_trace'] = json.loads(fp.read().decode('utf-8'))
            res['attrs'] = UnsafeMarkAttrSerializer(instance=instance.attrs.order_by('id'), many=True).data
            res['tags'] = list(instance.tags.values_list('tag__name', flat=True))
            res['threshold'] = instance.threshold_percentage
        return res

    class Meta:
        model = MarkUnsafeHistory
        fields = (
            'change_date', 'comment', 'description', 'verdict', 'status',
            'tags', 'attrs', 'function', 'error_trace', 'threshold'
        )


class UnsafeMarkSerializer(DynamicFieldsModelSerializer):
    mark_version = UnsafeMarkVersionSerializer(write_only=True)
    threshold = fields.IntegerField(min_value=0, max_value=100, write_only=True, default=0)

    def validate_threshold(self, value):
        return value / 100

    def create(self, validated_data):
        # Save kwargs:
        # identifier - preset
        # job - GUI creation
        # author - upload and preset
        # error_trace - GUI creation (ConvertedTrace instance)

        version_data = validated_data.pop('mark_version')

        if 'error_trace' in validated_data:
            # ConvertedTrace instance from save kwargs, used on GUI creation (on report base)
            version_data['error_trace'] = validated_data['error_trace']
        elif 'error_trace' in version_data:
            # ConvertedTrace object from version serializer, used in population and upload
            validated_data['error_trace'] = version_data['error_trace']
        else:
            raise exceptions.ValidationError(detail={'error_trace': 'Required'})

        # Get user from context (on GUI creation)
        if 'request' in self.context:
            validated_data['author'] = self.context['request'].user

        validated_data['status'] = version_data['status']

        instance = super().create(validated_data)
        create_mark_version(instance, **version_data)
        return instance

    def update(self, instance, validated_data):
        assert isinstance(instance, MarkUnsafe)
        version_data = validated_data.pop('mark_version')
        if 'request' in self.context:
            version_data['author'] = self.context['request'].user
        validated_data['version'] = instance.version + 1
        validated_data['status'] = version_data['status']

        instance = super().update(instance, validated_data)
        create_mark_version(instance, **version_data)
        return instance

    def to_representation(self, instance):
        value = super().to_representation(instance)
        if isinstance(instance, MarkUnsafe):
            last_version = MarkUnsafeHistory.objects.get(mark=instance, version=instance.version)
            value['mark_version'] = UnsafeMarkVersionSerializer(instance=last_version).data
            value['threshold'] = instance.threshold_percentage
        return value

    class Meta:
        model = MarkUnsafe
        fields = (
            'id', 'identifier', 'is_modifiable', 'verdict',
            'status', 'mark_version', 'function', 'threshold'
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
