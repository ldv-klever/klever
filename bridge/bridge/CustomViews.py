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
import mimetypes

from django.http import JsonResponse, StreamingHttpResponse, HttpResponseNotAllowed
from django.utils.translation import ugettext_lazy as _
from django.views.generic.base import View, ContextMixin
from django.views.generic.detail import SingleObjectMixin, SingleObjectTemplateResponseMixin

from rest_framework.views import APIView
from rest_framework.exceptions import APIException

from bridge.vars import UNKNOWN_ERROR, VIEW_TYPES
from bridge.utils import logger, BridgeException

from users.utils import ViewData


class JSONResponseMixin:
    def dispatch(self, request, *args, **kwargs):
        if not hasattr(super(), 'dispatch'):
            # This mixin should be used together with main View based class
            raise BridgeException(response_type='json')

        # TODO
        # if not request.user.is_authenticated:
        #     raise BridgeException(_('You are not signing in'), response_type='json')
        try:
            return getattr(super(), 'dispatch')(request, *args, **kwargs)
        except Exception as e:
            if isinstance(e, BridgeException):
                message = str(e.message)
            else:
                logger.exception(e)
                message = str(UNKNOWN_ERROR)
            raise BridgeException(message=message, response_type='json')


class JsonDetailView(JSONResponseMixin, SingleObjectMixin, View):
    def get(self, *args, **kwargs):
        self.__is_not_used(*args, **kwargs)
        self.object = self.get_object()
        return JsonResponse(self.get_context_data(object=self.object))

    def __is_not_used(self, *args, **kwargs):
        pass


class JsonDetailPostView(JSONResponseMixin, SingleObjectMixin, View):
    def post(self, *args, **kwargs):
        self.__is_not_used(*args, **kwargs)
        self.object = self.get_object()
        return JsonResponse(self.get_context_data(object=self.object))

    def __is_not_used(self, *args, **kwargs):
        pass


class JsonView(JSONResponseMixin, ContextMixin, View):
    def post(self, *args, **kwargs):
        self.__is_not_used(*args, **kwargs)
        return JsonResponse(self.get_context_data())

    def __is_not_used(self, *args, **kwargs):
        pass


class DetailPostView(JSONResponseMixin, SingleObjectTemplateResponseMixin, SingleObjectMixin, View):
    def post(self, *args, **kwargs):
        self.__is_not_used(*args, **kwargs)
        self.object = self.get_object()
        return self.render_to_response(self.get_context_data(object=self.object))

    def __is_not_used(self, *args, **kwargs):
        pass


class StreamingResponseView(View):
    file_name = None
    http_method = 'get'

    def get_generator(self):
        raise NotImplementedError('The method is not implemented')

    def get_filename(self):
        return self.file_name

    def __get_response(self, *args, **kwargs):
        self.__is_not_used(*args, **kwargs)

        try:
            generator = self.get_generator()
        except Exception as e:
            if not isinstance(e, BridgeException):
                logger.exception(e)
                raise BridgeException()
            raise
        if generator is None:
            raise BridgeException()

        file_name = getattr(generator, 'name', None) or self.get_filename()
        if not isinstance(file_name, str) or len(file_name) == 0:
            raise BridgeException()

        file_size = getattr(generator, 'size', None)

        mimetype = mimetypes.guess_type(os.path.basename(file_name))[0]
        response = StreamingHttpResponse(generator, content_type=mimetype)
        if file_size is not None:
            response['Content-Length'] = file_size
        response['Content-Disposition'] = 'attachment; filename="{}"'.format(file_name)
        return response

    def get(self, *args, **kwargs):
        if self.http_method != 'get':
            return HttpResponseNotAllowed(['get'])
        return self.__get_response(*args, **kwargs)

    def post(self, *args, **kwargs):
        if self.http_method != 'post':
            return HttpResponseNotAllowed(['post'])
        return self.__get_response(*args, **kwargs)

    def __is_not_used(self, *args, **kwargs):
        pass


class StreamingResponseAPIView(APIView):
    file_name = None
    http_method = 'get'

    def get_generator(self):
        raise NotImplementedError('The method is not implemented')

    def get_filename(self):
        return self.file_name

    def __get_response(self, *args, **kwargs):
        self.__is_not_used(*args, **kwargs)

        try:
            generator = self.get_generator()
        except Exception as e:
            if isinstance(e, BridgeException):
                raise APIException(str(e))
            logger.exception(e)
            raise APIException()

        if generator is None:
            raise APIException()

        file_name = getattr(generator, 'name', None) or self.get_filename()
        if not isinstance(file_name, str) or len(file_name) == 0:
            raise BridgeException()

        file_size = getattr(generator, 'size', None)

        mimetype = mimetypes.guess_type(os.path.basename(file_name))[0]
        response = StreamingHttpResponse(generator, content_type=mimetype)
        if file_size is not None:
            response['Content-Length'] = file_size
        response['Content-Disposition'] = 'attachment; filename="{}"'.format(file_name)
        return response

    def get(self, *args, **kwargs):
        if self.http_method != 'get':
            return HttpResponseNotAllowed(['get'])
        return self.__get_response(*args, **kwargs)

    def post(self, *args, **kwargs):
        if self.http_method != 'post':
            return HttpResponseNotAllowed(['post'])
        return self.__get_response(*args, **kwargs)

    def __is_not_used(self, *args, **kwargs):
        pass


class DataViewMixin:
    def get_view(self, view_type):
        if not hasattr(self, 'request'):
            raise BridgeException()
        request = getattr(self, 'request')
        if view_type not in VIEW_TYPES:
            raise BridgeException()
        return ViewData(request.user, view_type, request.POST if request.method == 'POST' else request.GET)
