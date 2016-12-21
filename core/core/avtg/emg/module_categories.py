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

import json
import re

from core.avtg.emg.interface_categories import CategoriesSpecification
from core.avtg.emg.common.interface import Container, Resource, Callback, KernelFunction
from core.avtg.emg.common.signature import Function, Structure, Union, Array, Pointer, Primitive, InterfaceReference, \
    setup_collection, import_declaration, import_typedefs, extract_name, check_null
from core.avtg.emg import tarjan


class ModuleCategoriesSpecification(CategoriesSpecification):
    """Implements parser of source analysis and representation of module interface categories specification."""

    def __init__(self, logger, conf):
        """
        Setup initial attributes and get logger object.

        :param logger: logging object.
        :param conf: Configuration properties dictionary.
        """
        self.logger = logger

        # Inheritable
        self._conf = conf
        self._types = dict()
        self._typedefs = dict()
        self._inits = list()
        self._exits = list()
        self._interfaces = dict()
        self._kernel_functions = dict()
        self._modules_functions = None
        self._locked_categories = set()
        self._interface_cache = dict()
        self._implementations_cache = dict()
        self._containers_cache = dict()

        # Private
        self.__deleted_interfaces = dict()
        self.__function_calls_cache = dict()
        self.__kernel_function_calls_cache = dict()
        
        # todo: support
        self._kernel_macro_functions = dict()
        self._kernel_macros = dict()

        setup_collection(self._types, self._typedefs)

    ####################################################################################################################
    # PUBLIC METHODS
    ####################################################################################################################

    @property
    def interfaces(self):
        """
        Return sorted list of interface names.

        :return: List of Interface object identifiers.
        """
        return sorted(self._interfaces.keys())

    @property
    def kernel_functions(self):
        """
        Return sorted list of kernel function names.

        :return: KernelFunction identifiers list.
        """
        return sorted(self._kernel_functions.keys())

    @property
    def modules_functions(self):
        """
        Return sorted list of modules functions names.

        :return: List of function name strings.
        """
        return sorted(self._modules_functions.keys())

    @property
    def inits(self):
        """
        Returns names of module initialization functions and files where they has been found.

        :return: List [filename1, initname1, filename2, initname2, ...]
        """
        return list(self._inits)

    @property
    def exits(self):
        """
        Returns names of module exit functions and files where they has been found.

        :return: List [filename1, exitname1, filename2, exitname2, ...]
        """
        return list(self._exits)

    def get_intf(self, identifier):
        """
        Provides an interface from the interface collection by a given identifier.

        :param identifier: Interface object identifier string.
        :return: Interface object.
        """
        return self._interfaces[identifier]

    def _set_intf(self, new_obj):
        """
        Set new interface object in the collection.

        :param new_obj: Interface object
        :return: None
        """
        self._interfaces[new_obj.identifier] = new_obj

    def get_kernel_function(self, name):
        """
        Provides kernel function by a given name from the collection.

        :param name: Kernel function name.
        :return: KernelFunction object.
        """
        return self._kernel_functions[name]

    def _set_kernel_function(self, new_obj):
        """
        Replace an object in kernel function collection.

        :param new_obj: Kernel function object.
        :return: KernelFunction object.
        """
        self._kernel_functions[new_obj.identifier] = new_obj

    def _remove_kernel_function(self, name):
        """
        Del kernel function from the collection.

        :param name: Kernel function name.
        :return: KernelFunction object.
        """
        del self._kernel_functions[name]

    def get_modules_function_files(self, name):
        """
        Returns sorted list of modules files where a function with a provided name is implemented.

        :param name: Function name string.
        :return: List with file names.
        """
        return sorted(self._modules_functions[name].keys())

    def is_removed_intf(self, identifier):
        """
        Returns True if there is an interface with a provided identifier in a deleted interfaces collection.

        :param identifier: Interface object identifier.
        :return: True or False.
        """
        if identifier in self.__deleted_interfaces:
            return True
        else:
            return False

    def get_or_restore_intf(self, identifier):
        """
        Search for an interface prvided by an identifier in an interface collection and deleted interfaces collection
        to provide an object. If it is found as a deleted interface then it would be restored back to the main
        collection.

        :param identifier: Interface identifier
        :return: Interface object.
        """
        if identifier in self._interfaces:
            return self._interfaces[identifier]
        elif identifier not in self._interfaces and identifier in self.__deleted_interfaces:
            # Restore interface itself
            self._interfaces[identifier] = self.__deleted_interfaces[identifier]
            del self.__deleted_interfaces[identifier]

            # Restore resources
            if type(self._interfaces[identifier]) is Callback:
                for pi in self._interfaces[identifier].param_interfaces:
                    self.get_or_restore_intf(pi)

            return self._interfaces[identifier]
        else:
            raise KeyError("Unknown interface '{}'".format(identifier))

    def _del_intf(self, identifier):
        """
        Search for an interface provided by an identifier in the main collection and return corresponding object.

        :param identifier:
        :return: Interface object.
        """
        self.__deleted_interfaces[identifier] = self._interfaces[identifier]
        del self._interfaces[identifier]

    def import_specification(self, avt, specification=None, module_specification=None, analysis=None):
        """
        Perform main routin with import of interface categories specification and then results of source analysis.
        After that object contains only relevant to environment generation interfaces and their implementations.

        :param specification: Dictionary with content of a JSON specification prepared manually.
        :param module_specification: Dictionary with content of manually prepared module categories specification.
        :param analysis: Dictionary with content of source analysis.
        :return: None
        """
        # Import typedefs if there are provided
        if analysis and 'typedefs' in analysis:
            import_typedefs(analysis['typedefs'])

        # Import interface categories
        if specification:
            super().import_specification(specification)

        if module_specification:
            # todo: import specification (issue 6561)
            raise NotImplementedError

        # Import source analysis
        self.logger.info("Import results of source code analysis")
        self.__import_source_analysis(analysis, avt)

    def collect_relevant_models(self, function):
        """
        Collects all kernel functions which can be called in a callstack of a provided module function.

        :param function: Module function name string.
        :return: List with kernel functions name strings.
        """
        self.logger.debug("Collect relevant kernel functions called in a call stack of callback '{}'".format(function))
        if not function in self.__kernel_function_calls_cache:
            level_counter = 0
            max_level = None

            if 'callstack deep search' in self._conf:
                max_level = int(self._conf['callstack deep search'])

            # Simple BFS with deep counting from the given function
            relevant = set()
            level_functions = {function}
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

            self.__kernel_function_calls_cache[function] = relevant
        else:
            self.logger.debug('Cache hit')
            relevant = self.__kernel_function_calls_cache[function]

        return sorted(relevant)

    def find_relevant_function(self, parameter_interfaces):
        """
        Get a list of options of function parameters (interfaces) and tries to find a kernel function which would
        has a prameter from each provided set in its parameters.

        :param interface: List with lists of Interface objects.
        :return: List with dictionaries:
                 {"function" -> 'KernelFunction obj', 'parameters' -> [Interfaces objects]}.
        """
        matches = []
        for function in self.kernel_functions:
            function_obj = self.get_kernel_function(function)
            match = {
                "function": function_obj,
                "parameters": []
            }
            if len(parameter_interfaces) > 0:
                # Match parameters
                params = []
                suits = 0
                for index in range(len(parameter_interfaces)):
                    found = 0
                    for param in (p for p in function_obj.param_interfaces[index:] if p):
                        for option in parameter_interfaces[index]:
                            if option.identifier == param.identifier:
                                found = param
                                break
                        if found:
                            break
                    if found:
                        suits += 1
                        params.append(param)
                if suits == len(parameter_interfaces):
                    match["parameters"] = params
                    matches.append(match)

        return matches

    @staticmethod
    def callback_name(call):
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

    def save_to_file(self, file):
        raise NotImplementedError
        # todo: export specification (issue 6561)
        #self.logger.info("First convert specification to json and then save")
        #content = json.dumps(self, ensure_ascii=False, sort_keys=True, indent=4, cls=SpecEncoder)
        #
        #with open(file, "w", encoding="utf8") as fh:
        #    fh.write(content)

    ####################################################################################################################
    # PRIVATE METHODS
    ####################################################################################################################

    def __functions_called_in(self, function, processed):
        kfs = set()
        mfs = set()
        processed.add(function)

        if function in self._modules_functions:
            self.logger.debug("Collect relevant functions called in a call stack of function '{}'".format(function))
            if function in self.__function_calls_cache:
                self.logger.debug("Cache hit")
                return self.__function_calls_cache[function]
            else:
                for file in sorted(self._modules_functions[function].keys()):
                    for called in self._modules_functions[function][file]['calls']:
                        if called in self._modules_functions and called not in processed:
                            mfs.add(called)
                        elif called in self.kernel_functions:
                            kfs.add(called)

                self.__function_calls_cache[function] = [kfs, mfs]
        return kfs, mfs

    def determine_original_file(self, label_value):
        label_name = self.callback_name(label_value)
        if label_name and label_name in self._modules_functions:
            # todo: if several files exist?
            return list(self._modules_functions[label_name])[0]
        raise RuntimeError("Cannot find an original file for label '{}'".format(label_value))

    def __set_declaration(self, interface, declaration):
        if type(interface.declaration) is Function:
            if interface.rv_interface:
                if type(interface.declaration.return_value) is InterfaceReference and \
                        interface.declaration.return_value.pointer:
                    self.__set_declaration(interface.rv_interface, declaration.return_value.points)
                else:
                    self.__set_declaration(interface.rv_interface, declaration.return_value)

            for index in range(len(interface.declaration.parameters)):
                p_declaration = declaration.parameters[index]

                if interface.param_interfaces[index]:
                    if type(interface.declaration.parameters[index]) is InterfaceReference and \
                            interface.declaration.parameters[index].pointer:
                        self.__set_declaration(interface.param_interfaces[index], p_declaration.points)
                    else:
                        self.__set_declaration(interface.param_interfaces[index], p_declaration)

        if not interface.declaration.clean_declaration:
            interface.declaration = declaration

    def __import_source_analysis(self, analysis, avt):
        self.logger.info("Import modules init and exit functions")
        self.__import_inits_exits(analysis, avt)

        self.logger.info("Extract complete types definitions")
        self.__extract_types(analysis)

        self.logger.info("Determine categories from extracted types")
        categories = self.__extract_categories()

        self.logger.info("Merge interface categories from both interface categories specification and modules "
                         "interface specification")
        self.__merge_categories(categories)

        self.logger.info("Remove useless interfaces")
        self.__remove_interfaces()

        self.logger.info("Both specifications are imported and categories are merged")

    def __import_inits_exits(self, analysis, avt):
        self.logger.debug("Move module initilizations functions to the modules interface specification")
        deps = {}
        for module, dep in avt['deps'].items():
            deps[module] = list(sorted(dep))
        order = tarjan.calculate_load_order(self.logger, deps)
        order_c_files = []
        for module in order:
            for module2 in avt['grps']:
                if module2['id'] != module:
                    continue
                order_c_files.extend([file['in file'] for file in module2['cc extra full desc files']])
        if "init" in analysis:
            self._inits = [(module, analysis['init'][module]) for module in order_c_files if module in analysis["init"]]
        if len(self._inits) == 0:
            raise ValueError('There is no module initialization function provided')

        self.logger.debug("Move module exit functions to the modules interface specification")
        if "exit" in analysis:
            self._exits = list(reversed([(module, analysis['exit'][module]) for module in order_c_files if module in analysis['exit']]))
        if len(self._exits) == 0:
            self.logger.warning('There is no module exit function provided')

    def __extract_types(self, analysis):
        entities = []
        # todo: this section below is slow enough
        if 'global variable initializations' in analysis:
            self.logger.info("Import types from global variables initializations")
            for variable in sorted(analysis["global variable initializations"],
                                   key=lambda var: str(var['declaration'])):
                variable_name = extract_name(variable['declaration'])
                if not variable_name:
                    raise ValueError('Global variable without a name')

                signature = import_declaration(variable['declaration'])
                if type(signature) is Structure or type(signature) is Array or type(signature) is Union:
                    entity = {
                        "path": variable['path'],
                        "description": variable,
                        "root value": variable_name,
                        "root type": None,
                        "root sequence": [],
                        "type": signature
                    }
                    signature.add_implementation(
                        variable_name,
                        variable['path'],
                        None,
                        None,
                        []
                    )
                    entities.append(entity)
            self.__import_entities(entities)

        if 'kernel functions' in analysis:
            self.logger.info("Import types from kernel functions")
            for function in sorted(analysis['kernel functions'].keys()):
                self.logger.debug("Parse signature of function {}".format(function))
                declaration = import_declaration(analysis['kernel functions'][function]['signature'])

                if function in self.kernel_functions:
                    self.__set_declaration(self.get_kernel_function(function), declaration)
                else:
                    new_intf = KernelFunction(function, analysis['kernel functions'][function]['header'])
                    new_intf.declaration = declaration
                    self._set_kernel_function(new_intf)

                self.get_kernel_function(function).files_called_at.\
                    update(set(analysis['kernel functions'][function]["called at"]))

        # Remove dirty declarations
        self._refine_interfaces()

        # Import modules functions
        modules_functions = {}
        if 'modules functions' in analysis:
            self.logger.info("Import modules functions and implementations from kernel functions calls in it")
            for function in [name for name in sorted(analysis["modules functions"].keys())
                             if 'files' in analysis["modules functions"][name]]:
                modules_functions[function] = {}
                module_function = analysis["modules functions"][function]
                for path in sorted(module_function["files"].keys()):
                    self.logger.debug("Parse signature of function {} from file {}".format(function, path))
                    modules_functions[function][path] = \
                        {'declaration': import_declaration(module_function["files"][path]["signature"])}

                    if "called at" in module_function["files"][path]:
                        modules_functions[function][path]["called at"] = \
                            set(module_function["files"][path]["called at"])
                    if "calls" in module_function["files"][path]:
                        modules_functions[function][path]['calls'] = module_function["files"][path]['calls']
                        for kernel_function in [name for name in sorted(module_function["files"][path]["calls"].keys())
                                                if name in self.kernel_functions]:
                            kf = self.get_kernel_function(kernel_function)
                            for call in module_function["files"][path]["calls"][kernel_function]:
                                kf.add_call(function)

                                for index in [index for index in range(len(call))
                                              if call[index] and
                                              check_null(kf.declaration, call[index])]:
                                    new = kf.declaration.parameters[index].\
                                        add_implementation(call[index], path, None, None, [])
                                    if len(kf.param_interfaces) > index and kf.param_interfaces[index]:
                                        new.fixed_interface = kf.param_interfaces[index].identifier

        self.logger.info("Remove kernel functions which are not called at driver functions")
        for function in self.kernel_functions:
            obj = self.get_kernel_function(function)
            if len(obj.functions_called_at) == 0:
                self._remove_kernel_function(function)

        self._modules_functions = modules_functions

    def __import_entities(self, entities):
        while len(entities) > 0:
            entity = entities.pop()
            bt = entity["type"]

            if "value" in entity["description"] and type(entity["description"]['value']) is str:
                if check_null(bt, entity["description"]["value"]):
                    bt.add_implementation(
                        entity["description"]["value"],
                        entity["path"],
                        entity["root type"],
                        entity["root value"],
                        entity["root sequence"]
                    )
                else:
                    self.logger.debug('Skip null pointer value for function pointer {}'.format(bt.to_string('%s')))
            elif "value" in entity["description"] and type(entity["description"]['value']) is list:
                if type(bt) is Array:
                    for entry in entity["description"]['value']:
                        if not entity["root type"]:
                            new_root_type = bt
                        else:
                            new_root_type = entity["root type"]

                        e_bt = bt.element
                        new_sequence = list(entity["root sequence"])
                        new_sequence.append(entry['index'])

                        new_desc = {
                            "type": e_bt,
                            "description": entry,
                            "path": entity["path"],
                            "root type": new_root_type,
                            "root value": entity["root value"],
                            "root sequence": new_sequence
                        }

                        entities.append(new_desc)
                elif type(bt) is Structure or type(bt) is Union:
                    for entry in sorted(entity["description"]['value'], key=lambda key: str(key['field'])):
                        if not entity["root type"] and not entity["root value"]:
                            new_root_type = bt
                            new_root_value = entity["description"]["value"]
                        else:
                            new_root_type = entity["root type"]
                            new_root_value = entity["root value"]

                        field = extract_name(entry['field'])
                        # Ignore actually unions and structures without a name
                        if field:
                            e_bt = import_declaration(entry['field'], None)
                            e_bt.add_parent(bt)
                            new_sequence = list(entity["root sequence"])
                            new_sequence.append(field)

                            new_desc = {
                                "type": e_bt,
                                "description": entry,
                                "path": entity["path"],
                                "root type": new_root_type,
                                "root value": new_root_value,
                                "root sequence": new_sequence
                            }

                            bt.fields[field] = e_bt
                            entities.append(new_desc)
                else:
                    raise NotImplementedError
            else:
                raise TypeError('Expect list or string')

    @staticmethod
    def __add_to_processing(element, process_list, category):
        if element not in process_list and element not in category['containers']:
            process_list.append(element)
        else:
            return

    @staticmethod
    def __add_interface_candidate(element, e_type, category):
        if element in category[e_type]:
            return
        else:
            category[e_type].append(element)

    def __add_callback(self, signature, category, identifier=None):
        if not identifier:
            identifier = signature.identifier

        if identifier not in category['callbacks']:
            category['callbacks'][identifier] = signature

            for parameter in [p for p in signature.points.parameters if type(p) is not str]:
                self.__add_interface_candidate(parameter, 'resources', category)

    def __not_violate_specification(self, declaration1, declaration2):
        intf1 = self.resolve_interface_weakly(declaration1, None, False)
        intf2 = self.resolve_interface_weakly(declaration2, None, False)

        if intf1 and intf2:
            categories1 = set([intf.category for intf in intf1])
            categories2 = set([intf.category for intf in intf2])

            if len(categories1.symmetric_difference(categories2)) == 0:
                return True
            else:
                return False
        else:
            return True

    def __extract_categories(self):
        structures = [self._types[name] for name in sorted(self._types.keys()) if type(self._types[name]) is Structure
                      and len([self._types[name].fields[nm] for nm in sorted(self._types[name].fields.keys())
                               if self._types[name].fields[nm].clean_declaration]) > 0]
        categories = []

        while len(structures) > 0:
            container = structures.pop()
            category = {
                "callbacks": {},
                "containers": [],
                "resources": []
            }

            to_process = [container]
            while len(to_process) > 0:
                tp = to_process.pop()

                if type(tp) is Structure or type(tp) is Union:
                    c_flag = False
                    for field in sorted(tp.fields.keys()):
                        if type(tp.fields[field]) is Pointer and \
                                (type(tp.fields[field].points) is Array or
                                 type(tp.fields[field].points) is Structure) and \
                                self.__not_violate_specification(tp.fields[field].points, tp):
                            self.__add_to_processing(tp.fields[field].points, to_process, category)
                            c_flag = True
                        if type(tp.fields[field]) is Pointer and type(tp.fields[field].points) is Function:
                            self.__add_callback(tp.fields[field], category, field)
                            c_flag = True
                        elif (type(tp.fields[field]) is Array or type(tp.fields[field]) is Structure) and \
                                self.__not_violate_specification(tp.fields[field], tp):
                            self.__add_to_processing(tp.fields[field], to_process, category)
                            c_flag = True

                    if tp in structures:
                        del structures[structures.index(tp)]
                    if c_flag:
                        self.__add_interface_candidate(tp, 'containers', category)
                elif type(tp) is Array:
                    if type(tp.element) is Pointer and \
                            (type(tp.element.points) is Array or
                             type(tp.element.points) is Structure) and \
                            self.__not_violate_specification(tp.element.points, tp):
                        self.__add_to_processing(tp.element.points, to_process, category)
                        self.__add_interface_candidate(tp, 'containers', category)
                    elif type(tp.element) is Pointer and type(tp.element) is Function:
                        self.__add_callback(tp.element, category)
                        self.__add_interface_candidate(tp, 'containers', category)
                    elif (type(tp.element) is Array or type(tp.element) is Structure) and \
                            self.__not_violate_specification(tp.element, tp):
                        self.__add_to_processing(tp.element, to_process, category)
                        self.__add_interface_candidate(tp, 'containers', category)
                if (type(tp) is Array or type(tp) is Structure) and len(tp.parents) > 0:
                    for parent in tp.parents:
                        if (type(parent) is Structure or
                                type(parent) is Array) and self.__not_violate_specification(parent, tp):
                            self.__add_to_processing(parent, to_process, category)
                        elif type(parent) is Pointer and len(parent.parents) > 0:
                            for ancestor in parent.parents:
                                if (type(ancestor) is Structure or
                                        type(ancestor) is Array) and self.__not_violate_specification(ancestor, tp):
                                    self.__add_to_processing(ancestor, to_process, category)

            if len(category['callbacks']) > 0:
                categories.append(category)

            # todo: default registration and deregistrations may need categories based on function pointers directly
            #       passed to kernel functions (feature #6568)
        return categories

    def __resolve_or_add_interface(self, signature, category, constructor):
        interface = self.resolve_interface(signature, category, False)
        if len(interface) == 0:
            interface = constructor(category, signature.pretty_name)
            self.logger.debug("Create new interface '{}' with signature '{}'".
                              format(interface.identifier, signature.identifier))
            interface.declaration = signature
            self._set_intf(interface)
            interface = [interface]
        elif len(interface) > 1:
            for intf in interface:
                intf.declaration = signature
        else:
            interface[-1].declaration = signature
        return interface

    def __new_callback(self, declaration, category, identifier):
        if type(declaration) is Pointer and type(declaration.points) is Function:
            probe_identifier = "{}.{}".format(category, identifier)
            if probe_identifier in self.interfaces:
                identifier = declaration.pretty_name

            interface = Callback(category, identifier)
            self.logger.debug("Create new interface '{}' with signature '{}'".
                              format(interface.identifier, declaration.identifier))
            interface.declaration = declaration
            self._set_intf(interface)
            return interface
        else:
            raise TypeError('Expect function pointer to create callback object')

    def __get_field_candidates(self, container):
        changes = True
        while changes:
            changes = False
            for field in [field for field in container.declaration.fields if field not in container.field_interfaces]:
                intf = self.__match_interface_for_container(container.declaration.fields[field], container.category,
                                                            field)
                if intf:
                    container.field_interfaces[field] = intf
                    changes = True

    def __match_interface_for_container(self, signature, category, id_match):
        candidates = self.resolve_interface_weakly(signature, category, False)

        if len(candidates) == 1:
            return candidates[0]
        elif len(candidates) == 0:
            return None
        else:
            strict_candidates = self.resolve_interface(signature, category, False)
            if len(strict_candidates) == 1:
                return strict_candidates[0]
            elif len(strict_candidates) > 1 and id_match:
                id_candidates = [intf for intf in strict_candidates if intf.short_identifier == id_match]
                if len(id_candidates) == 1:
                    return id_candidates[0]
                else:
                    return None

            if len(strict_candidates) > 1:
                raise RuntimeError('There are several interfaces with the same declaration {}'.
                                   format(signature.to_string('a')))

            # Filter of resources
            candidates = [intf for intf in candidates if type(intf) is not Resource]
            if len(candidates) == 1:
                return candidates[0]
            else:
                return None

    def __merge_categories(self, categories):
        self.logger.info("Try to find suitable interface descriptions for found types")
        for category in categories:
            category_identifier = self.__yield_existing_category(category)
            if not category_identifier:
                category_identifier = self.__yield_new_category(category)

            # Add containers and resources
            self.logger.info("Found interfaces for category {}".format(category_identifier))
            for signature in category['containers']:
                if type(signature) is not Array and type(signature) is not Structure:
                    raise TypeError('Expect structure or array to create container object')
                interface = self.__resolve_or_add_interface(signature, category_identifier, Container)
                if len(interface) > 1:
                    raise TypeError('Cannot match two containers with the same type')
                else:
                    interface = interface[-1]

                # Refine field interfaces
                for field in sorted(interface.field_interfaces.keys()):
                    if not interface.field_interfaces[field].declaration.clean_declaration and \
                            interface.declaration.fields[field].clean_declaration:
                        interface.field_interfaces[field].declaration = interface.declaration.fields[field]
                    elif not interface.field_interfaces[field].declaration.clean_declaration:
                        del interface.field_interfaces[field]
            for signature in category['resources']:
                intf = self.resolve_interface_weakly(signature, category_identifier, False)
                if len(intf) == 0:
                    interface = self.__resolve_or_add_interface(signature, category_identifier, Resource)
                    if len(interface) > 1:
                        raise TypeError('Cannot match two resources with the same type')

            # Add callbacks
            for identifier in sorted(category['callbacks'].keys()):
                candidates = self.resolve_interface(category['callbacks'][identifier], category_identifier, False)

                if len(candidates) > 0:
                    containers = self.select_containers(identifier, category['callbacks'][identifier],
                                                        category_identifier)
                    if len(containers) == 1 and identifier in containers[-1].field_interfaces and \
                            containers[-1].field_interfaces[identifier] in candidates:
                        containers[-1].field_interfaces[identifier].declaration = category['callbacks'][identifier]
                    elif len(containers) == 1 and identifier not in containers[-1].field_interfaces:
                        intf = self.__new_callback(category['callbacks'][identifier], category_identifier, identifier)
                        containers[-1].field_interfaces[identifier] = intf
                    else:
                        self.__new_callback(category['callbacks'][identifier], category_identifier, identifier)
                else:
                    self.__new_callback(category['callbacks'][identifier], category_identifier, identifier)

            # Resolve array elements
            for container in [cnt for cnt in self.containers(category_identifier) if cnt.declaration and
                              type(cnt.declaration) is Array and not cnt.element_interface]:
                intf = self.__match_interface_for_container(container.declaration.element, container.category, None)
                if intf:
                    container.element_interface = intf

            # Resolve structure interfaces
            for container in [cnt for cnt in self.containers(category_identifier) if cnt.declaration and
                              type(cnt.declaration) is Structure]:
                self.__get_field_candidates(container)

            # Resolve callback parameters
            for callback in self.callbacks(category_identifier):
                self._fulfill_function_interfaces(callback, category_identifier)

            # Resolve kernel function parameters
            for function in [self.get_kernel_function(name) for name in self.kernel_functions]:
                self._fulfill_function_interfaces(function)

        # Refine dirty declarations
        self._refine_interfaces()

    def __yield_existing_category(self, category):
        category_identifier = None
        for interface_category in ["containers"]:
            if category_identifier:
                break
            for signature in category[interface_category]:
                interface = self.resolve_interface(signature, False)
                if len(interface) > 0 and interface[-1].category not in self._locked_categories:
                    category_identifier = interface[-1].category
                    break
        for interface_category in ["callbacks"]:
            if category_identifier:
                break
            for signature in sorted(list(category[interface_category].values()), key=lambda y: y.identifier):
                interface = self.resolve_interface(signature, False)
                if len(interface) > 0 and interface[-1].category not in self._locked_categories:
                    category_identifier = interface[-1].category
                    break

        return category_identifier

    def __yield_new_category(self, category):
        category_identifier = None
        for interface_category in ["containers", "resources"]:
            if category_identifier:
                break
            for signature in category[interface_category]:
                if signature.pretty_name not in self.categories:
                    category_identifier = signature.pretty_name
                    break

        if category_identifier:
            return category_identifier
        else:
            raise ValueError('Cannot find a suitable category identifier')

    def __remove_interfaces(self):
        # Remove categories without implementations
        self.logger.info("Calculate relevant interfaces")
        relevant_interfaces = self.__calculate_relevant_interfaces()

        for interface in [self.get_intf(name) for name in self.interfaces]:
            if interface not in relevant_interfaces:
                self.logger.debug("Delete interface description {} as unrelevant".format(interface.identifier))
                self._del_intf(interface.identifier)

    def __calculate_relevant_interfaces(self):
        def __check_category_relevance(function):
            relevant = []

            if function.rv_interface:
                relevant.append(function.rv_interface)
            for parameter in function.param_interfaces:
                if parameter:
                    relevant.append(parameter)

            return relevant

        relevant_interfaces = set()

        # If category interfaces are not used in kernel functions it means that this structure is not transferred to
        # the kernel or just source analysis cannot find all containers
        # Add kernel function relevant interfaces
        for name in self.kernel_functions:
            relevant_interfaces.update(__check_category_relevance(self.get_kernel_function(name)))

        # Add all interfaces for non-container categories
        for interface in set(relevant_interfaces):
            containers = self.containers(interface.category)
            if len(containers) == 0:
                relevant_interfaces.update([self.get_intf(name) for name in self.interfaces
                                            if self.get_intf(name).category == interface.category])

        # Add callbacks and their resources
        for callback in self.callbacks():
            containers = self.resolve_containers(callback, callback.category)
            if len(containers) > 0 and len(self.implementations(callback)) > 0:
                relevant_interfaces.add(callback)
                relevant_interfaces.update(__check_category_relevance(callback))
            elif len(containers) == 0 and len(self.implementations(callback)) > 0 and \
                    callback.category in {i.category for i in relevant_interfaces}:
                relevant_interfaces.add(callback)
                relevant_interfaces.update(__check_category_relevance(callback))
            elif len(containers) > 0 and len(self.implementations(callback)) == 0:
                for container in containers:
                    if self.get_intf(container) in relevant_interfaces and \
                            len(self.get_intf(container).declaration.implementations) == 0:
                        relevant_interfaces.add(callback)
                        relevant_interfaces.update(__check_category_relevance(callback))
                        break

        # Add containers
        add_cnt = 1
        while add_cnt != 0:
            add_cnt = 0
            for container in [cnt for cnt in self.containers() if cnt not in relevant_interfaces]:
                if type(container.declaration) is Structure:
                    match = False

                    for f_intf in [container.field_interfaces[name] for name
                                   in sorted(container.field_interfaces.keys())]:
                        if f_intf and f_intf in relevant_interfaces:
                            match = True
                            break

                    if match:
                        relevant_interfaces.add(container)
                        add_cnt += 1
                elif type(container.declaration) is Array:
                    if container.element_interface in relevant_interfaces:
                        relevant_interfaces.add(container)
                        add_cnt += 1
                else:
                    raise TypeError('Expect structure or array container')

        return relevant_interfaces


class SpecEncoder(json.JSONEncoder):

    def default(self, object):
        # todo: this does not work currently (issue #6561)
        fd = {}

        if type(object) is ModuleCategoriesSpecification:
            # Dump kernel functions
            fd["kernel functions"] = {}
            for function in object.kernel_functions:
                fd["kernel functions"][function] = {
                    "signature": object.kernel_functions[function]["signature"].get_string(),
                    "header": list(object.kernel_functions[function]["files"].keys())[0]
                }

            # todo: Dump macro-functions
            # todo: Dump macros

            # Dump categories
            fd["categories"] = {}
            for category in object.categories:
                fd["categories"][category] = {
                    "containers": {},
                    "callbacks": {},
                    "resources": {}
                }

                # Add containers
                for container in object.categories[category]["containers"]:
                    fd["categories"][category]["containers"][container] = {
                        "signature": None
                    }

                    if object.categories[category]["containers"][container].header:
                        fd["categories"][category]["containers"][container]["header"] = \
                            object.categories[category]["containers"][container].header

                    fd["categories"][category]["containers"][container]["signature"] = \
                        object.categories[category]["containers"][container].signature.get_string()

                    fd["categories"][category]["containers"][container]["fields"] = \
                        object.categories[category]["containers"][container].fields

                # Add function pointers
                for callback in object.categories[category]["callbacks"]:
                    fd["categories"][category]["callbacks"][callback] = {
                        "signature": object.categories[category]["callbacks"][callback].signature.get_string()
                    }

                # Add resources
                for resource in object.categories[category]["resources"]:
                    fd["categories"][category]["resources"][resource] = {}

                    if resource not in object.categories[category]["containers"]:
                        fd["categories"][category]["resources"][resource]["signature"] = \
                            object.categories[category]["resources"][resource].signature.get_string()

                # todo: Add implementations
                # todo: Add init, exit functions
        else:
            raise NotImplementedError("Cannot encode unknown object with type {}".format(str(type(object))))

        return fd

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
