#
# Copyright (c) 2014-2015 ISPRAS (http://www.ispras.ru)
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
import re
import json

from core.vtg.emg.common import get_conf_property
from core.vtg.emg.common.c import Function, Variable, Macro
from core.vtg.emg.common.c.types import import_typedefs, import_declaration, extract_name, is_static


class Source:

    def __init__(self, logger, conf, analysis_file):
        """
        Setup initial attributes and get logger object.

        :param logger: logging object.
        :param conf: Source code analysis configuration.
        :param analysis_file: Name of the file with source analysis data.
        :param conf: Configuration properties dictionary.
        """
        self.logger = logger
        self._conf = conf
        self._source_functions = dict()
        self._source_vars = dict()
        self._macros = dict()
        self.__function_calls_cache = dict()

        self.logger.info("Read file with results of source analysis from {}".format(analysis_file))
        with open(analysis_file, encoding="utf8") as fh:
            analysis_data = json.loads(fh.read())
        self._import_code_analysis(analysis_data)

    @property
    def source_functions(self):
        """
        Return sorted list of function names.

        :return: function names list.
        """
        return list(self._source_functions.keys())

    def get_source_function(self, name, path=None):
        """
        Provides the function by a given name from the collection.

        :param name: Function name.
        :param path: Scope of the function.
        :return: Function object or None.
        """
        name = self.refined_name(name)
        if name and name in self._source_functions:
            if path and path in self._source_functions[name]:
                return self._source_functions[name][path]
            else:
                functions = self.get_source_functions(name)
                if len(functions) == 1:
                    return functions[0]
        return None

    def get_source_functions(self, name):
        """
        Provides all functions by a given name from the collection.

        :param name: Function name.
        :return: Pairs with the path and Function object.
        """
        name = self.refined_name(name)
        result = []
        if name and name in self._source_functions:
            for func in self._source_functions[name].values():
                if func not in result:
                    result.append(func)
        return result

    def set_source_function(self, new_obj, path):
        """
        Replace an Function object in the collection.

        :param new_obj: Function object.
        :param path: Scope of the function.
        :return: None.
        """
        if new_obj.name not in self._source_functions:
            self._source_functions[new_obj.name] = dict()
        self._source_functions[new_obj.name][path] = new_obj

    def remove_source_function(self, name):
        """
        Delete the function from the collection.

        :param name: Function name.
        :return: None.
        """
        del self._source_functions[name]

    def callstack_called_functions(self, func):
        """
        Collects all functions which can be called in a callstack of a provided function.

        :param func: Function name string.
        :return: List with functions names that call the given one.
        """
        if func not in self.__function_calls_cache:
            level_counter = 0
            max_level = None

            if get_conf_property(self._conf, 'callstack deep search', int):
                max_level = get_conf_property(self._conf, 'callstack deep search', int)

            # Simple BFS with deep counting from the given function
            relevant = set()
            level_functions = {func}
            processed = set()
            while len(level_functions) > 0 and (not max_level or level_counter < max_level):
                next_level = set()

                for fn in level_functions:
                    # kernel functions + modules functions
                    kfs, mfs = self.__functions_called_in(fn, processed)
                    next_level.update(mfs)
                    relevant.update(kfs)

                level_functions = next_level
                level_counter += 1

            self.__function_calls_cache[func] = relevant
        else:
            relevant = self.__function_calls_cache[func]

        return sorted(relevant)

    @property
    def source_variables(self):
        """
        Return sorted list of global variables.

        :return: Variable names list.
        """
        return list(self._source_vars.keys())

    def get_source_variable(self, name, path=None):
        """
        Provides a gloabal variable by a given name from the collection.

        :param name: Variable name.
        :param path: Scope of the variable.
        :return: Variable object or None.
        """
        name = self.refined_name(name)
        if name and name in self._source_vars:
            if path and path in self._source_vars[name]:
                return self._source_vars[name][path]
            else:
                variables = self.get_source_variables(name)
                if len(variables) == 1:
                    return variables[0]
        return None

    def get_source_variables(self, name):
        """
        Provides all global variables by a given name from the collection.

        :param name: Variable name.
        :return: Pairs with the path and Variable object.
        """
        name = self.refined_name(name)
        result = []
        if name and name in self._source_vars:
            for var in self._source_vars[name].values():
                if var not in result:
                    result.append(var)
        return result

    def set_source_variable(self, new_obj, path):
        """
        Replace an object in global variables collection.

        :param new_obj: Variable object.
        :param path: Scope.
        :return: None.
        """
        if new_obj.name not in self._source_vars:
            self._source_vars[new_obj.name] = dict()
        self._source_vars[new_obj.name][path] = new_obj

    def remove_source_variable(self, name):
        """
        Delete the global variable from the collection.

        :param name: Variable name.
        :return: None.
        """
        del self._source_vars[name]

    def get_macro(self, name):
        """
        Provides a macro by a given name from the collection.

        :param name: Macro name.
        :return: Macro object or None.
        """
        if name in self._macros:
            return self._macros[name]
        else:
            return None

    def set_macro(self, new_obj):
        """
        Set or replace an object in macros collection.

        :param new_obj: Macro object.
        :return: None.
        """
        self._macros[new_obj.name] = new_obj

    def remove_macro(self, name):
        """
        Delete the macro from the collection.

        :param name: Macro name.
        :return: None.
        """
        del self._macros[name]

    @staticmethod
    def refined_name(call):
        """
        Resolve function name from simple expressions which contains explicit function name like '& myfunc', '(myfunc)',
        '(& myfunc)' or 'myfunc'.

        :param call: Expression string.
        :return: Function name string.
        """
        name_re = re.compile("\(?\s*&?\s*(\w+)\s*\)?$")
        if name_re.fullmatch(call):
            return name_re.fullmatch(call).group(1)
        else:
            return None

    def __functions_called_in(self, path, name):
        if not (path in self.__function_calls_cache and name in self.__function_calls_cache[path]):
            fs = dict()
            processing = [[path, name]]
            processed = dict()
            while len(processing) > 0:
                p, n = processing.pop()
                func = self.get_source_function(n, p)
                if func:
                    for cp in func.calls:
                        for called in (f for f in func.calls[cp] if not (cp in processed and f in processed[cp])):
                            if cp in self.__function_calls_cache and called in self.__function_calls_cache[cp]:
                                for ccp in self.__function_calls_cache[cp][called]:
                                    if ccp not in fs:
                                        fs[ccp] = self.__function_calls_cache[cp][called][ccp]
                                    else:
                                        fs[ccp].update(self.__function_calls_cache[cp][called][ccp])
                                    processed[ccp].update(self.__function_calls_cache[cp][called][ccp])
                            else:
                                processing.append([cp, called])
                            if cp not in processed:
                                processed[cp] = {called}
                            else:
                                processed[cp].add(called)

                            fs[cp].add(called)

            self.__function_calls_cache[path][name] = fs

        return self.__function_calls_cache[path][name]

    def _import_code_analysis(self, source_analysis):
        """
        Read global variables, functions and macros to fill up the collection.

        :param source_analysis: Dictionary with content of source analysis.
        :return: None.
        """
        # Import typedefs if there are provided
        self.logger.info("Extract complete types definitions")
        if source_analysis and 'typedefs' in source_analysis:
            import_typedefs(source_analysis['typedefs'])

        if 'global variable initializations' in source_analysis:
            self.logger.info("Import types from global variables initializations")
            for variable in source_analysis["global variable initializations"]:
                variable_name = extract_name(variable['declaration'])
                if not variable_name:
                    raise ValueError('Global variable without a name')
                var = Variable(variable_name, variable['declaration'])

                # Here we know, that if we met a variable in an another file then it is an another variable becaouse
                # a program should contain a single global variable initialization
                self.set_source_variable(var, variable['path'])
                var.declaration_files.add(variable['path'])
                var.initialization_file = variable['path']
                var.static = is_static(variable['declaration'])

                if 'value' in variable:
                    var.value = variable['value']

        if 'functions' in source_analysis:
            self.logger.info("Import source functions")
            for func in source_analysis['functions']:
                for path in source_analysis['functions'][func]:
                    description = source_analysis['functions'][func][path]
                    declaration = import_declaration(description['signature'])
                    func_intf = self.get_source_function(func)
                    if func_intf and func_intf.declaration.compare(declaration) and not description['static']:
                        func_intf.declaration_files.add(path)
                    else:
                        func_intf = Function(func, description['signature'])
                        func_intf.declaration_files.add(path)
                        if 'definition' in description and description['definition']:
                            func_intf.definition_file = path

                    if 'static' in description:
                        func_intf.static = description['static']

                    func_intf.raw_declaration = description['signature']
                    self.set_source_function(func_intf, path)

            # Then add calls
            for func in source_analysis['functions']:
                for path in source_analysis['functions'][func]:
                    func_obj = self.get_source_function(func, path)
                    description = source_analysis['functions'][func][path]
                    if "called at" in description:
                        for name in description["called at"]:
                            func_obj.add_call(name, path)
                    if "calls" in description:
                        for name in description["calls"]:
                            for call in description["calls"][name]:
                                func_obj.call_in_function(name, call)
                                if path != func_obj.definition_file:
                                    raise ValueError("Function {!r} cannot call function {!r} outside of its "
                                                     "definition file {!r}: at {!r}".
                                                     format(func, name, func_obj.definition_file, path))
        else:
            self.logger.warning("There is no any functions in source analysis")

        self.logger.info("Remove functions which are not called at driver")
        for func in list(self._source_functions.keys()):
            if None in self._source_functions[func]:
                del self._source_functions[func][None]

            if func not in source_analysis['functions'] or len(self._source_functions[func].keys()) == 0:
                self.remove_source_function(func)

        if 'macro expansions' in source_analysis:
            for name in source_analysis['macro expansions']:
                macro = Macro(name)
                for path in source_analysis['macro expansions'][name]:
                    if 'args' in source_analysis['macro expansions'][name][path]:
                        for p in source_analysis['macro expansions'][name][path]['args']:
                            macro.add_parameters(path, p)
                self.set_macro(macro)
