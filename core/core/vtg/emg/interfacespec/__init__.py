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
import collections
import re

from core.vtg.emg.common.interface import Container, Resource, Callback
from core.vtg.emg.common.signature import Structure, Union, Array, Pointer, InterfaceReference, refine_declaration
from core.vtg.emg.common import get_conf_property
from core.vtg.emg.interfacespec.analysis import import_code_analysis
from core.vtg.emg.interfacespec.specification import import_interface_specification
from core.vtg.emg.interfacespec.categories import yield_categories


class InterfaceCategoriesSpecification:
    """Implements parser of source analysis and representation of module interface categories specification."""

    def __init__(self, logger, conf, avt, spec, analysis_data):
        """
        Setup initial attributes and get logger object.

        :param logger: logging object.
        :param conf: Configuration properties dictionary.
        """
        self.logger = logger
        self._conf = conf
        self._inits = collections.OrderedDict()
        self._exits = collections.OrderedDict()
        self._interfaces = dict()
        self._source_functions = dict()
        self._global_variables = dict()
        self._interface_cache = dict()
        self._implementations_cache = dict()
        self._containers_cache = dict()
        self.__deleted_interfaces = dict()
        self.__function_calls_cache = dict()

        self.logger.info("Analyze provided interface categories specification")
        import_interface_specification(self, spec)

        self.logger.info("Import results of source code analysis")

        self.logger.info("Metch interfaces with existing categories and introduce new categories")
        yield_categories(self, self._conf)

        self.logger.info("Determine unrelevant to the checked code interfaces and remove them")
        self.__refine_categories()

        self.logger.info("Both specifications are imported and categories are merged")

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
    def source_functions(self):
        """
        Return sorted list of kernel function names.

        :return: KernelFunction identifiers list.
        """
        return sorted(self._source_functions.keys())

    @property
    def categories(self):
        """
        Return a list with names of all existing categories in a deterministic order.

        :return: List of strings.
        """
        return sorted(set([self.get_intf(interface).category for interface in self.interfaces]))

    @property
    def inits(self):
        """
        Returns names of module initialization functions and files where they has been found.

        :return: List [filename1, initname1, filename2, initname2, ...]
        """
        return [(module, self._inits[module]) for module in self._inits]

    @property
    def exits(self):
        """
        Returns names of module exit functions and files where they has been found.

        :return: List [filename1, exitname1, filename2, exitname2, ...]
        """
        return [(module, self._exits[module]) for module in self._exits]

    def add_init(self, module, function_name):
        """
        Add Linux module initialization function.

        :param module: Module kernel object name string.
        :param function_name: Initialization function name string.
        :return: None
        """
        if module in self._inits and function_name != self._inits[module]:
            raise KeyError("Cannot set two initialization functions for a module {!r}".format(module))
        elif module not in self._inits:
            self._inits[module] = function_name

    def add_exit(self, module, function_name):
        """
        Add Linux module exit function.

        :param module: Linux module kernel object name string.
        :param function_name: Function name string.
        :return: None
        """
        if module in self._exits and function_name != self._exits[module]:
            raise KeyError("Cannot set two exit functions for a module {!r}".format(module))
        elif module not in self._exits:
            self._exits[module] = function_name

    def get_intf(self, identifier):
        """
        Provides an interface from the interface collection by a given identifier.

        :param identifier: Interface object identifier string.
        :return: Interface object.
        """
        return self._interfaces[identifier]

    def set_intf(self, new_obj):
        """
        Set new interface object in the collection.

        :param new_obj: Interface object
        :return: None
        """
        self._interfaces[new_obj.identifier] = new_obj

    def get_source_function(self, name, path=None):
        """
        Provides function by a given name from the collection.

        :param name: Source function name.
        :param path: Scope of the function.
        :return: SourceFunction object.
        """
        if name and name in self._source_functions:
            if path and path in self._source_functions[name]:
                return self._source_functions[name][path]
            elif not path and len(self._source_functions[name]) == 1:
                return self._source_functions[name].values()[0]
        return None

    def get_source_functions(self, name):
        """
        Provides all functions by a given name from the collection.

        :param name: Source function name.
        :param path: Scope of the function.
        :return: Pairs with the path and SourceFunction object.
        """
        if name and name in self._source_functions:
            result = []
            for func in self._source_functions[name].values():
                if func not in result:
                    result.append(func)
            return result
        return None

    def set_source_function(self, new_obj, path):
        """
        Replace an object in kernel function collection.

        :param new_obj: Kernel function object.
        :return: KernelFunction object.
        """
        self._source_functions[new_obj.identifier][path] = new_obj

    def remove_source_function(self, name):
        """
        Del kernel function from the collection.

        :param name: Kernel function name.
        :return: KernelFunction object.
        """
        del self._source_functions[name]

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

    def del_intf(self, identifier):
        """
        Search for an interface provided by an identifier in the main collection and return corresponding object.

        :param identifier:
        :return: Interface object.
        """
        self.__deleted_interfaces[identifier] = self._interfaces[identifier]
        del self._interfaces[identifier]

    def collect_relevant_models(self, func):
        """
        Collects all kernel functions which can be called in a callstack of a provided module function.

        :param func: Module function name string.
        :return: List with kernel functions name strings.
        """
        self.logger.debug("Collect relevant functions called in a call stack of callback '{}'".format(func))
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
            self.logger.debug('Cache hit')
            relevant = self.__function_calls_cache[func]

        return sorted(relevant)

    def find_relevant_function(self, parameter_interfaces):
        """
        Get a list of options of function parameters (interfaces) and tries to find a kernel function which would
        has a prameter from each provided set in its parameters.

        :param parameter_interfaces: List with lists of Interface objects.
        :return: List with dictionaries:
                 {"function" -> 'KernelFunction obj', 'parameters' -> [Interfaces objects]}.
        """
        matches = []
        for func in self.source_functions:
            for function_obj in self.get_source_functions(func):
                if len(function_obj.called_at) > 0:
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
                                params.append(found)
                        if suits == len(parameter_interfaces):
                            match["parameters"] = params
                            matches.append(match)
        return matches

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

    def get_global_var_declaration(self, name, file, original=False):
        """
        Return declaration as a string or object for given global variable name.

        :param name: String.
        :param file: File name.
        :param original: If true returns string of an original declaration.
        :return: None or Str or Signature.
        """
        tn = self.refined_name(name)
        if tn and tn in self._global_variables and file in self._global_variables[tn]:
            if original:
                return self._global_variables[tn][file]['original declaration']
            else:
                return self._global_variables[tn][file]['declaration']
        else:
            return None

    def get_modules_func_declaration(self, name, file, original=False):
        """
        Return declaration as a string or object for given function name.

        :param name: String.
        :param file: File name.
        :param original: If true returns string of an original declaration.
        :return: None or Str or Signature.
        """
        tn = self.refined_name(name)
        if tn and tn in self._modules_functions and file in self._modules_functions[tn]:
            if original:
                return self._modules_functions[tn][file]['original declaration']
            else:
                return self._modules_functions[tn][file]['declaration']
        else:
            return None

    def get_kernel_func_declaration(self, name, original=False):
        """
        Return declaration as a string or object for given function name.

        :param name: String.
        :param file: File name.
        :param original: If true returns string of an original declaration.
        :return: None or Str or Signature.
        """
        tn = self.refined_name(name)
        if tn and tn in self._kernel_functions:
            if original:
                return self._kernel_functions[tn].true_declaration
            else:
                return self._kernel_functions[tn].declaration
        else:
            return None

    def save_to_file(self, file):
        raise NotImplementedError
        # todo: export specification (issue 6561)
        # self.logger.info("First convert specification to json and then save")
        # content = json.dumps(self, ensure_ascii=False, sort_keys=True, indent=4, cls=SpecEncoder)
        #
        # with open(file, "w", encoding="utf8") as fh:
        #    fh.write(content)

    def determine_original_file(self, label_value):
        """
        Try to resolve by a given name from a global scope a module file in which the value is introduced.

        :param label_value: String expression like '& myfunc'.
        :return: File name.
        """
        label_name = self.refined_name(label_value)
        if label_name and label_name in self._modules_functions:
            # todo: if several files exist?
            return list(self._modules_functions[label_name])[0]
        raise RuntimeError("Cannot find an original file for label '{}'".format(label_value))

    def containers(self, category=None):
        """
        Return a list with deterministic order with all existing containers from a provided category or
        with containers from all categories if the first parameter has not been provided.

        :param category: Category name string.
        :return: List with Container objects.
        """
        return [self.get_intf(name) for name in self.interfaces
                if type(self.get_intf(name)) is Container and
                (not category or self.get_intf(name).category == category)]

    def callbacks(self, category=None):
        """
        Return a list with deterministic order with all existing callbacks from a provided category or
        with callbacks from all categories if the first parameter has not been provided.

        :param category: Category name string.
        :return: List with Callback objects.
        """
        return [self.get_intf(name) for name in self.interfaces
                if type(self.get_intf(name)) is Callback and
                (not category or self.get_intf(name).category == category)]

    def resources(self, category=None):
        """
        Return a list with deterministic order with all existing resources from a provided category or
        with resources from all categories if the first parameter has not been provided.

        :param category: Category name string.
        :return: List with Resource objects.
        """
        return [self.get_intf(name) for name in self.interfaces
                if type(self.get_intf(name)) is Resource and
                (not category or self.get_intf(name).category == category)]

    def uncalled_callbacks(self, category=None):
        """
        Returns a list with deterministic order which contains Callback from a given category or from all categories
        that are not called in the environment model.

        :param category: Category name string.
        :return: List with Callback objects.
        """
        return [cb for cb in self.callbacks(category) if not cb.called]

    def select_containers(self, field, signature=None, category=None):
        """
        Search for containers with a declaration of type Structure and with a provided field. If a signature parameter
        is provided than those containers are chosen which additionaly has the field with the corresponding type.
        Containers can be chosen from a provided categorty only.

        :param field: Name of the structure field to match.
        :param signature: Declaration object to match the field.
        :param category: a category name string.
        :return: List with Container objects.
        """
        self.logger.debug("Search for containers which has field '{}'".format(field))
        return [container for container in self.containers(category)
                if type(container.declaration) is Structure and
                ((field in container.field_interfaces and
                  (not signature or container.field_interfaces[
                      field].declaration.identifier == signature.identifier)) or
                 (field in container.declaration.fields and
                  (not signature or container.declaration.fields[field].identifier == signature.identifier))) and
                (not category or container.category == category)]

    def resolve_containers(self, declaration, category=None):
        """
        Tries to find containers from given category which contains an element or field of type according to
        provided declaration.

        :param declaration: Declaration of an element or a field.
        :param category:  Category name string.
        :return: List with Container objects.
        """
        self.logger.debug("Resolve containers for signature '{}'".format(declaration.identifier))
        if declaration.identifier not in self._containers_cache:
            self._containers_cache[declaration.identifier] = {}

        if category and category not in self._containers_cache[declaration.identifier]:
            self.logger.debug("Cache miss")
            cnts = self.__resolve_containers(declaration, category)
            self._containers_cache[declaration.identifier][category] = cnts
            return cnts
        elif not category and 'default' not in self._containers_cache[declaration.identifier]:
            self.logger.debug("Cache miss")
            cnts = self.__resolve_containers(declaration, category)
            self._containers_cache[declaration.identifier]['default'] = cnts
            return cnts
        elif category and category in self._containers_cache[declaration.identifier]:
            self.logger.debug("Cache hit")
            return self._containers_cache[declaration.identifier][category]
        else:
            self.logger.debug("Cache hit")
            return self._containers_cache[declaration.identifier]['default']

    def resolve_interface(self, signature, category=None, use_cache=True):
        """
        Tries to find an interface which matches a type from a provided declaration from a given category.

        :param signature: Declaration.
        :param category: Category object.
        :param use_cache: Flag that allows to use or omit cache - better to use cache only if all interfaces are
                          extracted or generated and no new types or interfaces will appear.
        :return: Returns list of Container objects.
        """
        if type(signature) is InterfaceReference and signature.interface in self.interfaces:
            return [self.get_intf(signature.interface)]
        elif type(signature) is InterfaceReference and signature.interface not in self.interfaces:
            raise KeyError('Cannot find description of interface {}'.format(signature.interface))
        else:
            self.logger.debug("Resolve an interface for signature '{}'".format(signature.identifier))
            if signature.identifier in self._interface_cache and use_cache:
                self.logger.debug('Cache hit')
            else:
                self.logger.debug('Cache miss')
                interfaces = [self.get_intf(name) for name in self.interfaces
                              if type(self.get_intf(name).declaration) is type(signature) and
                              (self.get_intf(name).declaration.identifier == signature.identifier) and
                              (not category or self.get_intf(name).category == category)]
                self._interface_cache[signature.identifier] = interfaces

            return self._interface_cache[signature.identifier]

    def resolve_interface_weakly(self, signature, category=None, use_cache=True):
        """
        Tries to find an interface which matches a type from a provided declaration from a given category. This
        function allows to match pointers to a declaration or types to which given type points.

        :param signature: Declaration.
        :param category: Category object.
        :param use_cache: Flag that allows to use or omit cache - better to use cache only if all interfaces are
                          extracted or generated and no new types or interfaces will appear.
        :return: Returns list of Container objects.
        """
        self.logger.debug("Resolve weakly an interface for signature '{}'".format(signature.identifier))
        intf = self.resolve_interface(signature, category, use_cache)
        if not intf and type(signature) is Pointer:
            intf = self.resolve_interface(signature.points, category, use_cache)
        elif not intf and type(signature) is not Pointer and signature.clean_declaration:
            intf = self.resolve_interface(signature.take_pointer, category, use_cache)
        return intf

    def implementations(self, interface, weakly=True):
        """
        Finds all implementations which are relevant toa given interface. This function finds all implementations
        available for a given declaration in interface and tries to filter out that implementations which implements
        the other interfaces with the same declaration. This can be done on base of connections with containers and
        many other assumptions.

        :param interface: Interface object.
        :param weakly: Seach for implementations in implementations of pointers to given type or in implementations
                       available for a type to which given type points.
        :return: List of Implementation objects.
        """
        self.logger.debug("Calculate implementations for interface '{}'".format(interface.identifier))
        if weakly and interface.identifier in self._implementations_cache and \
                type(self._implementations_cache[interface.identifier]['weak']) is list:
            self.logger.debug("Cache hit")
            return self._implementations_cache[interface.identifier]['weak']
        elif not weakly and interface.identifier in self._implementations_cache and \
                type(self._implementations_cache[interface.identifier]['strict']) is list:
            self.logger.debug("Cache hit")
            return self._implementations_cache[interface.identifier]['strict']
        self.logger.debug("Cache miss")

        if weakly:
            candidates = interface.declaration.weak_implementations
        else:
            candidates = [interface.declaration.implementations[name] for name in
                          sorted(interface.declaration.implementations.keys())]

        # Filter implementations with fixed interafces
        if len(candidates) > 0:
            candidates = [impl for impl in candidates
                          if not impl.fixed_interface or impl.fixed_interface == interface.identifier]

        if len(candidates) > 0:
            # Filter filter interfaces
            implementations = []
            for impl in candidates:
                cnts = self.resolve_containers(interface, interface.category)
                if len(impl.sequence) > 0 and len(cnts) > 0:
                    for cnt in sorted(list(cnts.keys())):
                        cnt_intf = self.get_intf(cnt)
                        if type(cnt_intf.declaration) is Array and cnt_intf.element_interface and \
                                interface.identifier == cnt_intf.element_interface.identifier:
                            implementations.append(impl)
                            break
                        elif (isinstance(cnt_intf.declaration, Structure) or isinstance(cnt_intf.declaration, Union)) \
                                and interface in cnt_intf.field_interfaces.values():
                            field = list(cnt_intf.field_interfaces.keys())[list(cnt_intf.field_interfaces.values()).
                                                                           index(interface)]

                            if field == impl.sequence[-1]:
                                base_value_match = not impl.base_value or \
                                                   (impl.base_value and
                                                    len([i for i in self.implementations(cnt_intf)
                                                         if (i.base_value and i.base_value == impl.base_value)
                                                         or (i.value and i.value == impl.base_value)]) > 0)
                                if base_value_match:
                                    implementations.append(impl)
                                    break
                elif len(impl.sequence) == 0 and len(cnts) == 0:
                    implementations.append(impl)

            candidates = implementations

        # Save results
        if interface.identifier not in self._implementations_cache:
            self._implementations_cache[interface.identifier] = {'weak': None, 'strict': None}

        # Sort results before saving
        candidates = sorted(candidates, key=lambda i: i.identifier)

        if weakly and not self._implementations_cache[interface.identifier]['weak']:
            self._implementations_cache[interface.identifier]['weak'] = candidates
        elif not weakly and not self._implementations_cache[interface.identifier]['strict']:
            self._implementations_cache[interface.identifier]['strict'] = candidates
        return candidates

    def refine_interfaces(self):
        """
        Try to go through all existing interfaces and their types and try to refine declarations replacing interface
        references in declarations (called dirty declarations) with particular types. Clean declarations that obtained
        after refinement cannot reference in declaration to other interfaces and thus such declarations fully correspond
        C language without any extensions. References however are still present in attributes of Interface objects and
        are not removed completely.

        :return:
        """

        # Clean declarations if it is poissible
        self.logger.debug('Clean all interface declarations from InterfaceReferences')
        clean_flag = True

        # Do refinements until nothing can be changed
        # todo: do not provide interfaces to external modules
        while clean_flag:
            clean_flag = False

            # Refine ordinary interfaces
            for interface in [self.get_intf(name) for name in self.interfaces] + \
                             [self.get_kernel_function(name) for name in self.kernel_functions]:
                if not interface.declaration.clean_declaration:
                    refined = refine_declaration(self._interfaces, interface.declaration)

                    if refined:
                        interface.declaration = refined
                        clean_flag = True

        self.logger.debug("Restore field declarations in structure declarations")
        for structure in [intf for intf in self.containers() if intf.declaration and
                          type(intf.declaration) is Structure]:
            for field in [field for field in sorted(structure.declaration.fields.keys())
                          if not structure.declaration.fields[field].clean_declaration]:
                new_declaration = refine_declaration(self._interfaces, structure.declaration.fields[field])
                if new_declaration:
                    structure.declaration.fields[field] = new_declaration

        return

    def __resolve_containers(self, target, category):
        self.logger.debug("Calculate containers for signature '{}'".format(target.identifier))

        return {container.identifier: container.contains(target) for container in self.containers(category)
                if (type(container.declaration) is Structure and len(container.contains(target)) > 0) or
                (type(container.declaration) is Array and container.contains(target))}

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

    def __refine_categories(self):
        def __check_category_relevance(function):
            relevant = []

            if function.rv_interface:
                relevant.append(function.rv_interface)
            for parameter in function.param_interfaces:
                if parameter:
                    relevant.append(parameter)

            return relevant

        # Remove categories without implementations
        self.logger.info("Calculate relevant interfaces")
        relevant_interfaces = set()

        # If category interfaces are not used in kernel functions it means that this structure is not transferred to
        # the kernel or just source analysis cannot find all containers
        # Add kernel function relevant interfaces
        for name in self.kernel_functions:
            intfs = __check_category_relevance(self.get_kernel_function(name))
            # Skip resources from kernel functions
            relevant_interfaces.update([i for i in intfs if not isinstance(i, Resource)])

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

        for interface in [self.get_intf(name) for name in self.interfaces]:
            if interface not in relevant_interfaces:
                self.logger.debug("Delete interface description {} as unrelevant".format(interface.identifier))
                self.del_intf(interface.identifier)

        return
