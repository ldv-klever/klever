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

from celery import shared_task

from bridge.utils import BridgeException
from reports.models import CoverageArchive
from reports.coverage import FillCoverageStatistics


@shared_task
def fill_coverage_statistics(carch_id):
    carch = CoverageArchive.objects.get(id=carch_id)
    try:
        res = FillCoverageStatistics(carch)
    except Exception as e:
        carch.delete()
        raise BridgeException('Error while parsing coverage statistics: {}'.format(e))
    carch.total = res.total_coverage
    carch.has_extra = res.has_extra
    carch.save()
