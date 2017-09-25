#
# Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
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
import re


def generic_simplifications(logger, trace):
    logger.info('Simplify error trace')
    _basic_simplification(logger, trace)
    _remove_switch_cases(logger, trace)
    _remove_tmp_vars(logger, trace)
    _remove_aux_functions(logger, trace)
    trace.sanity_checks()


def _basic_simplification(logger, error_trace):
    # Remove all edges without source attribute. Otherwise visualization will be very poor.
    for edge in (e for e in error_trace.trace_iterator() if 'source' not in e):
        # Now we do need source code to be presented with all edges.
        logger.warning('Do not expect edges without source attribute')
        error_trace.remove_edge_and_target_node(edge)

    # Simple transformations.
    for edge in error_trace.trace_iterator():
        # Make source code more human readable.
        # Remove all broken indentations - error traces visualizer will add its own ones but will do this in much
        # more attractive way.
        edge['source'] = re.sub(r'[ \t]*\n[ \t]*', ' ', edge['source'])

        # Remove "[...]" around conditions.
        if 'condition' in edge:
            edge['source'] = edge['source'].strip('[]')

        # Get rid of continues whitespaces.
        edge['source'] = re.sub(r'[ \t]+', ' ', edge['source'])

        # Remove space before trailing ";".
        edge['source'] = re.sub(r' ;$', ';', edge['source'])

        # Remove space before "," and ")".
        edge['source'] = re.sub(r' (,|\))', '\g<1>', edge['source'])

        # Replace "!(... ==/!=/<=/>=/</> ...)" with "... !=/==/>/</>=/<= ...".
        cond_replacements = {'==': '!=', '!=': '==', '<=': '>', '>=': '<', '<': '>=', '>': '<='}
        for orig_cond, replacement_cond in cond_replacements.items():
            m = re.match(r'^!\((.+) {0} (.+)\)$'.format(orig_cond), edge['source'])
            if m:
                edge['source'] = '{0} {1} {2}'.format(m.group(1), replacement_cond, m.group(2))
                # Do not proceed after some replacement is applied - others won't be done.
                break

        # Remove unnessary "(...)" around returned values/expressions.
        edge['source'] = re.sub(r'^return \((.*)\);$', 'return \g<1>;', edge['source'])

        # Make source code and assumptions more human readable (common improvements).
        for source_kind in ('source', 'assumption'):
            if source_kind in edge:
                # Remove unnessary "(...)" around integers.
                edge[source_kind] = re.sub(r' \((-?[0-9]+\w*)\)', ' \g<1>', edge[source_kind])

                # Replace "& " with "&".
                edge[source_kind] = re.sub(r'& ', '&', edge[source_kind])


def _remove_tmp_vars(logger, error_trace):
    # Get rid of temporary variables. Replace:
    #   ... tmp...;
    #   ...
    #   tmp... = func(...);
    #   [... tmp... ...;]
    # with (removing first and last statements if so):
    #   ...
    #   ... func(...) ...;
    removed_tmp_vars_num = __remove_tmp_vars(error_trace, next(error_trace.trace_iterator()))[0]

    if removed_tmp_vars_num:
        logger.debug('{0} temporary variables were removed'.format(removed_tmp_vars_num))


def __remove_tmp_vars(error_trace, edge):
    removed_tmp_vars_num = 0

    # Remember current function. All temporary variables defined in a given function can be used just in it.
    # The only function for which we can't do this is main (entry point) since we don't enter it explicitly but it
    # never returns due to some errors happen early so it doesn't matter.
    if 'enter' in edge:
        func_id = edge['enter']
        return_edge = error_trace.get_func_return_edge(edge)
        # Move forward to function declarations or/and statements.
        edge = error_trace.next_edge(edge)
    else:
        return_edge = None

    # Scan variable declarations to find temporary variable names and corresponding edge ids.
    tmp_var_names = dict()
    edges_map = dict()
    for edge in error_trace.trace_iterator(begin=edge):
        # Declarations are considered to finish when entering/returning from function, some condition is checked or some
        # assigment is performed. Unfortunately we consider calls to functions without bodies that follow declarations
        # as declarations.
        if 'return' in edge or 'enter' in edge or 'condition' in edge or '=' in edge['source']:
            break

        m = re.search(r'(tmp\w*);$', edge['source'])
        if m:
            edges_map[id(edge)] = edge
            tmp_var_names[m.group(1)] = id(edge)

    # Remember what temporary varibles aren't used after all. Temporary variables that are really required will be
    # remained as is.
    unused_tmp_var_decl_ids = set(list(tmp_var_names.values()))

    # Scan statements to find function calls which results are stored into temporary variables.
    error_trace_iterator = error_trace.trace_iterator(begin=edge)
    for edge in error_trace_iterator:
        # Reach end of current function.
        if edge is return_edge:
            break

        # Remember current edge that can represent function call. We can't check this by presence of attribute "enter"
        # since functions can be without bodies and thus without enter-return edges.
        func_call_edge = edge

        # Recursively get rid of temporary variables inside called function if there are some edges belonging to that
        # function.
        if 'enter' in edge and error_trace.next_edge(func_call_edge):
            removed_tmp_vars_num_tmp, next_edge = __remove_tmp_vars(error_trace, func_call_edge)
            removed_tmp_vars_num += removed_tmp_vars_num_tmp

            # Skip all edges belonging to called function.
            while True:
                edge = next(error_trace_iterator)
                if edge is next_edge:
                    break

        # Result of function call is stored into temporary variable.
        m = re.search(r'^(tmp\w*)\s+=\s+(.+);$', func_call_edge['source'])

        if not m:
            continue

        tmp_var_name = m.group(1)
        func_call = m.group(2)

        # Do not proceed if found temporary variable wasn't declared. Actually it will be very strange if this will
        # happen
        if tmp_var_name not in tmp_var_names:
            continue

        tmp_var_decl_id = tmp_var_names[tmp_var_name]

        # Try to find temorary variable usages on edges following corresponding function calls.
        tmp_var_use_edge = error_trace.next_edge(edge)

        # There is no usage of temporary variable but we still can remove its declaration and assignment.
        if not tmp_var_use_edge:
            func_call_edge['source'] = func_call + ';'
            break

        # Skip simplification of the following sequence:
        #   ... tmp...;
        #   ...
        #   tmp... = func(...);
        #   ... gunc(... tmp... ...);
        # since it requires two entered functions from one edge.
        if 'enter' in tmp_var_use_edge:
            # Do not assume that each temporary variable is used only once. This isn't the case when they are used
            # within cycles. That's why do not require temporary variable to be in list of temporary variables to be
            # removed - it can be withdrawn from this list on previous cycle iteration.
            if tmp_var_decl_id in unused_tmp_var_decl_ids:
                unused_tmp_var_decl_ids.remove(tmp_var_decl_id)
        else:
            m = re.search(r'^(.*){0}(.*)$'.format(tmp_var_name), tmp_var_use_edge['source'])

            # Do not proceed if pattern wasn't matched.
            if not m:
                continue

            func_call_edge['source'] = m.group(1) + func_call + m.group(2)

            # Move vital attributes from edge to be removed. If this edge represents warning it can not be removed
            # without this.
            for attr in ('condition', 'return', 'note', 'warn'):
                if attr in tmp_var_use_edge:
                    func_call_edge[attr] = tmp_var_use_edge.pop(attr)

            # Edge to be removed is return edge from current function.
            is_reach_cur_func_end = True if tmp_var_use_edge is return_edge else False

            # Remove edge corresponding to temporary variable usage.
            error_trace.remove_edge_and_target_node(tmp_var_use_edge)

            removed_tmp_vars_num += 1

            if is_reach_cur_func_end:
                break

    # Remove all temporary variable declarations in any case.
    for tmp_var_decl_id in reversed(list(unused_tmp_var_decl_ids)):
        error_trace.remove_edge_and_target_node(edges_map[tmp_var_decl_id])

    return removed_tmp_vars_num, edge


def _parse_func_call_actual_args(actual_args_str):
    actual_args = []
    actual_args_str_iter = iter(actual_args_str)
    actual_arg = ''
    for c in actual_args_str_iter:
        # Take into account that function pointer casts can use commas which also separate function arguments from
        # each other.
        if c == '(':
            actual_arg += c
            # Skip all nested "(...)".
            open_paren_num = 0
            while True:
                c_next = next(actual_args_str_iter)
                actual_arg += c_next
                if c_next == '(':
                    open_paren_num += 1
                elif c_next == ')':
                    if open_paren_num:
                        open_paren_num -= 1
                    else:
                        break
        elif c == ',':
            actual_args.append(actual_arg.strip())
            actual_arg = ''
        else:
            actual_arg += c

    # Add last argument which isn't followed by comma if so.
    if actual_arg:
        actual_args.append(actual_arg.strip())

    return actual_args


def _remove_aux_functions(logger, error_trace):
    # Get rid of auxiliary functions if possible. Replace:
    #   ... = aux_func(...)
    #     return func(...)
    # with:
    #   ... = func(...)
    # and:
    #   assume(aux_func(...) ...)
    #     return func(...)
    # with:
    #   assume(func(...) ...)
    # and:
    #   aux_func(...)
    #     func(...)
    #     [return]
    # with:
    #   func(...)
    # accurately replacing arguments if required.
    removed_aux_funcs_num = 0
    for edge in error_trace.trace_iterator():
        # Begin to match pattern just for edges that represent calls of auxiliary functions.
        if 'enter' not in edge or edge['enter'] not in error_trace.aux_funcs:
            continue

        aux_func_call_edge = edge

        next_edge = error_trace.next_edge(edge)

        # Do not proceed if there isn't next edge or it doesn't represent function call.
        if not next_edge or 'enter' not in next_edge:
            continue

        func_call_edge = next_edge

        # Get lhs and actual arguments of called auxiliary function if so.
        m = re.search(r'^(.*){0}\s*\((.*)\)(.*)$'.format(error_trace.resolve_function(aux_func_call_edge['enter'])),
                      aux_func_call_edge['source'])

        # Do not proceed if meet unexpected format of function call.
        if not m:
            continue

        lhs = m.group(1)
        aux_actual_args = _parse_func_call_actual_args(m.group(2))
        rel_expr = m.group(3)

        func_name = error_trace.resolve_function(func_call_edge['enter'])

        # Get actual arguments of called function if so.
        m = re.search(r'^.*{0}\s*\((.*)\);$'.format(func_name), func_call_edge['source'])

        # Do not proceed if meet unexpected format of function call.
        if not m:
            continue

        actual_args = _parse_func_call_actual_args(m.group(1))

        # Do not proceed if names of actual arguments of called function don't correspond to ones obtained during model
        # comments parsing. Without this we won't be able to replace them with corresponding actual arguments of called
        # auxiliary function.
        is_all_replaced = True
        for i, actual_arg in enumerate(actual_args):
            is_replaced = False
            for j, formal_arg_name in enumerate(error_trace.aux_funcs[aux_func_call_edge['enter']]['formal arg names']):
                if actual_arg.endswith(formal_arg_name) and j < len(aux_actual_args):
                    actual_args[i] = aux_actual_args[j]
                    is_replaced = True
                    break
            if is_replaced:
                continue

            is_all_replaced = False
            break

        if not is_all_replaced:
            continue

        # Third pattern. For first and second patterns it is enough that next edge returns from function since this
        # function can be just the parent auxiliary one.
        if 'return' not in func_call_edge:
            return_edge = error_trace.get_func_return_edge(func_call_edge)

            # Recursively skip body of next function entered when returning from the given one. Corresponding
            # pattern is:
            #   enter auxiliary function
            #     enter function
            #       ...
            #       enter function 1 and return from function
            #         ...
            #         [enter function 2 and] return from function 1
            #            ...
            while True:
                if return_edge and 'enter' in return_edge:
                    return_edge = error_trace.get_func_return_edge(return_edge)
                else:
                    break

            aux_func_return_edge = error_trace.get_func_return_edge(aux_func_call_edge)

            # Do not remove auxiliary function since there are some extra edges between function call and return from
            # auxiliary function.
            if return_edge and aux_func_return_edge is not error_trace.next_edge(return_edge):
                continue

            if aux_func_return_edge:
                # Do not remove auxiliary function since its return statement is not trivial.
                if aux_func_return_edge['source'] != 'return;':
                    continue
                error_trace.remove_edge_and_target_node(aux_func_return_edge)

        if error_trace.aux_funcs[aux_func_call_edge['enter']]['is callback']:
            for attr in ('file', 'start line'):
                aux_func_call_edge['original ' + attr] = aux_func_call_edge[attr]
                aux_func_call_edge[attr] = error_trace.next_edge(next_edge)[attr]

        func_call = func_name + '(' + (', '.join(actual_args) if actual_args else '') + ')'
        if 'condition' in aux_func_call_edge:
            aux_func_call_edge['source'] = func_call + rel_expr
        else:
            aux_func_call_edge['source'] = lhs + func_call + ';'

        aux_func_call_edge['enter'] = func_call_edge['enter']

        if 'note' in func_call_edge:
            aux_func_call_edge['note'] = func_call_edge['note']

        error_trace.remove_edge_and_target_node(func_call_edge)

        removed_aux_funcs_num += 1

    if removed_aux_funcs_num:
        logger.debug('{0} auxiliary functions were removed'.format(removed_aux_funcs_num))


def _remove_switch_cases(logger, error_trace):
    # Get rid of redundant switch cases. Replace:
    #   assume(x != A)
    #   assume(x != B)
    #   ...
    #   assume(x == Z)
    # with:
    #   assume(x == Z)
    removed_switch_cases_num = 0
    for edge in error_trace.trace_iterator():
        # Begin to match pattern just for edges that represent conditions.
        if 'condition' not in edge:
            continue

        # Get all continues conditions.
        cond_edges = []
        for cond_edge in error_trace.trace_iterator(begin=edge):
            if 'condition' not in cond_edge:
                break
            cond_edges.append(cond_edge)

        # Do not proceed if there is not continues conditions.
        if len(cond_edges) == 1:
            continue

        x = None
        start_idx = 0
        cond_edges_to_remove = []
        for idx, cond_edge in enumerate(cond_edges):
            m = re.search(r'^(.+) ([=!]=)', cond_edge['source'])

            # Start from scratch if meet unexpected format of condition.
            if not m:
                x = None
                continue

            # Do not proceed until first condition matches pattern.
            if x is None and m.group(2) != '!=':
                continue

            # Begin to collect conditions.
            if x is None:
                start_idx = idx
                x = m.group(1)
                continue
            # Start from scratch if first expression condition differs.
            elif x != m.group(1):
                x = None
                continue

            # Finish to collect conditions. Pattern matches.
            if x is not None and m.group(2) == '==':
                cond_edges_to_remove.extend(cond_edges[start_idx:idx])
                x = None
                continue

        for cond_edge in reversed(cond_edges_to_remove):
            error_trace.remove_edge_and_target_node(cond_edge)
            removed_switch_cases_num += 1

    if removed_switch_cases_num:
        logger.debug('{0} switch cases were removed'.format(removed_switch_cases_num))

