#!/usr/bin/python3

import re
from xml.dom import minidom

# Some constants for internal representation of error traces.
_CALL = 'CALL'
_RET = 'RET'


class MEA:
    def __init__(self, conf, logger, error_traces, assertion, filter="no"):
        self.error_traces = error_traces
        self.filter = filter
        self.logger = logger
        self.conf = conf
        self.__cached_traces = []
        self.__cache = {}
        self.assertion = assertion

    def execute(self):
        result = []
        for error_trace in self.error_traces:
            if self.is_equal(error_trace):
                self.logger.debug("{0} is equal".format(error_trace))
            else:
                result.append(error_trace)
        return result

    def is_equal(self, new_error_trace) -> bool:
        """
        Basic function for error traces comparison. Takes
        :param new_error_trace: New error trace, which is compared with processed_error_traces.
        :return: True if new_error_trace is equal to one of the processed_error_traces and False otherwise.
        """
        filters = {
            'model_functions': self.__model_functions_filter,
            'default': self.__full_equivalence_filter,
            'no': self.__do_not_filter
        }
        return filters[self.filter](new_error_trace)

    def __model_functions_filter(self, new_error_trace) -> bool:
        """
        Comparison function, which compares model functions call trees.
        """
        with open(new_error_trace, encoding='ascii') as fp:
            try:
                dom = minidom.parse(fp)
            except:
                return False

        graphml = dom.getElementsByTagName('graphml')[0]
        graph = graphml.getElementsByTagName('graph')[0]

        # Find model functions. It is done only for the first error trace.
        if not self.__cache:
            self.__get_model_functions(graphml)

        call_tree = [{"entry_point": _CALL}]
        for edge in graph.getElementsByTagName('edge'):
            for data in edge.getElementsByTagName('data'):
                if data.getAttribute('key') == 'enterFunction':
                    function_call = data.firstChild.data
                    call_tree.append({function_call: _CALL})
                if data.getAttribute('key') == 'returnFrom':
                    function_return = data.firstChild.data
                    if function_return in self.__cache:
                        call_tree.append({function_return: _RET})
                    else:
                        # Check from the last call of that function.
                        is_save = False
                        sublist = []
                        for elem in reversed(call_tree):
                            sublist.append(elem)
                            func_name = list(elem.keys()).__getitem__(0)
                            for mf in self.__cache.keys():
                                if func_name.__contains__(mf):
                                    is_save = True
                            if elem == {function_return: _CALL}:
                                sublist.reverse()
                                break
                        if is_save:
                            call_tree.append({function_return: _RET})
                        else:
                            call_tree = call_tree[:-sublist.__len__()]
        if call_tree not in self.__cached_traces:
            self.__cached_traces.append(call_tree)
            return False
        return True

    def __full_equivalence_filter(self, new_error_trace) -> bool:
        """
        Comparison function, which compares all error traces elements.
        """
        with open(new_error_trace, encoding='ascii') as fp:
            try:
                dom = minidom.parse(fp)
            except:
                return False

        graphml = dom.getElementsByTagName('graphml')[0]
        graph = graphml.getElementsByTagName('graph')[0]

        if graph not in self.__cached_traces:
            self.__cached_traces.append(graph)
            return False
        return True

    def __do_not_filter(self, new_error_trace) -> bool:
        return False

    def __get_model_functions(self, graphml):
        src_files = set()
        for key in graphml.getElementsByTagName('key'):
            if key.getAttribute('id') == 'originfile':
                default = key.getElementsByTagName('default')[0]
                default_src_file = default.firstChild.data
                src_files.add(default_src_file)
        graph = graphml.getElementsByTagName('graph')[0]
        for edge in graph.getElementsByTagName('edge'):
            for data in edge.getElementsByTagName('data'):
                if data.getAttribute('key') == 'originfile':
                    # Internal automaton variables do not have a source file.
                    if data.firstChild:
                        src_files.add(data.firstChild.data)

        for src_file in src_files:
            try:
                with open(src_file, encoding='utf8') as fp:
                    right_file = False
                    # TODO: may not work in case of several ldv_asserts.
                    match = re.search(r'ldv_assert\(\"(.*)\",', fp.read())
                    if match:
                        assertion = match.group(1)
                        if self.assertion in assertion:
                            right_file = True
                    if not right_file:
                        continue
                    fp.seek(0)
                    for line in fp:
                        match = re.search(
                            r'/\*\s+(MODEL_FUNC_DEF|ASPECT_FUNC_CALL)\s+(.*)\s+\*/', line)
                        if match:
                            kind, comment = match.groups()
                            # TODO: this does not work with automata.
                            if kind == 'MODEL_FUNC_DEF' or kind == 'ASPECT_FUNC_CALL':
                                # Get necessary function name located on following line.
                                line = next(fp)
                                match = re.search(r'(ldv_\w+)', line)
                                if match:
                                    func_name = match.groups()[0]
                                    self.__cache[func_name.replace("ldv_", "")] = 1
            except:
                pass
