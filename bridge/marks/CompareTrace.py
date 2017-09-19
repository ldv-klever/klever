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

import json
from types import MethodType

from django.utils.translation import ugettext_lazy as _

from bridge.utils import BridgeException, logger
from marks.models import MarkUnsafeConvert
from marks.ConvertTrace import GetConvertedErrorTrace

# To create new funciton:
# 1) Add created function to the class CompareTrace (its name shouldn't start with '__');
# 2) Use function self.__get_converted_trace(<fname>) to get converted error trace of unsafe report returns dict or list
#    (depends on convertion function)
# 3) Use self.pattern_error_trace to get pattern error trace (dict or list)
# 4) Return the result as float(int) between 0 and 1.
# 5) Add docstring to the created function.
# Do not use 'pattern_error_trace', 'error' and 'result' as function name.

DEFAULT_COMPARE = 'thread_call_forests'
CONVERSION = {}


class CompareTrace:

    def __init__(self, func_name, pattern_error_trace, unsafe):
        """
        If you want to pass exception message (can be translatable) to user,
        raise BridgeException(message) then.
        In case of success you need just self.result.
        :param func_name: name of the function (str).
        :param pattern_error_trace: pattern error trace of the mark (str).
        :param unsafe: unsafe (ReportUnsafe).
        :return: nothing.
        """

        self.unsafe = unsafe
        try:
            self.pattern_error_trace = json.loads(pattern_error_trace)
        except Exception as e:
            raise BridgeException("Can't parse error trace pattern (it must be JSON serializable): %s" % e)

        self.result = 0.0
        if func_name.startswith('_'):
            raise BridgeException("Function name mustn't start with '_'")
        try:
            func = getattr(self, func_name)
            if not isinstance(func, MethodType):
                raise BridgeException('Wrong function name')
        except AttributeError:
            raise BridgeException('The error trace comparison function does not exist')
        self.result = func()
        if isinstance(self.result, int):
            self.result = float(self.result)
        if not (isinstance(self.result, float) and 0 <= self.result <= 1):
            raise BridgeException("Compare function returned incorrect result: %s" % self.result)

    def callback_call_forests(self):
        """
Jaccard index of "callback_call_forests" convertion.
        """
        converted_et = self.__get_converted_trace('callback_call_forests')
        pattern = self.pattern_error_trace
        if any(not isinstance(x, str) for x in converted_et):
            converted_et = list(json.dumps(x) for x in converted_et)
        if any(not isinstance(x, str) for x in pattern):
            pattern = list(json.dumps(x) for x in pattern)
        return self.__jaccard(set(converted_et), set(pattern))

    def thread_call_forests(self):
        """
Jaccard index of "thread_call_forests" convertion.
        """
        converted_et = self.__get_converted_trace('thread_call_forests')
        pattern = self.pattern_error_trace
        if any(not isinstance(x, str) for x in converted_et):
            converted_et = list(json.dumps(x) for x in converted_et)
        if any(not isinstance(x, str) for x in pattern):
            pattern = list(json.dumps(x) for x in pattern)
        return self.__jaccard(set(converted_et), set(pattern))

    def __jaccard(self, set1, set2):
        self.__is_not_used()
        similar = len(set1 & set2)
        res = len(set1) + len(set2) - similar
        if res == 0:
            return 1
        return similar / res

    def __get_converted_trace(self, conversion_function_name):
        return GetConvertedErrorTrace(
            MarkUnsafeConvert.objects.get(name=conversion_function_name), self.unsafe
        ).parsed_trace()

    def __is_not_used(self):
        pass


class CheckTraceFormat:
    def __init__(self, compare_func, error_trace):
        self._func = compare_func
        self._trace = error_trace
        if self._func in {'callback_call_forests', 'thread_call_forests'}:
            try:
                self.__check_forests()
            except Exception as e:
                logger.exception(e)
                raise BridgeException(_('The converted error trace has wrong format'))

    def __check_calltree(self, calltree):
        if not isinstance(calltree, dict):
            raise BridgeException('One of the error trace call tree items is not a dict: %s' % calltree)
        if len(calltree) != 1:
            raise BridgeException('One of the error trace call tree items has wrong number of keys: %s' % calltree)
        func = next(iter(calltree))
        if not isinstance(func, str):
            raise BridgeException('Function name must be a string: %s' % func)
        if not isinstance(calltree[func], list):
            raise BridgeException('Function "%s" children are not a list: %s' % (func, calltree[func]))
        for child in calltree[func]:
            self.__check_calltree(child)

    def __check_forests(self):
        if not isinstance(self._trace, list):
            raise BridgeException('The error trace is not a list')
        for forest in self._trace:
            if not isinstance(forest, list):
                raise BridgeException('One of the error trace forests is not a list: %s' % forest)
            for calltree in forest:
                if not isinstance(calltree, dict):
                    raise BridgeException('One of the error trace call trees is not a dict: %s' % calltree)
                self.__check_calltree(calltree)
