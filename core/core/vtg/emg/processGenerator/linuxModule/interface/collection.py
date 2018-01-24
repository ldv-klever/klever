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

from core.vtg.emg.common.interface import Container, Resource, Callback
from core.vtg.emg.common.signature import Structure, Array, Pointer, InterfaceReference, refine_declaration
from core.vtg.emg.processGenerator.linuxModule.interface.analysis import import_code_analysis
from core.vtg.emg.processGenerator.linuxModule.interface.specification import import_interface_specification
from core.vtg.emg.processGenerator.linuxModule.interface.categories import yield_categories


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
        self._interfaces = dict()
        self._interface_cache = dict()
        self._containers_cache = dict()
        self.__deleted_interfaces = dict()

        self.logger.info("Analyze provided interface categories specification")
        import_interface_specification(self, spec)

        self.logger.info("Import results of source code analysis")
        # todo: Fix this
        import_code_analysis(self, avt, analysis_data)

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
    def categories(self):
        """
        Return a list with names of all existing categories in a deterministic order.

        :return: List of strings.
        """
        return sorted(set([self.get_intf(interface).category for interface in self.interfaces]))

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
            if isinstance(self._interfaces[identifier], Callback):
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

    def containers(self, category=None):
        """
        Return a list with deterministic order with all existing containers from a provided category or
        with containers from all categories if the first parameter has not been provided.

        :param category: Category name string.
        :return: List with Container objects.
        """
        return [self.get_intf(name) for name in self.interfaces
                if isinstance(self.get_intf(name), Container) and
                (not category or self.get_intf(name).category == category)]

    def callbacks(self, category=None):
        """
        Return a list with deterministic order with all existing callbacks from a provided category or
        with callbacks from all categories if the first parameter has not been provided.

        :param category: Category name string.
        :return: List with Callback objects.
        """
        return [self.get_intf(name) for name in self.interfaces
                if isinstance(self.get_intf(name), Callback) and
                (not category or self.get_intf(name).category == category)]

    def resources(self, category=None):
        """
        Return a list with deterministic order with all existing resources from a provided category or
        with resources from all categories if the first parameter has not been provided.

        :param category: Category name string.
        :return: List with Resource objects.
        """
        return [self.get_intf(name) for name in self.interfaces
                if isinstance(self.get_intf(name), Resource) and
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
        return [container for container in self.containers(category)
                if isinstance(container.declaration, Structure) and
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
        if declaration.identifier not in self._containers_cache:
            self._containers_cache[declaration.identifier] = {}

        if category and category not in self._containers_cache[declaration.identifier]:
            cnts = self.__resolve_containers(declaration, category)
            self._containers_cache[declaration.identifier][category] = cnts
            return cnts
        elif not category and 'default' not in self._containers_cache[declaration.identifier]:
            cnts = self.__resolve_containers(declaration, category)
            self._containers_cache[declaration.identifier]['default'] = cnts
            return cnts
        elif category and category in self._containers_cache[declaration.identifier]:
            return self._containers_cache[declaration.identifier][category]
        else:
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
        if isinstance(signature, InterfaceReference) and signature.interface in self.interfaces:
            return [self.get_intf(signature.interface)]
        elif isinstance(signature, InterfaceReference) and signature.interface not in self.interfaces:
            raise KeyError('Cannot find description of interface {}'.format(signature.interface))
        else:
            if not (signature.identifier in self._interface_cache and use_cache):
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
        intf = self.resolve_interface(signature, category, use_cache)
        if not intf and isinstance(signature, Pointer):
            intf = self.resolve_interface(signature.points, category, use_cache)
        elif not intf and not isinstance(signature, Pointer) and signature.clean_declaration:
            intf = self.resolve_interface(signature.take_pointer, category, use_cache)
        return intf

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
            kernel_interfaces = []
            for name in self.source_functions:
                functions = self.get_source_functions(name)
                kernel_interfaces.extend(functions)
            for interface in [self.get_intf(name) for name in self.interfaces] + kernel_interfaces:
                if not interface.declaration.clean_declaration:
                    refined = refine_declaration(self._interfaces, interface.declaration)

                    if refined:
                        interface.declaration = refined
                        clean_flag = True

        self.logger.debug("Restore field declarations in structure declarations")
        for structure in [intf for intf in self.containers() if intf.declaration and
                          isinstance(intf.declaration, Structure)]:
            for field in [field for field in sorted(structure.declaration.fields.keys())
                          if not structure.declaration.fields[field].clean_declaration]:
                new_declaration = refine_declaration(self._interfaces, structure.declaration.fields[field])
                if new_declaration:
                    structure.declaration.fields[field] = new_declaration

        return

    def __resolve_containers(self, target, category):
        return {container.identifier: container.contains(target) for container in self.containers(category)
                if (isinstance(container.declaration, Structure) and len(container.contains(target)) > 0) or
                (isinstance(container.declaration, Array) and container.contains(target))}

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
        for name in (name for name in self.source_functions if self.get_source_function(name)):
            intfs = __check_category_relevance(self.get_source_function(name))
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
                if isinstance(container.declaration, Structure):
                    match = False

                    for f_intf in [container.field_interfaces[name] for name
                                   in sorted(container.field_interfaces.keys())]:
                        if f_intf and f_intf in relevant_interfaces:
                            match = True
                            break

                    if match:
                        relevant_interfaces.add(container)
                        add_cnt += 1
                elif isinstance(container.declaration, Array):
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
