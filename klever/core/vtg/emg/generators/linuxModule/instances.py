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

import re
import json
import copy
import sortedcontainers

from klever.core.vtg.emg.common import c
from klever.core.vtg.emg.common import get_or_die, id_generator
from klever.core.vtg.emg.common.process.actions import Receive, Block, Signal
from klever.core.vtg.emg.common.process.serialization import CollectionEncoder
from klever.core.vtg.emg.common.c.types import Structure, Primitive, Pointer, Array, Function, import_declaration
from klever.core.vtg.emg.generators.linuxModule.interface import Implementation, Resource, Container, Callback
from klever.core.vtg.emg.generators.linuxModule.process import CallRetval, Call, ExtendedAccess, \
    ExtendedProcessCollection

_declarations = {'environment model': []}
_definitions = {'environment model': []}
_values_map = sortedcontainers.SortedDict()
_f_identifiers = id_generator()
_v_identifiers = id_generator()


def generate_instances(logger, conf, sa, interfaces, model, instance_maps):
    """
    Generate instances which are process copies and each contain unique single implementation per interface.

    :param logger: Logger object.
    :param conf: Configuration dictionary.
    :param sa: Source.
    :param interfaces: Interfaces collection.
    :param model: ProcessCollection.
    :param instance_maps: Dict
    :return: instance_maps, data.
    """
    # todo: This should be done completely in another way. First we can prepare instance maps with implementations then
    #       convert ExtendedProcesses into Processes at the same time applying instance maps. This would allow to avoid
    #       unnecessary serialization of the whole collection at the end and reduce memory usage by avoiding
    #       ExtendedProcess copying.
    model_processes, callback_processes = _yield_instances(logger, conf, sa, interfaces, model, instance_maps)

    # Now we can change names
    names = set()
    for process in callback_processes:
        # Change names into unique ones
        new_name = __add_pretty_name(logger, process, names)
        assert new_name not in names
        names.add(new_name)
    del names

    new_collection = ExtendedProcessCollection()
    new_collection.models.update({m.name: m for m in model_processes})
    new_collection.environment.update({str(p): p for p in callback_processes})

    # According to new identifiers change signals peers
    for process in new_collection.processes:
        if conf.get("convert statics to globals", True):
            _remove_statics(logger, sa, process)

    # Simplify first and set ids then dump
    new_collection.establish_peers()
    peers_cache = {}
    for process in new_collection.processes:
        _simplify_process(logger, conf, sa, interfaces, process, peers_cache, new_collection)

    model.environment = sortedcontainers.SortedDict({str(p): p for p in callback_processes})
    # todo: Here we can loose instances of model functions
    model.models = sortedcontainers.SortedDict({str(p): p for p in model_processes})
    filename = 'instances.json'

    # Save processes
    data = json.dumps(model, cls=CollectionEncoder, sort_keys=True, indent=2)
    with open(filename, mode='w', encoding='utf-8') as fp:
        fp.write(data)

    return instance_maps, data


def _simplify_process(logger, conf, sa, interfaces, process, peers_cache, new_collection):
    """
    Convert the extended processes into simple ones by replacing extensions with simple analogues.

    :param logger: Logger.
    :param conf: Dict.
    :param sa: Source.
    :param interfaces: Interfaces collection.
    :param process: ExtendedProcess.
    :param peers_cache: dict.
    :param new_collection: ExtendedProcessCollection.
    """
    logger.debug("Simplify process {!r}".format(process.name))
    # Create maps
    label_map = sortedcontainers.SortedDict()

    def get_declaration(l, a):
        decl = l.get_declaration(str(a.interface))
        impl = process.get_implementation(a)
        if impl:
            if not (impl.declaration == decl or impl.declaration.pointer_alias(decl) or
                    (isinstance(impl.declaration, Function) and impl.declaration.take_pointer == decl)):
                logger.warning(
                    "Seems that driver provides inconsistent implementation for {!r} label of {!r} process "
                    "where expected {!r} but got {!r}".format(l.name, process.name, decl.to_string(),
                                                              impl.declaration.to_string()))
                decl = impl.declaration
            val = impl.adjusted_value(decl)
        else:
            val = None
        return decl, val

    for label in (l for l in list(process.labels.values()) if l.interfaces and len(l.interfaces) > 0):
        label_map[label.name] = sortedcontainers.SortedDict()
        simpl_access = process.resolve_access(label)
        if len(simpl_access) > 1:
            for number, access in enumerate(simpl_access):
                declaration, value = get_declaration(label, access)
                new = process.add_label("{}_{}".format(label.name, number), declaration, value=value)
                label_map[label.name][str(access.interface)] = new
            del process.labels[label.name]
        elif len(simpl_access) == 1:
            access = simpl_access[0]
            declaration, value = get_declaration(label, access)
            label.declaration = declaration
            label.value = value
            label_map[label.name][str(access.interface)] = label

    # Replace array sizes. Sometimes we need to get the size of global arrays and for this purpose we write $SIZE(%label%).
    # Where %label% is an interface label that must have an implementation which is a global array. The expression above
    # should be replaces by a size number like '4'.
    for action in process.actions.filter(include={Block}):
        for pos, statement in enumerate(action.statements):
            array_size_re = r'\$SIZE\(%(\w+)%\)'
            match = re.search(array_size_re, statement)
            if match:
                size = None
                whole = match.group(0)
                label_name = match.group(1)

                access = process.resolve_access(f'%{label_name}%')
                if access:
                    access = access[0]
                    impl = process.get_implementation(access)
                    if impl:
                        if isinstance(impl.declaration, Array):
                            size = impl.declaration.size
                        elif isinstance(impl.declaration, Pointer) and isinstance(impl.declaration.points, Array):
                            size = impl.declaration.points.size

                        if not isinstance(size, int):
                            logger.warning(f'Cannot determine the size of implementation {str(impl)}')
                else:
                    logger.warning(f'Cannot determine access of the label %{str(label_name)}%')

                if not isinstance(size, int):
                    size = 0
                    logger.warning(f'Cannot determine the size of label {whole}')

                action.statements[pos] = statement.replace(whole, str(size))

    # Then replace accesses in parameters with simplified expressions
    for action in process.actions.filter(include={Signal}, exclude={CallRetval, Call}):
        peers = new_collection.peers(process, {str(action)})
        if peers:
            guards = []

            for index, param in enumerate(action.parameters):
                # Determine dispatcher parameter
                try:
                    interface = str(new_collection.get_common_parameter(action, process, index))
                except RuntimeError as e:
                    suits = peers_cache[str(process)].setdefault(action.name, [])
                    if len(suits) > index:
                        interface = suits[index]
                    else:
                        cache_repr = {p: {a: [(str(r.process), r.action.name, r.interfaces) for r in peers_cache[p][a]]
                                          for a in peers_cache[p]} for p in peers_cache}
                        raise RuntimeError(
                            f"Cannot find peers for '{str(process)}' and '{str(action)}' in '{str(cache_repr)}'") from e

                # Determine dispatch parameter
                access = process.resolve_access(param, interface)
                new_label = label_map[access.label.name][str(access.interface)]
                new_expression = access.access_with_label(new_label)
                action.parameters[index] = new_expression

                if isinstance(action, Receive) and conf.get("add registration guards", True):
                    access = process.resolve_access(new_expression)[0]
                    implementation = process.get_implementation(access)
                    if implementation and implementation.value and not \
                            (isinstance(implementation.declaration, Function) or
                             (isinstance(implementation.declaration, Pointer) and
                              isinstance(implementation.declaration.points, Function))):
                        guards.append("{} == {}".format("$ARG{}".format(index + 1),
                                                        implementation.adjusted_value(new_label.declaration)))

                # Go through peers and set proper interfaces
                for peer in peers:
                    peers_cache.setdefault(str(peer.process), {})
                    peers_cache[str(peer.process)].setdefault(action.name, [])

                    if len(peers_cache[str(peer.process)][action.name]) == index:
                        peers_cache[str(peer.process)][action.name].append(interface)

                    contr_peers = new_collection.peers(peer.process, action.name)
                    for pr in contr_peers:
                        peers_cache.setdefault(str(pr.process), {})
                        peers_cache[str(pr.process)].setdefault(action.name, [])

                        if len(peers_cache[str(pr.process)][action.name]) == index:
                            peers_cache[str(pr.process)][action.name].append(interface)

            if guards:
                if action.condition:
                    action.condition.extend(guards)
                else:
                    action.condition = guards
        else:
            # Replace it with a stub
            new = process.actions.add_condition(action.name + '_replacement', [],
                                                ["/* Skip signal {!r} as it has no peers */".format(action.name)],
                                                "Stub instead of the {!r} signal.".format(action.name))
            process.actions.replace_action(action, new)

    # Remove callback actions
    param_identifiers = id_generator()
    action_identifiers = id_generator()
    for action in list(process.actions.filter(include={Call})):
        _convert_calls_to_conds(logger, conf, sa, interfaces, process, label_map, action, action_identifiers,
                                param_identifiers)

    # Process rest code
    def code_replacement(statements):
        access_re = re.compile(r'(%\w+(?:(?:[.]|->)\w+)*%)')

        # Replace rest accesses
        final = []
        for original_stm in statements:
            # Collect duplicates
            if access_re.finditer(original_stm):
                matched = False
                tmp = sortedcontainers.SortedSet({original_stm})
                for match in access_re.finditer(original_stm):
                    new_tmp = sortedcontainers.SortedSet()
                    expression = match.group(1)
                    accesses = process.resolve_access(expression)
                    for s in tmp:
                        for acc in accesses:
                            if acc.interface:
                                nl = label_map[acc.label.name][str(acc.base_interface)]
                                s = acc.replace_with_label(s, nl)
                                new_tmp.add(s)
                                matched = True
                    if len(new_tmp) != 0:
                        tmp = new_tmp
                if not matched:
                    final.append(original_stm)
                else:
                    final.extend(list(tmp))
            else:
                final.append(original_stm)

        return final

    for action in process.actions.values():
        if isinstance(action, Block):
            # Implement statements processing
            action.statements = code_replacement(action.statements)
        if action.condition:
            action.condition = code_replacement(action.condition)

    # Now we ready to get rid of implementations but first we must add declarations to the main file
    for access in process.allowed_implementations:
        for intf in (i for i in process.allowed_implementations[access] if process.allowed_implementations[access][i]):
            implementation = process.allowed_implementations[access][intf]
            file = implementation.initialization_file
            if implementation.value not in _values_map.get(file, {}):
                # Maybe it is a variable
                svar = sa.get_source_variable(implementation.value, file)
                if svar and not (implementation.declaration.static or svar.declaration.static):
                    true_declaration = svar.declaration.to_string(svar.name, typedef='complex_and_params',
                                                                  specifiers=True, qualifiers=True)
                elif not svar:
                    # Seems that it is a function
                    sf = sa.get_source_function(implementation.value, file)
                    if sf and not (sf.static or sf.declaration.static):
                        true_declaration = sf.declaration.to_string(sf.name, typedef='complex_and_params', scope={file},
                                                                    specifiers=True, qualifiers=True)
                    elif not svar and re.match(r'[a-zA-Z_]+', implementation.value.replace('&', '').strip()):
                        # This is something from outside. Add external declaration.
                        if '&' in implementation.value and isinstance(implementation.declaration, Pointer):
                            true_declaration = implementation.declaration.points.to_string(
                                implementation.value.replace('&', '').strip(), typedef='complex_and_params',
                                scope={file}, specifiers=False, qualifiers=True)
                        else:
                            true_declaration = implementation.declaration.to_string(
                                implementation.value.strip(), typedef='complex_and_params',
                                specifiers=False, qualifiers=True)
                    else:
                        true_declaration = None
                else:
                    true_declaration = None

                # Check
                if true_declaration:
                    # Add declaration
                    if re.compile(r'^\s*static\s+').match(true_declaration):
                        true_declaration = true_declaration.replace('static', 'extern')
                    else:
                        true_declaration = 'extern ' + true_declaration
                    if ';' not in true_declaration:
                        true_declaration += ';'
                    true_declaration += '\n'
                    process.add_declaration('environment model', implementation.value, true_declaration)
                else:
                    logger.warning("There is no function or variable {!r} in module code".
                                   format(implementation.value))
            else:
                logger.warning("Skip import if an implementation {!r} and it is {}".
                               format(implementation.value,
                                      'static' if implementation.declaration.static else 'not static'))

    process.allowed_implementations = None

    # Remove unused labels
    for label in process.unused_labels:
        del process.labels[label]


def _convert_calls_to_conds(logger, conf, sa, interfaces, process, label_map, call, action_identifiers,
                            param_identifiers):
    """
    This function takes an extended Process and converts the given Call action into a Condition object as a part of
    translation of an extended Process into a common one.

    :param logger: Logger object.
    :param conf: Configuration dictionary.
    :param sa: Source object.
    :param interfaces: Interfaces collection.
    :param process: Process object.
    :param label_map: Process label map dictionary.
    :param call: Call object.
    :param action_identifiers: Generator of action identifiers.
    :param param_identifiers: Generator of parameters identifiers.
    :return:
    """

    the_last_added = None

    def ret_expression():
        # Generate external function retval
        return_expression = ''
        ret_access = None
        if call.retlabel:
            ret_access = process.resolve_access(call.retlabel)
        else:
            ret_subprocess = [a for a in process.actions.filter(include={CallRetval})
                              if a.callback == call.callback and a.retlabel]
            if ret_subprocess:
                ret_access = process.resolve_access(ret_subprocess[0].retlabel)

        if ret_access:
            suits = [a for a in ret_access if
                     (a.interface and
                      a.interface.declaration == signature.points.return_value) or
                     (not a.interface and a.label and
                      any((signature.points.return_value == d for d in a.label.declarations)))]
            if len(suits) > 0:
                if suits[0].interface:
                    lbl = label_map[suits[0].label.name][str(suits[0].interface)]
                else:
                    lbl = suits[0].label
                return_expression = suits[0].access_with_label(lbl) + ' = '
            else:
                raise RuntimeError("Cannot find a suitable label for return value of action {!r}".format(call.name))

        return return_expression

    def match_parameters(callback_declaration):
        # Try to match action parameters
        found_positions = {}
        for label_index, param in enumerate(call.parameters):
            accss = process.resolve_access(param)
            for acc in (a for a in accss if a.interface):
                for position in (p for p in list(range(len(callback_declaration.points.parameters)))[label_index:]
                                 if p not in found_positions):
                    parameter = callback_declaration.points.parameters[position]
                    if acc.interface.declaration == parameter or acc.interface.declaration.pointer_alias(parameter):
                        expression = acc.access_with_label(label_map[acc.label.name][str(acc.base_interface)])
                        found_positions[position] = expression
                        break

        # Fulfil rest parameters
        pointer_params = []
        label_params = []
        for index, param in enumerate(callback_declaration.points.parameters):
            if not isinstance(param, str) and index not in found_positions:
                if not isinstance(param, Primitive) and not isinstance(param, Pointer):
                    param_signature = param.take_pointer
                    pointer_params.append(index)
                    expression = "*%{}%"
                else:
                    param_signature = callback_declaration.points.parameters[index]
                    expression = "%{}%"
                tmp_lb = process.add_label("emg_param_{}_{}".format(index, next(param_identifiers)),
                                           param_signature)
                label_params.append(tmp_lb)
                expression = expression.format(tmp_lb.name)

                # Add string
                found_positions[index] = expression

        return pointer_params, label_params, found_positions

    def manage_default_resources(label_parameters):
        # Add precondition and postcondition
        pre = add_pre_conditions()
        post = add_post_conditions()
        if label_parameters:
            for label in {l.name: l for l in label_parameters if isinstance(l.declaration, Pointer)}.values():
                pre.append('{0} = $UALLOC({0});'.format(repr(label)))
                post.append('$FREE({});'.format(repr(label)))

        if pre:
            pre_name = 'pre_call_{}'.format(next(action_identifiers))
            pre = process.actions.add_condition(pre_name, [], pre, "Callback {} precondition.".format(call.name))
            pre.trace_relevant = True
        if post:
            post_name = 'post_call_{}'.format(next(action_identifiers))
            post = process.actions.add_condition(post_name, [], post,
                                                 "Callback {} postcondition.".format(format(call.name)))
            post.trace_relevant = True

        return pre, post

    def generate_function(callback_declaration, inv):
        _, label_parameters, external_parameters = match_parameters(callback_declaration)
        pre, post = manage_default_resources(label_parameters)
        return_expression = ret_expression()

        # Determine label params
        external_parameters = [external_parameters[i] for i in sorted(list(external_parameters.keys()))]

        true_invoke = return_expression + '{}'.format(inv) + '(' + ', '.join(external_parameters) + ');'
        return [true_invoke], pre, post

    def add_post_conditions():
        post_call = []
        if access.interface and access.interface.interrupt_context:  # pylint: disable=undefined-loop-variable
            post_call.append('$SWITCH_TO_PROCESS_CONTEXT();')

        if call.post_call:
            post_call.extend(call.post_call)

        if post_call:
            post_call.insert(0, '/* Callback post-call */')

        return post_call

    def add_pre_conditions():
        callback_pre_call = []
        if call.pre_call:
            callback_pre_call.extend(call.pre_call)

        if access.interface and access.interface.interrupt_context:  # pylint: disable=undefined-loop-variable
            callback_pre_call.append('$SWITCH_TO_IRQ_CONTEXT();')

        if callback_pre_call:
            callback_pre_call.insert(0, '/* Callback pre-call */')

        return callback_pre_call

    def make_action(callback_declaration, inv):
        cd, pre, post = generate_function(callback_declaration, inv)

        return cd, pre, post

    def reinitialize_variables(base_code):
        reinitialization_action_set = conf.get('callback actions with reinitialization')
        if reinitialization_action_set and call.name in reinitialization_action_set:
            base_code.append("$REINITIALIZE_STATE;")

    # Determine callback implementations
    generated_callbacks = 0
    accesses = process.resolve_access(call.callback)
    for access in accesses:
        reinitialize_vars_flag = False
        if access.interface:
            signature = access.interface.declaration
            implementation = process.get_implementation(access)

            if implementation and sa.refined_name(implementation.value):
                file = implementation.initialization_file
                if file in _values_map and implementation.value in _values_map:
                    break
                invoke = sa.refined_name(implementation.value)
                check = False
            elif not isinstance(implementation, bool) and conf.get('implicit callback calls', True) \
                    and not (access.label.callback and len(access.label.interfaces) > 1) \
                    and not access.label.match_implemented:
                # Call by pointer
                invoke = access.access_with_label(label_map[access.label.name][str(access.base_interface)])
                check = True
                reinitialize_vars_flag = True
            else:
                # Avoid call if neither implementation and pointer call are known
                invoke = None
        else:
            signature = access.label.declaration
            if access.label.value and sa.refined_name(access.label.value):
                # Call function provided by an explicit name but with no interface
                invoke = sa.refined_name(access.label.value)
                check = False
            else:
                if access.interface and conf.get('implicit callback calls', True):
                    # Call if label(variable) is provided but with no explicit value
                    try:
                        invoke = access.access_with_label(access.label)
                        check = True
                    except ValueError:
                        invoke = None
                else:
                    invoke = None

        if invoke:
            code = []
            if not (isinstance(signature, Pointer) and isinstance(signature.points, Function)):
                raise ValueError(f"Expect function pointer for '{str(access)}' but got '{str(signature)}'")

            # Determine structure type name of the container with the callback if such exists
            structure_name = None
            if access.interface and implementation and implementation.sequence:
                field = implementation.sequence[-1]
                containers = interfaces.resolve_containers(access.interface.declaration, access.interface.category)
                if len(containers.keys()) > 0:
                    for name in (name for name in containers if field in containers[name]):
                        structure = interfaces.get_intf(name).declaration
                        # todo: this code does not take into account that implementation of callback and
                        #       implementation of the container should be connected.
                        if isinstance(structure, Structure):
                            structure_name = structure.name
                            break
            if not structure_name:
                # Use instead role and category
                field = call.name
                structure_name = process.category.upper()

            # Generate comment
            comment = call.comment.format(field, structure_name)
            conditions = call.condition if call.condition and call.condition else []

            new_code, pre_action, post_action = make_action(signature, invoke)
            code.extend(new_code)

            # Generate if wrapper around code invoke
            # Note, that it is a bad idea to add condition to the conditions since it might prevent execution of all
            # next code after the translation since we do not know is this action influence branch chose or it does not
            if check:
                code = ["if ({}) ".format(invoke) + "{"] + ['\t' + stm for stm in code] + ["}"]

            # Insert new action and replace this one
            new = process.actions.add_condition("{}_{}".format(call.name, next(action_identifiers)),
                                                conditions, code, comment)
            new.trace_relevant = True

            if generated_callbacks == 0:
                process.actions.replace_action(call, new)
                the_last_added = new
            else:
                process.actions.insert_alternative_action(new, the_last_added)
            generated_callbacks += 1

            # Reinitialize state
            if reinitialize_vars_flag:
                reinitialize_variables(code)

            # Add post and pre conditions
            if pre_action:
                process.actions.insert_action(pre_action, new, before=True)
                # This is because the original callback may be replaced by a series of actions and we should add
                # alternatives to the first action of such series
                the_last_added = pre_action
            if post_action:
                process.actions.insert_action(post_action, new, before=False)

    if generated_callbacks == 0:
        # It is simply enough to delete the action or generate an empty action with a specific comment
        code = []

        # Make comments
        code.append('/* Skip callback without implementations */')
        # If necessary reinitialize variables, for instance, if probe skipped
        if reinitialize_vars_flag:
            reinitialize_variables(code)

        n = process.actions.add_condition("{}_{}".format(call.name, next(action_identifiers)),
                                          [], code, "No callbacks implemented to call here")
        process.actions.replace_action(call, n)
        n.statements = code


def _yield_instances(logger, conf, sa, interfaces, model, instance_maps):
    """
    Generate automata for all processes in an intermediate environment model.

    :param logger: logging initialized object.
    :param conf: Dictionary with configuration properties {'property name'->{'child property' -> {... -> value}}.
    :param sa: Source object.
    :param interfaces: InterfaceCollection object.
    :param model: ProcessCollection object.
    :param instance_maps: Dictionary {'category name' -> {'process name' ->
           {'Access.expression string'->'Interface string'->'value string'}}}.
    :return: List with model automata, list with callback automata.
    """
    logger.info("Generate automata for processes with callback calls")
    identifiers = id_generator()
    identifiers_map = sortedcontainers.SortedDict()

    def rename_process(inst):
        inst.instance_number = int(identifiers.__next__())
        if str(inst) in identifiers_map:
            identifiers_map[str(inst)].append(inst)
        else:
            identifiers_map[str(inst)] = [inst]

    # Check configuration properties first
    conf.setdefault("max instances number", 1000)
    conf.setdefault("instance modifier", 1)
    conf.setdefault("instances per resource implementation", 1)
    instances_left = get_or_die(conf, "max instances number")

    # Returning values
    model_fsa, callback_fsa = [], []

    # Determine how many instances is required for a model
    for process in model.environment.values():
        base_list = [_copy_process(process, instances_left)]
        base_list = _fulfill_label_maps(logger, conf, sa, interfaces, base_list, process, instance_maps, instances_left)
        logger.info("Generate {} FSA instances for environment model processes {!r} with category {!r}".
                    format(len(base_list), process.name, process.category))

        for instance in base_list:
            rename_process(instance)
            callback_fsa.append(instance)

    # Generate automata for models
    logger.info("Generate automata for functions model processes")
    for process in model.models.values():
        logger.info("Generate FSA for functions model process {!r}".format(process.name))
        processes = _fulfill_label_maps(logger, conf, sa, interfaces, [process], process, instance_maps, instances_left)
        # todo: at the moment anyway several instances of function models are ignored, it is better to do it there until
        #       the solution is found
        processes = processes[:1]
        for instance in processes:
            rename_process(instance)
            model_fsa.append(instance)

    return model_fsa, callback_fsa


def _fulfill_label_maps(logger, conf, sa, interfaces, instances, process, instance_maps, instances_left):
    """
    Generate instances and finally assign to each process its instance map which maps accesses to particular
    implementations of relevant interfaces.

    :param logger: logging initialized object.
    :param conf: Dictionary with configuration properties {'property name'->{'child property' -> {... -> value}}.
    :param sa: Source analysis.
    :param interfaces: InterfaceCollection object.
    :param instances: List of Process objects.
    :param process: Process object.
    :param instance_maps: Dictionary {'category name' -> {'process name' ->
           {'Access.expression string'->'Interface string'->'value string'}}}
    :param instances_left: Number of instances which EMG is still allowed to generate.
    :return: List of Process objects.
    """
    base_list = instances

    # Get map from accesses to implementations
    logger.info("Determine number of instances for process {!r}".format(str(process)))

    if process.category not in instance_maps:
        instance_maps[process.category] = sortedcontainers.SortedDict()

    if process.name in instance_maps[process.category]:
        cached_map = instance_maps[process.category][process.name]
    else:
        cached_map = None
    maps, cached_map = _split_into_instances(sa, interfaces, process,
                                             get_or_die(conf, "instances per resource implementation"),
                                             cached_map)
    instance_maps[process.category][process.name] = cached_map

    logger.info("Going to generate {} instances for process {!r} with category {!r}".
                format(len(maps), process.name, process.category))
    new_base_list = []
    for access_map in maps:
        for instance in base_list:
            newp = _copy_process(instance, instances_left)

            newp.allowed_implementations = access_map
            __generate_model_comment(newp)

            # Add relevant headers
            header_list = list.copy(newp.headers)
            for access in access_map:
                for i in access_map[access]:
                    try:
                        interface = interfaces.get_or_restore_intf(i)
                        if interface:
                            if interface.header:
                                for header in interface.header:
                                    if header not in header_list:
                                        header_list.append(header)

                            acc = newp.resolve_access(access, str(interface))
                            if not acc:
                                # TODO: I am not sure that this would guarantee all cases of adding new accesses
                                prot = newp.resolve_access(access)[0]
                                new = ExtendedAccess(access)
                                new.label = prot.label
                                new.interface = interface
                                if prot.base_interface:
                                    new.base_interface = prot.base_interface
                                new.list_access = prot.list_access
                                if len(new.list_access) == 1 and new.label:
                                    new.label.set_declaration(str(interface), access_map[access][i].declaration)

                                newp.add_access(access, new)
                    except KeyError:
                        logger.warning("There is no interface {!r} for process instance {!r}".format(i, process.name))
            newp.headers = header_list

            new_base_list.append(newp)

    return new_base_list


def __get_relevant_expressions(process):
    """
    Function extracts relevant interface implementation for a process.

    :param process: Process object.
    :return: List of string identifiers.
    """

    # First get list of container implementations
    expressions = []
    for collection in process.accesses().values():
        for acc in collection:
            if acc.interface and isinstance(acc.interface, Container) and \
                    acc.expression in process.allowed_implementations and \
                    process.allowed_implementations[acc.expression] and \
                    str(acc.interface) in process.allowed_implementations[acc.expression] and \
                    process.allowed_implementations[acc.expression][str(acc.interface)] and \
                    process.allowed_implementations[acc.expression][str(acc.interface)].value:
                expressions.append(process.allowed_implementations[acc.expression][str(acc.interface)].value)

            if len(expressions) == 3:
                break

    # If there is no container implementations find callbacks
    if len(expressions) == 0:
        for collection in process.accesses().values():
            for acc in collection:
                if acc.interface and isinstance(acc.interface, Callback) and \
                        acc.expression in process.allowed_implementations and \
                        process.allowed_implementations[acc.expression] and \
                        str(acc.interface) in process.allowed_implementations[acc.expression] and \
                        process.allowed_implementations[acc.expression][str(acc.interface)] and \
                        process.allowed_implementations[acc.expression][str(acc.interface)].value:
                    expressions.append(process.allowed_implementations[acc.expression][str(acc.interface)].value)

                if len(expressions) == 3:
                    break

    expressions = [re.sub(r'\s|&', '', e) for e in expressions]
    return expressions


def __add_pretty_name(logger, process, names):
    """
    This function adds to a process name a unique suffix based on some implementation to avoid numerical process
    identifiers and consequently use them in manual specification for addressing signals.

    :param logger: Logger object.
    :param process: Process object.
    :param names: Already issued names.
    :return: A new issued name.
    """
    expressions = __get_relevant_expressions(process)
    if process.category != 'functions models':
        old_name = process.name
        if len(expressions):
            new_name = None
            while not new_name and expressions:
                candidate = expressions.pop(0)
                candidate = f"{old_name}_{candidate}"
                if candidate not in names:
                    new_name = candidate
                    process.name = new_name

        if process.name == old_name:
            process.name = f"{old_name}_{process.instance_number}"
        logger.debug(f"Set new process name: '{process.name}' instead of '{old_name}'")
    return process.name


def __generate_model_comment(process):
    """
    Adds to the Process comment a suffix that points which interface implementation the process is relevant to.

    :param process: Process objet.
    :return: None.
    """
    expressions = __get_relevant_expressions(process)
    # Generate a comment as a concatenation of an original comment and a suffix
    if len(expressions) > 0:
        comment = "{} (Relevant to {})".format(process.comment,
                                               ' '.join(("{!r}".format(e) for e in expressions)))
        process.comment = comment


def _remove_statics(logger, sa, process):
    """
    This function removes calls of static functions in an environment model. Instead it creates wrappers for
    static functions and static global variables and use them.

    :param logger: Logger object.
    :param sa: Source collection.
    :param process: Process object - modified!
    :return: None
    """

    access_map = process.allowed_implementations

    def resolve_existing(search_name, search_implementation, collection):
        if search_implementation in collection and search_name in collection[search_implementation]:
            return collection[search_implementation][search_name]
        return None

    def create_definition(decl, nm, impl, require_suffix=False):
        if require_suffix:
            new_name = "emg_wrapper_{}_{}".format(nm, next(_f_identifiers))
        else:
            new_name = "emg_wrapper_{}".format(nm)
        f = c.Function(new_name, decl)
        f.definition_file = impl.initialization_file

        # Generate call
        if not f.declaration.return_value or f.declaration.return_value == 'void':
            ret = ''
        else:
            ret = 'return'

        # Generate params
        params = ', '.join(["arg{}".format(i) for i in range(len(f.declaration.parameters))])
        call = "{} {}({});".format(ret, sa.refined_name(implementation.value), params)
        f.body.append(call)
        logger.info("Generated new wrapper function {!r}".format(f.name))
        return f

    # For each static Implementation add to the origin file aspect which adds a variable with the same global
    # declaration
    for access in access_map:
        for interface in (i for i in access_map[access] if access_map[access][i]):
            implementation = access_map[access][interface]
            static = implementation.declaration.static
            file = implementation.initialization_file
            func = None
            var = None

            svar = sa.get_source_variable(implementation.value, file)
            function_name = False
            if not svar:
                search_declaration = None
                if isinstance(implementation.declaration, Function):
                    search_declaration = implementation.declaration
                elif isinstance(implementation.declaration, Pointer) and \
                        isinstance(implementation.declaration.points, Function):
                    search_declaration = implementation.declaration.points
                candidate = sa.get_source_function(implementation.value, file, declaration=search_declaration)
                if candidate:
                    static = static or candidate.static
                    declaration = candidate.declaration
                    value = candidate.name
                    function_name = candidate.name

                    # Sometimes file is not detected so we need to save it anywhere
                    if not file:
                        if candidate.definition_file:
                            file = candidate.definition_file
                        else:
                            file = list(candidate.declaration_files).pop() if candidate.declaration_files else None
                else:
                    # Seems that this is a variable without initialization
                    declaration = implementation.declaration
                    value = implementation.value
            else:
                # Because this is a Variable
                static = static or svar.declaration.static
                declaration = svar.declaration
                value = svar.name

                if not file:
                    file = svar.initialization_file

            # Determine name
            if static:
                name = sa.refined_name(implementation.value)
                if declaration and name not in _values_map.get(file, {}):
                    # Prepare dictionary
                    for coll in (_definitions, _declarations):
                        coll.setdefault(file, sortedcontainers.SortedDict())

                    # Create new artificial variables and functions
                    if function_name:
                        func = resolve_existing(name, implementation, _definitions)
                        if not func:
                            suffix = False
                            if len(sa.get_source_functions(function_name)) > 1:
                                suffix = True
                            func = create_definition(declaration.to_string('x', specifiers=False), name, implementation,
                                                     require_suffix=suffix)
                            _definitions[file][name] = func
                            if not isinstance(declaration, Pointer) and isinstance(implementation.declaration, Pointer):
                                # Try to use pointer instead of the value
                                declaration = declaration.take_pointer

                    elif not function_name and not isinstance(declaration, Primitive):
                        var = resolve_existing(name, implementation, _declarations)
                        if not var:
                            if isinstance(declaration, Array):
                                size = declaration.size
                                declaration = declaration.take_pointer
                                declaration.points.size = size
                                value = '& ' + value
                            elif not isinstance(declaration, Pointer):
                                # Try to use pointer instead of the value
                                declaration = declaration.take_pointer
                                value = '& ' + value

                            if len(sa.get_source_variables(name)) > 1:
                                v_name = "emg_alias_{}_{}".format(name, next(_v_identifiers))
                            else:
                                v_name = "emg_alias_{}".format(name)
                            var = c.Variable(v_name, declaration.to_string('x', specifiers=False))
                            var.declaration_files.add(file)
                            var.value = value
                            _declarations[file][name] = var

                    if var or func:
                        new_value = func.name if func else var.name
                        if file not in _values_map:
                            _values_map[file] = sortedcontainers.SortedDict()
                        _values_map[file][new_value] = implementation.value

                        # This is quite precise match to avoid an exception assign valus through a void* match
                        if implementation.declaration != declaration and \
                                isinstance(implementation.declaration, Pointer):
                            implementation.declaration = import_declaration("void *")
                        implementation.declaration = declaration
                        implementation.value = new_value

                        if var:
                            logger.info('Add declaration of alias variable {!r}'.format(var.name))
                            process.add_declaration(file, var.name, var.declare_with_init() + ";\n")
                            process.add_declaration('environment model', var.name, var.declare(extern=True) + ";\n")
                        else:
                            logger.info('Add declaration of wrapper function {!r}'.format(func.name))
                            process.add_definition(file, func.name, func.define() + ["\n"])
                            process.add_declaration('environment model', func.name, func.declare(extern=True)[0])
                else:
                    logger.info("Do not generate wrappers for function {!r} as it is already processed".format(name))


def _copy_process(process, instances_left):
    """
    Return a copy of a process. The copy is not recursive and Process object would has the same objects in its
    attributes.

    :param process: Process object.
    :param instances_left: Number of instances which EMG is still allowed to generate.
    :return: Process object copy.
    """
    inst = process.clone()

    if instances_left == 0:
        raise RuntimeError('EMG tries to generate more instances than it is allowed by configuration')
    if instances_left:
        instances_left -= 1

    return inst


def _split_into_instances(sa, interfaces, process, resource_new_insts, simplified_map=None):
    """
    Get a process and calculate instances to get automata with exactly one implementation per interface.

    This function generates a number of instances which equals to max number of implementations available for
    an interface. For example, having 2 implementations for an instance A and 3 implementations for an instance B
    there are 3 instances will be generated. By the way only containers, interfaces without base values
    (parent containers) and implementations from the same array container are considered for creating instances,
     since the other interfaces will get their implementations according to chosen implementations for interfaces
    mentioned above. For example there is no need to generate instances for interfaces file_operations and
    file.operations.open if implementations of the second one depends on implementations of the first one.

    Generated instance here is a just map from accesses and interfaces to particular implementations which will be
    provided to a copy of the Process object later in translation.
    :param sa: Source analysis.
    :param interfaces: InterfaceCollection object.
    :param process: Process object.
    :param resource_new_insts: Number of new instances allowed to generate for resources.
    :param simplified_map: {'Access.expression string'->'Interface string'->'value string'}
    :return: List of dictionaries with implementations:
              {'Access.expression string'->'Interface string'->'Implementation object/None'}.
             List of dictionaries with values:
              {'Access.expression string'->'Interface string'->'value string'}
    """
    access_map = {}

    accesses = process.accesses()
    interface_to_value, value_to_implementation, basevalue_to_value, interface_to_expression, final_options_list = \
        _extract_implementation_dependencies(access_map, accesses)

    # Generate access maps itself with base values only
    maps = []
    total_chosen_values = set()
    if final_options_list:
        ivector = [0 for _ in enumerate(final_options_list)]

        for _ in enumerate(interface_to_value[final_options_list[0]]):
            new_map = copy.deepcopy(access_map)
            chosen_values = sortedcontainers.SortedSet()

            # Set chosen implementations
            for interface_index, identifier in enumerate(final_options_list):
                expression = interface_to_expression[identifier]
                options = list(sorted([val for val in interface_to_value[identifier]
                                       if len(interface_to_value[identifier][val]) == 0]))
                chosen_value = options[ivector[interface_index]]
                implementation = value_to_implementation[chosen_value]

                # Assign only values without base values
                if not interface_to_value[identifier][chosen_value]:
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
        if not maps:
            maps = [[access_map, sortedcontainers.SortedSet()]]

    # Then set the other values
    for expression, accesses in access_map.items():
        for interface, access in accesses.items():
            intf_additional_maps = []
            # If container has values which depends on another container add a map with uninitialized value for the
            # container
            if access and [val for val in interface_to_value[interface]
                                        if interface_to_value[interface][val]]:
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
                         (not interface_to_value[interface][value] or
                          chosen_values.intersection(interface_to_value[interface][value]) or
                          [cv for cv in interface_to_value[interface][value]
                           if cv not in value_to_implementation and cv not in chosen_values])])
                    if not strict_suits:
                        # If values are repeated just choose random one
                        suits = sorted(
                            [value for value in interface_to_value[interface]
                             if not interface_to_value[interface][value] or
                             chosen_values.intersection(interface_to_value[interface][value]) or
                             ([cv for cv in interface_to_value[interface][value]
                               if cv not in value_to_implementation and cv not in chosen_values])])
                        if suits:
                            suits = [suits.pop()]
                    else:
                        suits = strict_suits

                    if len(suits) == 1:
                        amap[expression][interface] = value_to_implementation[suits[0]]
                        chosen_values.add(suits[0])
                        total_chosen_values.add(suits[0])
                    elif len(suits) > 1:
                        # There can be many useless resource implementations ...
                        interface_obj = interfaces.get_intf(interface)
                        if isinstance(interface_obj, Resource) and resource_new_insts > 0:
                            suits = suits[0:resource_new_insts]
                        elif isinstance(interface_obj, Container):
                            # Ignore additional container values which does not influence the other interfaces
                            suits = [v for v in suits if v in basevalue_to_value and len(basevalue_to_value) > 0]
                        else:
                            # Try not to repeat values
                            suits = [v for v in suits if v not in total_chosen_values]

                        value_map = _match_array_maps(expression, interface, suits, maps, interface_to_value,
                                                      value_to_implementation)
                        intf_additional_maps.extend(
                            _fulfil_map(expression, interface, value_map, [[amap, chosen_values]],
                                        value_to_implementation, total_chosen_values, interface_to_value))

            # Add additional maps
            maps.extend(intf_additional_maps)

    if isinstance(simplified_map, list):
        # Forbid pointer implementations
        complete_maps = maps
        maps = []

        # Set proper given values
        for index, value in enumerate(simplified_map):
            smap = value[0]
            instance_map = sortedcontainers.SortedDict()
            used_values = sortedcontainers.SortedSet()

            for expression in smap.keys():
                instance_map[expression] = sortedcontainers.SortedDict()

                for interface in smap[expression].keys():
                    if smap[expression][interface]:
                        value = smap[expression][interface]
                        if value in value_to_implementation:
                            instance_map[expression][interface] = value_to_implementation[value]
                        else:
                            instance_map[expression][interface] = \
                                interfaces.get_value_as_implementation(sa, value, interface)

                        used_values.add(smap[expression][interface])
                    elif complete_maps[index][0][expression][interface]:
                        # To avoid calls by pointer
                        instance_map[expression][interface] = ''
                    else:
                        instance_map[expression][interface] = smap[expression][interface]
            maps.append([instance_map, used_values])
    else:
        # Prepare simplified map with values instead of Implementation objects
        simplified_map = []
        for smap, cv in maps:
            instance_desc = [sortedcontainers.SortedDict(), list(cv)]

            for expression, smaps in smap.items():
                instance_desc[0][expression] = sortedcontainers.SortedDict()
                for interface, item in smaps.items():
                    if item:
                        instance_desc[0][expression][interface] = item.value
                    else:
                        instance_desc[0][expression][interface] = item
            simplified_map.append(instance_desc)

    return [m for m, cv in maps], simplified_map


def _extract_implementation_dependencies(access_map, accesses):
    """
    This function performs the following operations:
    * Calculate relevant maps for choosing implementations for instances.
    * Detect containers with several implementations, interfaces without a containers having more than one
      implementation, interfaces having several implementations from an array.
    * Reduces a number of container implementations trying to choose only that ones which together 'cover' all relevant
      child values to reduce number of instances with the same callbacks.

    :param access_map: Dictionary which is a prototype of an instance map used for process copying:
                       {'Access.expression string'->'Interface string'->'Implementation object/None'}.
    :param accesses: Process.accesses() dictionary:
                     {'Access.expression string' -> [List with Access objects with the same expression attribute]}
    :return: The following data:
    interface_to_value: Dictionary {'Interface string' -> 'Implementation.value string' ->
                                    'Implementation.base_value string'}
    value_to_implementation: Dictionary {'Implementation.value string' -> 'Implementation object'}
    basevalue_to_value: Dictionary with relevant implementations on each container value:
                        {'Value string' -> {'Set with relevant value strings'}
    interface_to_expression: Dictionary {'Interface string' -> 'Access.expression string'}
    final_options_list: List ['Interface string'] - contains sorted list of interfaces identifiers for which
    is necessary to choose implementations first (see description above). The greatest element is the first.
    """
    # Necessary data to return
    interface_to_value = sortedcontainers.SortedDict()
    value_to_implementation = sortedcontainers.SortedDict()
    interface_to_expression = sortedcontainers.SortedDict()
    basevalue_to_value = sortedcontainers.SortedDict()

    # Additional data
    basevalue_to_interface = sortedcontainers.SortedDict()
    options_interfaces = sortedcontainers.SortedSet()

    # Collect dependencies between interfaces, implementations and containers
    for access in accesses.keys():
        access_map[access] = {}

        for inst_access in [inst for inst in accesses[access] if inst.interface]:
            access_map[inst_access.expression][str(inst_access.interface)] = None
            interface_to_expression[str(inst_access.interface)] = access

            implementations = inst_access.interface.implementations
            interface_to_value[str(inst_access.interface)] = {}
            for impl in implementations:
                value_to_implementation[impl.value] = impl

                if impl.value not in interface_to_value[str(inst_access.interface)]:
                    interface_to_value[str(inst_access.interface)][impl.value] = sortedcontainers.SortedSet()

                if impl.base_value:
                    interface_to_value[str(inst_access.interface)][impl.value].add(impl.base_value)

                    if impl.base_value not in basevalue_to_value:
                        basevalue_to_value[impl.base_value] = []
                        basevalue_to_interface[impl.base_value] = sortedcontainers.SortedSet()
                    basevalue_to_value[impl.base_value].append(impl.value)
                    basevalue_to_interface[impl.base_value].add(str(inst_access.interface))
                else:
                    options_interfaces.add(str(inst_access.interface))

    # Choose greedy minimal set of container implementations which cover all relevant child interface implementations
    # (callbacks, resources ...)
    containers_impacts = {}
    for container_id in [container_id for container_id in list(options_interfaces)
                         if [value for value in interface_to_value[container_id] if value in basevalue_to_value]]:
        # Collect all child values
        summary_values = sortedcontainers.SortedSet()
        summary_interfaces = sortedcontainers.SortedSet()
        original_options = sortedcontainers.SortedSet()

        for value in [value for value in interface_to_value[container_id] if value in basevalue_to_value]:
            summary_values.update(basevalue_to_value[value])
            summary_interfaces.update(basevalue_to_interface[value])
            original_options.add(value)

        # Greedy add implementations to fill all child values
        fulfilled_values = sortedcontainers.SortedSet()
        fulfilled_interfaces = sortedcontainers.SortedSet()
        final_set = sortedcontainers.SortedSet()
        original_options = sorted(sorted(original_options), key=lambda v: len(basevalue_to_value[v]), reverse=True)
        while set(summary_values - fulfilled_values) and \
                (len(fulfilled_values) != len(summary_values) or len(fulfilled_interfaces) != len(summary_interfaces)):
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
                raise RuntimeError('Infinite loop due to inability to cover an implementation by a container')

        containers_impacts[container_id] = len(final_set)

        # Keep values with base values anyway
        final_set.update([value for value in interface_to_value[container_id]
                          if len(interface_to_value[container_id][value]) > 0])
        interface_to_value[container_id] = {val: interface_to_value[container_id][val] for val in final_set}

    # Sort options
    options = [o for o in options_interfaces
               if [value for value in interface_to_value[o] if value in basevalue_to_value]]
    final_options_list = sorted(sorted(options), key=lambda o: containers_impacts[o], reverse=True)

    return interface_to_value, value_to_implementation, basevalue_to_value, interface_to_expression, final_options_list


def _match_array_maps(expression, interface, values, maps, interface_to_value, value_to_implementation):
    """
    Tries to find an existing solution map for a given value which will contain another values from the same container
    from which springs a value under consideration. Function also distinguish containers from the same arrays and tries
    to not mix callbacks from such arrays of containers. Such match allows to drastically reduce number of generated
    instances especially generated for containers from arrays.

    :param expression: Expression string.
    :param interface: An interface identifier.
    :param values: List of unique values implementing the interface.
    :param maps: Existing solutions: List with elements with a list of structure:
                 [{'Access.expression string'->'Interface string'->'Implementation object/None'},
                   set{used values strings}].
    :param interface_to_value: Dictionary {'Interface string' -> 'Implementation.value string' ->
                                           'Implementation.base_value string'}
    :param value_to_implementation: Dictionary {'Implementation.value string' -> 'Implementation object'}
    :return: Map from values to solutions (if so suitable found):
             {'Value string'->[{'Access.expression string'->'Interface string'->
                               'Implementation object/None'}, set{used values strings}]}
    """
    result_map = sortedcontainers.SortedDict()
    added = []

    for value in values:
        v_implementation = value_to_implementation[value]
        result_map[value] = None

        if interface_to_value[interface][value]:
            suitable_map = None
            for mp, chosen_values in ((m, cv) for m, cv in maps if not m[expression][interface] and m not in added):
                for e in (e for e in mp.keys() if isinstance(mp[e], dict)):
                    same_container = \
                        [mp for i in mp[e] if i != interface and isinstance(mp[e][i], Implementation) and
                         mp[e][i].base_value and _from_same_container(v_implementation, mp[e][i])]
                    if same_container and mp not in added:
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
                       [{'Access.expression string'->'Interface string'->'Implementation object/None'},
                        set{used values strings}]}
    :param reuse: List with elements with a list of structure:
                  [{'Access.expression string'->'Interface string'->'Implementation object/None'},
                   set{used values strings}].
    :param value_to_implementation: Dictionary {'Implementation.value string' -> 'Implementation object'}.
    :param total_chosen_values: Set of already added values from all instance maps.
    :param interface_to_value: Dictionary {'Interface string' -> 'Implementation.value string' ->
                                           'Implementation.base_value string'}
    :return: List with new created elements with a list of structure:
                  [{'Access.expression string'->'Interface string'->'Implementation object/None'},
                   set{used values strings}].
    """
    new_maps = []

    if not reuse:
        raise ValueError('Expect non-empty list of maps for instantiating from')
    first = reuse[0]

    for value in value_map.keys():
        if value_map[value]:
            new = value_map[value]
        else:
            if reuse:
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
    :param interface_to_value: Dictionary {'Interface string' -> 'Access.expression string'}.
    :param value_to_implementation: Dictionary {'Implementation.value string' -> 'Implementation object'}.
    :return: Set with all added values (a given one plus a container if so).
    """
    added = {value}

    chosen_values.add(value)
    total_chosen_values.add(value)

    hidden_container_values = [cv for cv in interface_to_value[interface][value] if cv not in value_to_implementation]

    if hidden_container_values:
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
        if a.base_value and b.base_value and a.base_value == b.base_value:
            iterate = min(len(a.sequence), len(b.sequence))
            if iterate > 1:
                for i in range(iterate):
                    if a.sequence[i] != b.sequence[i]:
                        return False
                    if isinstance(a.sequence[i], int):
                        return True
    else:
        if a.base_value and b.base_value and a.base_value == b.base_value:
            return True
        if a.base_value and not b.base_value and a.base_value == b.value:
            return True

    return False
