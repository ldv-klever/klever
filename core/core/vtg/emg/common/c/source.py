#
# Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
# Ivannikov Institute for System Programming of the Russian Academy of Sciences
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
import clade.interface as clade_api

from core.utils import find_file_or_dir
from core.vtg.emg.common.c import Function, Variable, Macro
from core.vtg.emg.common.c.types import import_typedefs, import_declaration, extract_name, is_static


class Source:
    """
    Representation of a collection with the data collected by a source code analysis. The collection contains
    information about functions, variable initializations, a functions call graph, macros.
    """

    def __init__(self, logger, conf, abstract_task):
        """
        Setup initial attributes and get logger object.

        :param logger: logging object.
        :param conf: Source code analysis configuration.
        :param abstract_task: Abstract verification task dictionary (given by VTG).
        :param conf: Configuration properties dictionary.
        """
        self.logger = logger
        self._conf = conf
        self._source_functions = dict()
        self._source_vars = dict()
        self._macros = dict()
        self.__function_calls_cache = dict()

        # Initialize Clade cient to make requests
        self._clade = clade_api
        self._clade.setup(self._conf['Clade']['base'])

        # Ask for dependencies for each CC
        cfiles, files_map = self._collect_file_dependencies(abstract_task)

        # Read file with source analysis
        self._import_code_analysis(self._clade, cfiles, files_map)

    @property
    def source_functions(self):
        """
        Return a list of function names.

        :return: function names list.
        """
        return list(self._source_functions.keys())

    def get_source_function(self, name, path=None, declaration=None):
        """
        Provides the function by a given name from the collection.

        :param name: Function name.
        :param path: File where the function should be declared or defined.
        :param declaration: Declaration object representing the function of interest.
        :return: Function object or None.
        """
        name = self.refined_name(name)
        if name and name in self._source_functions:
            if path and path in self._source_functions[name]:
                return self._source_functions[name][path]
            else:
                functions = self.get_source_functions(name, declaration=declaration)
                if len(functions) == 1:
                    return functions[0]
                elif len(functions) > 1:
                    raise ValueError("There are several definitions of function {!r} in provided code you must specify "
                                     "scope".format(name))
        return None

    def get_source_functions(self, name, declaration=None):
        """
        Provides all functions found by a given name from the collection.

        :param name: Function name.
        :param declaration: Declaration object representing the function of interest.
        :return: List with Function objects.
        """
        name = self.refined_name(name)
        result = []
        if name and name in self._source_functions:
            for func in self._source_functions[name].values():
                if func not in result and (not declaration or (declaration and declaration.compare(func.declaration))):
                    result.append(func)
        return result

    def set_source_function(self, new_obj, path):
        """
        Replace an Function object in the collection.

        :param new_obj: Function object.
        :param path: File where the function should be declared or defined.
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

    @property
    def source_variables(self):
        """
        Return list of global variables.

        :return: Variable names list.
        """
        return list(self._source_vars.keys())

    def get_source_variable(self, name, path=None):
        """
        Provides a gloabal variable by a given name and scope file from the collection.

        :param name: Variable name.
        :param path: File with the variable declaration or initialization.
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
        :return: List with Variable objects.
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
        :param path: File with the variable declaration or initialization.
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

        :param call: An expression string.
        :return: Extracted function name string.
        """
        name_re = re.compile("\(?\s*&?\s*(\w+)\s*\)?$")
        if name_re.fullmatch(call):
            return name_re.fullmatch(call).group(1)
        else:
            return None

    def _import_code_analysis(self, clade_api, cfiles, dependencies):
        """
        Read global variables, functions and macros to fill up the collection.

        :param source_analysis: Dictionary with the content of source analysis.
        :param files_map: Dictionary to resolve main file by an included file.
        :return: None.
        """
        # Import typedefs if there are provided
        self.logger.info("Extract complete types definitions")
        typedef = clade_api.TypeDefinitions(cfiles).graph
        if typedef:
            import_typedefs(typedef)
        #
        # if 'variables' in source_analysis:
        #     self.logger.info("Import types from global variables initializations")
        #     for variable in source_analysis["variables"]:
        #         variable_name = extract_name(variable['declaration'])
        #         if not variable_name:
        #             raise ValueError('Global variable without a name')
        #         var = Variable(variable_name, variable['declaration'])
        #
        #         # Here we know, that if we met a variable in an another file then it is an another variable because
        #         # a program should contain a single global variable initialization
        #         self.set_source_variable(var, variable['path'])
        #         var.declaration_files.add(variable['path'])
        #         var.initialization_file = variable['path']
        #         var.static = is_static(variable['declaration'])
        #
        #         if 'value' in variable:
        #             var.value = variable['value']
        #
        # if 'callgraph' in source_analysis:
        #     self.logger.info("Import source functions")
        #     for func in source_analysis['callgraph']:
        #         for definition_candidate in source_analysis['callgraph'][func]:
        #             desc = source_analysis['callgraph'][func][definition_candidate]
        #
        #             # Use any file
        #             if definition_candidate == "unknown" or definition_candidate not in files_map:
        #                 # todo: This is a mistake of callgraph collectors filter
        #                 if "declared_in" in desc:
        #                     candidates = [k for k in desc["declared_in"].keys() if k in files_map]
        #                     if len(candidates) == 0:
        #                         continue
        #                 else:
        #                     continue
        #
        #                 definition_candidate = candidates[-1]
        #                 definition_file = list(files_map[definition_candidate])[-1]
        #             else:
        #                 definition_file = list(files_map[definition_candidate])[-1]
        #
        #             signature = desc['signature'] if 'signature' in desc \
        #                 else list(desc["declared_in"].values())[-1]['signature']
        #             func_intf = Function(func, signature)
        #             func_intf.definition_file = definition_file
        #
        #             # Set static
        #             if "type" in desc and desc["type"] == "static":
        #                 func_intf.static = True
        #             else:
        #                 func_intf.static = False
        #
        #             # Set declarations
        #             self.set_source_function(func_intf, definition_file)
        #             func_intf.declaration_files.add(definition_file)
        #             if "declared_in" in desc:
        #                 for dfile in (f for f in desc["declared_in"] if f in files_map):
        #                     for actual_file in files_map[dfile]:
        #                         self.set_source_function(func_intf, actual_file)
        #                         func_intf.declaration_files.add(actual_file)
        #
        #             if "calls" in desc:
        #                 for called_function in desc["calls"]:
        #                     for from_where in desc["calls"][called_function]:
        #                         for call in desc["calls"][called_function][from_where]['args']:
        #                             func_intf.call_in_function(called_function, call)
        #
        #             if 'called_in' in desc:
        #                 for caller in desc['called_in']:
        #                     for scope in desc['called_in'][caller]:
        #                         # todo: This is also not filtered properly information from the callgraph collector
        #                         if scope != "unknown" and scope in files_map:
        #                             for actual_scope in files_map[scope]:
        #                                 func_intf.add_call(caller, actual_scope)
        # else:
        #     self.logger.warning("There is no any functions in source analysis")
        #
        # self.logger.info("Remove functions which are not called at driver")
        # for func in list(self._source_functions.keys()):
        #     if None in self._source_functions[func]:
        #         del self._source_functions[func][None]
        #
        #     if func not in source_analysis['callgraph'] or len(self._source_functions[func].keys()) == 0:
        #         self.remove_source_function(func)
        #
        # if 'macros' in source_analysis:
        #     for name in source_analysis['macros']:
        #         macro = Macro(name)
        #         for scope in source_analysis['macros'][name]:
        #             for actual_scope in files_map[scope]:
        #                 for call in source_analysis['macros'][name][scope]['args']:
        #                     macro.add_parameters(actual_scope, call)
        #         self.set_macro(macro)

    def _collect_file_dependencies(self, abstract_task):
        """
        Collect for each included header file or c file its "main" file to which it was included. This is required
        since we cannot write aspects and instrument files which have no CC command so me build this map.

        :param abstract_task: Abstract task dictionary.
        :return: Collection dictionary {included file: {files that include this one}}.
        """
        collection = dict()
        c_files = set()

        def _collect_cc_deps(cfile, deps):
            # Collect for each file CC entry to which it is included
            for file in deps:
                if file not in collection:
                    collection[file] = set()
                collection[file].add(cfile)

        # Read each CC description and import map of files to in files
        for group in abstract_task['grps']:
            for desc in group['Extra CCs']:
                cc_desc = self._clade.get_cc(desc['CC'])
                c_file = cc_desc['in'][0]
                # Now read deps
                _collect_cc_deps(c_file, self._clade.get_cc_deps(desc['CC']))
                c_files.add(c_file)

        return c_files, collection
