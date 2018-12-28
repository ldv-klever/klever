from rest_framework import fields, serializers, exceptions

from bridge.vars import MPTT_FIELDS

from marks.models import MarkUnknown, SafeTag, UnsafeTag


class UnknownMarkSerializer(serializers.ModelSerializer):
    component = fields.CharField(source='component.name')

    class Meta:
        model = MarkUnknown
        fields = ('identifier', 'component', 'function', 'is_regexp', 'status', 'description')


class SafeTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = SafeTag
        exclude = MPTT_FIELDS


class UnsafeTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnsafeTag
        exclude = MPTT_FIELDS
