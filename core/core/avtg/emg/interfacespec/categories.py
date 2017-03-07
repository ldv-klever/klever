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
from core.avtg.emg.interfacespec.specification import fulfill_function_interfaces
from core.avtg.emg.common.interface import Container, Resource, Callback
from core.avtg.emg.common.signature import Function, Structure, Union, Array, Pointer, extracted_types


def yield_categories(collection):
    container_sets = __distribute_container_types(collection)
    # todo: Distribute sets of containers and create new categories if necessaary
    # todo: Add information about callbacks
    # todo: Add information about resources
    pass


def __distribute_container_types(collection):
    container_sets = list()
    container_callbacks = dict()
    processed = list()

    def add_container(current_set, container):
        # Do nothing if it is processed
        if container in processed and container not in current_set:
            # Check presence in other sets
            merged = False
            for candidate_set in container_sets:
                if container in candidate_set:
                    # Merge current and procerssed one collection
                    candidate_set.extend(current_set)
                    current_set = candidate_set
                    merged = True
                    break

            # New extended containers set will be anyway added, so remove reduced it version from the collection
            if merged:
                container_sets.remove(current_set)
            else:
                raise RuntimeError("Cannot determine container set for {!r}".format(container.identifier))
        elif container not in current_set:
            current_set.append(container)

        return current_set

    def add_to_processing(current_set, queue, declaration):
        # Just add a declaration to queue for further processing in the context of current set propcessing
        if declaration not in queue and declaration not in current_set:
            queue.append(declaration)

    def add_callback(container, field, callback):
        if container.identifier not in container_callbacks:
            container_callbacks[container.identifier] = dict()
        if field not in container_callbacks[container.identifier]:
            container_callbacks[container.identifier][field] = callback

    # All container types that has global variable implementations
    containers = [tp for name, tp in extracted_types() if (isinstance(tp, Structure) or isinstance(tp, Array) or
                                                           isinstance(tp, Union)) and
                  len(tp.implementations) > 0]
    while len(containers) > 0:
        container = containers.pop()
        to_process = [container]
        current = list()
        relevance = False

        while len(to_process) > 0:
            tp = to_process.pop()

            if isinstance(tp, Union) or isinstance(tp, Structure):
                for field in sorted(tp.fields.keys()):
                    if isinstance(tp.fields[field], Pointer) and \
                            (isinstance(tp.fields[field].points, Array) or
                             isinstance(tp.fields[field].points, Structure)):
                        add_to_processing(current, to_process, tp.fields[field].points)
                    elif isinstance(tp.fields[field], Array) or isinstance(tp.fields[field], Structure):
                        add_to_processing(current, to_process, tp.fields[field])
                    elif isinstance(tp.fields[field], Pointer) and isinstance(tp.fields[field].points, Function):
                        add_callback(tp, field, tp.fields[field])
                        relevance = True
            elif isinstance(tp, Array):
                if isinstance(tp.element, Pointer) and (isinstance(tp.element.points, Array) or
                                                        isinstance(tp.element.points, Structure)):
                    add_to_processing(current, to_process, tp.element.points)
                elif isinstance(tp.element, Array) or isinstance(tp.element, Structure):
                    add_to_processing(current, to_process, tp.element)

            # Check parents
            for parent in tp.parents + tp.take_pointer.parents:
                if isinstance(parent, Array) or isinstance(parent, Structure) or isinstance(parent, Union):
                    add_to_processing(current, to_process, parent)

            current = add_container(current, tp)

        if len(current) > 0 and relevance:
            for container in (c for c in current if c not in processed):
                processed.append(container)
                if container in containers:
                    containers.remove(container)
            container_sets.append(current)

    return container_sets


# todo remove
def __merge_categories(collection, categories):
    # todo: check that is is used
    def __resolve_or_add_interface(signature, category, constructor):
        interface = collection.resolve_interface(signature, category, False)
        if len(interface) == 0:
            interface = constructor(category, signature.pretty_name)
            collection.logger.debug("Create new interface '{}' with signature '{}'".
                              format(interface.identifier, signature.identifier))
            interface.declaration = signature
            collection.set_intf(interface)
            interface = [interface]
        elif len(interface) > 1:
            for intf in interface:
                intf.declaration = signature
        else:
            interface[-1].declaration = signature
        return interface

    # todo: check that is is used
    def __new_callback(declaration, category, identifier):
        if type(declaration) is Pointer and type(declaration.points) is Function:
            probe_identifier = "{}.{}".format(category, identifier)
            if probe_identifier in collection.interfaces:
                identifier = declaration.pretty_name

            interface = Callback(category, identifier)
            collection.logger.debug("Create new interface '{}' with signature '{}'".
                              format(interface.identifier, declaration.identifier))
            interface.declaration = declaration
            collection.set_intf(interface)
            return interface
        else:
            raise TypeError('Expect function pointer to create callback object')

    # todo: check that is is used
    def __match_interface_for_container(signature, category, id_match):
        candidates = collection.resolve_interface_weakly(signature, category, False)

        if len(candidates) == 1:
            return candidates[0]
        elif len(candidates) == 0:
            return None
        else:
            strict_candidates = collection.resolve_interface(signature, category, False)
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

    # todo: check that is is used
    def __get_field_candidates(container):
        changes = True
        while changes:
            changes = False
            for field in [field for field in container.declaration.fields if field not in container.field_interfaces]:
                intf = __match_interface_for_container(container.declaration.fields[field], container.category,
                                                            field)
                if intf:
                    container.field_interfaces[field] = intf
                    changes = True

    # todo: check that is is used
    def __yield_existing_category(category):
        category_identifier = None
        for interface_category in ["containers"]:
            if category_identifier:
                break
            for signature in category[interface_category]:
                interface = collection.resolve_interface(signature, False)
                if len(interface) > 0:
                    category_identifier = interface[-1].category
                    break
        for interface_category in ["callbacks"]:
            if category_identifier:
                break
            for signature in sorted(list(category[interface_category].values()), key=lambda y: y.identifier):
                interface = collection.resolve_interface(signature, False)
                if len(interface) > 0:
                    category_identifier = interface[-1].category
                    break

        return category_identifier

    # todo: check whether is is used
    def __yield_new_category(category):
        category_identifier = None
        for interface_category in ["containers", "resources"]:
            if category_identifier:
                break
            for signature in category[interface_category]:
                if signature.pretty_name not in collection.categories:
                    category_identifier = signature.pretty_name
                    break

        if category_identifier:
            return category_identifier
        else:
            raise ValueError('Cannot find a suitable category identifier')

    collection.logger.info("Try to find suitable interface descriptions for found types")
    for category in categories:
        category_identifier = __yield_existing_category(category)
        if not category_identifier:
            category_identifier = __yield_new_category(category)

        # Add containers and resources
        collection.logger.info("Found interfaces for category {}".format(category_identifier))
        for signature in category['containers']:
            if type(signature) is not Array and type(signature) is not Structure:
                raise TypeError('Expect structure or array to create container object')
            interface = __resolve_or_add_interface(signature, category_identifier, Container)
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
            intf = collection.resolve_interface_weakly(signature, category_identifier, False)
            if len(intf) == 0:
                interface = __resolve_or_add_interface(signature, category_identifier, Resource)
                if len(interface) > 1:
                    raise TypeError('Cannot match two resources with the same type')

        # Add callbacks
        for identifier in sorted(category['callbacks'].keys()):
            candidates = collection.resolve_interface(category['callbacks'][identifier], category_identifier, False)

            if len(candidates) > 0:
                containers = collection.select_containers(identifier, category['callbacks'][identifier],
                                                          category_identifier)
                if len(containers) == 1 and identifier in containers[-1].field_interfaces and \
                        containers[-1].field_interfaces[identifier] in candidates:
                    containers[-1].field_interfaces[identifier].declaration = category['callbacks'][identifier]
                elif len(containers) == 1 and identifier not in containers[-1].field_interfaces:
                    intf = __new_callback(category['callbacks'][identifier], category_identifier, identifier)
                    containers[-1].field_interfaces[identifier] = intf
                else:
                    __new_callback(category['callbacks'][identifier], category_identifier, identifier)
            else:
                __new_callback(category['callbacks'][identifier], category_identifier, identifier)

        # Resolve array elements
        for container in [cnt for cnt in collection.containers(category_identifier) if cnt.declaration and
                          type(cnt.declaration) is Array and not cnt.element_interface]:
            intf = __match_interface_for_container(container.declaration.element, container.category, None)
            if intf:
                container.element_interface = intf

        # Resolve structure interfaces
        for container in [cnt for cnt in collection.containers(category_identifier) if cnt.declaration and
                          type(cnt.declaration) is Structure]:
            __get_field_candidates(container)

        # Resolve callback parameters
        for callback in collection.callbacks(category_identifier):
            fulfill_function_interfaces(collection, callback, category_identifier)

        # Resolve kernel function parameters
        for function in [collection.get_kernel_function(name) for name in collection.kernel_functions]:
            fulfill_function_interfaces(collection, function)

    # Refine dirty declarations
    collection.refine_interfaces()

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
