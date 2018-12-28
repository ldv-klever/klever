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
from types import FunctionType

from django.conf import settings
from django.db.models import Q
from django.utils.translation import ungettext_lazy

from bridge.vars import SCHEDULER_TYPE
from bridge.utils import BridgeException

import marks.SafeUtils as SafeUtils
import marks.UnsafeUtils as UnsafeUtils
import marks.UnknownUtils as UnknownUtils

from marks.models import MarkUnsafeCompare, MarkUnsafeConvert, ErrorTraceConvertionCache
from service.models import Scheduler

from jobs.population import JobsPopulation
from marks.ConvertTrace import ConvertTrace
from marks.CompareTrace import CompareTrace, CONVERSION
from marks.tags import CreateTagsFromFile


class Population:
    def __init__(self, user):
        self._user = user
        self.changes = self.__population()

    def __population(self):
        sch_crtd1 = Scheduler.objects.get_or_create(type=SCHEDULER_TYPE[0][0])[1]
        sch_crtd2 = Scheduler.objects.get_or_create(type=SCHEDULER_TYPE[1][0])[1]

        return {
            'functions': self.__populate_functions(),
            'jobs': JobsPopulation(self._user).populate(),
            'tags': self.__populate_tags(),
            'marks': {
                'unknown': self.__populate_unknown_marks(),
                'safe': self.__populate_safe_marks(),
                'unsafe': self.__populate_unsafe_marks()
            },
            'schedulers': (sch_crtd1 or sch_crtd2)
        }

    def __populate_functions(self):
        functions_changed = False

        conversions = {}
        for func_name in [x for x, y in ConvertTrace.__dict__.items()
                          if type(y) == FunctionType and not x.startswith('_')]:
            description = self.__correct_description(getattr(ConvertTrace, func_name).__doc__)
            func, crtd = MarkUnsafeConvert.objects.get_or_create(name=func_name)
            if crtd or description != func.description:
                functions_changed = True
                func.description = description
                func.save()
            conversions[func_name] = func
        MarkUnsafeConvert.objects.filter(~Q(name__in=list(conversions))).delete()

        comparisons = []
        for func_name in [x for x, y in CompareTrace.__dict__.items()
                          if type(y) == FunctionType and not x.startswith('_')]:
            comparisons.append(func_name)
            description = self.__correct_description(getattr(CompareTrace, func_name).__doc__)

            conversion = CONVERSION.get(func_name, func_name)
            if conversion not in conversions:
                raise BridgeException('Convert function "%s" for comparison "%s" does not exist' %
                                      (conversion, func_name))

            func, crtd = MarkUnsafeCompare.objects.get_or_create(name=func_name, convert=conversions[conversion])
            if crtd or description != func.description:
                functions_changed = True
                func.description = description
                func.save()
        MarkUnsafeCompare.objects.filter(~Q(name__in=comparisons)).delete()
        ErrorTraceConvertionCache.objects.all().delete()
        return functions_changed

    def __correct_description(self, descr):
        descr_strs = descr.split('\n')
        new_descr_strs = []
        for s in descr_strs:
            if len(s) > 0 and len(s.split()) > 0:
                new_descr_strs.append(s)
        return '\n'.join(new_descr_strs)

    def __populate_unknown_marks(self):
        res = UnknownUtils.PopulateMarks(self._user)
        return (res.created, res.total) if res.created else None

    def __populate_safe_marks(self):
        res = SafeUtils.PopulateMarks(self._user)
        new_num = len(res.created)
        return (new_num, res.total) if new_num else None

    def __populate_unsafe_marks(self):
        res = UnsafeUtils.PopulateMarks(self._user)
        new_num = len(res.created)
        return (new_num, res.total) if new_num else None

    def __populate_tags(self):
        created_tags = []
        num_of_new = self.__create_tags('unsafe')
        if num_of_new > 0:
            created_tags.append(ungettext_lazy(
                '%(count)d new unsafe tag uploaded.', '%(count)d new unsafe tags uploaded.', num_of_new
            ) % {'count': num_of_new})
        num_of_new = self.__create_tags('safe')
        if num_of_new > 0:
            created_tags.append(ungettext_lazy(
                '%(count)d new safe tag uploaded.', '%(count)d new safe tags uploaded.', num_of_new
            ) % {'count': num_of_new})
        return created_tags

    def __create_tags(self, tag_type):
        preset_tags = os.path.join(settings.BASE_DIR, 'marks', 'tags_presets', "%s.json" % tag_type)
        if not os.path.isfile(preset_tags):
            return 0
        with open(preset_tags, mode='rb') as fp:
            try:
                res = CreateTagsFromFile(self._user, fp, tag_type, True)
            except Exception as e:
                raise BridgeException("Error while creating tags: %s" % str(e))
            return res.number_of_created
