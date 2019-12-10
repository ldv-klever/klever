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

from django.http import StreamingHttpResponse, HttpResponseNotAllowed
from django.views.generic.base import View

from rest_framework.views import APIView
from rest_framework.exceptions import APIException
from rest_framework.generics import GenericAPIView
from rest_framework.renderers import TemplateHTMLRenderer
from rest_framework.response import Response

from bridge.vars import VIEW_TYPES
from bridge.utils import logger, BridgeException

from users.utils import ViewData


class TemplateAPIRetrieveView(GenericAPIView):
    template_name = None
    renderer_classes = (TemplateHTMLRenderer,)

    def get_context_data(self, instance, **kwargs):
        return {'user': self.request.user, 'object': instance}

    def get(self, request, *args, **kwargs):
        self.__is_not_used(*args, **kwargs)
        assert self.template_name is not None, 'Template was not provided'
        instance = self.get_object()
        context = self.get_context_data(instance)
        return Response(context, template_name=self.template_name)

    def __is_not_used(self, *args, **kwargs):
        pass


class TemplateAPIListView(GenericAPIView):
    template_name = None
    renderer_classes = (TemplateHTMLRenderer,)

    def get_context_data(self, queryset, **kwargs):
        context = {'user': self.request.user, 'object_list': queryset}
        context.update(kwargs)
        return context

    def get(self, request, *args, **kwargs):
        self.__is_not_used(*args, **kwargs)
        assert self.template_name is not None, 'Template was not provided'
        queryset = self.get_queryset()
        context = self.get_context_data(queryset)
        return Response(context, template_name=self.template_name)

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

        generator = self.get_generator()

        if generator is None:
            raise APIException()

        file_name = getattr(generator, 'name', None) or self.get_filename()
        if not isinstance(file_name, str) or len(file_name) == 0:
            raise APIException()

        file_size = getattr(generator, 'size', None)

        mimetype = mimetypes.guess_type(os.path.basename(file_name))[0]
        response = StreamingHttpResponse(generator, content_type=mimetype)
        if file_size:
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
