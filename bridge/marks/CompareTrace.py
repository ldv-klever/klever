import json
from types import MethodType
from reports.etv import error_trace_callstack, ErrorTraceCallstackTree

# To create new funciton:
# 1) Add created function to the class CompareTrace;
# 2) Use self.error_trace and self.pattern_error_trace for comparing
# 3) Return the result as float(int) between 0 and 1.
# 4) Add docstring to the created function.
# Do not use 'error_trace', 'pattern_error_trace', 'error'
# and 'result' as function name.

DEFAULT_COMPARE = 'callstack_tree_compare'


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
        self.pattern_error_trace = pattern_error_trace
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
            self.error = "Compare function reterned incorrect result: %s" % \
                         self.result
            self.result = 0.0

    def default_compare(self):
        """
Default comparing function.
Always returns 1.
        """
        return 1

    def random_compare(self):
        """
Random comparing function.
Returns random number between 0 and 1.
        """
        import random
        return random.random()

    def strict_compare(self):
        """
This comparing function returns 1 only when error_trace matches the pattern.
Never fails.
        """
        if self.error_trace == self.pattern_error_trace:
            return 1
        return 0

    def startswith_compare(self):
        """
If length of pattern error trace is greater than returns 0;
Else returns n/m where n - number of the same symbols at the start of
the error trace. And m - the length of pattern error trace.
        """
        if len(self.pattern_error_trace) > len(self.error_trace):
            return 0
        num_of_same = 0
        for i in range(len(self.pattern_error_trace)):
            if self.pattern_error_trace[i] == self.error_trace[i]:
                num_of_same += 1
            else:
                break
        return num_of_same/len(self.pattern_error_trace)

    def callstack_compare(self):
        """
If call stacks are identical returns 1 else returns 0.
        """
        err_trace1 = error_trace_callstack(self.error_trace)
        err_trace2 = self.pattern_error_trace
        if err_trace1 == err_trace2:
            return 1
        return int(json.loads(err_trace1)[0] == json.loads(err_trace2)[1] and
                   json.loads(err_trace1)[1] == json.loads(err_trace2)[0])

    def callstack_tree_compare(self):
        """
If call stacks trees are identical returns 1 else returns 0.
        """
        err_trace1 = ErrorTraceCallstackTree(self.error_trace).trace
        err_trace2 = self.pattern_error_trace
        if err_trace1 == err_trace2:
            return 1
        return int(json.loads(err_trace1)[0] == json.loads(err_trace2)[1] and
                   json.loads(err_trace1)[1] == json.loads(err_trace2)[0])
