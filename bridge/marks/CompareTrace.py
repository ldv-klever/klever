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
from bridge.utils import BridgeException
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

DEFAULT_COMPARE = 'call_forests_compare'


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

    def default_compare(self):
        """
Default comparison function.
Always returns 1.
        """
        return 1

    def callstack_compare(self):
        """
If call stacks are identical returns 1 else returns 0.
        """

        err_trace_converted = self.__get_converted_trace('call_stack')
        pattern = self.pattern_error_trace
        return int(err_trace_converted == pattern)

    def callstack_tree_compare(self):
        """
If call stacks trees are identical returns 1 else returns 0.
        """

        err_trace_converted = self.__get_converted_trace('call_stack_tree')
        pattern = self.pattern_error_trace
        return int(err_trace_converted == pattern)

    def call_forests_compare(self):
        """
Returns the number of similar forests divided by the maximum number of forests in 2 error traces.
        """
        converted_et = self.__get_converted_trace('call_forests')
        pattern = self.pattern_error_trace
        if any(not isinstance(x, str) for x in converted_et):
            converted_et = list(json.dumps(x) for x in converted_et)
        if any(not isinstance(x, str) for x in pattern):
            pattern = list(json.dumps(x) for x in pattern)
        err_trace_converted = set(converted_et)
        pattern = set(pattern)
        max_len = max(len(err_trace_converted), len(pattern))
        if max_len == 0:
            return 1
        return len(err_trace_converted & pattern) / max_len

    def forests_callbacks_compare(self):
        """
Returns the number of similar forests with callbacks calls divided by the maximum number of forests in 2 error traces.
        """
        converted_et = self.__get_converted_trace('forests_callbacks')
        pattern = self.pattern_error_trace
        if any(not isinstance(x, str) for x in converted_et):
            converted_et = list(json.dumps(x) for x in converted_et)
        if any(not isinstance(x, str) for x in pattern):
            pattern = list(json.dumps(x) for x in pattern)
        err_trace_converted = set(converted_et)
        pattern = set(pattern)
        max_len = max(len(err_trace_converted), len(pattern))
        if max_len == 0:
            return 1
        return len(err_trace_converted & pattern) / max_len

    def __get_converted_trace(self, conversion_function_name):
        return GetConvertedErrorTrace(
            MarkUnsafeConvert.objects.get(name=conversion_function_name), self.unsafe
        ).parsed_trace()
