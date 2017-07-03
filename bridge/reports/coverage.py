#
# Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
# Institute for System Programming of the Russian Academy of Sciences
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
import json
import zipfile
import xml.etree.ElementTree as ETree
from xml.dom import minidom

from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.urlresolvers import reverse
from django.db.models import Q, Count, Case, When
from django.utils.translation import ugettext_lazy as _

from bridge.vars import UNSAFE_VERDICTS, SAFE_VERDICTS, JOB_WEIGHT, VIEW_TYPES
from bridge.tableHead import Header
from bridge.utils import logger, BridgeException
from bridge.ZipGenerator import ZipStream

from reports.models import ReportComponent, Attr, AttrName, ReportAttr, ReportUnsafe, ReportSafe, ReportUnknown,\
    ReportRoot
from marks.models import UnknownProblem, UnsafeReportTag, SafeReportTag

from users.utils import DEF_NUMBER_OF_ELEMENTS, ViewData
from jobs.utils import get_resource_data, get_user_time
from marks.tables import SAFE_COLOR, UNSAFE_COLOR


class GetCoverage:
    def __init__(self, report_id):
        self.type = None
        self.report = self.__get_report(report_id)

    def __get_report(self, report_id):
        try:
            self.type = 'safe'
            return ReportSafe.objects.get(id=report_id)
        except ObjectDoesNotExist:
            try:
                self.type = 'unsafe'
                return ReportUnsafe.objects.get(id=report_id)

            except ObjectDoesNotExist:
                try:
                    self.type = 'unknown'
                    return ReportUnknown.objects.get(id=report_id)
                except ObjectDoesNotExist:
                    raise BridgeException(_('The report was not found'))

    def __get_coverage(self):
        pass
