import datetime
import pytz

from django.utils.translation import ugettext_lazy as _

from rest_framework import fields, serializers


class TimeStampField(fields.Field):
    default_error_messages = {'invalid': _('Timastamp format is wrong. Float expected.')}

    def __init__(self, *args, **kwargs):
        self.timezone = kwargs.pop('timezone', 'UTC')
        super().__init__(*args, **kwargs)

    def to_internal_value(self, value):
        if isinstance(value, datetime.datetime):
            return value
        try:
            return datetime.datetime.fromtimestamp(float(value), pytz.timezone(self.timezone))
        except (ValueError, TypeError):
            self.fail('invalid')

    def to_representation(self, value):
        return value.timestamp() if value else None


class DynamicFieldsModelSerializer(serializers.ModelSerializer):
    def __init__(self, *args, **kwargs):
        serializer_fields = kwargs.pop('fields', None)
        super().__init__(*args, **kwargs)

        if serializer_fields:
            # Drop any fields that are not specified in the `fields`
            for field_name in set(self.fields.keys()) - set(serializer_fields):
                self.fields.pop(field_name)
