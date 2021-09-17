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

import json
import os

from urllib.parse import unquote

from django.conf import settings

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import APIException

from bridge.access import ManagerPermission
from tools.profiling import DBLogsAnalizer
from tools.utils import ParseReportsLogs
from tools.secret import FixOldCoverage


class CalculateDBLogStatisticsView(APIView):
    permission_classes = (ManagerPermission,)

    def post(self, request):
        analizer = DBLogsAnalizer()
        analizer.analize()
        analizer.print_results()
        return Response({})


class ParseReportsLogsAPIView(APIView):
    def post(self, request):
        res = ParseReportsLogs(request.FILES['log'], request.data.get('decision', None))
        return Response({
            'decision': res.decision_id, 'reports': json.dumps(res.data, ensure_ascii=False)
        })


class ClearLogAPIView(APIView):
    def delete(self, request):
        if not request.query_params.get('name'):
            raise APIException('The name parameter is required')
        file_path = os.path.join(settings.LOGS_DIR, unquote(request.query_params['name']))
        if os.path.isfile(file_path):
            with open(file_path, mode='w', encoding='utf-8') as fp:
                fp.write('')
        return Response({})


class LogContentAPIView(APIView):
    def get(self, request):
        if not request.query_params.get('name'):
            raise APIException('The name parameter is required')
        file_path = os.path.join(settings.LOGS_DIR, unquote(request.query_params['name']))
        if not os.path.isfile(file_path):
            raise APIException('The log was not found')

        position = 0
        reload_log = False
        if request.query_params.get('position'):
            position = int(request.query_params['position'])
        with open(file_path, mode='rb') as fp:
            new_position = fp.seek(0, os.SEEK_END)
            if position > new_position:
                fp.seek(0)
                reload_log = True
            elif position:
                fp.seek(position)
            else:
                fp.seek(0)
            content = fp.read().decode('utf-8')
        return Response({'content': content, 'position': new_position, 'reload': reload_log})


class FixOldCoverageAPIView(APIView):
    permission_classes = (ManagerPermission,)

    def post(self, request):
        fixer = FixOldCoverage()
        fixer.fix_all()
        return Response({'number': fixer.count})
