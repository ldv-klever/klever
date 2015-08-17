# To create new funciton (ALL STEPS ARE REQUIRED):
# 1) Add created function in class ConvertTrace;
# 2) Use self.error_trace for convertion
# 3) Make self.pattern_error_trace equals to converted trace
# 4) Add function name to self.actions in __init__ function of this class;
# 5) Add description to DESCRIPTIONS (you can add empty description.
# If you need to import something just add it under this "README".


DESCRIPTIONS = {
    'default_convert': """
Default convertion is just copying the trace.
Never failed.
    """,
    'reverse_trace': """
This function is reversing the trace.
Never failed. Is it useful?
Maybe...
    """,
}


class ConvertTrace(object):

    def __init__(self, function_name, error_trace):
        self.name = function_name
        self.error_trace = error_trace
        self.pattern_error_trace = None
        self.actions = {
            'default_convert': self.__default_convert,
            'reverse_trace': self.__reverse_trace,
        }
        self.error = None
        try:
            self.__convert_trace()
        except Exception as e:
            self.error = e

    def __convert_trace(self):
        if self.name in self.actions:
            self.actions[self.name]()
        else:
            self.__default_convert()

    def __default_convert(self):
        self.pattern_error_trace = self.error_trace

    def __reverse_trace(self):
        self.pattern_error_trace = self.error_trace[::-1]
