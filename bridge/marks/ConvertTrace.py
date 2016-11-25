import json
from io import BytesIO
from types import MethodType
from django.core.exceptions import ObjectDoesNotExist
from bridge.utils import ArchiveFileContent, logger, file_get_or_create
from reports.etv import error_trace_callstack, ErrorTraceCallstackTree, error_trace_model_functions
from marks.models import ErrorTraceConvertionCache

# To create new funciton:
# 1) Add created function to the class ConvertTrace;
# 2) Use self.error_trace for convertion
# 3) Return the converted trace. This value MUST be json serializable.
# 5) Add docstring to the created function.
# Do not use 'error_trace', 'pattern_error_trace', 'error' as function name.

DEFAULT_CONVERT = 'model_functions'
ET_FILE_NAME = 'converted-error-trace.json'


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
                return
        except AttributeError:
            self.error = 'Function was not found'
            return
        try:
            self.pattern_error_trace = function()
        except Exception as e:
            self.error = e
            return

    def call_stack(self):
        """
This function is extracting the error trace call stack to first warning.
Return list of lists of function names in json format.
        """
        return error_trace_callstack(self.error_trace)

    def model_functions(self):
        """
This function is extracting model functions tree in specific format.
        """
        return error_trace_model_functions(self.error_trace)

    def call_stack_tree(self):
        """
This function is extracting the error trace call stack tree.
All its leaves are model functions.
Return list of lists of levels of function names in json format.
        """

        return ErrorTraceCallstackTree(self.error_trace).trace


class GetConvertedErrorTrace(object):
    def __init__(self, function, unsafe):
        self.error = None
        self.unsafe = unsafe
        self.function = function
        self.error_trace = self.__get_error_trace()
        if self.error is not None:
            return
        try:
            self.converted = self.__convert()
        except Exception as e:
            logger.exception("Can't get converted error trace: %s" % e)
            self.error = "Can't get converted error trace"
        if self.error is not None:
            return
        self._parsed_trace = None

    def __get_error_trace(self):
        afc = ArchiveFileContent(self.unsafe.archive, file_name=self.unsafe.error_trace)
        if afc.error is not None:
            logger.error("Can't get error trace for unsafe '%s': %s" % (self.unsafe.pk, afc.error), stack_info=True)
            self.error = "Can't get error trace for unsafe '%s'" % self.unsafe.pk
            return None
        return afc.content

    def __convert(self):
        try:
            return ErrorTraceConvertionCache.objects.get(unsafe=self.unsafe, function=self.function).converted
        except ObjectDoesNotExist:
            res = ConvertTrace(self.function.name, self.error_trace)
            if res.error is not None:
                self.error = res.error
                return None
            et_file = file_get_or_create(
                BytesIO(json.dumps(res.pattern_error_trace, indent=4).encode('utf8')), ET_FILE_NAME
            )[0]
            ErrorTraceConvertionCache.objects.create(unsafe=self.unsafe, function=self.function, converted=et_file)
            self._parsed_trace = res.pattern_error_trace
            return et_file

    def parsed_trace(self):
        if self._parsed_trace is not None:
            return self._parsed_trace
        with self.converted.file as fp:
            return json.loads(fp.read().decode('utf8'))
