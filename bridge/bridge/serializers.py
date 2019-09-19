import datetime
import pytz

from django.core.exceptions import PermissionDenied
from django.http.response import Http404
from django.utils.translation import ugettext_lazy as _

from rest_framework import fields, serializers, exceptions
from rest_framework.views import exception_handler
from rest_framework.renderers import JSONRenderer

from bridge.vars import UNKNOWN_ERROR
from bridge.utils import BridgeException, logger


def bridge_exception_handler(exc, context):
    # Switch from PDFRenderer to JSONRenderer for exceptions
    context['request'].accepted_renderer = JSONRenderer()

    if isinstance(exc, BridgeException):
        exc = exceptions.APIException(str(exc))
    if not isinstance(exc, (Http404, PermissionDenied, exceptions.APIException)):
        logger.exception(exc)
        # Always return API exception for DRF requests
        exc = exceptions.APIException(str(UNKNOWN_ERROR))
    return exception_handler(exc, context)


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
