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

from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from bridge.access import DataViewPermission

from users.models import DataView, PreferableView
from users.serializers import DataViewSerializer


class DataViewAPIViewSet(ModelViewSet):
    permission_classes = (DataViewPermission,)
    serializer_class = DataViewSerializer
    lookup_url_kwarg = 'type'

    def get_serializer(self, *args, **kwargs):
        if self.request.method == 'GET':
            fields = self.request.query_params.getlist('fields')
        elif self.request.method == 'POST':
            fields = {'shared', 'name', 'view', 'type'}
        else:
            fields = {'shared', 'view'}
        return super().get_serializer(*args, fields=fields, **kwargs)

    def get_queryset(self):
        return DataView.objects.filter(author=self.request.user)


class PreferViewAPIView(APIView):
    def delete(self, request, view_type):
        PreferableView.objects.filter(view__type=view_type, user=request.user).delete()
        return Response({})

    def post(self, request, view_id):
        view = get_object_or_404(DataView, id=view_id, author=request.user)
        PreferableView.objects.filter(view__type=view.type, user=request.user).delete()
        PreferableView.objects.create(view=view, user=request.user)
        return Response({})
