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

from klever.core.vtg.emg.common.c.types import Declaration, Function, Array, Pointer, Primitive
from klever.core.vtg.emg.generators.linuxModule.interface import Resource, Callback, StructureContainer, \
    FunctionInterface, ArrayContainer


def yield_categories(logger, conf, collection, sa):
    """
    Analyze all new types found by SA component and yield final set of interface categories built from manually prepared
    interface specifications and global variables. All new categories and interfaces are added directly to the
    InterfaceCategoriesSpecification object. Also all types declarations are updated according with new imported C
    types. However, there are still unused interfaces present in the collection after this function termination.

    :param logger: Logger object.
    :param conf: Configuration dict.
    :param collection: InterfaceCategoriesSpecification object.
    :param sa: Source object.
    """

    # Add resources
    if conf.get("generate new resource interfaces"):
        __populate_resources(collection)

    # Complement interface references
    __complement_interfaces(logger, collection)

    logger.info("Determine unrelevant to the checked code interfaces and remove them")
    __refine_categories(logger, conf, collection, sa)


def __populate_resources(collection):
    # Iterate over categories
    for category in collection.categories:
        usage = sortedcontainers.SortedDict()

        # Extract callbacks
        for callback in collection.callbacks(category):
            for parameter in (p for i, p in enumerate(callback.declaration.points.parameters)
                              if isinstance(p, Declaration) and
                              not (len(callback.param_interfaces) > i and callback.param_interfaces[i])):
                if str(parameter) in usage:
                    usage[str(parameter)]["counter"] += 1
                elif not collection.resolve_interface_weakly(parameter, category=callback.category, use_cache=False):
                    # Only unmatched resources should be introduced
                    usage[str(parameter)] = {
                        "counter": 1,
                        "declaration": parameter
                    }

        # Introduce new resources
        for declaration in (usage[i]["declaration"] for i in usage if usage[i]["counter"] > 1):
            if "{}.{}".format(category, declaration.pretty_name) not in collection.interfaces:
                identifier = declaration.pretty_name
            elif "{}.{}".format(category, 'emg_' + declaration.pretty_name) not in collection.interfaces:
                identifier = 'emg_' + declaration.pretty_name
            else:
                raise RuntimeError("Cannot yield identifier for callback {!r} of category {!r}".
                                   format(str(declaration), category))

            interface = Resource(category, identifier)
            interface.declaration = declaration
            collection.set_intf(interface)


def __fulfill_function_interfaces(logger, collection, interface, category=None):
    """
    Check an interface declaration (function or function pointer) and try to match its return value type and
    parameters arguments types with existing interfaces. The algorithm should be the following:

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
        # todo: Implement check against arrays of primitives
        return isinstance(decl, Primitive) or (isinstance(decl, Pointer) and isinstance(decl.points, Primitive)) or \
            decl == 'void *' or decl == 'void **'

    # Check declaration type
    if isinstance(interface, Callback):
        declaration = interface.declaration.points
    elif isinstance(interface, FunctionInterface):
        declaration = interface.declaration
    else:
        raise TypeError("Expect pointer to function or function declaration but got {!r}".
                        format(str(type(interface.declaration).__name__)))

    # Second match rest types
    if not interface.rv_interface and declaration.return_value and not is_primitive_or_void(declaration.return_value):
        rv_interface = collection.resolve_interface(declaration.return_value, category, False)
        if len(rv_interface) == 0:
            rv_interface = collection.resolve_interface_weakly(declaration.return_value, category, False)
        if len(rv_interface) == 1:
            interface.rv_interface = rv_interface[-1]
        elif len(rv_interface) > 1:
            logger.warning(
                'Interface {!r} return value signature {!r} can be match with several following interfaces: {}'.
                format(interface.name, str(declaration.return_value), ', '.join((str(i) for i in rv_interface))))

    for index, param in enumerate(declaration.parameters):
        if not (len(interface.param_interfaces) > index and interface.param_interfaces[index]) and \
                not isinstance(param, str) and \
                not is_primitive_or_void(param):
            p_interface = collection.resolve_interface(param, category, False)
            if len(p_interface) == 0:
                p_interface = collection.resolve_interface_weakly(param, category, False)
            if len(p_interface) == 1:
                p_interface = p_interface[0]
            elif len(p_interface) == 0:
                p_interface = None
            else:
                logger.warning(
                    'Interface {!r} parameter in the position {} with signature {!r} can be match with several '
                    'following interfaces: {}'.
                    format(interface.name, index, str(param),
                           ', '.join((str(i) for i in p_interface))))
                p_interface = None

            interface.set_param_interface(index, p_interface)

            if p_interface and not category:
                category = p_interface.category


def __complement_interfaces(logger, collection):
    def __match_interface_for_container(signature, category, id_match):
        candidates = collection.resolve_interface_weakly(signature, category, use_cache=False)
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) == 0:
            return None

        strict_candidates = collection.resolve_interface(signature, category, use_cache=False)
        if len(strict_candidates) == 1:
            return strict_candidates[0]
        if len(strict_candidates) > 1 and id_match:
            id_candidates = [i for i in strict_candidates if i.name == id_match]
            if len(id_candidates) == 1:
                return id_candidates[0]

            return None

        if len(strict_candidates) > 1:
            raise RuntimeError("There are several interfaces with the same declaration {!r}".
                               format(signature.to_string('a')))

        # Filter of resources
        candidates = [i for i in candidates if not isinstance(i, Resource)]
        if len(candidates) == 1:
            return candidates[0]

        return None

    # Resolve callback parameters
    for callback in collection.callbacks():
        __fulfill_function_interfaces(logger, collection, callback, callback.category)

    # Resolve kernel function parameters
    for func in collection.function_interfaces:
        __fulfill_function_interfaces(logger, collection, func)

    # todo: Remove dirty declarations in container references and add additional clean one

    # Resolve array elements
    for container in (cnt for cnt in collection.containers() if cnt.declaration and
                      isinstance(cnt.declaration, Array) and not cnt.element_interface):
        intf = __match_interface_for_container(container.declaration.element, container.category, None)
        if intf:
            container.element_interface = intf

    # Resolve structure interfaces
    for container in (cnt for cnt in collection.containers() if cnt.declaration and isinstance(cnt, StructureContainer)):
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


def __refine_categories(logger, conf, collection, sa):
    def __check_category_relevance(func):
        relevant = []

        if func.rv_interface:
            relevant.append(func.rv_interface)
        for parameter in func.param_interfaces:
            if parameter:
                relevant.append(parameter)

        return relevant

    # Remove categories without implementations
    relevant_interfaces = set()

    # If category interfaces are not used in kernel functions it means that this structure is not transferred to
    # the kernel or just source analysis cannot find all containers
    # Add kernel function relevant interfaces
    for intf in (i for i in collection.function_interfaces if i.name in sa.source_functions):
        intfs = __check_category_relevance(intf)
        # Skip resources from kernel functions
        relevant_interfaces.update([i for i in intfs if not isinstance(i, Resource)])
        relevant_interfaces.add(intf)

    # Add all interfaces for non-container categories
    for interface in set(relevant_interfaces):
        containers = collection.containers(interface.category)
        if not containers:
            relevant_interfaces.update([collection.get_intf(name) for name in collection.interfaces
                                        if collection.get_intf(name).category == interface.category])

    # Add callbacks and their resources
    for callback in collection.callbacks():
        containers = collection.resolve_containers(callback, callback.category)
        if len(containers) > 0 and len(callback.implementations) > 0:
            relevant_interfaces.add(callback)
            relevant_interfaces.update(__check_category_relevance(callback))
        elif len(containers) == 0 and len(callback.implementations) > 0 and \
                callback.category in {i.category for i in relevant_interfaces}:
            relevant_interfaces.add(callback)
            relevant_interfaces.update(__check_category_relevance(callback))
        elif len(containers) > 0 and len(callback.implementations) == 0:
            for container in containers:
                if collection.get_intf(container) in relevant_interfaces and \
                                len(collection.get_intf(container).implementations) == 0:
                    relevant_interfaces.add(callback)
                    relevant_interfaces.update(__check_category_relevance(callback))
                    break

    # Add containers
    add_cnt = 1
    while add_cnt != 0:
        add_cnt = 0
        for container in [cnt for cnt in collection.containers() if cnt not in relevant_interfaces]:
            if isinstance(container, StructureContainer):
                match = False

                for f_intf in [container.field_interfaces[name] for name in container.field_interfaces]:
                    if f_intf and f_intf in relevant_interfaces:
                        match = True
                        break

                if match:
                    relevant_interfaces.add(container)
                    add_cnt += 1
            elif isinstance(container, ArrayContainer):
                if container.element_interface in relevant_interfaces:
                    relevant_interfaces.add(container)
                    add_cnt += 1
            else:
                raise TypeError("Expect structure or array container")

    interfaces_to_delete = [str(i) for i in [collection.get_intf(name) for name in collection.interfaces]
                            if i not in relevant_interfaces]
    if "allowed categories" in conf:
        allowed_categories = set(conf.get("allowed categories"))
        logger.debug("Got a whitelist of allowed categories: {}".format(', '.join(allowed_categories)))
        assert isinstance(allowed_categories, set), "Expect a list of allowed categories"
        for intf in [str(i) for i in [collection.get_intf(name) for name in collection.interfaces]
                     if i not in collection.function_interfaces and i.category not in allowed_categories and
                     str(i) not in interfaces_to_delete]:
            interfaces_to_delete.append(intf)

        # Now check functions
        for function_intf in collection.function_interfaces:
            relevant_categories = {i.category for i in __check_category_relevance(function_intf)}
            if not allowed_categories.intersection(relevant_categories):
                interfaces_to_delete.append(str(function_intf))

    logger.debug("Delete irrelevant interface descriptions: {}".format(', '.join(interfaces_to_delete)))
    for interface_name in interfaces_to_delete:
        collection.del_intf(interface_name)

    logger.debug('Finally we have the following interfaces saved:')
    for category in collection.categories:
        for interface_kind in ('containers', 'callbacks', 'resources'):
            getter = getattr(collection, interface_kind)
            interface_names = tuple(map(str, getter(category)))
            if interface_names:
                logger.debug(f"{interface_kind.capitalize()} of '{category}': {', '.join(interface_names)}")
