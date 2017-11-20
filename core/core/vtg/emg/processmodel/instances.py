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

from core.vtg.emg.common import check_or_set_conf_property, get_necessary_conf_property
from core.vtg.emg.common.signature import Implementation
from core.vtg.emg.common.process import Dispatch, Receive, Condition, CallRetval, Call, get_common_parameter
from core.vtg.emg.common.interface import Resource, Container


def generate_instances(logger, conf, analysis, model, instance_maps):
    entry_process, model_processes, callback_processes = yield_instances(logger, conf, analysis, model, instance_maps)

    # Generate new actions in processes
    for process in [entry_process] + model_processes + callback_processes:
        simplify_process(logger, conf, analysis, model, process)

    # todo: Save these processes instead of the old one


def simplify_process(logger, conf, analysis, model, process):
    # todo: add logging
    # todo: add new function name
    # Create maps
    label_map = dict()
    for label in (l for l in list(process.labels.values()) if l.interfaces and len(l.interfaces) > 0):
        label_map[label.name] = dict()
        simpl_access = process.resolve_access(label)
        for number, access in enumerate(simpl_access):
            declaration = label.get_declaration(access.interface.identifier)
            value = process.get_implementation(access)
            new = process.add_label("{}_{}".format(label.name, number), declaration, value=value)
            label_map[label.name][access.interface.identifier] = new

    # Then replace accesses in parameters with simplified expressions
    for action in (a for a in process.actions.values() if isinstance(a, Dispatch) or isinstance(a, Receive)):
        for index in range(len(action.parameters)):
            # Determine dispatcher parameter
            try:
                interface = get_common_parameter(action, process, index)
                interface = interface.identifier
            except RuntimeError:
                suts = [peer['interfaces'][index] for peer in action.peers
                        if 'interfaces' in peer and len(peer['interfaces']) > index]
                if len(suts) > 0:
                    interface = suts[0]
                else:
                    raise

            # Determine dispatcher parameter
            access = process.resolve_access(action.parameters[index], interface)
            new_label = label_map[access.label.name][access.interface.identifier]
            new_expression = access.access_with_label(new_label)
            action.parameters[index] = new_expression

            # Go through peers and set proper interfaces
            for peer in action.peers:
                if 'interfaces' not in peer:
                    peer['interfaces'] = list()
                if len(peer['interfaces']) == index:
                    peer['interfaces'].append(interface)
                for pr in peer['subprocess'].peers:
                    if 'interfaces' not in pr:
                        pr['interfaces'] = list()
                    if len(pr['interfaces']) == index:
                        pr['interfaces'].append(interface)

    # todo: remove callback actions
    # todo: process rest code
    return

def yield_instances(logger, conf, analysis, model, instance_maps):
    """
    Generate automata for all processes in an intermediate environment model.

    :param logger: logging initialized object.
    :param conf: Dictionary with configuration properties {'property name'->{'child property' -> {... -> value}}.
    :param analysis: ModuleCategoriesSpecification object.
    :param model: ProcessModel object.
    :param instance_maps: Dictionary {'category name' -> {'process name' ->
           {'Access.expression string'->'Interface.identifier string'->'value string'}}}.
    :return: Entry point autmaton, list with model qutomata, list with callback automata.
    """
    def yeild_identifier():
        """Return unique identifier."""
        identifier_counter = 1
        while True:
            identifier_counter += 1
            yield identifier_counter
    logger.info("Generate automata for processes with callback calls")
    identifiers = yeild_identifier()
    
    # Check configuraition properties first
    check_or_set_conf_property(conf, "max instances number", default_value=1000, expected_type=int)
    check_or_set_conf_property(conf, "instance modifier", default_value=1, expected_type=int)
    check_or_set_conf_property(conf, "instances per resource implementation", default_value=1, expected_type=int)
    instances_left = get_necessary_conf_property(conf, "max instances number")

    # Returning values
    entry_fsa, model_fsa, callback_fsa = None, list(), list()

    # Determine how many instances is required for a model
    for process in model.event_processes:
        base_list = _original_process_copies(logger, conf, analysis, process, instances_left)
        base_list = _fulfill_label_maps(logger, conf, analysis, base_list, process, instance_maps, instances_left)
        logger.info("Generate {} FSA instances for environment model processes {} with category {}".
                    format(len(base_list), process.name, process.category))

        for instance in base_list:
            instance.identifier = "{}_{}".format(instance, identifiers.__next__())
            callback_fsa.append(instance)

    # Generate automata for models
    logger.info("Generate automata for kernel model processes")
    for process in model.model_processes:
        logger.info("Generate FSA for kernel model process {}".format(process.name))
        processes = _fulfill_label_maps(logger, conf, analysis, [process], process, instance_maps, instances_left)
        for instance in processes:
            instance.identifier = "{}_{}".format(instance, identifiers.__next__())
            model_fsa.append(instance)

    # Generate state machine for init an exit
    logger.info("Generate FSA for module initialization and exit functions")
    entry_fsa = model.entry_process

    return entry_fsa, model_fsa, callback_fsa


def _original_process_copies(logger, conf, analysis, process, instances_left):
    """
    Generate process copies which would be used independently for instance creation.

    :param logger: logging initialized object.
    :param conf: Dictionary with configuration properties {'property name'->{'child property' -> {... -> value}}.
    :param analysis: ModuleCategoriesSpecification object.
    :param process: Process object.
    :param instances_left: Number of instances which EMG is still allowed to generate.
    :return: List of process copies.
    """
    # Determine max number of instances that can be generated
    original_instances = list()

    base_list = []
    if get_necessary_conf_property(conf, "instance modifier"):
        # Used by a parallel env model
        base_list.append(_copy_process(process, instances_left))
    else:
        undefined_labels = []
        # Determine nonimplemented containers
        logger.debug("Calculate number of not implemented labels and collateral values for process {} with "
                     "category {}".format(process.name, process.category))
        for label in [process.labels[name] for name in sorted(process.labels.keys())
                      if len(process.labels[name].interfaces) > 0]:
            nonimplemented_intrerfaces = [interface for interface in label.interfaces
                                          if len(analysis.implementations(analysis.get_intf(interface))) == 0]
            if len(nonimplemented_intrerfaces) > 0:
                undefined_labels.append(label)

        # Determine is it necessary to make several instances
        if len(undefined_labels) > 0:
            for i in range(get_necessary_conf_property(conf, "instance modifier")):
                base_list.append(_copy_process(process, instances_left))
        else:
            base_list.append(_copy_process(process, instances_left))

        logger.info("Prepare {} instances for {} undefined labels of process {} with category {}".
                    format(len(base_list), len(undefined_labels), process.name, process.category))

    return base_list


def _fulfill_label_maps(logger, conf, analysis, instances, process, instance_maps, instances_left):
    """
    Generate instances and finally assign to each process its instance map which maps accesses to particular
    implementations of relevant interfaces.

    :param logger: logging initialized object.
    :param conf: Dictionary with configuration properties {'property name'->{'child property' -> {... -> value}}.
    :param analysis: ModuleCategoriesSpecification object.
    :param instances: List of Process objects.
    :param process: Process object.
    :param instance_maps: Dictionary {'category name' -> {'process name' ->
           {'Access.expression string'->'Interface.identifier string'->'value string'}}}
    :param instances_left: Number of instances which EMG is still allowed to generate.
    :return: List of Process objects.
    """
    base_list = instances

    # Get map from accesses to implementations
    logger.info("Determine number of instances for process '{}' with category '{}'".
                format(process.name, process.category))

    if process.category not in instance_maps:
        instance_maps[process.category] = dict()

    if process.name in instance_maps[process.category]:
        cached_map = instance_maps[process.category][process.name]
    else:
        cached_map = None
    maps, cached_map = _split_into_instances(analysis, process,
                                             get_necessary_conf_property(conf, "instances per resource implementation"),
                                             cached_map)
    instance_maps[process.category][process.name] = cached_map

    logger.info("Going to generate {} instances for process '{}' with category '{}'".
                format(len(maps), process.name, process.category))
    new_base_list = []
    for access_map in maps:
        for instance in base_list:
            newp = _copy_process(instance, instances_left)
            newp.allowed_implementations = access_map
            new_base_list.append(newp)

    return new_base_list


def _copy_process(process, instances_left):
    """
    Return a copy of a process. The copy is not recursive and Process object would has the same objects in its
    attributes.

    :param process: Process object.
    :param instances_left: Number of instances which EMG is still allowed to generate.
    :return: Process object copy.
    """
    inst = copy.copy(process)
    if instances_left == 0:
        raise RuntimeError('EMG tries to generate more instances than it is allowed by configuration')
    elif instances_left:
        instances_left -= 1

    inst.allowed_implementations = dict(process.allowed_implementations)
    return inst


def _split_into_instances(analysis, process, resource_new_insts, simplified_map=None):
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

    # Generate access maps itself with base values only
    maps = []
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
    for expression in sorted(access_map.keys()):
        for interface in sorted(access_map[expression].keys()):
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
                    strict_suits = sorted(
                                   [value for value in interface_to_value[interface]
                                    if value not in total_chosen_values and
                                    (len(interface_to_value[interface][value]) == 0 or
                                     len(chosen_values.intersection(interface_to_value[interface][value])) > 0 or
                                     len([cv for cv in interface_to_value[interface][value]
                                          if cv not in value_to_implementation and cv not in chosen_values]) > 0)])
                    if len(strict_suits) == 0:
                        # If values are repeated just choose random one
                        suits = sorted(
                                [value for value in interface_to_value[interface]
                                 if len(interface_to_value[interface][value]) == 0 or
                                 len(chosen_values.intersection(interface_to_value[interface][value])) > 0 or
                                 (len([cv for cv in interface_to_value[interface][value]
                                       if cv not in value_to_implementation and cv not in chosen_values]) > 0)])
                        if len(suits) > 0:
                            suits = [suits.pop()]
                    else:
                        suits = strict_suits

                    if len(suits) == 1:
                        amap[expression][interface] = value_to_implementation[suits[0]]
                        chosen_values.add(suits[0])
                        total_chosen_values.add(suits[0])
                    elif len(suits) > 1:
                        # There can be many useless resource implementations ...
                        interface_obj = analysis.get_intf(interface)
                        if type(interface_obj) is Resource and resource_new_insts > 0:
                            suits = suits[0:resource_new_insts]
                        elif type(interface_obj) is Container:
                            # Ignore additional container values which does not influence the other interfaces
                            suits = [v for v in suits if v in basevalue_to_value and len(basevalue_to_value) > 0]
                        else:
                            # Try not to repeate values
                            suits = [v for v in suits if v not in total_chosen_values]

                        value_map = _match_array_maps(expression, interface, suits, maps, interface_to_value,
                                                      value_to_implementation)
                        intf_additional_maps.extend(
                            _fulfil_map(expression, interface, value_map, [[amap, chosen_values]],
                                        value_to_implementation, total_chosen_values, interface_to_value))

            # Add additional maps
            maps.extend(intf_additional_maps)

    if type(simplified_map) is list:
        # Forbid pointer implementations
        complete_maps = maps
        maps = []

        # Set proper given values
        for index, value in enumerate(simplified_map):
            smap = value[0]
            instance_map = dict()
            used_values = set()

            for expression in sorted(smap.keys()):
                instance_map[expression] = dict()

                for interface in sorted(smap[expression].keys()):
                    if smap[expression][interface]:
                        instance_map[expression][interface] = value_to_implementation[smap[expression][interface]]
                        used_values.add(smap[expression][interface])
                    elif complete_maps[index][0][expression][interface]:
                        # To avoid calls by pointer
                        instance_map[expression][interface] = ''
                    else:
                        instance_map[expression][interface] = smap[expression][interface]
            maps.append([instance_map, used_values])
    else:
        # Prepare simplified map with values instead of Implementation objects
        simplified_map = list()
        for smap, cv in maps:
            instance_desc = [dict(), list(cv)]

            for expression in sorted(smap.keys()):
                instance_desc[0][expression] = dict()
                for interface in sorted(smap[expression].keys()):
                    if smap[expression][interface]:
                        instance_desc[0][expression][interface] = smap[expression][interface].value
                    else:
                        instance_desc[0][expression][interface] = smap[expression][interface]
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
    for container_id in [container_id for container_id in sorted(list(options_interfaces))
                         if len([value for value in interface_to_value[container_id]
                                 if value in basevalue_to_value]) > 0]:
        # Collect all child values
        summary_values = set()
        summary_interfaces = set()
        original_options = set()

        for value in [value for value in sorted(list(interface_to_value[container_id])) if value in basevalue_to_value]:
            summary_values.update(basevalue_to_value[value])
            summary_interfaces.update(basevalue_to_interface[value])
            original_options.add(value)

        # Greedy add implementations to fill all child values
        fulfilled_values = set()
        fulfilled_interfaces = set()
        final_set = set()
        original_options = sorted(sorted(original_options), key=lambda v: len(basevalue_to_value[v]), reverse=True)
        while len(fulfilled_values) != len(summary_values) or len(fulfilled_interfaces) != len(summary_interfaces):
            value = sorted(set(summary_values - fulfilled_values)).pop()
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
    final_options_list = sorted(sorted(options), key=lambda o: containers_impacts[o], reverse=True)

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
                for e in (e for e in sorted(mp.keys()) if type(mp[e]) is dict):
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

    for value in sorted(value_map.keys()):
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
