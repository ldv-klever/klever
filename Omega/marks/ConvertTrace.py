from types import MethodType

# To create new funciton:
# 1) Add created function to the class ConvertTrace;
# 2) Use self.error_trace for convertion
# 3) Return the converted trace, string.
# 5) Add docstring to the created function.
# Do not use 'error_trace', 'pattern_error_trace', 'error' as function name.

DEFAULT_CONVERT = 'default_convert'


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
            self.pattern_error_trace = function()
        except Exception as e:
            self.error = e
            return
        if not isinstance(self.pattern_error_trace, str) or \
                len(self.pattern_error_trace) == 0:
            self.error = "Convert function reterned empty trace"

    def default_convert(self):
        """
Default convertion is just copying the trace.
Never failed.
        """
        return self.error_trace

    def reverse_trace(self):
        """
This function is reversing the trace.
Never failed. Is it useful?
Maybe...
        """
        return self.error_trace[::-1]
