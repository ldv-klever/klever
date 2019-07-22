#
# Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
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

from operator import attrgetter

from core.vtg.emg.common import get_conf_property
from core.vtg.emg.common.process import Subprocess
from core.vtg.emg.modelTranslator.fsa_translator.common import initialize_automaton_variables


def label_based_function(cmodel, conf, analysis, automaton, cf, model=True):
    v_code, f_code = list(), list()

    # Determine returning expression for reuse
    if not get_conf_property(conf, 'direct control functions calls') and not model:
        ret_expression = 'return 0;'
    else:
        ret_expression = 'return;'

    if model:
        kfunction_obj = analysis.get_source_function(automaton.process.name)
        if kfunction_obj.declaration.return_value and kfunction_obj.declaration.return_value.identifier != 'void':
            ret_expression = None

    # Initialize variables
    # First add variables declarations
    for var in automaton.variables(only_used=True):
        scope = {automaton.process.file} if automaton.process.file else None
        v_code.append(var.declare(scope=scope) + ';')

    # Then add memory external allocation marks
    f_code.extend(initialize_automaton_variables(conf, automaton))

    # After that assign explicit values
    for var in (v for v in automaton.variables(only_used=True) if v.value):
        f_code.append("{} = {};".format(var.name, var.value))

    main_v_code, main_f_code = __label_sequence(automaton, list(automaton.fsa.initial_states)[0], ret_expression)
    v_code.extend(main_v_code)
    f_code.extend(main_f_code)
    f_code.append("/* End of the process */")
    if ret_expression:
        f_code.append(ret_expression)

    processed = []
    for subp in [s for s in sorted(automaton.fsa.states, key=lambda s: s.identifier)
                 if isinstance(s.action, Subprocess)]:
        if subp.action.name not in processed:
            sp_v_code, sp_f_code = __label_sequence(automaton, list(subp.successors)[0], ret_expression)

            v_code.extend(sp_v_code)
            f_code.extend([
                '',
                '/* Sbprocess {} */'.format(subp.action.name),
                'ldv_{}_{}:'.format(subp.action.name, automaton.identifier)
            ])
            f_code.extend(sp_f_code)
            f_code.append("/* End of the subprocess '{}' */".format(subp.action.name))
            if ret_expression:
                f_code.append(ret_expression)
            processed.append(subp.action.name)

    v_code = [cmodel.model_comment('CONTROL_FUNCTION_INIT_BEGIN', 'Declare auxiliary variables.')] + \
             v_code + \
             [cmodel.model_comment('CONTROL_FUNCTION_INIT_END', 'Declare auxiliary variables.')]
    if model:
        name = automaton.process.name
        v_code.insert(0, cmodel.control_function_comment_begin(cf.name, automaton.process.comment))
    else:
        name = '{}({})'.format(automaton.process.name, automaton.process.category)
        v_code.insert(0, cmodel.control_function_comment_begin(cf.name, automaton.process.comment, automaton.identifier))
    f_code.append(cmodel.control_function_comment_end(cf.name, name))
    cf.body.extend(v_code + f_code)

    return cf.name


def normalize_fsa(automaton, composer):
    """
    Normalize fsa to make life easier for code generators. Do the following transformations:
    * Avoid several entry point states;
    * Generate for each subprocess jump state an artificial state which can be considered as entry point to get into
      subprocess. All subprocess jumping states will have the only successor - such corresponding artificial state.
    * For cases when two (or more) predecessor states lead into two (or more) successor states at once insert an
      intermediate state which will has two (or more) predecessors and two (or more) successors to prevent such cross
      dependencies.

    :param automaton: Automaton object.
    :param composer: Method to compose new code blocks.
    :return: None.
    """
    new_states = list()

    # Keep subprocess states as jump points
    # Insert process and subprocess artificial single entry states
    for subprocess in (a for a in automaton.process.actions.values() if isinstance(a, Subprocess)):
        new = automaton.fsa.new_state(None)
        new_states.append(new)

        # Insert state
        jump_states = sorted([s for s in automaton.fsa.states if s.action and s.action.name == subprocess.name],
                             key=attrgetter('identifier'))
        for jump in jump_states:
            for successor in jump.successors:
                successor.replace_predecessor(jump, new)
                jump.replace_successor(successor, new)

    # Add a single artificial initial state if there are several of them
    if len(automaton.fsa.initial_states) > 1:
        initial_states = automaton.fsa.initial_states
        new = automaton.fsa.new_state(None)
        new_states.append(new)

        # Make generator before adding an additional state, since new state without successors and predecessors is
        # considered as an entry point too
        for initial in initial_states:
            initial.insert_predecessor(new)

    # Remove cross dependencies
    candidates = [s for s in automaton.fsa.states if len(s.successors) > 1 and
                  len(list(s.successors)[0].predecessors) > 1]
    while len(candidates) > 0:
        candidate = candidates.pop()
        target_set = candidate.successors
        source_set = list(target_set)[0].predecessors

        # Check that all source nodes have the same target set and vice versa
        cross_dependency_exist = True
        for t in target_set:
            if len(set(t.predecessors).symmetric_difference(source_set)) != 0:
                cross_dependency_exist = False
                break

        if cross_dependency_exist:
            for s in source_set:
                if len(set(s.successors).symmetric_difference(target_set)) != 0:
                    cross_dependency_exist = False
                    break

        # Remove cross dependency
        if cross_dependency_exist:
            new = automaton.fsa.new_state(None)
            new_states.append(new)
            for s in source_set:
                for t in target_set:
                    s.remove_successor(t)
                    t.remove_predecessor(s)
                    new.insert_predecessor(s)
                    new.insert_successor(t)

                # Remove rest candidates
                if s in candidates:
                    candidates.remove(s)

    # Compose new action code blocks
    for state in new_states:
        composer(state, automaton)

    return


def __merge_points(initial_states):
    # Terminal marking
    def add_terminal(terminal, out_value, split_points, subprocess=False):
        for split in out_value:
            for branch in out_value[split]:
                if branch in split_points[split]['merge branches'] and subprocess:
                    split_points[split]['merge branches'].remove(branch)
                if branch not in split_points[split]['terminals']:
                    split_points[split]['terminals'][branch] = set()
                split_points[split]['terminals'][branch].add(terminal)

            split_points[split]['terminal merge sets'][terminal] = out_value[split]

    # Condition calculation
    def do_condition(states, terminal_branches, finals, merge_list, split, split_data, merge_points, graph):
        # Set up branches
        condition = {'pending': list(), 'terminals': list()}
        largest_unintersected_mergesets = []
        while len(merge_list) > 0:
            merge = merge_list.pop(0)
            merged_states = split_data['split sets'][merge]
            terminal_branches -= merged_states
            diff = states - merged_states
            if len(diff) < len(states):
                largest_unintersected_mergesets.append(merge)
                if len(merged_states) == 1:
                    condition['pending'].append(next(iter(merged_states)))
                elif len(merged_states) > 1:
                    sc_finals = set(merge_points[merge][split])
                    # Do not add terminals if there is living edge with the branch from the merge point
                    sc_terminals = set(split_data['terminals'].keys()).intersection(merged_states)
                    for candidate in list(sc_terminals):
                        living_out_edge = [o for o in graph[merge] if split in graph[merge][o] and
                                           candidate in graph[merge][o][split]]
                        if len(living_out_edge) > 0:
                            sc_terminals.remove(candidate)
                    new_condition = do_condition(set(merged_states), sc_terminals, sc_finals, list(merge_list),
                                                 split, split_data, merge_points, graph)
                    condition['pending'].append(new_condition)
                else:
                    raise RuntimeError('Invalid merge')
            states = diff

        # Add rest independent branches
        if len(states) > 0:
            condition['pending'].extend(sorted(states))

        # Add predecessors of the latest merge sets if there are not covered in terminals, but be aware of merge points
        # that merge branches before original split point is finally closed
        for merge in largest_unintersected_mergesets:
            bad = False
            for terminal_branch in terminal_branches:
                for terminal in split_data['terminals'][terminal_branch]:
                    if split_points[split]['split sets'][merge].\
                            issubset(split_data['terminal merge sets'][terminal]):
                        bad = True
                        break

            if not bad:
                # Check that it is truely last merge point
                living_outs = [o for o in graph[merge] if split in graph[merge][o] and len(graph[merge][o][split]) > 0]
                if len(living_outs) == 0:
                    condition['terminals'].extend(merge_points[merge][split])

                # Add terminal
                terminal_branches.update(set(split_data['terminals'].keys()).
                                         intersection(split_data['split sets'][merge]))

        # Add terminals which are not belong to any merge set.
        for branch in terminal_branches:
            condition['terminals'].extend(split_data['terminals'][branch])

        # Add provided
        condition['terminals'].extend(finals)

        # Return child condition if the last is not a condition
        if len(condition['pending']) == 1:
            condition = condition['pending'][0]

        # Save all branches
        condition['branches'] = list(condition['pending'])

        # Save total number of branches
        condition['len'] = len(condition['pending'])

        return condition

    # Collect iformation about branches
    graph = dict()
    split_points = dict()
    merge_points = dict()
    processed = set()
    queue = sorted(initial_states, key=attrgetter('identifier'))
    merge_queue = list()
    while len(queue) > 0 or len(merge_queue) > 0:
        if len(queue) != 0:
            st = queue.pop(0)
        else:
            st = merge_queue.pop(0)

        # Add epson states
        if st.identifier not in graph:
            graph[st.identifier] = dict()

        # Calculate output branches
        out_value = dict()
        if st not in initial_states and len(st.predecessors) > 1 and \
                len({s for s in st.predecessors if s.identifier not in processed}) > 0:
            merge_queue.append(st)
        else:
            if st not in initial_states and len(st.predecessors) > 1:
                # Try to collect all branches first
                for predecessor in st.predecessors:
                    for split in graph[predecessor.identifier][st.identifier]:
                        if split not in out_value:
                            out_value[split] = set()
                        out_value[split].update(graph[predecessor.identifier][st.identifier][split])

                        for node in graph[predecessor.identifier][st.identifier][split]:
                            split_points[split]['branch liveness'][node] -= 1

                # Remove completely merged branches
                for split in list(out_value.keys()):
                    for predecessor in (p for p in st.predecessors
                                        if split in graph[p.identifier][st.identifier]):
                        if len(out_value[split].symmetric_difference(
                                graph[predecessor.identifier][st.identifier][split])) > 0 or \
                           len(split_points[split]['merge branches'].
                                symmetric_difference(graph[predecessor.identifier][st.identifier][split])) == 0:
                            # Add terminal states for each branch
                            if st.identifier not in merge_points:
                                merge_points[st.identifier] = dict()
                            merge_points[st.identifier][split] = \
                                {p.identifier for p in st.predecessors
                                 if split in graph[p.identifier][st.identifier]}

                            # Add particular set of merged branches
                            split_points[split]['split sets'][st.identifier] = out_value[split]

                            # Remove, since all branches are merged
                            if len(split_points[split]['merge branches'].
                                           difference(out_value[split])) == 0 and \
                               len({s for s in split_points[split]['total branches']
                                    if split_points[split]['branch liveness'][s] > 0}) == 0:
                                # Merge these branches
                                del out_value[split]
                            break
            elif st not in initial_states and len(st.predecessors) == 1:
                # Just copy meta info from the previous predecessor
                out_value = dict(graph[list(st.predecessors)[0].identifier][st.identifier])
                for split in out_value:
                    for node in out_value[split]:
                        split_points[split]['branch liveness'][node] -= 1

            # If it is a split point, create meta information on it and start tracking its branches
            if len(st.successors) > 1:
                split_points[st.identifier] = {
                    'total branches': {s.identifier for s in st.successors},
                    'merge branches': {s.identifier for s in st.successors},
                    'split sets': dict(),
                    'terminals': dict(),
                    'terminal merge sets': dict(),
                    'branch liveness': {s.identifier: 0 for s in st.successors}
                }
            elif len(st.successors) == 0:
                add_terminal(st.identifier, out_value, split_points)

            # Assign branch tracking information to an each output branch
            for successor in st.successors:
                if successor not in graph:
                    graph[successor.identifier] = dict()
                # Assign branches from the previous split points
                graph[st.identifier][successor.identifier] = dict(out_value)

                # Branches with subprocesses has no merge point
                if isinstance(successor.action, Subprocess):
                    new_out_value = dict(out_value)
                    if st.identifier in split_points and st.identifier not in new_out_value:
                        new_out_value[st.identifier] = {successor.identifier}
                    add_terminal(successor.identifier, new_out_value, split_points, subprocess=True)
                else:
                    if st.identifier in split_points:
                        # Mark new branch
                        graph[st.identifier][successor.identifier][st.identifier] = {successor.identifier}

                    for split in graph[st.identifier][successor.identifier]:
                        for branch in graph[st.identifier][successor.identifier][split]:
                            # Do not expect to find merge point for this branch
                            split_points[split]['branch liveness'][branch] += 1

                    if len(successor.predecessors) > 1:
                        if successor not in merge_queue:
                            merge_queue.append(successor)
                    else:
                        if successor not in queue:
                            queue.append(successor)

                processed.add(st.identifier)

    # Do sanity check
    conditions = dict()
    for split in split_points:
        for branch in split_points[split]['branch liveness']:
            if split_points[split]['branch liveness'][branch] > 0:
                raise RuntimeError('Incorrect merge point detection')

        # Calculate conditions then
        conditions[split] = list()

        # Check merge points number
        left = set(split_points[split]['total branches'])
        merge_list = sorted(split_points[split]['split sets'].keys(),
                            key=lambda y: len(split_points[split]['split sets'][y]), reverse=True)
        condition = do_condition(left, split_points[split]['terminals'].keys(), set(), merge_list, split,
                                 split_points[split], merge_points, graph)
        conditions[split] = condition

    return conditions


def __label_sequence(automaton, initial_state, ret_expression):
    def start_branch(tab, f_code, condition):
        if condition['len'] == 2:
            if len(condition['pending']) == 1:
                f_code.append('\t' * tab + 'if (ldv_undef_int()) {')
            elif len(condition['pending']) == 0:
                f_code.append('\t' * tab + 'else {')
            else:
                raise ValueError('Invalid if conditional left states: {}'.
                                 format(len(condition['pending'])))
            tab += 1
        elif condition['len'] > 2:
            index = condition['len'] - len(condition['pending'])
            f_code.append('\t' * tab + 'case {}: '.format(index) + '{')
            tab += 1
        else:
            raise ValueError('Invalid condition branch number: {}'.format(condition['len']))
        return tab

    def close_branch(tab, f_code, condition):
        if condition['len'] == 2:
            tab -= 1
            f_code.append('\t' * tab + '}')
        elif condition['len'] > 2:
            f_code.append('\t' * tab + 'break;')
            tab -= 1
            f_code.append('\t' * tab + '}')
        else:
            raise ValueError('Invalid condition branch number: {}'.format(condition['len']))
        return tab

    def start_condition(tab, f_code, condition, conditional_stack, state_stack):
        conditional_stack.append(condition)

        if len(conditional_stack[-1]['pending']) > 2:
            f_code.append('\t' * tab + 'switch (ldv_undef_int()) {')
            tab += 1
        tab = process_next_branch(tab, f_code, conditional_stack, state_stack)
        return tab

    def close_condition(tab, f_code, conditional_stack):
        # Close the last branch
        tab = close_branch(tab, f_code, conditional_stack[-1])

        # Close conditional statement
        if conditional_stack[-1]['len'] > 2:
            f_code.append('\t' * tab + 'default: ldv_assume(0);')
            tab -= 1
            f_code.append('\t' * tab + '}')
        conditional_stack.pop()
        return tab

    # Start processing the next conditional branch
    def process_next_branch(tab, f_code, conditional_stack, state_stack):
        # Try to add next branch
        next_branch = conditional_stack[-1]['pending'].pop()
        tab = start_branch(tab, f_code, conditional_stack[-1])

        if isinstance(next_branch, dict):
            # Open condition
            tab = start_condition(tab, f_code, next_branch, conditional_stack, state_stack)
        else:
            # Just add a state
            next_state = automaton.fsa.resolve_state(next_branch)
            state_stack.append(next_state)
        return tab

    def require_merge(state, processed_states, condition):
        if len(condition['pending']) == 0 and state.identifier in condition['terminals'] and \
                        len(set(condition['terminals']) - processed_states) == 0:
            return True
        else:
            return False

    f_code = []
    v_code = []

    # Add artificial state if input contains more than one state
    state_stack = [initial_state]

    # First calculate merge points
    conditions = __merge_points(list(state_stack))

    processed_states = set()
    conditional_stack = []
    tab = 0
    while len(state_stack) > 0:
        state = state_stack.pop()
        processed_states.add(state.identifier)

        # Get statements
        v, f = state.code
        new_v_code = list(v)
        new_f_code = list(f)

        v_code.extend(new_v_code)
        if isinstance(state.action, Subprocess):
            new_f_code.extend([
                '/* Jump to a subprocess {!r} initial state */'.format(state.action.name),
                'goto ldv_{}_{};'.format(state.action.name, automaton.identifier)
            ])

        # If this is a terminal state - quit control function
        if not isinstance(state.action, Subprocess) and len(state.successors) == 0:
            new_f_code.extend([
                ''
                "/* Exit function at a terminal state */",
            ])
            if ret_expression:
                new_f_code.append(ret_expression)

        f_code.extend(['\t' * tab + stm for stm in new_f_code])

        # If this is a terminal state before completely closed merge point close the whole merge
        while len(conditional_stack) > 0 and require_merge(state, processed_states, conditional_stack[-1]):
            # Close the last branch and the condition
            tab = close_condition(tab, f_code, conditional_stack)

        # Close branch of the last condition
        if len(conditional_stack) > 0 and state.identifier in conditional_stack[-1]['terminals']:
            # Close this branch
            tab = close_branch(tab, f_code, conditional_stack[-1])
            # Start new branch
            tab = process_next_branch(tab, f_code, conditional_stack, state_stack)
        elif not isinstance(state.action, Subprocess):
            # Add new states in terms of the current branch
            if len(state.successors) > 1:
                # Add new condition
                condition = conditions[state.identifier]
                tab = start_condition(tab, f_code, condition, conditional_stack, state_stack)
            elif len(state.successors) == 1:
                # Just add the next state
                state_stack.append(next(iter(state.successors)))

    if len(conditional_stack) > 0:
        raise RuntimeError('Cannot leave unclosed conditions: {}'.format(automaton.process.name))

    return [v_code, f_code]
