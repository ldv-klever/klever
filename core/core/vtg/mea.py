#!/usr/bin/python3

import os
import re
from xml.dom import minidom


# List of known external filters.
# Filter "model_functions" should be considered as default.
_external_filters = ["no_filter",  # Do not perform external filtering.
                     "full_equivalence",
                     "model_functions"]

# Some constants for internal representation of error traces.
_CALL = 'CALL'
_RET = 'RET'


# This class implements Multiple Error Analysis (MEA) algorithm.
class MEA:

    # Internal representation of stored error traces for specified bug kind.
    # If bug kind was not specified, all error traces are stored in the same group.
    stored_error_traces = {}

    # Should be used only along with corresponding external filter.
    model_functions = []

    external_filter = None
    logger = None
    conf = None

    def __init__(self, conf, logger):
        self.logger = logger
        self.conf = conf

        self.logger.info('Checking for all violations of bug kinds by '
                         'means of Multiple Error Analysis')

        # Internal Filter.
        if 'mea internal filter' in self.conf['VTG strategy']['verifier']:
            internal_filter = self.conf['VTG strategy']['verifier']['mea internal filter']
            self.logger.info('Using internal filter "{0}" for Multiple Error Analysis'.
                             format(internal_filter))
            self.conf['VTG strategy']['verifier']['options'].append(
                {'-setprop': 'cpa.arg.errorPath.filters={0}'.format(internal_filter)})

        # External Filter.
        if 'mea external filter' in self.conf['VTG strategy']['verifier']:
            external_filter = self.conf['VTG strategy']['verifier']['mea external filter']

            if not _external_filters.__contains__(external_filter):
                self.logger.warning('External filter "{0} is not supported"'.
                                    format(external_filter))
                self.logger.warning('No external filter will be used')
            else:
                self.logger.info('Using external filter "{0}" for Multiple Error Analysis'.
                                 format(external_filter))
                self.external_filter = external_filter

    # Model functions in source files and in error traces should be the same.
    def add_model_function(self, mf):
        self.model_functions.add(mf.replace("ldv_", ""))

    # Returns current number of error traces for this bug kind.
    def get_current_error_trace_number(self, bug_kind=None):
        return self.stored_error_traces[bug_kind].__len__()

    # Applies external filter and returns if this error trace should be added or not.
    def error_trace_filter(self, new_error_trace, bug_kind=None):
        if not self.external_filter or self.external_filter == 'no_filter':
            return self.without_filter(new_error_trace, bug_kind)
        elif self.external_filter == 'full_equivalence':
            # This filter does not make much sense, since basic Internal filter should do this.
            return self.basic_error_trace_filter(new_error_trace, bug_kind)
        elif self.external_filter == 'model_functions':
            # Default strategy, always should work.
            return self.model_functions_filter(new_error_trace, bug_kind)
        else:
            # Something was wrong with config if we are here.
            raise AttributeError('Wrong configuration: "{0}" is impossible value for '
                                 'external error trace filter')

    # Returns true if new_error_trace does not equivalent to any of the stored error traces.
    # Also stores new traces in this case.
    def basic_error_trace_filter(self, new_error_trace, bug_kind=None):
        if bug_kind in self.stored_error_traces:
            stored_error_traces_for_bug_kind = self.stored_error_traces[bug_kind]
        else:
            stored_error_traces_for_bug_kind = []

        if not stored_error_traces_for_bug_kind.__contains__(new_error_trace):
            stored_error_traces_for_bug_kind.append(new_error_trace)
            self.stored_error_traces[bug_kind] = stored_error_traces_for_bug_kind
            return True
        return False

    # This function finds all model function names in source files.
    # If bug_kind is specified, it will filter model functions by corresponding bug kind.
    def get_model_functions(self, graphml, bug_kind=None):
        self.model_functions = set()
        src_files = set()
        graph = graphml.getElementsByTagName('graph')[0]
        for key in graphml.getElementsByTagName('key'):
            if key.getAttribute('id') == 'originfile':
                default = key.getElementsByTagName('default')[0]
                default_src_file = self.__normalize_path(default.firstChild)
                src_files.add(default_src_file)
        for edge in graph.getElementsByTagName('edge'):
            for data in edge.getElementsByTagName('data'):
                if data.getAttribute('key') == 'originfile':
                    src_files.add(self.__normalize_path(data.firstChild))

        for src_file in src_files:
            with open(os.path.join(self.conf['source tree root'], src_file), encoding='utf8') as fp:
                i = 0
                last_seen_model_function = None
                for line in fp:
                    i += 1
                    match = re.search(
                        r'/\*\s+(MODEL_FUNC_DEF)\s+(.*)\s+\*/',
                        line)
                    if match:
                        kind, comment = match.groups()

                        if kind == 'MODEL_FUNC_DEF':
                            # Get necessary function name located on following line.
                            try:
                                line = next(fp)
                                # Don't forget to increase counter.
                                i += 1
                                match = re.search(r'(ldv_\w+)', line)
                                if match:
                                    func_name = match.groups()[0]
                                    if not bug_kind:
                                        self.add_model_function(func_name)
                                    else:
                                        last_seen_model_function = func_name
                            except StopIteration:
                                raise ValueError('Model function definition does not exist')
                    if bug_kind:
                        match = re.search(r'ldv_assert\(\"(.*)\",', line)
                        if match:
                            assertion = match.group(1)
                            if assertion.__contains__(bug_kind):
                                if last_seen_model_function:
                                    self.add_model_function(last_seen_model_function)
                                else:
                                    raise ValueError('Model function definition does not exist')
                            else:
                                self.logger.debug('MF {0} is not considered for our bug kind'.
                                                  format(last_seen_model_function))
        self.logger.debug('Model functions "{0}" has been extracted'.format(self.model_functions))

    # Filter by model functions.
    def model_functions_filter(self, new_error_trace, bug_kind=None):
        if bug_kind in self.stored_error_traces:
            stored_error_traces_for_bug_kind = self.stored_error_traces[bug_kind]
        else:
            stored_error_traces_for_bug_kind = []

        # Prepare internal representation of model functions call tree for the selected error trace.
        with open(new_error_trace, encoding='ascii') as fp:
            dom = minidom.parse(fp)
        graphml = dom.getElementsByTagName('graphml')[0]
        graph = graphml.getElementsByTagName('graph')[0]

        # Find model functions. It is done only for the first error trace.
        if not self.model_functions:
            self.get_model_functions(graphml, bug_kind)

        call_tree = [{"entry_point": _CALL}]
        for edge in graph.getElementsByTagName('edge'):
            for data in edge.getElementsByTagName('data'):
                if data.getAttribute('key') == 'enterFunction':
                    function_call = data.firstChild.data
                    call_tree.append({function_call: _CALL})
                if data.getAttribute('key') == 'returnFrom':
                    function_return = data.firstChild.data
                    if self.model_functions.__contains__(function_return):
                        # That is a model function return, add it to call tree.
                        call_tree.append({function_return: _RET})
                    else:
                        # Check from the last call of that function.
                        is_save = False
                        sublist = []
                        for elem in reversed(call_tree):
                            sublist.append(elem)
                            func_name = list(elem.keys()).__getitem__(0)
                            for mf in self.model_functions:
                                if func_name.__contains__(mf):
                                    is_save = True
                            if elem == {function_return: _CALL}:
                                sublist.reverse()
                                break
                        if is_save:
                            call_tree.append({function_return: _RET})
                        else:
                            call_tree = call_tree[:-sublist.__len__()]
        self.logger.debug('Model function call tree "{0}" has been extracted'.format(call_tree))

        if not stored_error_traces_for_bug_kind.__contains__(call_tree):
            stored_error_traces_for_bug_kind.append(call_tree)
            self.stored_error_traces[bug_kind] = stored_error_traces_for_bug_kind
            return True
        return False

    # Do not perform filtering.
    def without_filter(self, new_error_trace, bug_kind=None):
        if bug_kind in self.stored_error_traces:
            stored_error_traces_for_bug_kind = self.stored_error_traces[bug_kind]
        else:
            stored_error_traces_for_bug_kind = []

        stored_error_traces_for_bug_kind.append(new_error_trace)
        self.stored_error_traces[bug_kind] = stored_error_traces_for_bug_kind
        return True

    def __normalize_path(self, path):
        # Each file is specified via absolute path or path relative to source tree root or it is placed to current
        # working directory. Make all paths relative to source tree root.
        if os.path.isabs(path.data) or os.path.isfile(path.data):
            path.data = os.path.relpath(path.data, os.path.realpath(self.conf['source tree root']))

        if not os.path.isfile(os.path.join(self.conf['source tree root'], path.data)):
            raise FileNotFoundError('File "{0}" referred by error trace does not exist'.format(path.data))

        return path.data
