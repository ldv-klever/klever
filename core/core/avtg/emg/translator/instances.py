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

    # Generate access maps itself
    maps = []
    ivector = [0 for i in enumerate(final_options_list)]
    for _ in enumerate(interface_to_value[final_options_list[0]]):
        new_map = dict(access_map)
        chosen_values = set()

        # Set chosen implementations
        for interface_index, identifier in enumerate(final_options_list):
            expression = interface_to_expression[identifier]
            chosen_value = list(interface_to_value[identifier].keys())[ivector[interface_index]]
            implementation = value_to_implementation[chosen_value]

            new_map[expression][identifier] = implementation
            chosen_values.add(chosen_value)

            # Iterate over values
            ivector[interface_index] += 1
            if ivector[interface_index] == len(interface_to_value[identifier]):
                ivector[interface_index] = 0

        # Then set implementations for the other accesses
        for expression in new_map:
            for interface in new_map[expression]:
                # Choose those values whose base values are already chosen
                suits = [value for value in interface_to_value[interface] if not interface_to_value[interface][value] or
                         interface_to_value[interface][value] in chosen_values]

                if len(suits) == 1:
                    new_map[expression][interface] = value_to_implementation[suits[0]]
                elif len(suits) > 1:
                    raise RuntimeError("Missed a container which provides a base value for the interface '{}'".
                                       format(interface))

        maps.append(new_map)

    return maps


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

    # Additional data
    basevalue_to_value = {}
    basevalue_to_interface = {}
    options_interfaces = set()
    array_options_interfaces = set()

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

                if impl.base_value:
                    interface_to_value[inst_access.interface.identifier][impl.value] = impl.base_value

                    if impl.base_value not in basevalue_to_value:
                        basevalue_to_value[impl.base_value] = []
                        basevalue_to_interface[impl.base_value] = set()
                    basevalue_to_value[impl.base_value].append(impl.value)

                    if inst_access.interface.identifier in basevalue_to_value[impl.base_value]:
                        array_options_interfaces.add(inst_access.interface.identifier)
                    basevalue_to_interface[impl.base_value].add(inst_access.interface.identifier)
                else:
                    interface_to_value[inst_access.interface.identifier][impl.value] = None
                    options_interfaces.add(inst_access.interface.identifier)

    # Choose greedy minimal set of container implementations which cover all relevant child interface implementations
    # (callbacks, resources ...)
    for container_id in [container_id for container_id in options_interfaces
                         if None in interface_to_value[container_id].values()]:
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
        original_options = reversed(list(sorted(list(interface_to_value[container_id].keys()),
                                                key=lambda v: len(basevalue_to_value[v]))))
        while len(fulfilled_values) != len(summary_values) and len(fulfilled_interfaces) != len(summary_interfaces):
            value = set(summary_values - fulfilled_values).pop()

            original_len = len(final_set)
            for option in original_options:
                if value in basevalue_to_value[option]:
                    final_set.add(option)
                    fulfilled_values.update(basevalue_to_value[option])
                    fulfilled_interfaces.update(basevalue_to_interface[option])
                    break
            if len(final_set) == original_len:
                raise RuntimeError('Inconsistent information about impplementations provided')

        interface_to_value[container_id] = {val: None for val in final_set}

    # Sort options
    impacts = {}
    # Impact is number of options available for the interface
    options = options_interfaces.union(array_options_interfaces)
    options = [o for o in options if len(interface_to_value[o]) > 0]
    for interface_id in options:
        impacts[interface_id] = len(interface_to_value[interface_id])
    final_options_list = list(reversed(sorted(options, key=lambda o: impacts[o])))

    return interface_to_value, value_to_implementation, interface_to_expression, final_options_list

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
