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

import copy

from core.avtg.emg.common.interface import Container, Resource, Callback, KernelFunction
from core.avtg.emg.common.signature import InterfaceReference, Primitive, Array, Function, Structure, Pointer, Union, \
    refine_declaration, import_declaration


class CategoriesSpecification:
    """
    Parser and importer of a interface categories specification which should be provided to a EMG plugin.
    """

    ####################################################################################################################
    # PUBLIC METHODS
    ####################################################################################################################

    @property
    def categories(self):
        """
        Return a list with names of all existing categories in a deterministic order.

        :return: List of strings.
        """
        return sorted(set([self.get_intf(interface).category for interface in self.interfaces]))

    def import_specification(self, specification):
        """
        Starts specification import.

        First it creates Interface objects for each container, resource and callback in specification and then imports
        kernel functions matching their parameters with already imported interfaces.
        :param specification: Dictionary with content of a JSON specification prepared manually.
        :return: None
        """
        self.logger.info("Analyze provided interface categories specification")
        for category in sorted(specification["categories"]):
            self.logger.debug("Found interface category {}".format(category))
            self.__import_category_interfaces(category, specification["categories"][category])

            if 'extensible' in specification["categories"][category] and \
                    not specification["categories"][category]['extensible']:
                self._locked_categories.add(category)

        if "kernel functions" in specification:
            self.logger.info("Import kernel functions description")
            for intf in self.__import_kernel_interfaces("kernel functions", specification):
                self._set_kernel_function(intf)
                self.logger.debug("New kernel function {} has been imported".format(intf.identifier))
        else:
            self.logger.warning("Kernel functions are not provided within an interface categories specification, "
                                "expect 'kernel functions' attribute")

        # Add fields to container declaration types
        for container in self.containers():
            if type(container.declaration) is Structure:
                for field in sorted(container.field_interfaces):
                    if container.field_interfaces[field].declaration and \
                            (type(container.field_interfaces[field].declaration) is Array or
                             type(container.field_interfaces[field].declaration) is Structure):
                        if container.declaration.fields[field].pointer:
                            container.declaration.fields[field] = \
                                container.field_interfaces[field].declaration.take_pointer
                        if container.declaration not in container.declaration.fields[field].parents:
                            container.declaration.fields[field].parents.append(container.declaration)

        # todo: import "kernel macro-functions" (issue #6573)

        # Refine "dirty" declarations
        self._refine_interfaces()

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
                  (not signature or container.field_interfaces[field].declaration.identifier == signature.identifier)) or
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
                if len(impl.sequence) > 0:
                    cnts = self.resolve_containers(interface)
                    for cnt in sorted(list(cnts.keys())):
                        cnt_intf = self.get_intf(cnt)
                        if type(cnt_intf.declaration) is Array and cnt_intf.element_interface and \
                                interface.identifier == cnt_intf.element_interface.identifier:
                            implementations.append(impl)
                            break
                        elif (type(cnt_intf.declaration) is Structure or type(cnt_intf.declaration) is Union) and \
                                interface in cnt_intf.field_interfaces.values():
                            field = list(cnt_intf.field_interfaces.keys())[list(cnt_intf.field_interfaces.values()).
                                                                           index(interface)]
                            if field == impl.sequence[-1]:
                                implementations.append(impl)
                                break
                else:
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

    ####################################################################################################################
    # PRIVATE METHODS
    ####################################################################################################################

    def __resolve_containers(self, target, category):
        self.logger.debug("Calculate containers for signature '{}'".format(target.identifier))

        return {container.identifier: container.contains(target) for container in self.containers(category)
                if (type(container.declaration) is Structure and len(container.contains(target)) > 0) or
                (type(container.declaration) is Array and container.contains(target))}

    def _refine_interfaces(self):
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

    def _fulfill_function_interfaces(self, interface, category=None):
        """
        Check an interface declaration (function or function pointer) and try to match its return value type and
        parameters arguments types with existing interfaces. The algorythm should be the following:

        * Match explicitly stated interface References (only if they meet given category).
        * Match rest parameters:
            - Avoid matching primitives and arrays and pointers of primitives;
            - Match interfaces from given category or from the category of already matched interfaces by interface
              references;
            - If there are more that one category is matched - do not do match to avoid mistakes in match.

        :param interface: Interface object: KernelFunction or Callback
        :param category: Category filter
        :return: None
        """

        def is_primitive_or_void(decl):
            """
            Return True if given declaration object has type of Primitive or pointer(* and **) to Primitive.

            :param decl: Declaration object
            :return: True - it is primitive, False - otherwise
            """
            # todo: Implement check agains arrays of primitives
            if type(decl) is Primitive or \
                (type(decl) is Pointer and
                 (type(decl.points) is Primitive or decl.identifier in {'void *', 'void **'})):
                return True
            else:
                return False

        def assign_parameter_interface(function_intf, matched_intf, position):
            """
            Add matched parameter interface to the list of matched parameters. This takes care of unfilled list of
            parameters in the interface list.

            :param function_intf: KernelFunction or Callback object.
            :param matched_intf: Interface object.
            :param position: int.
            :return: None
            """
            if len(function_intf.param_interfaces) > position and not function_intf.param_interfaces[position]:
                function_intf.param_interfaces[position] = matched_intf
            else:
                function_intf.param_interfaces.append(matched_intf)

        self.logger.debug("Try to match collateral interfaces for function '{}'".format(interface.identifier))
        # Check declaration type
        if type(interface.declaration) is Pointer and type(interface.declaration.points) is Function:
            declaration = interface.declaration.points
        elif type(interface.declaration) is Function:
            declaration = interface.declaration
        else:
            raise TypeError('Expect pointer to function or function declaration but got {}'.
                            format(str(type(interface.declaration))))

        # First check explicitly stated interfaces
        if not interface.rv_interface and declaration.return_value and \
                type(declaration.return_value) is InterfaceReference and \
                declaration.return_value.interface in self.interfaces:
            interface.rv_interface = self.get_intf(declaration.return_value.interface)
        elif interface.rv_interface and not category:
            category = interface.rv_interface.category

        # Check explicit parameter interface references
        for index in range(len(declaration.parameters)):
            if not (len(interface.param_interfaces) > index and interface.param_interfaces[index]):
                if type(declaration.parameters[index]) is InterfaceReference and \
                        declaration.parameters[index].interface in self.interfaces:
                    p_interface = self.get_intf(declaration.parameters[index].interface)
                else:
                    p_interface = None

                assign_parameter_interface(interface, p_interface, index)

                if p_interface and not category:
                    category = p_interface.category

        # Second match rest types
        if not interface.rv_interface and \
                declaration.return_value and not is_primitive_or_void(declaration.return_value):
            rv_interface = self.resolve_interface(declaration.return_value, category, False)
            if len(rv_interface) == 0:
                rv_interface = self.resolve_interface_weakly(declaration.return_value, category, False)
            if len(rv_interface) == 1:
                interface.rv_interface = rv_interface[-1]
            elif len(rv_interface) > 1:
                self.logger.warning('Interface {!r} return value signature {!r} can be match with several '
                                    'following interfaces: {}'.
                                    format(interface.identifier, declaration.return_value.identifier,
                                           ', '.join((i.identifier for i in rv_interface))))

        for index in range(len(declaration.parameters)):
            if not (len(interface.param_interfaces) > index and interface.param_interfaces[index]) and \
                    type(declaration.parameters[index]) is not str and \
                    not is_primitive_or_void(declaration.parameters[index]):
                p_interface = self.resolve_interface(declaration.parameters[index], category, False)
                if len(p_interface) == 0:
                    p_interface = self.resolve_interface_weakly(declaration.parameters[index], category, False)
                if len(p_interface) == 1:
                    p_interface = p_interface[0]
                elif len(p_interface) == 0:
                    p_interface = None
                else:
                    self.logger.warning('Interface {!r} parameter in the position {} with signature {!r} can be match '
                                        'with several following interfaces: {}'.
                                        format(interface.identifier, index, declaration.parameters[index].identifier,
                                               ', '.join((i.identifier for i in p_interface))))
                    p_interface = None

                assign_parameter_interface(interface, p_interface, index)

                if p_interface and not category:
                    category = p_interface.category

    def __import_kernel_interfaces(self, category_name, collection):
        for identifier in sorted(collection[category_name].keys()):
            if "signature" not in collection[category_name][identifier]:
                raise TypeError("Specify 'signature' for kernel interface {} at {}".format(identifier, category_name))
            elif "header" not in collection[category_name][identifier] and \
                    "headers" not in collection[category_name][identifier]:
                raise TypeError("Specify 'header' for kernel interface {} at {}".format(identifier, category_name))

            self.logger.debug("Import kernel function description '{}'".format(identifier))
            if "header" in collection[category_name][identifier]:
                interface = KernelFunction(identifier, collection[category_name][identifier]["header"])
            else:
                interface = KernelFunction(identifier, collection[category_name][identifier]["headers"])

            interface.declaration = import_declaration(collection[category_name][identifier]["signature"])
            if type(interface.declaration) is Function:
                self._fulfill_function_interfaces(interface)
            else:
                raise TypeError('Expect function declaration in description of kernel function {}'.format(identifier))

            yield interface

    def __import_interfaces(self, category_name, identifier, desc, constructor):
        if "{}.{}".format(category_name, identifier) not in self.interfaces:
            self.logger.debug("Import described interface description '{}.{}'".format(category_name, identifier))
            interface = constructor(category_name, identifier, manually_specified=True)
            self._set_intf(interface)
        else:
            raise ValueError('Interface {} is described twice'.format(identifier.identifier))

        if "implemented in kernel" in desc:
            interface.implemented_in_kernel = desc["implemented in kernel"]

        if "headers" in desc:
            interface.header = desc["headers"]
        elif "header" in desc:
            interface.header = [desc["header"]]

        if "signature" in desc:
            interface.declaration = import_declaration(desc["signature"])

        if "interrupt context" in desc and desc["interrupt context"]:
            interface.interrupt_context = True

        return interface

    def __import_category_interfaces(self, category_name, dictionary):
        self.logger.debug("Initialize description for category {}".format(category_name))

        # Import interfaces
        if "containers" in dictionary:
            self.logger.debug("Import containers from a description of an interface category {}".format(category_name))
            for identifier in sorted(dictionary['containers'].keys()):
                self.__import_interfaces(category_name, identifier, dictionary["containers"][identifier], Container)
        if "resources" in dictionary:
            self.logger.debug("Import resources from a description of an interface category {}".format(category_name))
            for identifier in sorted(dictionary['resources'].keys()):
                self.__import_interfaces(category_name, identifier, dictionary["resources"][identifier], Resource)
        if "callbacks" in dictionary:
            self.logger.debug("Import callbacks from a description of an interface category {}".format(category_name))
            for identifier in sorted(dictionary['callbacks'].keys()):
                self.__import_interfaces(category_name, identifier, dictionary["callbacks"][identifier], Callback)

        if "containers" in dictionary:
            self.logger.debug("Import containers from a description of an interface category {}".format(category_name))
            for identifier in sorted(dictionary['containers'].keys()):
                fi = "{}.{}".format(category_name, identifier)
                # Import field interfaces
                if "fields" in dictionary['containers'][identifier]:
                    for field in sorted(dictionary['containers'][identifier]["fields"].keys()):
                        f_signature = import_declaration(dictionary['containers'][identifier]["fields"][field])
                        self.get_intf(fi).field_interfaces[field] = self.get_intf(f_signature.interface)
                        self.get_intf(fi).declaration.fields[field] = f_signature

        for callback in self.callbacks(category_name):
            self._fulfill_function_interfaces(callback)


__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
