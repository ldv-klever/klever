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
from core.vtg.emg.common.c.types import Declaration, Function, Structure, Array, Pointer, Primitive
from core.vtg.emg.processGenerator.linuxModule.interface import Resource, Callback, StructureContainer, \
    FunctionInterface


def yield_categories(collection):
    """
    Analyze all new types found by SA component and yield final set of interface categories built from manually prepared
    interface specifications and global variables. All new categories and interfaces are added directly to the
    InterfaceCategoriesSpecification object. Also all types declarations are updated according with new imported C
    types. However, there are still unused interfaces present in the collection after this function termination.

    :param collection: InterfaceCategoriesSpecification object.
    :param conf: Configuration property dictionary of InterfaceCategoriesSpecification object.
    :return: None
    """

    # Add resources
    __populate_resources(collection)

    # Complement interface references
    __complement_interfaces(collection)

    return


def populate_callbacks(collection):
    for container in (c for c in collection.containers() if isinstance(c, StructureContainer)):
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
            container.field_interfaces[field] = interface

    return


def __populate_resources(collection):
    # Iterate over categories
    for category in collection.categories:
        usage = dict()

        # Extract callbacks
        for callback in collection.callbacks(category):
            for parameter in (p for i, p in enumerate(callback.declaration.points.parameters)
                              if isinstance(p, Declaration) and
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


def fulfill_function_interfaces(collection, interface, category=None):
    """
    Check an interface declaration (function or function pointer) and try to match its return value type and
    parameters arguments types with existing interfaces. The algorythm should be the following:

    * Match explicitly stated interface References (only if they meet given category).
    * Match rest parameters:
        - Avoid matching primitives and arrays and pointers of primitives;
        - Match interfaces from given category or from the category of already matched interfaces by interface
          references;
        - If there are more that one category is matched - do not do match to avoid mistakes in match.

    :param collection: InterfaceCategoriesSpecification object.
    :param interface: Interface object: KernelFunction or Callback.
    :param category: Category filter.
    :return: None.
    """

    def is_primitive_or_void(decl):
        """
        Return True if given declaration object has type of Primitive or pointer(* and **) to Primitive.

        :param decl: Declaration object
        :return: True - it is primitive, False - otherwise
        """
        # todo: Implement check agains arrays of primitives
        if isinstance(decl, Primitive) or (isinstance(decl, Pointer) and isinstance(decl.points, Primitive)) or \
                decl.identifier in {'void *', 'void **'}:
            return True
        else:
            return False

    collection.logger.debug("Try to match collateral interfaces for function '{!r}'".format(interface.identifier))
    # Check declaration type
    if isinstance(interface, Callback):
        declaration = interface.declaration.points
    elif isinstance(interface, FunctionInterface):
        declaration = interface.declaration
    else:
        raise TypeError('Expect pointer to function or function declaration but got {!r}'.
                        format(str(type(interface.declaration).__name__)))

    # Second match rest types
    if not interface.rv_interface and declaration.return_value and not is_primitive_or_void(declaration.return_value):
        rv_interface = collection.resolve_interface(declaration.return_value, category, False)
        if len(rv_interface) == 0:
            rv_interface = collection.resolve_interface_weakly(declaration.return_value, category, False)
        if len(rv_interface) == 1:
            interface.rv_interface = rv_interface[-1]
        elif len(rv_interface) > 1:
            collection.logger.warning(
                'Interface {!r} return value signature {!r} can be match with several following interfaces: {}'.
                format(interface.identifier, declaration.return_value.identifier,
                       ', '.join((i.identifier for i in rv_interface))))

    for index in range(len(declaration.parameters)):
        if not (len(interface.param_interfaces) > index and interface.param_interfaces[index]) and \
                not isinstance(declaration.parameters[index], str) and \
                not is_primitive_or_void(declaration.parameters[index]):
            p_interface = collection.resolve_interface(declaration.parameters[index], category, False)
            if len(p_interface) == 0:
                p_interface = collection.resolve_interface_weakly(declaration.parameters[index], category, False)
            if len(p_interface) == 1:
                p_interface = p_interface[0]
            elif len(p_interface) == 0:
                p_interface = None
            else:
                collection.logger.warning(
                    'Interface {!r} parameter in the position {} with signature {!r} can be match with several '
                    'following interfaces: {}'.format(interface.identifier,
                                                      index, declaration.parameters[index].identifier,
                                                      ', '.join((i.identifier for i in p_interface))))
                p_interface = None

            interface.set_param_interface(index, p_interface)

            if p_interface and not category:
                category = p_interface.category


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
    for func in collection.function_interfaces:
        fulfill_function_interfaces(collection, func)

    # todo: Remove dirty declarations in container references and add additional clean one

    # Resolve array elements
    for container in (cnt for cnt in collection.containers() if cnt.declaration and
                      isinstance(cnt.declaration, Array) and not cnt.element_interface):
        intf = __match_interface_for_container(container.declaration.element, container.category, None)
        if intf:
            container.element_interface = intf

    # Resolve structure interfaces
    for container in (cnt for cnt in collection.containers() if cnt.declaration and
                      isinstance(cnt, StructureContainer)):
        for field in container.declaration.fields:
            if field not in container.field_interfaces:
                intf = __match_interface_for_container(container.declaration.fields[field], container.category,
                                                       field)
                if intf:
                    container.field_interfaces[field] = intf

            if field in container.field_interfaces and isinstance(container.field_interfaces[field], Callback) and \
                    isinstance(container.declaration.fields[field], Pointer) and \
                    isinstance(container.declaration.fields[field].points, Function) and \
                    isinstance(container.field_interfaces[field].declaration, Pointer) and \
                    isinstance(container.field_interfaces[field].declaration.points, Function):
                # Track implementations from structures if types slightly differs and attached to structure variable
                container.field_interfaces[field].declaration = container.declaration.fields[field]

    return

