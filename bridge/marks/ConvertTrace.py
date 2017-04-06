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
from io import BytesIO
from types import MethodType
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import ugettext_lazy as _
from bridge.utils import ArchiveFileContent, logger, file_get_or_create, BridgeException
from reports.etv import error_trace_callstack, ErrorTraceCallstackTree, ErrorTraceForests
from marks.models import ErrorTraceConvertionCache, ConvertedTraces

# To create new funciton:
# 1) Add created function to the class ConvertTrace;
# 2) Use self.error_trace for convertion
# 3) Return the converted trace. This value MUST be json serializable. Dict and list are good choices.
# 5) Add docstring to the created function.
# Do not use 'error_trace', 'pattern_error_trace', 'error' as function name.

DEFAULT_CONVERT = 'call_forests'
ET_FILE_NAME = 'converted-error-trace.json'


class ConvertTrace:

    def __init__(self, function_name, error_trace):
        """
        If something failed self.error is not None.
        In case of success you need just self.patter_error_trace.
        :param function_name: name of the function (str).
        :param error_trace: error trace (str).
        :return: nothing.
        """
        self.error_trace = error_trace
        self.pattern_error_trace = None
        if function_name.startswith('_'):
            raise BridgeException('Wrong function name')
        try:
            func = getattr(self, function_name)
            if not isinstance(func, MethodType):
                raise BridgeException('Wrong function name')
        except AttributeError:
            raise BridgeException(_('Error trace convert function does not exist'))
        self.pattern_error_trace = func()

    def call_stack(self):
        """
This function is extracting the error trace call stack to first warning.
Return list of lists of function names in json format.
        """
        return error_trace_callstack(self.error_trace)

    def call_stack_tree(self):
        """
This function is extracting the error trace call stack tree.
All its leaves are model functions.
Return list of lists of levels of function names in json format.
        """

        return ErrorTraceCallstackTree(self.error_trace).trace

    def call_forests(self):
        """
This function is extracting the error trace call stack "forests".
The forest is a couple of call trees under callback action.
Return list of forests.
        """

        return ErrorTraceForests(self.error_trace, False).trace

    def forests_callbacks(self):
        """
This function is extracting the error trace call stack "forests".
The forest is a couple of call trees under callback action.
Return list of forests. These forests includes callback actions as leaves.
        """

        return ErrorTraceForests(self.error_trace, True).trace


class GetConvertedErrorTrace:
    def __init__(self, func, unsafe):
        self.unsafe = unsafe
        self.function = func
        self._parsed_trace = None
        self.error_trace = self.__get_error_trace()
        self.converted = self.__convert()

    def __get_error_trace(self):
        try:
            return ArchiveFileContent(self.unsafe, self.unsafe.error_trace).content.decode('utf8')
        except Exception as e:
            logger.exception(e, stack_info=True)
            raise BridgeException("Can't exctract error trace for unsafe '%s' from archive" % self.unsafe.pk)

    def __convert(self):
        try:
            return ErrorTraceConvertionCache.objects.get(unsafe=self.unsafe, function=self.function).converted
        except ObjectDoesNotExist:
            self._parsed_trace = ConvertTrace(self.function.name, self.error_trace).pattern_error_trace
            et_file = file_get_or_create(BytesIO(
                json.dumps(self._parsed_trace, ensure_ascii=False, sort_keys=True, indent=4).encode('utf8')
            ), ET_FILE_NAME, ConvertedTraces
            )[0]
            ErrorTraceConvertionCache.objects.create(unsafe=self.unsafe, function=self.function, converted=et_file)
            return et_file

    def parsed_trace(self):
        if self._parsed_trace is not None:
            return self._parsed_trace
        with self.converted.file as fp:
            return json.loads(fp.read().decode('utf8'))
