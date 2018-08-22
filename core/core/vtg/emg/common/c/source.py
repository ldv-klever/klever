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
import ujson
import clade.interface as clade_api

from core.utils import find_file_or_dir
from core.vtg.emg.common import get_conf_property
from core.vtg.emg.common.c import Function, Variable, Macro
from core.vtg.emg.common.c.types import import_typedefs, extract_name, is_static


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
        variables = clade_api.VariableInitializations(cfiles)
        if variables.vars:
            self.logger.info("Import global variables initializations")
            for path, vals in variables.vars.items():
                for variable in vals:
                    variable_name = extract_name(variable['declaration'])
                    if not variable_name:
                        raise ValueError('Global variable without a name')
                    var = Variable(variable_name, variable['declaration'])

                    # Here we know, that if we met a variable in an another file then it is an another variable because
                    # a program should contain a single global variable initialization
                    self.set_source_variable(var, path)
                    var.declaration_files.add(path)
                    var.initialization_file = path
                    var.static = is_static(variable['declaration'])

                    if 'value' in variable:
                        var.value = variable['value']

        # Variables which are used in variables initalizations
        self.logger.info("Import source functions")
        vfunctions = variables.used_vars_functions
        # Function scope definitions
        fs = clade_api.FunctionsScopes(set(dependencies.keys())).scope_to_funcs
        # Get functions defined in dependencies and in the main functions and have calls
        cg = clade_api.CallGraph().partial_graph(set(dependencies.keys()))
        # Add called functions
        for scope in cg:
            for func in cg[scope]:
                desc = cg[scope][func]
                if scope in cfiles:
                    # Definition of the function is in the code of interest
                    self._add_function(func, scope, fs, dependencies, cfiles)
                elif ('called_in' in desc and set(desc['called_in'].keys()).intersection(cfiles)) or func in vfunctions:
                    if scope in fs and func in fs[scope]:
                        # Function is called in the target code but defined in dependencies
                        self._add_function(func, scope, fs, dependencies, cfiles)
                    elif scope != 'unknown':
                        self.logger.warning("There is no information on declarations of function {!r} from {!r} scope".
                                            format(func, scope))
        # Add functions missed in the call graph
        for scope in (s for s in fs if s in cfiles):
            for func in fs[scope]:
                func_intf = self.get_source_function(func, scope)
                if not func_intf:
                    self._add_function(func, scope, fs, dependencies, cfiles)

        for func in self.source_functions:
            for obj in self.get_source_functions(func):
                scopes = set(obj.declaration_files).union(set(obj.header_files))
                if not obj.definition_file:
                    # It is likely be this way
                    scopes.add('unknown')
                for scope in (s for s in scopes if cg.get(s, dict()).get(func)):
                    for cscope, desc in ((s, d) for s, d in cg[scope][func].get('called_in', {}).items()
                                         if s in cfiles):
                        for caller in desc:
                            for line in desc[caller]:
                                params = desc[caller][line].get('args')
                                caller_intf = self.get_source_function(caller, cscope)
                                obj.add_call(caller, cscope)
                                caller_intf.call_in_function(obj, params)

        macros_file = get_conf_property(self._conf['source analysis'], 'macros white list')
        if macros_file:
            macros_file = find_file_or_dir(self.logger, self._conf['main working directory'], macros_file)
            with open(macros_file, 'r', encoding='utf8') as fp:
                white_list = ujson.load(fp)
            if white_list:
                macros = clade_api.MacroExpansions(white_list, cfiles).macros
                for path, macros in macros.items():
                    for macro, desc in macros.items():
                        obj = self.get_macro(macro)
                        if not obj:
                            obj = Macro(macro)
                        for call in desc.get('args', []):
                            obj.add_parameters(path, call)
                        self.set_macro(obj)

    def _add_function(self, func, scope, fs, deps, cfiles):
        fs_desc = fs[scope][func]
        if scope == 'unknown':
            key = list(fs_desc['declared_in'].keys())[0]
            signature = fs_desc['declared_in'][key]['signature']
            func_intf = Function(func, signature)
            # Do not set definition file since it is out of scope of the target verification object
        else:
            signature = fs_desc.get('signature')
            func_intf = Function(func, signature)
            func_intf.definition_file = scope

        # Set static
        if fs_desc.get('type') == "static":
            func_intf.static = True
        else:
            func_intf.static = False

        # Add declarations
        files = {func_intf.definition_file} if func_intf.definition_file else set()
        files.update({f for f in fs_desc.get('declared_in', set()) if f != 'unknown' and f in deps})
        for file in files:
            if file not in cfiles and file not in func_intf.header_files:
                func_intf.header_files.append(file)
            for cfile in deps[file]:
                self.set_source_function(func_intf, cfile)
                func_intf.declaration_files.add(cfile)

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
