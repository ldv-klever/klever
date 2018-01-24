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
from core.vtg.emg.common.c.types import Declaration, Function, Structure, Array, Pointer
from core.vtg.emg.processGenerator.linuxModule.interface import Resource, Callback
from core.vtg.emg.processGenerator.linuxModule.interface.specification import fulfill_function_interfaces


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

    # Add information about callbacks
    __populate_callbacks(collection)

    # Add resources
    __populate_resources(collection)

    # Complement interface references
    __complement_interfaces(collection)

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
            candidates = [i for i in candidates if not isinstance(i, Resource)]
            if len(candidates) == 1:
                return candidates[0]
            else:
                return None

    # Resolve callback parameters
    for callback in collection.callbacks():
        fulfill_function_interfaces(collection, callback, callback.category)

    # Resolve kernel function parameters
    for func in (collection.get_source_function(name) for name in collection.source_functions
                 if collection.get_source_function(name)):
        fulfill_function_interfaces(collection, func)

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

