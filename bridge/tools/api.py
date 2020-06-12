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

from rest_framework.views import APIView
from rest_framework.response import Response

from bridge.access import ManagerPermission
from tools.profiling import DBLogsAnalizer
from tools.utils import ParseReportsLogs


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
