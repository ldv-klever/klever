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
import graphviz
from operator import attrgetter

from core.avtg.emg.common.signature import Primitive, Pointer
from core.avtg.emg.common.process import Subprocess, Receive, Dispatch, Call, CallRetval, Condition
from core.avtg.emg.translator.code  import Variable, FunctionModels


class FSA:

    def __init__(self, process):
        self.process = process
        self.states = set()
        self._initial_states = set()
        self.__id_cnt = 0

        # Generate AST states
        sp_asts = dict()
        sp_processed = set()
        asts = list()

        # Generate states
        def generate_nodes(self, process, pr_ast):
            asts = [[pr_ast, True]]
            initial_states = set()

            while len(asts) > 0:
                ast, initflag = asts.pop()

                if ast['type'] == 'choice':
                    for action in ast['actions']:
                        asts.append([action, initflag])
                elif ast['type'] == 'concatenation':
                    for action in ast['actions']:
                        if initflag:
                            asts.append([action, initflag])
                            initflag = False
                        else:
                            asts.append([action, initflag])
                else:
                    node = State(ast, self.__yield_id())

                    if ast['name'] not in process.actions:
                        raise KeyError("Process '{}' does not have action description '{}'".
                                       format(process.name, ast['name']))
                    node.action = process.actions[ast['name']]
                    if type(process.actions[ast['name']]) is Receive:
                        node.action.replicative = node.desc['replicative']
                    if type(process.actions[ast['name']]) is Dispatch:
                        node.action.broadcast = node.desc['broadcast']

                    self.states.add(node)
                    ast['node'] = node

                    if initflag:
                        initial_states.add(node)

            return initial_states

        for name in [name for name in sorted(process.actions.keys()) if type(process.actions[name]) is Subprocess]:
            ast = copy.copy(process.actions[name].process_ast)
            generate_nodes(self, process, ast)
            sp_asts[name] = ast
        p_ast = copy.copy(process.process_ast)
        self._initial_states = generate_nodes(self, process, p_ast)
        asts.append([p_ast, None])

        def resolve_last(pr_ast):
            if not pr_ast:
                return set()

            asts = [pr_ast]
            last = set()

            while len(asts) > 0:
                ast = asts.pop()

                if ast['type'] == 'choice':
                    for action in ast['actions']:
                        asts.append(action)
                elif ast['type'] == 'concatenation':
                    asts.append(ast['actions'][-1])
                else:
                    last.add(ast['node'])

            return last

        while len(asts) > 0:
            ast, prev = asts.pop()

            if ast['type'] == 'choice':
                for action in ast['actions']:
                    asts.append([action, prev])
            elif ast['type'] == 'concatenation':
                for action in ast['actions']:
                    asts.append([action, prev])
                    prev = action
            else:
                if ast['type'] == 'subprocess':
                    pair = "{} {}".format(ast['name'], str(prev))
                    if pair not in sp_processed:
                        sp_processed.add(pair)
                        asts.append([sp_asts[ast['name']], ast])

                last = resolve_last(prev)
                if len(last) > 0 and prev['type'] != "subprocess":
                    # Filter out subprocesses if there are
                    last = [s for s in last if type(s.action) is not Subprocess]

                for pre_state in last:
                    ast['node'].insert_predecessor(pre_state)

        # Normalize fsa to make life easier for code generators
        # Keep subprocess states as jumb points
        # Insert process and subprocess entry states
        for subprocess in (a for a in self.process.actions.values() if type(a) is Subprocess):
            new = self.__new_state(None)

            # Insert state
            jump_states = sorted([s for s in self.states if s.action and s.action.name == subprocess.name],
                                  key=attrgetter('identifier'))
            for jump in jump_states:
                for successor in jump.successors:
                    successor.replace_predecessor(jump, new)
                    jump.replace_successor(successor, new)

        # Add initial state if necessary
        if len(self._initial_states) > 1:
            new = self.__new_state(None)
            for initial in self._initial_states:
                initial.insert_predecessor(new)

            self._initial_states = set([new])

        return

    @property
    def initial_states(self):
        return sorted(self._initial_states, key=attrgetter('identifier'))

    def resolve_state(self, identifier):
        for state in (s for s in self.states if s.identifier == identifier):
            return state

        raise KeyError("State '{}' does not exist in process '{}' of category '{}'".
                       format(identifier, self.process.name, self.process.category))

    def clone_state(self, node):
        new_desc = copy.copy(node.desc)
        new_id = self.__yield_id()

        new_state = State(new_desc, new_id)
        new_state.action = node.action

        for pred in node.predecessors:
            new_state.insert_predecessor(pred)

        for succ in node.successors:
            new_state.insert_successor(succ)

        self.states.add(new_state)

        return new_state

    def add_new_predecessor(self, node, action):
        new = self.__new_state(action)

        for pred in node.predecessors:
            pred.replace_successor(node, new)

        node.insert_predecessor(new)
        return new

    def add_new_successor(self, node, action):
        new = self.__new_state(action)

        for succ in node.successors:
            succ.replace_predecessor(node, new)

        node.insert_successor(new)
        return new

    def __new_state(self, action):
        if action:
            desc = {
                'label': '<{}>'.format(action.name)
            }
        else:
            desc = {
                'label': 'Artificial state'
            }
        new = State(desc, self.__yield_id())
        new.action = action
        self.states.add(new)
        return new

    def __yield_id(self):
        self.__id_cnt += 1
        return self.__id_cnt


class State:

    def __init__(self, desc, identifier):
        self.identifier = identifier
        self.desc = desc
        self._predecessors = set()
        self._successors = set()
        self.action = None
        self.code = None

    @property
    def successors(self):
        return sorted(self._successors, key=attrgetter('identifier'))

    @property
    def predecessors(self):
        return sorted(self._predecessors, key=attrgetter('identifier'))

    def insert_successor(self, new):
        self.add_successor(new)
        new.add_predecessor(self)

    def insert_predecessor(self, new):
        self.add_predecessor(new)
        new.add_successor(self)

    def replace_successor(self, old, new):
        self.remove_successor(old)
        old.remove_predecessor(self)
        self.add_successor(new)
        new.add_predecessor(self)

    def replace_predecessor(self, old, new):
        self.remove_predecessor(old)
        old.remove_successor(self)
        self.add_predecessor(new)
        new.add_successor(self)

    def add_successor(self, new):
        self._successors.add(new)

    def add_predecessor(self, new):
        self._predecessors.add(new)

    def remove_successor(self, old):
        if old in self._successors:
            self._successors.remove(old)

    def remove_predecessor(self, old):
        if old in self._predecessors:
            self._predecessors.remove(old)

    # todo: remove
    def _relevant_checks(self):
        checks = []

        # Add state checks
        if self.code and 'relevant automata' in self.code:
            for name in sorted(self.code['relevant automata'].keys()):
                for st in self.code['relevant automata'][name]['states']:
                    for index in self.code['relevant automata'][name]["automaton"].state_blocks:
                        if st in self.code['relevant automata'][name]["automaton"].state_blocks[index]:
                            checks.append("{} == {}".
                                          format(self.code['relevant automata'][name]["automaton"].state_variable.name,
                                                 index))

        return checks


class Automaton:

    def __init__(self, logger, translation_conf, process, identifier):
        # Set default values
        self.control_function = None
        self.state_blocks = {}
        self.cf_structure = None
        self.functions = []
        self.__state_variable = None
        self.__thread_variable = None
        self.__label_variables = {}
        self.__file = None
        self.conf = translation_conf
        self.translation_models = FunctionModels(self.conf)

        # Set given values
        self.logger = logger
        self.process = process
        self.identifier = identifier

        # Generate FSA itself
        self.logger.info("Generate states for automaton {} based on process {} with category {}".
                         format(self.identifier, self.process.name, self.process.category))
        self.fsa = FSA(self.process)
        self.variables()

    @property
    def file(self):
        if self.__file:
            return self.__file
        files = set()

        # Try to determine base values
        base_values = set()
        change = True
        while change:
            change = False

            for expr in self.process.allowed_implementations:
                for impl in (impl for impl in self.process.allowed_implementations[expr].values() if impl):
                    if impl.base_value and impl.base_value not in base_values:
                        base_values.add(impl.base_value)
                        change = True
                    elif not impl.base_value and impl.value not in base_values:
                        base_values.add(impl.value)
                        change = True

                    if impl.value in base_values and impl.file not in files:
                        files.add(impl.file)
                        change = True

        # If no base values then try to find callback call files
        files.update(set([s.code['file'] for s in self.fsa.states if s.code and 'file' in s.code]))

        if len(files) > 0:
            chosen_one = sorted(list(files))[0]
            self.__file = chosen_one
        else:
            self.__file = None

        return self.__file

    @property
    def state_variable(self):
        if not self.__state_variable:
            var = Variable('ldv_statevar_{}'.format(self.identifier),  None, 'int a', True)
            var.use += 1
            self.__state_variable = var

        return self.__state_variable

    def thread_variable(self, number=1):
        if not self.__thread_variable:
            if number > 1:
                var = Variable('ldv_thread_{}'.format(self.identifier),  None, 'struct ldv_thread_set a', True)
                var.value = '{' + '.number = {}'.format(number) + '}'
            else:
                var = Variable('ldv_thread_{}'.format(self.identifier),  None, 'struct ldv_thread a', True)
            var.use += 1
            self.__thread_variable = var

        return self.__thread_variable

    def variables(self):
        variables = []

        # Generate variable for each label
        for label in [self.process.labels[name] for name in sorted(self.process.labels.keys())]:
            if label.interfaces:
                for interface in label.interfaces:
                    variables.append(self.determine_variable(label, interface))
            else:
                var = self.determine_variable(label)
                if var:
                    variables.append(self.determine_variable(label))

        return variables

    def new_param(self, name, declaration, value):
        lb = self.process.add_label(name, declaration, value)
        lb.resource = True
        vb = self.determine_variable(lb)
        return lb, vb

    def determine_variable(self, label, interface=None):
        if not interface:
            if label.name in self.__label_variables and "default" in self.__label_variables[label.name]:
                return self.__label_variables[label.name]["default"]
            else:
                if label.prior_signature:
                    var = Variable("ldv_{}_{}_{}".format(self.identifier, label.name, "default"), None,
                                   label.prior_signature, export=True)
                    if label.value:
                        var.value = label.value
                    if label.file:
                        var.file = label.file

                    if label.name not in self.__label_variables:
                        self.__label_variables[label.name] = {}
                    self.__label_variables[label.name]["default"] = var
                    return self.__label_variables[label.name]["default"]
                else:
                    self.logger.warning("Cannot create variable for label which is not matched with interfaces and does"
                                        " not have signature")
                    return None
        else:
            if label.name in self.__label_variables and interface in self.__label_variables[label.name]:
                return self.__label_variables[label.name][interface]
            else:
                if interface not in label.interfaces:
                    raise KeyError("Label {} is not matched with interface {}".format(label.name, interface))
                else:
                    access = self.process.resolve_access(label, interface)
                    category, short_id = interface.split(".")
                    implementation = self.process.get_implementation(access)
                    var = Variable("ldv_{}_{}_{}".format(self.identifier, label.name, short_id), None,
                                   label.get_declaration(interface), export=True)

                    if implementation:
                        var.value = implementation.adjusted_value(var.declaration)

                        # Change file according to the value
                        var.file = implementation.file

                    if label.name not in self.__label_variables:
                        self.__label_variables[label.name] = {}
                    self.__label_variables[label.name][interface] = var
                    return self.__label_variables[label.name][interface]

    def save_digraph(self, directory):
        # Generate graph
        self.logger.info("Generate graph for automaton based on process {} with category {}".
                         format(self.process.name, self.process.category))
        dg_file = "{}/{}.dot".format(directory, "{}_{}_{}".
                                     format(self.process.category, self.process.name, self.identifier))

        graph = graphviz.Digraph(
            name=str(self.identifier),
            comment="Digraph for FSA {} based on self.process {} with category {}".
                    format(self.identifier, self.process.name, self.process.category),
            format="png"
        )

        # Add self.process description
        graph.node(
            self.process.name,
            "self.process: {}".format(self.process.process),
            {
                "shape": "rectangle"
            }
        )

        # Add subself.process description
        for subp in [self.process.actions[name] for name in sorted(self.process.actions.keys())
                       if type(self.process.actions[name]) is Subprocess]:
            graph.node(
                subp.name,
                "Subprocess {}: {}".format(subp.name, subp.process),
                {
                    "shape": "rectangle"
                }
            )

        subprocesses = {}
        for state in self.fsa.states:
            label = "Action {}: {}\n".format(state.identifier, state.desc['label'])

            if 'guard' in state.code and len(state.code['guard']) > 0:
                label += 'Guard: ' + ' && '.join(state.code['guard'])
                label += '\n'

            if type(state.action) is Call and 'invoke' in state.code:
                if 'file' in state.code:
                    label += "File: '{}'\n".format(state.code['file'])
                call = ''
                if 'pre_call' in state.code:
                    call += '\n'.join(state.code['pre_call'])
                    call += '\n'
                if 'retval' in state.code:
                    call += "{} = ".format(state.code['retval'])
                call += state.code['invoke']
                if 'check pointer' in state.code and state.code['check pointer']:
                    call += 'if ({})'.format(state.code['invoke']) + '\n\t'
                call += '(' + ', '.join(state.code['parameters']) + ')'
                if 'post_call' in state.code:
                    call += '\n'.join(state.code['post_call'])
                    call += '\n'
                label += call
            else:
                if 'body' in state.code and len(state.code['body']) > 0:
                    label += 'Body:\n' + '\n'.join(state.code['body'])

            if 'relevant automata' in state.code:
                label += '\nRelevant automata:\n'
                if len(state.code['relevant automata']) > 0:
                    for automaton in state.code['relevant automata'].values():
                        label += "Automaton '{}': '{}' ({})\n".format(automaton['automaton'].identifier,
                                                                      automaton['automaton'].process.name,
                                                                      automaton['automaton'].process.category)

            if type(state.action) is not Subprocess or state.action.name not in subprocesses:
                graph.node(str(state.identifier), label)
                if type(state.action) is Subprocess:
                    subprocesses[state.action.name] = state.identifier

        for state in self.fsa.states:
            if type(state.action) is not Subprocess or state.identifier in subprocesses.values():
                for succ in state.successors:
                    if type(succ.action) is Subprocess:
                        graph.edge(
                            str(state.identifier),
                            str(subprocesses[succ.action.name])
                        )
                    else:
                        graph.edge(
                            str(state.identifier),
                            str(succ.identifier)
                    )

        if len(self.fsa._initial_states) > 1:
            name = 'Artificial initial state'
            graph.node(name, name)
            for entry in self.fsa._initial_states:
                graph.edge(
                    str(name),
                    str(entry.identifier)
                )

        # Save to dg_file
        graph.save(dg_file)
        graph.render()
        self.logger.debug("Graph image has been successfully rendered and saved")

    def generate_meta_code(self, analysis, model, translator, state):
        base_case = {
            "guard": [],
            "body": [],
        }

        if type(state.action) is Call:
            self.logger.debug("Prepare code for callback call '{}' in automaton '{}' for process '{}' of category "
                              "'{}'".format(state.action.name, self.identifier, self.process.name,
                                            self.process.category))
            accesses = self.process.resolve_access(state.action.callback)
            callbacks = []

            for access in accesses:
                if access.interface:
                    signature = access.interface.declaration
                    implementation = self.process.get_implementation(access)

                    if implementation and analysis.callback_name(implementation.value):
                        invoke = '(' + implementation.value + ')'
                        file = implementation.file
                        check = False
                        func_variable = access.access_with_variable(self.determine_variable(access.label,
                                                                                            access.list_interface[0].
                                                                                            identifier))
                    elif signature.clean_declaration:
                        invoke = access.access_with_variable(self.determine_variable(access.label,
                                                                                     access.list_interface[0].
                                                                                     identifier))
                        func_variable = invoke
                        file = translator.entry_file
                        check = True
                    else:
                        invoke = None
                else:
                    signature = access.label.prior_signature

                    func_variable = self.determine_variable(access.label)
                    if access.label.value and analysis.callback_name(access.label.value):
                        invoke = analysis.callback_name(access.label.value)
                        func_variable = func_variable.name
                        file = analysis.determine_original_file(access.label.value)
                        check = False
                    else:
                        if func_variable:
                            invoke = access.access_with_variable(func_variable)
                            func_variable = func_variable.name
                            file = translator.entry_file
                            check = True
                        else:
                            invoke = None

                if invoke:
                    new_case = copy.deepcopy(base_case)
                    additional_checks = translator.registration_intf_check(analysis, model, invoke)
                    if len(list(additional_checks.keys())) > 0:
                        new_case['relevant automata'] = additional_checks

                    if len(callbacks) == 0:
                        st = state
                    else:
                        st = self.fsa.clone_state(state)

                    if access.interface and access.interface.interrupt_context:
                        new_case['pre_call'] = [
                            "/* Callback pre-call */"
                        ]
                        new_case['pre_call'].extend(
                            self.translation_models.text_processor(self.process, '$SWITCH_TO_IRQ_CONTEXT();'))
                        new_case['post_call'] = [
                            "/* Callback post-call */"
                        ]
                        new_case['post_call'].extend(
                            self.translation_models.text_processor(self.process, '$SWITCH_TO_PROCESS_CONTEXT();'))
                    callbacks.append([st, new_case, signature, invoke, file, check, func_variable])

            if len(callbacks) > 0:
                for st, case, signature, invoke, file, check, func_variable in callbacks:
                    self.logger.debug("Prepare callback call '{}'".format(invoke))
                    # Generate function call and corresponding function
                    params = []
                    pointer_params = []
                    label_params = []
                    cb_statements = []

                    # Try to match action parameters
                    found_positions = dict()
                    for label_index in range(len(st.action.parameters)):
                        accesses = self.process.resolve_access(st.action.parameters[label_index])
                        for acc in (a for a in accesses if a.list_interface and len(a.list_interface) > 0):
                            for position in (p for p in list(range(len(signature.points.parameters)))[label_index:]
                                             if p not in found_positions):
                                parameter = signature.points.parameters[position]
                                if (acc.list_interface[-1].declaration.compare(parameter) or
                                        acc.list_interface[-1].declaration.pointer_alias(parameter)):
                                    expression = acc.access_with_variable(
                                        self.determine_variable(acc.label, acc.list_interface[0].identifier))
                                    found_positions[position] = expression
                                    break

                    # Fulfil rest parameters
                    for index in range(len(signature.points.parameters)):
                        if type(signature.points.parameters[index]) is not str and index not in found_positions:
                            if type(signature.points.parameters[index]) is not Primitive and \
                                    type(signature.points.parameters[index]) is not Pointer:
                                param_signature = signature.points.parameters[index].take_pointer
                                pointer_params.append(index)
                            else:
                                param_signature = signature.points.parameters[index]

                            lb, var = self.new_param("ldv_param_{}_{}".format(st.identifier, index),
                                                     param_signature, None)
                            label_params.append(lb)
                            expression = var.name

                            # Add string
                            found_positions[index] = expression

                    # Print params
                    params = [found_positions[i] for i in sorted(found_positions.keys())]

                    # Add precondition and postcondition
                    if len(label_params) > 0:
                        pre_statements = []
                        post_statements = []
                        for label in sorted(list(set(label_params)), key=lambda lb: lb.name):
                            pre_statements.append('%{}% = $UALLOC(%{}%);'.format(label.name, label.name))
                            post_statements.append('$FREE(%{}%);'.format(label.name))

                        pre_name = 'pre_call_{}'.format(st.identifier)
                        pre_action = self.process.add_condition(pre_name, [], pre_statements)
                        pre_st = self.fsa.add_new_predecessor(st, pre_action)
                        self.generate_meta_code(analysis, model, translator, pre_st)

                        post_name = 'post_call_{}'.format(st.identifier)
                        post_action = self.process.add_condition(post_name, [], post_statements)
                        post_st = self.fsa.add_new_successor(st, post_action)
                        self.generate_meta_code(analysis, model, translator, post_st)

                    # Generate return value assignment
                    ret_access = None
                    if st.action.retlabel:
                        ret_access = self.process.resolve_access(st.action.retlabel)
                    else:
                        ret_subprocess = [self.process.actions[name] for name in sorted(self.process.actions.keys())
                                          if type(self.process.actions[name]) is CallRetval and
                                          self.process.actions[name].callback == st.action.callback and
                                          self.process.actions[name].retlabel]
                        if ret_subprocess:
                            ret_access = self.process.resolve_access(ret_subprocess[0].retlabel)

                    # Match label
                    if ret_access:
                        suits = [access for access in ret_access if
                                 (access.interface and
                                  access.interface.declaration.compare(signature.points.return_value)) or
                                 (not access.interface and access.label and
                                  signature.points.return_value.identifier in (d.identifier for d
                                                                               in access.label.declarations))]
                        if len(suits) > 0:
                            if suits[0].interface:
                                label_var = self.determine_variable(suits[0].label, suits[0].interface.identifier)
                            else:
                                label_var = self.determine_variable(suits[0].label)
                            retval = suits[0].access_with_variable(label_var)
                            case['retval'] = retval
                        else:
                            raise RuntimeError("Cannot find a suitable label for return value of action '{}'".
                                               format(state.action.name))

                    # Add additional condition
                    if state.action.condition and len(state.action.condition) > 0:
                        for statement in state.action.condition:
                            cn = self.translation_models.text_processor(self, statement)
                            base_case["guard"].extend(cn)

                    if st.action.pre_call and len(st.action.pre_call) > 0:
                        pre_call = []
                        for statement in st.action.pre_call:
                            pre_call.extend(self.translation_models.text_processor(self, statement))

                        if 'pre_call' not in case:
                            case['pre_call'] = ['/* Callback pre-call */'] + pre_call
                        else:
                            # Comment + user pre-call + interrupt switch
                            case['pre_call'] = ['/* Callback pre-call */'] + pre_call + case['pre_call'][1:]

                    if st.action.post_call and len(st.action.post_call) > 0:
                        post_call = []
                        for statement in st.action.post_call:
                            post_call.extend(self.translation_models.text_processor(self, statement))

                        if 'post_call' not in case:
                            case['post_call'] = ['/* Callback post-call */'] + post_call
                        else:
                            # Comment + user post-call + interrupt switch
                            case['post_call'] = ['/* Callback pre-call */'] + pre_call + case['post_call'][1:]

                    # Generate comment
                    case["parameters"] = params
                    case["pointer parameters"] = pointer_params
                    case["callback"] = signature
                    case["check pointer"] = check
                    case["invoke"] = invoke
                    case["body"].append("/* Call callback {} */".format(st.action.name))
                    case["body"].extend(cb_statements)
                    case['file'] = file
                    case['variable'] = func_variable
                    st.code = case
            else:
                # Generate comment
                base_case["body"].append("/* Skip callback call {} without an implementation */".
                                         format(state.action.name))
                state.code = base_case
        elif type(state.action) is Dispatch:
            self.logger.debug("Prepare code for dispatch '{}' in automaton '{}' for process '{}' of category "
                              "'{}'".format(state.action.name, self.identifier, self.process.name,
                                            self.process.category))
            # Generate dispatch function
            automata_peers = dict()
            if len(state.action.peers) > 0:
                # Do call only if model which can be called will not hang
                translator.extract_relevant_automata(automata_peers, state.action.peers, Receive)
            else:
                # Generate comment
                base_case["body"].append("/* Dispatch {} is not expected by any process, skip it */".
                                         format(state.action.name))

            # Add additional condition
            if state.action.condition and len(state.action.condition) > 0:
                for statement in state.action.condition:
                    cn = self.translation_models.text_processor(self, statement)
                    base_case["guard"].extend(cn)

            base_case['relevant automata'] = automata_peers
            state.code = base_case
        elif type(state.action) is CallRetval:
            self.logger.debug("Prepare code for retval '{}' in automaton '{}' for process '{}' of category "
                              "'{}'".format(state.action.name, self.identifier, self.process.name,
                                            self.process.category))
            base_case["body"].append("/* Should wait for return value of {} here, "
                                     "but in sequential model it is not necessary */".format(state.action.name))
            state.code = base_case
        elif type(state.action) is Receive:
            self.logger.debug("Prepare code for receive '{}' in automaton '{}' for process '{}' of category "
                              "'{}'".format(state.action.name, self.identifier, self.process.name,
                                            self.process.category))
            # Generate dispatch function
            automata_peers = {}
            if len(state.action.peers) > 0:
                # Do call only if model which can be called will not hang
                translator.extract_relevant_automata(automata_peers, state.action.peers, Dispatch)

                # Add additional condition
                base_case["receive guard"] = []
                if state.action.condition and len(state.action.condition) > 0:
                    for statement in state.action.condition:
                        cn = self.translation_models.text_processor(self, statement)
                        base_case["receive guard"].extend(cn)
            else:
                # Generate comment
                base_case["body"].append("/* Receive {} does not expect any signal from existing processes, skip it */".
                                         format(state.action.name))

            base_case['relevant automata'] = automata_peers
            state.code = base_case
        elif type(state.action) is Condition:
            self.logger.debug("Prepare code for condition '{}' in automaton '{}' for process '{}' of category "
                              "'{}'".format(state.action.name, self.identifier, self.process.name,
                                            self.process.category))
            # Generate comment
            base_case["body"].append("/* Code or condition insertion {} */".format(state.action.name))

            # Add additional condition
            if state.action.condition and len(state.action.condition) > 0:
                for statement in state.action.condition:
                    cn = self.translation_models.text_processor(self, statement)
                    base_case["guard"].extend(cn)

            if state.action.statements:
                for statement in state.action.statements:
                    base_case["body"].extend(self.translation_models.text_processor(self, statement))
            state.code = base_case
        elif type(state.action) is Subprocess:
            self.logger.debug("Prepare code for subprocess '{}' in automaton '{}' for process '{}' of category "
                              "'{}'".format(state.action.name, self.identifier, self.process.name,
                                            self.process.category))
            # Generate comment
            base_case["body"].append("/* Jump to an initial state of subprocess '{}' */".format(state.action.name))

            # Add additional condition
            if state.action.condition and len(state.action.condition) > 0:
                for statement in state.action.condition:
                    cn = self.translation_models.text_processor(self, statement)
                    base_case["guard"].extend(cn)

            # Add additional condition
            if state.action.condition and len(state.action.condition) > 0:
                for statement in state.action.condition:
                    cn = self.translation_models.text_processor(self, statement)
                    base_case["guard"].extend(cn)

            state.code = base_case
        elif state.action is None:
            self.logger.debug("Prepare code for artificial state '{}' in automaton '{}' for process '{}' of category "
                              "'{}'".format(state.identifier, self.identifier, self.process.name,
                                            self.process.category))
            # Generate comment
            base_case["body"].append("/* Artificial state {} */".format(state.identifier))
            state.code = base_case
        else:
            raise ValueError("Unexpected state machine edge type: {}".format(state.action.type))


__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
