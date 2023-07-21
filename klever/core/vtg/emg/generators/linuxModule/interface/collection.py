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

import sortedcontainers

from klever.core.vtg.emg.common.c.types import Pointer, Primitive
from klever.core.vtg.emg.generators.linuxModule.interface import Container, Resource, Callback, FunctionInterface


class InterfaceCollection:

    def __init__(self):
        self._interfaces = sortedcontainers.SortedDict()
        self._interface_cache = sortedcontainers.SortedDict()
        self._containers_cache = sortedcontainers.SortedDict()
        self.__deleted_interfaces = sortedcontainers.SortedDict()

    @property
    def interfaces(self):
        """
        Return sorted list of interface names.

        :return: List of Interface object identifiers.
        """
        return list(self._interfaces.keys())

    @property
    def categories(self):
        """
        Return a list with names of all existing categories in a deterministic order.

        :return: List of strings.
        """
        return sorted({self.get_intf(interface).category for interface in self.interfaces})

    def get_intf(self, identifier):
        """
        Provides an interface from the interface collection by a given identifier.

        :param identifier: Interface object identifier string.
        :return: Interface object.
        """
        return self._interfaces.get(identifier)

    def set_intf(self, new_obj):
        """
        Set new interface object in the collection.

        :param new_obj: Interface object
        :return: None
        """
        self._interfaces[str(new_obj)] = new_obj

    def is_removed_intf(self, identifier):
        """
        Returns True if there is an interface with a provided identifier in a deleted interfaces collection.

        :param identifier: Interface object identifier.
        :return: True or False.
        """
        return identifier in self.__deleted_interfaces

    def is_removed_function(self, name):
        """
        Returns True if there is an function interface with a provided identifier in a deleted interfaces collection.

        :param name: Function name string.
        :return: True or False.
        """
        return f"functions models.{name}" in self.__deleted_interfaces

    def get_or_restore_intf(self, identifier):
        """
        Search for an interface provided by an identifier in an interface collection and deleted interfaces collection
        to provide an object. If it is found as a deleted interface then it would be restored back to the main
        collection.

        :param identifier: Interface identifier
        :return: Interface object.
        """
        if identifier in self._interfaces:
            return self._interfaces[identifier]
        if identifier not in self._interfaces and identifier in self.__deleted_interfaces:
            # Restore interface itself
            self._interfaces[identifier] = self.__deleted_interfaces[identifier]
            del self.__deleted_interfaces[identifier]

            # Restore resources
            if isinstance(self._interfaces[identifier], Callback):
                for pi in (pi for pi in self._interfaces[identifier].param_interfaces if pi):
                    self.get_or_restore_intf(str(pi))

            return self._interfaces[identifier]

        raise KeyError("Unknown interface {!r}".format(identifier))

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
        return [self.get_intf(name) for name in self.interfaces if isinstance(self.get_intf(name), Container) and
                (not category or self.get_intf(name).category == category)]

    def callbacks(self, category=None):
        """
        Return a list with deterministic order with all existing callbacks from a provided category or
        with callbacks from all categories if the first parameter has not been provided.

        :param category: Category name string.
        :return: List with Callback objects.
        """
        return [self.get_intf(name) for name in self.interfaces if isinstance(self.get_intf(name), Callback) and
                (not category or self.get_intf(name).category == category)]

    def resources(self, category=None):
        """
        Return a list with deterministic order with all existing resources from a provided category or
        with resources from all categories if the first parameter has not been provided.

        :param category: Category name string.
        :return: List with Resource objects.
        """
        return [self.get_intf(name) for name in self.interfaces if isinstance(self.get_intf(name), Resource) and
                (not category or self.get_intf(name).category == category)]

    @property
    def function_interfaces(self):
        return [self.get_intf(i) for i in self.interfaces if isinstance(self.get_intf(i), FunctionInterface) and
                self.get_intf(i).category == "functions models"]

    def uncalled_callbacks(self, category=None):
        """
        Returns a list with deterministic order which contains Callback from a given category or from all categories
        that are not called in the environment model.

        :param category: Category name string.
        :return: List with Callback objects.
        """
        return [cb for cb in self.callbacks(category) if not cb.called]

    def resolve_containers(self, declaration, category=None):
        """
        Tries to find containers from given category which contains an element or field of type according to
        provided declaration.

        :param declaration: Declaration of an element or a field.
        :param category:  Category name string.
        :return: List with Container objects.
        """
        if str(declaration) not in self._containers_cache:
            self._containers_cache[str(declaration)] = sortedcontainers.SortedDict()

        if category and category not in self._containers_cache[str(declaration)]:
            cnts = self.__resolve_containers(declaration, category)
            self._containers_cache[str(declaration)][category] = cnts
            return cnts
        if not category and 'default' not in self._containers_cache[str(declaration)]:
            cnts = self.__resolve_containers(declaration, category)
            self._containers_cache[str(declaration)]['default'] = cnts
            return cnts
        if category and category in self._containers_cache[str(declaration)]:
            return self._containers_cache[str(declaration)][category]

        return self._containers_cache[str(declaration)]['default']

    def resolve_interface(self, signature, category=None, use_cache=True):
        """
        Tries to find an interface which matches a type from a provided declaration from a given category.

        :param signature: Declaration.
        :param category: Category object.
        :param use_cache: Flag that allows to use or omit cache - better to use cache only if all interfaces are
                          extracted or generated and no new types or interfaces will appear.
        :return: Returns list of Container objects.
        """
        if not (str(signature) in self._interface_cache and use_cache):
            if signature == 'void' or signature == 'void *' or isinstance(signature, Primitive):
                interfaces = []
            else:
                interfaces = [self.get_intf(name) for name in self.interfaces
                              if self.get_intf(name).declaration and self.get_intf(name).declaration == signature
                              and (not category or self.get_intf(name).category == category) and not
                              (self.get_intf(name).declaration == 'void' or
                               self.get_intf(name).declaration == 'void *' or
                               isinstance(self.get_intf(name).declaration, Primitive))]
            self._interface_cache[str(signature)] = interfaces

        return self._interface_cache[str(signature)]

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
        elif not intf and not isinstance(signature, Pointer):
            intf = self.resolve_interface(signature.take_pointer, category, use_cache)
        return intf

    def get_value_as_implementation(self, sa, value, interface_name):
        name = sa.refined_name(value)
        interface = self.get_or_restore_intf(interface_name)
        if not interface:
            raise ValueError("Unknown specified interface {!r}".format(interface_name))

        if value:
            global_obj = sa.get_source_function(name)
            if global_obj:
                file = global_obj.definition_file
            else:
                raise KeyError("There is no function {!r}".format(name))
        else:
            global_obj = sa.get_source_variable(name)
            if global_obj:
                file = global_obj.initialization_file
            else:
                raise KeyError("There is no global variable {!r}".format(name))

        implementation = interface.add_implementation(name, global_obj.declaration, file)
        return implementation

    def __resolve_containers(self, target, category):
        return {str(container): container.contains(target) for container in self.containers(category)
                if container.contains(target)}
