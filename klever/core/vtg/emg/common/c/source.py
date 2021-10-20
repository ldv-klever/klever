#
# Copyright (c) 2019 ISP RAS (http://www.ispras.ru)
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

import os
import re
import ujson
import sortedcontainers
from clade import Clade

from klever.core.vtg.emg.common.c import Function, Variable, Macro, import_declaration
from klever.core.vtg.emg.common.c.types import import_typedefs, extract_name, dump_types
from klever.core.vtg.utils import find_file_or_dir


def create_source_representation(logger, conf, abstract_task):
    """
    Create Source object.

    :param logger: Logger object.
    :param conf: Conf dict.
    :param abstract_task: Abstract task dict.
    :return: Source object.
    """
    # Initialize Clade client to make requests
    clade = Clade(conf['build base'])
    if not clade.work_dir_ok():
        raise RuntimeError('Build base is not OK')

    prefixes = _prefixes(conf, clade)

    # Ask for dependencies for each CC
    cfiles, dep_paths, files_map = _collect_file_dependencies(clade, abstract_task)

    # Read file with source analysis
    collection = Source(cfiles, prefixes, dep_paths)
    collection.c_full_paths = _c_full_paths(collection, cfiles)

    _import_code_analysis(logger, conf, clade, files_map, collection)
    if conf.get('dump types'):
        dump_types('type collection.json')
    if conf.get('dump source code analysis'):
        collection.dump('vars.json', 'functions.json', 'macros.json')
    return collection


def _prefixes(conf, clade):
    return {spath: clade.get_storage_path(spath) for spath in conf["working source trees"] + ['']}


def _c_full_paths(collection, cfiles):
    full_paths = {collection.find_file(file) for file in cfiles}
    return full_paths


def _import_code_analysis(logger, conf, clade, dependencies, collection):
    # Import typedefs if there are provided
    logger.info("Extract complete types definitions")
    typedef = clade.get_typedefs(set(dependencies.keys()).union(collection.cfiles))
    if typedef:
        import_typedefs(typedef, dependencies)

    variables = clade.get_variables(set(collection.cfiles))
    if variables:
        logger.info("Import global variables initializations")
        for path, vals in variables.items():
            for variable in vals:
                variable_name = extract_name(variable['declaration'])
                if not variable_name:
                    raise ValueError('Global variable without a name')
                var = Variable(variable_name, variable['declaration'])

                # Here we know, that if we met a variable in an another file then it is an another variable because
                # a program should contain a single global variable initialization
                collection.set_source_variable(var, path)
                var.declaration_files.add(path)
                var.initialization_file = path

                if 'value' in variable:
                    var.value = variable['value']

    # Variables which are used in variables initializations
    logger.info("Import source functions")
    vfunctions = clade.get_used_in_vars_functions()

    # Get functions defined in dependencies and in the main functions and have calls
    cg = clade.get_callgraph(set(dependencies.keys()))

    # Function scope definitions
    # todo: maybe this should be fixed in Clade
    # As we will not get definitions for library functions if there are in compiled parts we should add all scopes
    # that are given for all function called from outside of the code we analyze
    for scope in (s for s in collection.cfiles if s in cg):
        for func in (f for f in cg[scope] if cg[scope][f].get('calls')):
            for dep in cg[scope][func].get('calls'):
                dependencies.setdefault(dep, sortedcontainers.SortedSet())
                dependencies[dep].add(scope)
    fs = clade.get_functions_by_file(set(dependencies.keys()).union(collection.cfiles))

    # Add called functions
    for scope in cg:
        for func in cg[scope]:
            desc = cg[scope][func]
            if scope in collection.cfiles:
                # Definition of the function is in the code of interest
                try:
                    collection.add_function(func, scope, fs, dependencies, collection.cfiles)
                except ValueError:
                    pass
                # Add called functions
                for def_scope, cf_desc in desc.get('calls', dict()).items():
                    if def_scope not in collection.cfiles:
                        for called_func in (f for f in cf_desc if def_scope in fs and f in fs[def_scope]):
                            collection.add_function(called_func, def_scope, fs, dependencies, collection.cfiles)

            elif ('called_in' in desc and
                  set(desc['called_in'].keys()).intersection(collection.cfiles)) or func in vfunctions:
                if scope in fs and func in fs[scope]:
                    # Function is called in the target code but defined in dependencies
                    collection.add_function(func, scope, fs, dependencies, collection.cfiles)
                elif scope != 'unknown':
                    logger.warning("There is no information on declarations of function {!r} from {!r} scope".
                                   format(func, scope))
    # Add functions missed in the call graph
    for scope in (s for s in fs if s in collection.cfiles):
        for func in fs[scope]:
            func_intf = collection.get_source_function(func, scope)
            if not func_intf:
                try:
                    collection.add_function(func, scope, fs, dependencies, collection.cfiles)
                except ValueError:
                    pass

    for func in collection.source_functions:
        for obj in collection.get_source_functions(func):
            scopes = set(obj.declaration_files).union(set(obj.header_files))
            if not obj.definition_file:
                # It is likely be this way
                scopes.add('unknown')
            for scope in (s for s in scopes if cg.get(s, dict()).get(func)):
                for cscope, desc in ((s, d) for s, d in cg[scope][func].get('called_in', {}).items()
                                     if s in collection.cfiles):
                    for caller in desc:
                        for line in desc[caller]:
                            params = desc[caller][line].get('args')
                            caller_intf = collection.get_source_function(caller, cscope)
                            obj.add_call(caller, cscope)

                            if params:
                                # Here can be functions which are not defined or visible
                                for _, passed_func in list(params):
                                    passed_obj = collection.get_source_function(passed_func, cscope)
                                    if not passed_obj:
                                        passed_scope = collection.search_function(passed_func, cscope, fs)
                                        if passed_scope:
                                            collection.add_function(passed_func, passed_scope, fs, dependencies,
                                                                    collection.cfiles)
                                        else:
                                            logger.warning("Cannot find function {!r} from scope {!r}".
                                                           format(passed_func, cscope))
                                            # Ignore this call since model will not be correct without signature
                                            params = None
                                            break
                                caller_intf.call_in_function(obj, params)
            if obj.definition_file and obj.definition_file in scopes and obj.definition_file in cg and \
                    func in cg[obj.definition_file]:
                for called_def_scope in cg[obj.definition_file][func].get('calls', dict()):
                    for called_func in cg[obj.definition_file][func]['calls'][called_def_scope]:
                        called_obj = collection.get_source_function(called_func, paths={obj.definition_file})
                        if called_obj:
                            called_obj.add_call(func, obj.definition_file)

    logger.debug("The following functions were imported: {}".format(', '.join(collection.source_functions)))

    macros_file = conf.get('macros white list', 'linux/emg/macros white list.json')
    if macros_file:
        macros_file = find_file_or_dir(logger, conf['main working directory'], macros_file)
        with open(macros_file, 'r', encoding='utf-8') as fp:
            white_list = sorted(ujson.load(fp))
        if white_list:
            macros = clade.get_macros_expansions(sorted(collection.cfiles), white_list)
            for path, macros in macros.items():
                for macro, desc in macros.items():
                    obj = collection.get_macro(macro)
                    if not obj:
                        obj = Macro(macro)
                    for call in desc.get('args', []):
                        obj.add_parameters(path, call)
                    collection.set_macro(obj)


def _collect_file_dependencies(clade, abstract_task):
    collection = sortedcontainers.SortedDict()
    c_files = sortedcontainers.SortedSet()

    def _collect_cc_deps(cfile, deps):
        # Collect for each file CC entry to which it is included
        for file in deps:
            if file not in collection:
                collection[file] = sortedcontainers.SortedSet()
            collection[file].add(cfile)

    # Read each CC description and import map of files to in files
    for group in abstract_task['grps']:
        for desc in group['Extra CCs']:
            cc_desc = clade.get_cmd(*desc['CC'])
            cc_c_files = sortedcontainers.SortedSet(cc_desc['in'])
            deps = clade.get_cmd_deps(*desc['CC'])
            for c_file in cc_c_files:
                # Now read deps
                _collect_cc_deps(c_file, deps)
                c_files.add(c_file)

    return c_files, sortedcontainers.SortedSet(collection.keys()), collection


class Source:
    """
    Representation of a collection with the data collected by a source code analysis. The collection contains
    information about functions, variable initializations, a functions call graph, macros.
    """
    __REGEX_TYPE = type(re.compile('a'))

    def __init__(self, cfiles, prefixes, deps):
        self.cfiles = cfiles
        self.prefixes = prefixes
        self.deps = deps

        self.dep_paths = sortedcontainers.SortedSet()
        self._source_functions = sortedcontainers.SortedDict()
        self._source_vars = sortedcontainers.SortedDict()
        self._macros = sortedcontainers.SortedDict()

        self.__function_calls_cache = sortedcontainers.SortedDict()

    def dump(self, var_file, func_file, macro_file):
        with open(var_file, 'w', encoding='utf-8') as fp:
            ujson.dump({k: {f: v.declare_with_init() for f, v in fs.items()} for k, fs in self._source_vars.items()},
                       fp, indent=2, sort_keys=True)
        with open(func_file, 'w', encoding='utf-8') as fp:
            ujson.dump({k: {f: v.declare()[0] for f, v in fs.items()} for k, fs in self._source_vars.items()}, fp,
                       indent=2, sort_keys=True)
        # todo: dump macros after implementation

    @property
    def source_functions(self):
        """
        Return a list of function names.

        :return: function names list.
        """
        return tuple(self._source_functions.keys())

    def find_file(self, path):
        """
        Find real file that match the given either relative or absolute path.

        :param path: String.
        :return: Absolute path string.
        """
        def _accurate_concatenation(one, two):
            if one:
                if one[-1] == '/':
                    one = one[:-1]
                if two[0] == '/':
                    two = two[1:]
                return '%s/%s' % (one, two)
            else:
                return two

        if path == 'environment model':
            return path

        for source_prefix, with_clade_dir in self.prefixes.items():
            real_path = _accurate_concatenation(with_clade_dir, path)
            if os.path.isfile(real_path):
                return _accurate_concatenation(source_prefix, path)
        else:
            raise FileNotFoundError('There is no file {!r} in the build base or the path to source files is incorrect.'
                                    ' Set the following prefixes: {}'.format(path, str(self.prefixes)))

    def get_source_function(self, name=None, paths=None, declaration=None):
        """
        Provides the function by a given name from the collection.

        :param name: Function name.
        :param paths: Possible file with a definition or declaration.
        :param declaration: Declaration object representing the function of interest.
        :return: Function object or None.
        """
        if isinstance(paths, str):
            # This is for convenience
            paths = [paths]

        # First try to get the most precise match
        match = self.get_source_functions(name, paths, declaration)
        if match and len(match) == 1:
            # Bingo!
            return match[0]
        else:
            # This is a bit weaker search because comparing declaration can be difficult
            match = self.get_source_functions(name, paths)
            if match and len(match) == 1:
                return match[0]
            elif match and len(match) > 1:
                raise ValueError("There are several definitions of function {!r} in provided code you must specify "
                                 "scope".format(name))

        return None

    def get_source_functions(self, name=None, paths=None, declaration=None):
        """
        Provides all functions found by a given name from the collection.

        :param name: Function name.
        :param paths: possible paths with definitions or declarations.
        :param declaration: Declaration object representing the function of interest.
        :return: List with Function objects.
        """
        result = []
        if declaration and isinstance(declaration, str):
            declaration = import_declaration(declaration)
        if name and isinstance(name, self.__REGEX_TYPE):
            names = [f for f in self.source_functions if name.fullmatch(f)]
        elif name and self.refined_name(name) in self.source_functions:
            names = (self.refined_name(name),)
        elif name:
            return []
        else:
            names = self.source_functions

        for func_name in names:
            for path, func in ((p, f) for p, f in self._source_functions[func_name].items() if not paths or p in paths):
                if func not in result and (not declaration or (declaration and declaration == func.declaration)):
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
            self._source_functions[new_obj.name] = sortedcontainers.SortedDict()
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
        return tuple(self._source_vars.keys())

    def get_source_variable(self, name, path=None):
        """
        Provides a global variable by a given name and scope file from the collection.

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
            self._source_vars[new_obj.name] = sortedcontainers.SortedDict()
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
        name_re = re.compile(r'\(?\s*&?\s*(\w+)\s*\)?$')
        if name_re.fullmatch(call):
            return name_re.fullmatch(call).group(1)
        else:
            return None

    def search_function(self, func_name, some_scope, fs):
        # Be aware of  this function - it is costly
        if some_scope in fs and func_name in fs[some_scope]:
            return some_scope
        elif 'unknown' in fs and func_name in fs['unknown']:
            return 'unknown'
        else:
            for s in (s for s in fs if func_name in fs[s]):
                return s
        return None

    def add_function(self, func, scope, fs, deps, cfiles):
        fs_desc = fs[scope][func]
        if scope == 'unknown':
            key = list(fs_desc['declarations'].keys())[0]
            signature = fs_desc['declarations'][key]['signature']
            func_intf = Function(func, signature)
            # Do not set definition file since it is out of scope of the target program fragment
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
        files = sortedcontainers.SortedSet()
        if func_intf.definition_file:
            files.add(func_intf.definition_file)
        if fs_desc['declarations']:
            files.update({f for f in fs_desc['declarations'] if f != 'unknown' and f in deps})
        for file in files:
            if file not in cfiles and file not in func_intf.header_files:
                func_intf.header_files.append(file)
            for cfile in deps[file]:
                self.set_source_function(func_intf, cfile)
                func_intf.declaration_files.add(cfile)
