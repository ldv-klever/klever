import copy
import graphviz

from core.avtg.emg.common.signature import Primitive, Pointer
from core.avtg.emg.common.code import Variable, FunctionModels
from core.avtg.emg.common.process import Subprocess, Receive, Dispatch, Call, CallRetval, Condition


class FSA:

    def __init__(self, process):
        self.process = process
        self.initial_states = set()
        self.finite_states = set()
        self.states = set()
        self.__id_cnt = 0

        # Generate AST states
        self.__generate_states(process)

    def clone_state(self, node):
        new_desc = copy.copy(node.desc)
        new_id = self.__yield_id()

        new_state = Node(new_desc, new_id)
        new_state.action = node.action

        for pred in node.predecessors:
            new_state.predecessors.add(pred)
            pred.successors.add(new_state)

        for succ in node.successors:
            new_state.successors.add(succ)
            succ.predecessors.add(new_state)

        self.states.add(new_state)

        return new_state

    def new_state(self, action):
        desc = {
            'label': '<{}>'.format(action.name)
        }
        new = Node(desc, self.__yield_id())
        new.action = action
        self.states.add(new)
        return new

    def add_new_predecessor(self, node, action):
        new = self.new_state(action)

        for pred in node.predecessors:
            pred.successors.remove(node)
            pred.successors.add(new)
            new.predecessors.add(pred)

        node.predecessors = set([new])
        new.successors = set([node])

        return new

    def add_new_successor(self, node, action):
        new = self.new_state(action)

        for succ in node.successors:
            succ.predecessors.remove(node)
            succ.predecessors.add(new)
            new.successors.add(succ)

        node.successors = set([new])
        new.predecessors = set([node])

        return new

    def __generate_states(self, process):
        sb_asts = dict()
        sb_processed = set()
        asts = list()

        for name in [name for name in sorted(process.actions.keys()) if type(process.actions[name]) is Subprocess]:
            ast = copy.copy(process.actions[name].process_ast)
            self.__generate_nodes(process, ast)
            sb_asts[name] = ast
        p_ast = copy.copy(process.process_ast)
        self.initial_states = self.__generate_nodes(process, p_ast)
        asts.append([p_ast, None])

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
                    if pair not in sb_processed:
                        sb_processed.add(pair)
                        asts.append([sb_asts[ast['name']], ast])

                for pre_state in self.__resolve_last(prev):
                    ast['node'].predecessors.add(pre_state)
                    pre_state.successors.add(ast['node'])

    def __resolve_last(self, pr_ast):
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

    def __generate_nodes(self, process, pr_ast):
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
                node = Node(ast, self.__yield_id())

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

    def __yield_id(self):
        self.__id_cnt += 1
        return self.__id_cnt


class Node:

    def __init__(self, desc, identifier):
        self.identifier = identifier
        self.desc = desc
        self.predecessors = set()
        self.successors = set()
        self.action = None
        self.code = None

    def replace_successor(self, old, new):
        self.successors.remove(old)
        self.successors.add(new)

    def replace_predecessor(self, old, new):
        self.predecessors.remove(old)
        self.predecessors.add(new)


class Automaton:

    def __init__(self, logger, analysis, process, identifier):
        # Set default values
        self.control_function = None
        self.state_blocks = {}
        self.cf_structure = None
        self.functions = []
        self.__state_variable = None
        self.__thread_variable = None
        self.__label_variables = {}

        # Set given values
        self.logger = logger
        self.process = process
        self.identifier = identifier

        # Generate FSA itself
        self.logger.info("Generate states for automaton {} based on process {} with category {}".
                         format(self.identifier, self.process.name, self.process.category))
        self.fsa = FSA(self.process)
        self.variables(analysis)

    @property
    def state_variable(self):
        if not self.__state_variable:
            var = Variable('ldv_statevar_{}'.format(self.identifier),  None, 'int a', True)
            var.use += 1
            self.__state_variable = var

        return self.__state_variable

    @property
    def thread_variable(self):
        if not self.__thread_variable:
            var = Variable('ldv_thread_{}'.format(self.identifier),  None, 'struct ldv_thread a', True)
            var.use += 1
            self.__thread_variable = var

        return self.__thread_variable

    def variables(self, analysis):
        variables = []

        # Generate variable for each label
        for label in [self.process.labels[name] for name in sorted(self.process.labels.keys())]:
            if label.interfaces:
                for interface in label.interfaces:
                    variables.append(self.determine_variable(analysis, label, interface))
            else:
                var = self.determine_variable(analysis, label)
                if var:
                    variables.append(self.determine_variable(analysis, label))

        return variables

    def new_param(self, analysis, name, declaration, value):
        lb = self.process.add_label(name, declaration, value)
        lb.resource = True
        vb = self.determine_variable(analysis, lb)
        return lb, vb

    def determine_variable(self, analysis, label, interface=None):
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
                    implementations = self.process.get_implementations(analysis, access)
                    var = Variable("ldv_{}_{}_{}".format(self.identifier, label.name, short_id), None,
                                   label.get_declaration(interface), export=True)

                    if len(implementations) == 1:
                        var.value = implementations[0].adjusted_value(var.declaration)

                        # Change file according to the value
                        var.file = implementations[0].file

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
            label = "Action: {}\n".format(state.desc['label'])

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

        if len(self.fsa.initial_states) > 1:
            name = 'Artificial initial state'
            graph.node(name, name)
            for entry in self.fsa.initial_states:
                graph.edge(
                    str(name),
                    str(entry.identifier)
                )

        # Save to dg_file
        graph.save(dg_file)
        graph.render()

    def generate_code(self, analysis, model, translator, state):
        base_case = {
            "guard": [],
            "body": [],
        }

        if type(state.action) is Call:
            accesses = self.process.resolve_access(state.action.callback)
            callbacks = []

            for access in accesses:
                if access.interface:
                    signature = access.interface.declaration
                    implementations = self.process.get_implementations(analysis, access)

                    if len(implementations) > 1:
                        raise NotImplementedError(
                            "Cannot process fsm with several implementations of a single callback")
                    elif len(implementations) == 1 and analysis.callback_name(implementations[0].value):
                        invoke = '(' + implementations[0].value + ')'
                        file = implementations[0].file
                        check = False
                        func_variable = access.access_with_variable(self.determine_variable(analysis, access.label,
                                                                                            access.list_interface[0].
                                                                                            identifier))
                    elif signature.clean_declaration:
                        invoke = access.access_with_variable(self.determine_variable(analysis, access.label,
                                                                                     access.list_interface[0].
                                                                                     identifier))
                        func_variable = invoke
                        file = translator.entry_file
                        check = True
                    else:
                        invoke = None
                else:
                    signature = access.label.prior_signature

                    func_variable = self.determine_variable(analysis, access.label)
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
                        new_case['pre_call'].extend(self.text_processor(analysis, '$SWITCH_TO_IRQ_CONTEXT();'))
                        new_case['post_call'] = [
                            "/* Callback post-call */"
                        ]
                        new_case['post_call'].extend(self.text_processor(analysis, '$SWITCH_TO_PROCESS_CONTEXT();'))
                    callbacks.append([st, new_case, signature, invoke, file, check, func_variable])

            if len(callbacks) > 0:
                for st, case, signature, invoke, file, check, func_variable in callbacks:
                    # Generate function call and corresponding function
                    params = []
                    pointer_params = []
                    label_params = []
                    cb_statements = []

                    # Determine parameters
                    for index in range(len(signature.points.parameters)):
                        parameter = signature.points.parameters[index]

                        if type(parameter) is not str:
                            expression = None

                            # Search access
                            for access_parameter in st.action.parameters[index:]:
                                accesses = self.process.resolve_access(access_parameter)
                                for acc in accesses:
                                    if acc.list_interface and len(acc.list_interface) > 0 and \
                                            (acc.list_interface[-1].declaration.compare(parameter) or
                                             acc.list_interface[-1].declaration.pointer_alias(parameter)):
                                        expression = acc.access_with_variable(
                                            self.determine_variable(analysis, acc.label,
                                                                    acc.list_interface[0].
                                                                    identifier))
                                        break
                                if expression:
                                    break

                            # Generate new variable
                            if not expression:
                                if type(signature.points.parameters[index]) is not Primitive and \
                                        type(signature.points.parameters[index]) is not Pointer:
                                    param_signature = signature.points.parameters[index].take_pointer
                                    pointer_params.append(index)
                                else:
                                    param_signature = signature.points.parameters[index]

                                lb, var = self.new_param(analysis, "ldv_param_{}_{}".format(st.identifier, index),
                                                         param_signature, None)
                                label_params.append(lb)
                                expression = var.name

                            # Add string
                            params.append(expression)

                    # Add precondition and postcondition
                    if len(label_params) > 0:
                        pre_statements = []
                        post_statements = []
                        for label in sorted(list(set(label_params)), key=lambda lb: lb.name):
                            pre_statements.append('%{}% = $ALLOC(%{}%);'.format(label.name, label.name))
                            post_statements.append('$FREE(%{}%);'.format(label.name))

                        pre_name = 'pre_call_{}'.format(st.identifier)
                        pre_action = self.process.add_condition(pre_name, [], pre_statements)
                        pre_st = self.fsa.add_new_predecessor(st, pre_action)
                        self.generate_code(analysis, model, translator, pre_st)

                        post_name = 'post_call_{}'.format(st.identifier)
                        post_action = self.process.add_condition(post_name, [], post_statements)
                        post_st = self.fsa.add_new_successor(st, post_action)
                        self.generate_code(analysis, model, translator, post_st)

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

                    if ret_access:
                        retval = ret_access[0].access_with_variable(
                            self.determine_variable(analysis, ret_access[0].label))
                        case['retval'] = retval

                    # Add additional condition
                    if state.action.condition and len(state.action.condition) > 0:
                        for statement in state.action.condition:
                            cn = self.text_processor(analysis, statement)
                            base_case["guard"].extend(cn)

                    if st.action.pre_call and len(st.action.pre_call) > 0:
                        pre_call = []
                        for statement in st.action.pre_call:
                            pre_call.extend(self.text_processor(analysis, statement))

                        if 'pre_call' not in case:
                            case['pre_call'] = ['/* Callback pre-call */'] + pre_call
                        else:
                            # Comment + user pre-call + interrupt switch
                            case['pre_call'] = ['/* Callback pre-call */'] + pre_call + case['pre_call'][1:]

                    if st.action.post_call and len(st.action.post_call) > 0:
                        post_call = []
                        for statement in st.action.post_call:
                            post_call.extend(self.text_processor(analysis, statement))

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
            # Generate dispatch function
            automata_peers = {}
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
                    cn = self.text_processor(analysis, statement)
                    base_case["guard"].extend(cn)

            base_case['relevant automata'] = automata_peers
            state.code = base_case
        elif type(state.action) is CallRetval:
            base_case["body"].append("/* Should wait for return value of {} here, "
                                     "but in sequential model it is not necessary */".format(state.action.name))
            state.code = base_case
        elif type(state.action) is Receive:
            # Generate dispatch function
            automata_peers = {}
            if len(state.action.peers) > 0:
                # Do call only if model which can be called will not hang
                translator.extract_relevant_automata(automata_peers, state.action.peers, Dispatch)

                # Add additional condition
                base_case["receive guard"] = []
                if state.action.condition and len(state.action.condition) > 0:
                    for statement in state.action.condition:
                        cn = self.text_processor(analysis, statement)
                        base_case["receive guard"].extend(cn)
            else:
                # Generate comment
                base_case["body"].append("/* Receive {} does not expect any signal from existing processes, skip it */".
                                         format(state.action.name))

            base_case['relevant automata'] = automata_peers
            state.code = base_case
        elif type(state.action) is Condition:
            # Generate comment
            base_case["body"].append("/* Code or condition insertion {} */".format(state.action.name))

            # Add additional condition
            if state.action.condition and len(state.action.condition) > 0:
                for statement in state.action.condition:
                    cn = self.text_processor(analysis, statement)
                    base_case["guard"].extend(cn)

            if state.action.statements:
                for statement in state.action.statements:
                    base_case["body"].extend(self.text_processor(analysis, statement))
            state.code = base_case
        elif type(state.action) is Subprocess:
            # Generate comment
            base_case["body"].append("/* Jump to an initial state of subprocess '{}' */".format(state.action.name))

            # Add additional condition
            if state.action.condition and len(state.action.condition) > 0:
                for statement in state.action.condition:
                    cn = self.text_processor(analysis, statement)
                    base_case["guard"].extend(cn)

            # Add additional condition
            if state.action.condition and len(state.action.condition) > 0:
                for statement in state.action.condition:
                    cn = self.text_processor(analysis, statement)
                    base_case["guard"].extend(cn)

            state.code = base_case
        else:
            raise ValueError("Unexpected state machine edge type: {}".format(state.action.type))

    def text_processor(self, analysis, statement):
        # Replace model functions
        mm = FunctionModels()
        accesses = self.process.accesses()

        statements = [statement]
        for access in accesses:
            new_statements = []
            for text in list(statements):
                processed = False
                for option in sorted(accesses[access], key=lambda ac: ac.expression):
                    if option.interface:
                        signature = option.label.get_declaration(option.interface.identifier)
                    else:
                        signature = option.label.prior_signature

                    if signature:
                        if option.interface:
                            var = self.determine_variable(analysis, option.label,
                                                               option.list_interface[0].identifier)
                        else:
                            var = self.determine_variable(analysis, option.label)

                        try:
                            tmp = mm.replace_models(option.label.name, signature, text)
                            tmp = option.replace_with_variable(tmp, var)
                            new_statements.append(tmp)
                            processed = True
                        except ValueError:
                            processed = True

                if not processed:
                    new_statements.append(text)
            statements = new_statements

        # Filter out statements without processes expressions
        final = set()
        for stm in list(statements):
            if '%' not in stm and '$' not in statements:
                final.add(stm)

        return list(final)

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
