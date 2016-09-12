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

DEFAULT_COMPARE = 'callstack_tree_compare'


class CompareTrace(object):

    def __init__(self, func_name, pattern_error_trace, unsafe):
        """
        If something failed self.error is not None.
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
            self.error = "Can't parse error trace pattern (it must be JSON serializable): %s" % e
            return

        self.error = None
        self.result = 0.0
        if func_name.startswith('__'):
            self.error = 'Wrong function name'
            return
        try:
            function = getattr(self, func_name)
            if not isinstance(function, MethodType):
                self.error = 'Wrong function name'
                return
        except AttributeError:
            self.error = 'Function was not found'
            return
        try:
            self.result = function()
        except Exception as e:
            self.error = e
            return
        if isinstance(self.result, int):
            self.result = float(self.result)
        if not (isinstance(self.result, float) and 0 <= self.result <= 1):
            self.error = "Compare function reterned incorrect result: %s" % self.result
            self.result = 0.0

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
        if err_trace_converted == pattern:
            return 1
        return int(err_trace_converted[0] == pattern[1] and err_trace_converted[1] == pattern[0])

    def model_functions_compare(self):
        """
If model functions are identical returns 1 else returns 0.
        """

        err_trace_converted = self.__get_converted_trace('model_functions')
        pattern = self.pattern_error_trace
        if err_trace_converted == pattern:
            return 1
        return 0

    def callstack_tree_compare(self):
        """
If call stacks trees are identical returns 1 else returns 0.
        """

        err_trace_converted = self.__get_converted_trace('call_stack_tree')
        pattern = self.pattern_error_trace
        if err_trace_converted == pattern:
            return 1
        return int(err_trace_converted[0] == pattern[1] and err_trace_converted[1] == pattern[0])

    def __get_converted_trace(self, conversion_function_name):
        res = GetConvertedErrorTrace(MarkUnsafeConvert.objects.get(name=conversion_function_name), self.unsafe)
        if res.error is not None:
            raise ValueError(res.error)
        return res.parsed_trace()
