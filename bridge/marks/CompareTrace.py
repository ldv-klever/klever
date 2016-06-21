import json
from types import MethodType

from reports.etv import error_trace_callstack, ErrorTraceCallstackTree, error_trace_model_functions
from marks.models import MarkUnsafeConvert
from marks.ConvertTrace import GetConvertedErrorTrace

# To create new funciton:
# 1) Add created function to the class CompareTrace;
# 2) Use self.error_trace and self.pattern_error_trace for comparing
# 3) Return the result as float(int) between 0 and 1.
# 4) Add docstring to the created function.
# Do not use 'error_trace', 'pattern_error_trace', 'error'
# and 'result' as function name.

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

        res = GetConvertedErrorTrace(MarkUnsafeConvert.objects.get(name='call_stack'), self.unsafe)
        if res.error is not None:
            raise ValueError(res.error)

        err_trace_converted = res.parsed_trace()
        pattern = self.pattern_error_trace
        if err_trace_converted == pattern:
            return 1
        return int(err_trace_converted[0] == pattern[1] and err_trace_converted[1] == pattern[0])

    def model_functions_compare(self):
        """
If model functions are identical returns 1 else returns 0.
        """
        err_trace1 = error_trace_model_functions(self.error_trace)
        err_trace2 = self.pattern_error_trace
        if err_trace1 == err_trace2:
            return 1
        return 0

    def callstack_tree_compare(self):
        """
If call stacks trees are identical returns 1 else returns 0.
        """
        res = GetConvertedErrorTrace(MarkUnsafeConvert.objects.get(name='call_stack_tree'), self.unsafe)
        if res.error is not None:
            raise ValueError(res.error)

        err_trace_converted = res.parsed_trace()
        pattern = self.pattern_error_trace
        if err_trace_converted == pattern:
            return 1
        return int(err_trace_converted[0] == pattern[1] and err_trace_converted[1] == pattern[0])

