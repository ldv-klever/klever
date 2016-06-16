import json
from types import MethodType
from reports.etv import error_trace_callstack

# To create new funciton:
# 1) Add created function to the class CompareTrace;
# 2) Use self.error_trace and self.pattern_error_trace for comparing
# 3) Return the result as float(int) between 0 and 1.
# 4) Add docstring to the created function.
# Do not use 'error_trace', 'pattern_error_trace', 'error'
# and 'result' as function name.

DEFAULT_COMPARE = 'callstack_compare'


class CompareTrace(object):

    def __init__(self, function_name, pattern_error_trace, error_trace):
        """
        If something failed self.error is not None.
        In case of success you need just self.result.
        :param function_name: name of the function (str).
        :param pattern_error_trace: pattern error trace of the mark (str).
        :param error_trace: error trace (str).
        :return: nothing.
        """
        self.error_trace = error_trace
        try:
            self.pattern_error_trace = json.loads(pattern_error_trace)
        except Exception as e:
            self.error = "Can't parse error trace pattern (it must be JSON serializable): %s" % e
            return

        self.error = None
        self.result = 0.0
        if function_name.startswith('__'):
            self.error = 'Wrong function name'
            return
        try:
            function = getattr(self, function_name)
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
        err_trace_converted = error_trace_callstack(self.error_trace)
        pattern = self.pattern_error_trace
        if err_trace_converted == pattern:
            return 1
        return int(err_trace_converted[0] == pattern[1] and err_trace_converted[1] == pattern[0])
