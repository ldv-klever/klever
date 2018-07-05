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

from core.vtg.emg.common import get_conf_property
from core.vtg.emg.common.interface import Container, Resource, Callback
from core.vtg.emg.common.signature import Declaration, Function, Structure, Union, Array, Pointer, extracted_types
from core.vtg.emg.interfacespec.specification import fulfill_function_interfaces


def yield_categories(collection, conf):
    """
    Analyze all new types found by SA component and yield final set of interface categories built from manually prepared
    interface specifications and global variables. All new categories and interfaces are added directly to the
    InterfaceCategoriesSpecification object. Also all types declarations are updated according with new imported C
    types. However, there are still unused interfaces present in the collection after this function termination.

    :param collection: InterfaceCategoriesSpecification object.
    :param conf: Configuration property dictionary of InterfaceCategoriesSpecification object.
    :return: None
    """

    # Extract dependencies between containers and callbacks that are stored in containers
    container_sets, container_callbacks = __distribute_container_types()

    # Distribute sets of containers and create new categories if necessaary
    if get_conf_property(conf, "generate artificial categories", bool):
        __generate_new_categories(collection, container_sets, container_callbacks)

    # Add information about callbacks
    __populate_callbacks(collection)

    # Add resources
    __populate_resources(collection)

    # Complement interface references
    __complement_interfaces(collection)

    return


def __distribute_container_types():
    container_sets = list()
    container_callbacks = dict()
    processed = list()

    def add_container(current_set, cont):
        # Do nothing if it is processed
        if cont in processed and cont not in current_set:
            # Check presence in other sets
            merged = False
            for candidate_set in container_sets:
                if cont in candidate_set:
                    # Merge current and procerssed one collection
                    candidate_set.extend(current_set)
                    current_set = candidate_set
                    merged = True
                    break

            # New extended containers set will be anyway added, so remove reduced it version from the collection
            if merged:
                container_sets.remove(current_set)
            else:
                current_set.append(cont)
        elif cont not in current_set:
            current_set.append(cont)

        return current_set

    def add_to_processing(current_set, queue, declaration):
        # Just add a declaration to queue for further processing in the context of current set propcessing
        if declaration not in queue and declaration not in current_set:
            queue.append(declaration)

    def add_callback(cont, fld, callback):
        if cont.identifier not in container_callbacks:
            container_callbacks[cont.identifier] = dict()
        if fld not in container_callbacks[cont.identifier]:
            container_callbacks[cont.identifier][fld] = callback

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

    return container_sets, container_callbacks


def __generate_new_categories(collection, containers_set, callbacks_set):
    # Match existing container with existing categories and remove them from the set
    for cset in containers_set:
        for container in list(cset):
            if container.identifier in callbacks_set:
                # Remove only if a container has been found
                intfs = collection.resolve_interface(container, use_cache=False)
                container_intfs = [i for i in intfs if isinstance(i, Container)]

                if len(container_intfs) > 0:
                    cset.remove(container)
            else:
                # Do not track containers without callbacks
                cset.remove(container)

    # Create new categories from rest containers with callbacks. Do not merge anythging to make heuristical categories
    # simpler
    for cset in containers_set:
        for container in (c for c in cset if c.identifier in callbacks_set):
            if container.pretty_name not in collection.categories:
                category = container.pretty_name
            else:
                category = 'ldv_' + container.pretty_name

            if category in collection.categories:
                raise RuntimeError('Cannot find uniwue name for category {!r}'.format(category))
            interface = Container(category, container.pretty_name)
            interface.declaration = container
            collection.set_intf(interface)

    return


def __populate_callbacks(collection):
    for container in (c for c in collection.containers() if isinstance(c.declaration, Structure)):
        for field in (f for f in container.declaration.fields if isinstance(container.declaration.fields[f], Pointer)
                      and isinstance(container.declaration.fields[f].points, Function)
                      and f not in container.field_interfaces):
            declaration = container.declaration.fields[field]
            if "{}.{}".format(container.category, field) not in collection.interfaces:
                identifier = field
            elif "{}.{}".format(container.category, declaration.pretty_name) not in collection.interfaces:
                identifier = declaration.pretty_name
            else:
                raise RuntimeError("Cannot yield identifier for callback {!r} of category {!r}".
                                   format(declaration.identifier, container.category))

            interface = Callback(container.category, identifier)
            interface.declaration = declaration
            collection.set_intf(interface)

    return


def __populate_resources(collection):
    # Iterate over categories
    for category in collection.categories:
        usage = dict()

        # Extract callbacks
        for callback in collection.callbacks(category):
            for parameter in (p for i, p in enumerate(callback.declaration.points.parameters)
                              if isinstance(p, Declaration) and p.clean_declaration and
                              not (len(callback.param_interfaces) > i and callback.param_interfaces[i])):
                if parameter.identifier in usage:
                    usage[parameter.identifier]["counter"] += 1
                else:
                    # Try to resolve interface
                    intfs = collection.resolve_interface_weakly(parameter, category=callback.category, use_cache=False)
                    if len(intfs) == 0:
                        # Only unmatched resources should be introduced
                        usage[parameter.identifier] = {
                            "counter": 1,
                            "declaration": parameter
                        }

        # Introduce new resources
        for declaration in (usage[i]["declaration"] for i in usage if usage[i]["counter"] > 1):
            if "{}.{}".format(category, declaration.pretty_name) not in collection.interfaces:
                identifier = declaration.pretty_name
            elif "{}.{}".format(category, 'ldv_' + declaration.pretty_name) not in collection.interfaces:
                identifier = 'ldv_' + declaration.pretty_name
            else:
                raise RuntimeError("Cannot yield identifier for callback {!r} of category {!r}".
                                   format(declaration.identifier, category))

            interface = Resource(category, identifier)
            interface.declaration = declaration
            collection.set_intf(interface)

    return


def __complement_interfaces(collection):
    def __match_interface_for_container(signature, category, id_match):
        candidates = collection.resolve_interface_weakly(signature, category, use_cache=False)
        if len(candidates) == 1:
            return candidates[0]
        elif len(candidates) == 0:
            return None
        else:
            strict_candidates = collection.resolve_interface(signature, category, use_cache=False)
            if len(strict_candidates) == 1:
                return strict_candidates[0]
            elif len(strict_candidates) > 1 and id_match:
                id_candidates = [i for i in strict_candidates if i.short_identifier == id_match]
                if len(id_candidates) == 1:
                    return id_candidates[0]
                else:
                    return None

            if len(strict_candidates) > 1:
                raise RuntimeError('There are several interfaces with the same declaration {}'.
                                   format(signature.to_string('a')))

            # Filter of resources
            candidates = [i for i in candidates if type(i) is not Resource]
            if len(candidates) == 1:
                return candidates[0]
            else:
                return None

    # Resolve callback parameters
    for callback in collection.callbacks():
        fulfill_function_interfaces(collection, callback, callback.category)

    # Resolve kernel function parameters
    for function in (collection.get_kernel_function(name) for name in collection.kernel_functions):
        fulfill_function_interfaces(collection, function)

    # Refine dirty declarations
    collection.refine_interfaces()

    # Remove dirty declarations in container references and add additional clean one
    for container in collection.containers():
        # Refine field interfaces
        for field in list(container.field_interfaces.keys()):
            if not container.field_interfaces[field].declaration.clean_declaration and \
                    container.declaration.fields[field].clean_declaration:
                container.field_interfaces[field].declaration = container.declaration.fields[field]
            elif not container.field_interfaces[field].declaration.clean_declaration:
                del container.field_interfaces[field]

    # Resolve array elements
    for container in (cnt for cnt in collection.containers() if cnt.declaration and
                      isinstance(cnt.declaration, Array) and not cnt.element_interface):
        intf = __match_interface_for_container(container.declaration.element, container.category, None)
        if intf:
            container.element_interface = intf

    # Resolve structure interfaces
    for container in (cnt for cnt in collection.containers() if cnt.declaration and
                      isinstance(cnt.declaration, Structure)):
        for field in container.declaration.fields:
            if field not in container.field_interfaces:
                intf = __match_interface_for_container(container.declaration.fields[field], container.category,
                                                       field)
                if intf:
                    container.field_interfaces[field] = intf

            if field in container.field_interfaces and isinstance(container.field_interfaces[field], Callback) and \
                    isinstance(container.declaration.fields[field], Pointer) and \
                    isinstance(container.declaration.fields[field].points, Function) and \
                    container.declaration.fields[field].clean_declaration and \
                    isinstance(container.field_interfaces[field].declaration, Pointer) and \
                    isinstance(container.field_interfaces[field].declaration.points, Function):
                # Track implementations from structures if types slightly differs and attached to structure variable
                container.field_interfaces[field].declaration = container.declaration.fields[field]

    return

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
