import copy
from core.avtg.emg.common.interface import Resource, Container
from core.avtg.emg.common.signature import Implementation


def split_into_instances(analysis, process, resource_new_insts, simplified_map=None):
    """
    Get a process and calculate instances to get automata with exactly one implementation per interface.

    This function generates a number of instances which equals to max number of implementations available for
    an interface. For example, having 2 implementations for an intance A and 3 implementations for an instance B
    there are 3 instances will be generated. By the way only containers, interfaces without base values
    (parent containers) and implementations from the same array container are concidered for creating instances,
     since the other interfaces will get their implementations according to chosen implementations for interfaces
    mentioned above. For example there is no need to generate instances for interfaces file_operations and
    file.operations.open if implementations of the second one depends on implementations of the first one.

    Generated instance here is a just map from accesses and interfaces to particular implementations whish will be
    provided to a copy of the Process object later in translator.
    :param analysis: ModuleCategoriesSpecification object.
    :param process: Process object.
    :param resource_new_insts: Number of new instances allowed to generate for resources.
    :param simplified_map: {'Access.expression string'->'Interface.identifier string'->'value string'}
    :return: List of dictionaries with implementations:
              {'Access.expression string'->'Interface.identifier string'->'Implementation object/None'}.
             List of dictionaries with values:
              {'Access.expression string'->'Interface.identifier string'->'value string'}
    """
    access_map = {}

    accesses = process.accesses()
    interface_to_value, value_to_implementation, basevalue_to_value, interface_to_expression, final_options_list = \
        _extract_implementation_dependencies(analysis, access_map, accesses)

    # If maps are predefined try to use them
    maps = []
    if type(simplified_map) is list:
        for m, cv in simplified_map:
            instance_map = dict()
            used_values = set()
            for expression in m:
                instance_map[expression] = dict()
                for interface in m[expression]:
                    if m[expression][interface]:
                        instance_map[expression][interface] = value_to_implementation[m[expression][interface]]
                        used_values.add(m[expression][interface])
                    else:
                        instance_map[expression][interface] = m[expression][interface]
            maps.append([instance_map, used_values])
    else:
        # Generate access maps itself with base values only
        total_chosen_values = set()
        if len(final_options_list) > 0:
            ivector = [0 for i in enumerate(final_options_list)]
            for _ in enumerate(interface_to_value[final_options_list[0]]):
                new_map = copy.deepcopy(access_map)
                chosen_values = set()

                # Set chosen implementations
                for interface_index, identifier in enumerate(final_options_list):
                    expression = interface_to_expression[identifier]
                    options = list(sorted([val for val in interface_to_value[identifier]
                                           if len(interface_to_value[identifier][val]) == 0]))
                    chosen_value = options[ivector[interface_index]]
                    implementation = value_to_implementation[chosen_value]

                    # Assign only values without base values
                    if len(interface_to_value[identifier][chosen_value]) == 0:
                        new_map[expression][identifier] = implementation
                        chosen_values.add(chosen_value)
                        total_chosen_values.add(chosen_value)

                    # Iterate over values
                    ivector[interface_index] += 1
                    if ivector[interface_index] == len(options):
                        ivector[interface_index] = 0
                maps.append([new_map, chosen_values])
        else:
            # Choose atleast one map
            if len(maps) == 0:
                maps = [[access_map, set()]]

        # Then set the other values
        for expression in access_map:
            for interface in access_map[expression]:
                intf_additional_maps = []
                # If container has values which depends on another container add a map with unitialized value for the
                # container
                if access_map[expression][interface] and len([val for val in interface_to_value[interface]
                                                              if len(interface_to_value[interface][val]) != 0]) > 0:
                    new = [copy.deepcopy(maps[0][0]), copy.copy(maps[0][1])]
                    new[1].remove(new[0][expression][interface])
                    new[0][expression][interface] = None
                    maps.append(new)

                for amap, chosen_values in maps:
                    if not amap[expression][interface]:
                        # Choose those values whose base values are already chosen

                        # Try to avoid repeating values
                        strict_suits = [value for value in interface_to_value[interface]
                                        if value not in total_chosen_values and
                                        (len(interface_to_value[interface][value]) == 0 or
                                         len(chosen_values.intersection(interface_to_value[interface][value])) > 0 or
                                         len([cv for cv in interface_to_value[interface][value]
                                              if cv not in value_to_implementation and cv not in chosen_values]) > 0)]
                        if len(strict_suits) == 0:
                            # If values are repeated just choose random one
                            suits = [value for value in interface_to_value[interface]
                                     if len(interface_to_value[interface][value]) == 0 or
                                     len(chosen_values.intersection(interface_to_value[interface][value])) > 0 or
                                     (len([cv for cv in interface_to_value[interface][value]
                                           if cv not in value_to_implementation and cv not in chosen_values]) > 0)]
                            if len(suits) > 0:
                                suits = [list(sorted(suits)).pop()]
                        else:
                            suits = strict_suits

                        if len(suits) == 1:
                            amap[expression][interface] = value_to_implementation[suits[0]]
                            chosen_values.add(suits[0])
                            total_chosen_values.add(suits[0])
                        elif len(suits) > 1:
                            # Choose at least one
                            first = suits.pop()

                            # There can be many useless resource implementations ...
                            if type(analysis.interfaces[interface]) is Resource and resource_new_insts > 0:
                                suits = suits[0:resource_new_insts]
                            elif type(analysis.interfaces[interface]) is Container:
                                # Ignore additional container values which does not influence the other interfaces
                                suits = [v for v in suits if v in basevalue_to_value and len(basevalue_to_value) > 0]
                            else:
                                # Try not to repeate values
                                suits = [v for v in suits if v not in total_chosen_values]

                            # Return the first one
                            value_map = _match_array_maps(expression, interface, suits, maps, interface_to_value,
                                                          value_to_implementation)
                            intf_additional_maps.extend(_fulfil_map(expression, interface, value_map, [[amap, chosen_values]],
                                                                    value_to_implementation, total_chosen_values,
                                                                    interface_to_value))

                # Add additional maps
                maps.extend(intf_additional_maps)

        # Prepare simplified map with values instead of Implementation objects
        simplified_map = list()
        for m, cv in maps:
            instance_desc = [dict(), list(cv)]
            for expression in m:
                instance_desc[0][expression] = dict()
                for interface in m[expression]:
                    if m[expression][interface]:
                        instance_desc[0][expression][interface] = m[expression][interface].value
                    else:
                        instance_desc[0][expression][interface] = m[expression][interface]
            simplified_map.append(instance_desc)

    return [m for m, cv in maps], simplified_map


def _extract_implementation_dependencies(analysis, access_map, accesses):
    """
    This function performs the following operations:
    * Calculate relevant maps for choosing implementations for instances.
    * Detect containers with several implementations, interfaces without a containers having more than one
      implementation, interfaces having several implementations from an array.
    * Reduces a number of container implementations trying to choose only that ones which together 'cover' all relevant
      child values to reduce number of instances with the same callbacks.

    :param analysis: ModuleCategoriesSpecification object.
    :param access_map: Dictionary which is a prototype of an instance map used for process copying:
                       {'Access.expression string'->'Interface.identifier string'->'Implementation object/None'}.
    :param accesses: Process.accesses() dictionary:
                     {'Access.expression string' -> [List with Access objects with the same expression attribute]}
    :return: The following data:
    interface_to_value: Dictionary {'Interface.identifier string' -> 'Implementation.value string' ->
                                    'Implementation.base_value string'}
    value_to_implementation: Dictionary {'Implementation.value string' -> 'Implementation object'}
    basevalue_to_value: Dictionary with relevant implementations on each container value:
                        {'Value string' -> {'Set with relevant value strings'}
    interface_to_expression: Dictionary {'Interface.identifier string' -> 'Access.expression string'}
    final_options_list: List ['Interface.identifier string'] - contains sorted list of interfaces identifiers for which
    is necessary to choose implementations first (see description above). The greatest element is the first.
    """
    # Necessary data to return
    interface_to_value = {}
    value_to_implementation = {}
    interface_to_expression = {}
    basevalue_to_value = {}

    # Additional data
    basevalue_to_interface = {}
    options_interfaces = set()

    # Collect dependencies between interfaces, implem,entations and containers
    for access in sorted(accesses.keys()):
        access_map[access] = {}
        for inst_access in [inst for inst in accesses[access] if inst.interface]:
            access_map[inst_access.expression][inst_access.interface.identifier] = None
            interface_to_expression[inst_access.interface.identifier] = access

            implementations = analysis.implementations(inst_access.interface)
            interface_to_value[inst_access.interface.identifier] = {}
            for impl in implementations:
                value_to_implementation[impl.value] = impl

                if impl.value not in interface_to_value[inst_access.interface.identifier]:
                    interface_to_value[inst_access.interface.identifier][impl.value] = set()

                if impl.base_value:
                    interface_to_value[inst_access.interface.identifier][impl.value].add(impl.base_value)

                    if impl.base_value not in basevalue_to_value:
                        basevalue_to_value[impl.base_value] = []
                        basevalue_to_interface[impl.base_value] = set()
                    basevalue_to_value[impl.base_value].append(impl.value)
                    basevalue_to_interface[impl.base_value].add(inst_access.interface.identifier)
                else:
                    options_interfaces.add(inst_access.interface.identifier)

    # Choose greedy minimal set of container implementations which cover all relevant child interface implementations
    # (callbacks, resources ...)
    containers_impacts = {}
    for container_id in [container_id for container_id in options_interfaces
                         if len([value for value in interface_to_value[container_id]
                                 if value in basevalue_to_value]) > 0]:
        # Collect all child values
        summary_values = set()
        summary_interfaces = set()
        original_options = set()
        for value in [value for value in interface_to_value[container_id] if value in basevalue_to_value]:
            summary_values.update(basevalue_to_value[value])
            summary_interfaces.update(basevalue_to_interface[value])
            original_options.add(value)

        # Greedy add implementations to fill all child values
        fulfilled_values = set()
        fulfilled_interfaces = set()
        final_set = set()
        original_options = list(reversed(sorted(list(original_options), key=lambda v: len(basevalue_to_value[v]))))
        while len(fulfilled_values) != len(summary_values) or len(fulfilled_interfaces) != len(summary_interfaces):
            value = set(summary_values - fulfilled_values).pop()
            chosen_value = None

            for option in original_options:
                if value in basevalue_to_value[option]:
                    chosen_value = option
                    final_set.add(option)
                    fulfilled_values.update(basevalue_to_value[option])
                    fulfilled_interfaces.update(basevalue_to_interface[option])
                    break

            if not chosen_value:
                raise RuntimeError('Inifnite loop due to inability to cover an implementation by a container')

        containers_impacts[container_id] = len(final_set)
        # Keep values with base values anyway
        final_set.update([value for value in interface_to_value[container_id]
                          if len(interface_to_value[container_id][value]) > 0])
        interface_to_value[container_id] = {val: interface_to_value[container_id][val] for val in final_set}

    # Sort options
    options = [o for o in options_interfaces if len([value for value in interface_to_value[o]
                                                     if value in basevalue_to_value]) > 0]
    final_options_list = list(reversed(sorted(options, key=lambda o: containers_impacts[o])))

    return interface_to_value, value_to_implementation, basevalue_to_value, interface_to_expression, final_options_list


def _match_array_maps(expression, interface, values, maps, interface_to_value, value_to_implementation):
    """
    Tries to find an existing solution map for a given value which will contain another values from the same container
    from which springs a value under conideration. Function also distinguish containers from the same arrays and tries
    to not mix callbacks from such arrays of containers. Such match allows to drastically reduce number of generated
    instances especially generated for containers from arrays.

    :param expression: Expression string.
    :param interface: An interface identifier.
    :param values: List of unique values implementing the interface.
    :param maps: Existing solutions: List with elements with a list of structure:
                 [{'Access.expression string'->'Interface.identifier string'->'Implementation object/None'},
                   set{used values strings}].
    :param interface_to_value: Dictionary {'Interface.identifier string' -> 'Implementation.value string' ->
                                           'Implementation.base_value string'}
    :param value_to_implementation: Dictionary {'Implementation.value string' -> 'Implementation object'}
    :return: Map from values to solutions (if so suitable found):
             {'Value string'->[{'Access.expression string'->'Interface.identifier string'->'Implementation object/None'},
                               set{used values strings}]}
    """
    result_map = dict()
    added = []

    for value in values:
        v_implementation = value_to_implementation[value]
        result_map[value] = None

        if len(interface_to_value[interface][value]) > 0:
            suitable_map = None
            for mp, chosen_values in ((m, cv) for m, cv in maps if not m[expression][interface] and m not in added):
                for e in (e for e in mp if type(mp[e]) is dict):
                    same_container = \
                        [mp for i in mp[e] if i != interface and type(mp[e][i]) is Implementation and
                         mp[e][i].base_value and _from_same_container(v_implementation, mp[e][i])]
                    if len(same_container) > 0 and mp not in added:
                        suitable_map = [mp, chosen_values]
                        added.append(mp)
                        break
                if suitable_map:
                    break
            if suitable_map:
                result_map[value] = suitable_map
    return result_map


def _fulfil_map(expression, interface, value_map, reuse, value_to_implementation, total_chosen_values,
                interface_to_value):
    """
    Get map from values to maps (instance prototypes) and assign a value to a corresponding map, if map is not found for
    a value the function creates a new one on base of the first item in reuse parameter. Reuse parameter is used as a
    stack with an additional maps which can be used before creating new maps.

    :param expression: Expression string.
    :param interface: An interface identifier.
    :param value_map: {'Value string' ->
                       [{'Access.expression string'->'Interface.identifier string'->'Implementation object/None'},
                        set{used values strings}]}
    :param reuse: List with elements with a list of structure:
                  [{'Access.expression string'->'Interface.identifier string'->'Implementation object/None'},
                   set{used values strings}].
    :param value_to_implementation: Dictionary {'Implementation.value string' -> 'Implementation object'}.
    :param total_chosen_values: Set of already added values from all instance maps.
    :param interface_to_value: Dictionary {'Interface.identifier string' -> 'Implementation.value string' ->
                                           'Implementation.base_value string'}
    :return: List with new created elements with a list of structure:
                  [{'Access.expression string'->'Interface.identifier string'->'Implementation object/None'},
                   set{used values strings}].
    """
    new_maps = []

    if len(reuse) == 0:
        raise ValueError('Expect non-empty list of maps for instanciating from')
    first = reuse[0]

    for value in value_map:
        if value_map[value]:
            new = value_map[value]
        else:
            if len(reuse) > 0:
                new = reuse.pop()
            else:
                new = [copy.deepcopy(first[0]), copy.copy(first[1])]
                new_maps.append(new)

        new[0][expression][interface] = value_to_implementation[value]
        _add_value(interface, value, new[1], total_chosen_values, interface_to_value, value_to_implementation)

    return new_maps


def _add_value(interface, value, chosen_values, total_chosen_values, interface_to_value, value_to_implementation):
    """
    Add a given value and a corresponding container (if it can be found) to a chosen value set.

    :param interface: Interface identifier.
    :param value: Provided implementation of an interface.
    :param chosen_values: Set of already added values.
    :param total_chosen_values: Set of already added values from all instance maps.
    :param interface_to_expression: Dictionary {'Interface.identifier string' -> 'Access.expression string'}.
    :param value_to_implementation: Dictionary {'Implementation.value string' -> 'Implementation object'}.
    :return: Set with all added values (a given one plus a container if so).
    """
    added = set([value])

    chosen_values.add(value)
    total_chosen_values.add(value)

    hidden_container_values = sorted([cv for cv in interface_to_value[interface][value]
                                      if cv not in value_to_implementation])

    if len(hidden_container_values) > 0:
        first_random = hidden_container_values.pop()
        chosen_values.add(first_random)
        total_chosen_values.add(first_random)
        added.add(first_random)

    return added


def _from_same_container(a, b):
    """
    Check that two implementations spring from a one container and if it is an array check that there are belong to the
    same item.

    :param a: Implementation object.
    :param b: Implementation object which can be even that container.
    :return: True - yes, belong;
             False - no, the first value is from an another container.
    """
    types = [type(a) for a in a.sequence]
    if int in types:
        exist_array = True
    else:
        exist_array = False

    if exist_array:
        if a.base_value and b.base_value and a.base_value == b.base_value:
            iterate = min(len(a.sequence), len(b.sequence))
            if iterate > 1:
                for i in range(iterate):
                    if a.sequence[i] != b.sequence[i]:
                        return False
                    elif type(a.sequence[i]) is int:
                        return True
    else:
        if a.base_value and b.base_value and a.base_value == b.base_value:
            return True
        elif a.base_value and not b.base_value and a.base_value == b.value:
            return True

    return False

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
