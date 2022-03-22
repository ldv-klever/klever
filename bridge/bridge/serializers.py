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

import datetime
import pytz

from django.core.exceptions import PermissionDenied
from django.http.response import Http404
from django.utils.translation import gettext_lazy as _

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
    default_error_messages = {'invalid': _('Timestamp format is wrong (float number is expected)')}

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
