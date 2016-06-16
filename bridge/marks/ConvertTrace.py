import json
from types import MethodType
from reports.etv import error_trace_callstack, ErrorTraceCallstackTree

# To create new funciton:
# 1) Add created function to the class ConvertTrace;
# 2) Use self.error_trace for convertion
# 3) Return the converted trace. This value MUST be json serializable.
# 5) Add docstring to the created function.
# Do not use 'error_trace', 'pattern_error_trace', 'error' as function name.

DEFAULT_CONVERT = 'call_stack_tree'


class ConvertTrace(object):

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
        self.error = None
        if function_name.startswith('__'):
            self.error = 'Wrong function name'
            return
        try:
            function = getattr(self, function_name)
            if not isinstance(function, MethodType):
                self.error = 'Wrong function name'
                type(function)
                return
        except AttributeError:
            self.error = 'Function was not found'
            return
        try:
            self.pattern_error_trace = json.dumps(function(), indent=4)
        except Exception as e:
            self.error = e
            return
        if not isinstance(self.pattern_error_trace, str) or len(self.pattern_error_trace) == 0:
            self.error = "Convert function reterned empty trace"

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
