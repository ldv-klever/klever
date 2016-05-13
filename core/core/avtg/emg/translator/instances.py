def split_into_instances(analysis, process):
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
    :return: Dictionary: {'Access.expression string'->'Interface.identifier string'->'Implementation object/None'}.
    """
    access_map = {}

    accesses = process.accesses()
    interface_to_value, value_to_implementation, interface_to_expression, final_options_list = \
        _extract_implementation_dependencies(analysis, access_map, accesses)

    # Generate access maps itself with base values only
    maps = []
    total_chosen_values = set()
    if len(final_options_list) > 0:
        ivector = [0 for i in enumerate(final_options_list)]
        for _ in enumerate(interface_to_value[final_options_list[0]]):
            new_map = dict(access_map)
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
        # Choose at least one map
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
                new = [dict(maps[0][0]), set(maps[0][1])]
                new[1].remove(new[0][expression][interface])
                new[0][expression][interface] = None
                maps.append(new)

            for amap, chosen_values in ([m, s] for m, s in maps if not m[expression][interface]):
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
                    # Expect that this caused by an array
                    # todo: remember arrays to choose the same for such values
                    additional_maps = [[dict(amap), set(chosen_values)] for i in range(len(suits) - 1)]

                    # Fulfill existing instance
                    first = suits.pop()
                    amap[expression][interface] = value_to_implementation[first]
                    chosen_values.add(first)
                    total_chosen_values.add(first)

                    # Fulfill new instances
                    for additional_value in suits:
                        nm, ncv = additional_maps.pop()

                        hidden_container_values = sorted([cv for cv in interface_to_value[interface][additional_value]
                                                          if cv not in value_to_implementation])
                        if len(hidden_container_values) > 0:
                            first_random = hidden_container_values.pop()
                            ncv.add(first_random)
                            total_chosen_values.add(first_random)

                        nm[expression][interface] = value_to_implementation[additional_value]
                        ncv.add(additional_value)
                        total_chosen_values.add(additional_value)

                        intf_additional_maps.append([nm, ncv])

            # Add additional maps
            maps.extend(intf_additional_maps)

    return (m for m, cv in maps)


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
        for value in [value for value in interface_to_value[container_id] if value in basevalue_to_value]:
            summary_values.update(basevalue_to_value[value])
            summary_interfaces.update(basevalue_to_interface[value])

        # Greedy add implementations to fill all child values
        fulfilled_values = set()
        fulfilled_interfaces = set()
        final_set = set()
        original_options = reversed(list(sorted(list([v for v in interface_to_value[container_id] if v in
                                                      basevalue_to_value]),
                                                key=lambda v: len(basevalue_to_value[v]))))
        while len(fulfilled_values) != len(summary_values) and len(fulfilled_interfaces) != len(summary_interfaces):
            value = set(summary_values - fulfilled_values).pop()

            for option in original_options:
                if value in basevalue_to_value[option]:
                    final_set.add(option)
                    fulfilled_values.update(basevalue_to_value[option])
                    fulfilled_interfaces.update(basevalue_to_interface[option])
                    break

        containers_impacts[container_id] = len(final_set)
        # Keep values with base values anyway
        final_set.update([value for value in interface_to_value[container_id]
                          if len(interface_to_value[container_id][value]) > 0])
        interface_to_value[container_id] = {val: interface_to_value[container_id][val] for val in final_set}

    # Sort options
    options = [o for o in options_interfaces if len([value for value in interface_to_value[o]
                                                     if value in basevalue_to_value]) > 0]
    final_options_list = list(reversed(sorted(options, key=lambda o: containers_impacts[o])))

    return interface_to_value, value_to_implementation, interface_to_expression, final_options_list

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
