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
    _basic_simplification(trace)
    _remove_artificial_edges(logger, trace)
    _remove_aux_functions(logger, trace)


def _basic_simplification(error_trace):
    # Simple transformations.
    for edge in error_trace.trace_iterator():
        # Make source code more human readable.
        if 'source' in edge:
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

            # Replace "!(... ==/!=/</> ...)" with "... !=/==/>/< ...".
            edge['source'] = re.sub(r'^!\((.+)==(.+)\)$', '\g<1>!=\g<2>', edge['source'])
            edge['source'] = re.sub(r'^!\((.+)!=(.+)\)$', '\g<1>==\g<2>', edge['source'])
            edge['source'] = re.sub(r'^!\((.+)<(.+)\)$', '\g<1>>\g<2>', edge['source'])
            edge['source'] = re.sub(r'^!\((.+)>(.+)\)$', '\g<1><\g<2>', edge['source'])

        # Make source code and assumptions more human readable (common improvements).
        for source_kind in ('source', 'assumption'):
            if source_kind in edge:
                # Replace unnessary "(...)" around integers and identifiers.
                edge[source_kind] = re.sub(r' \((-?\w+)\)', ' \g<1>', edge[source_kind])

                # Replace "& " with "&".
                edge[source_kind] = re.sub(r'& ', '&', edge[source_kind])


def _remove_artificial_edges(logger, error_trace):
    # More advanced transformations.
    # Get rid of artificial edges added after returning from functions.
    removed_edges_num = 0
    for edge in error_trace.trace_iterator():
        if 'return' in edge:
            next_edge = error_trace.next_edge(edge)
            error_trace.remove_edge_and_target_node(next_edge)
            removed_edges_num += 1
    if removed_edges_num:
        logger.debug('{0} useless edges were removed'.format(removed_edges_num))

    # Get rid of temporary variables. Replace:
    #   ... tmp...;
    #   ...
    #   tmp... = func(...);
    #   ... tmp... ...;
    # with (removing first and last statements):
    #   ...
    #   ... func(...) ...;
    # Provide first function enter edge
    enter_edge = None
    for edge in error_trace.trace_iterator():
        if 'enter' in edge:
            enter_edge = edge
            break
    removed_tmp_vars_num, edge = _remove_tmp_vars(error_trace, enter_edge)

    if removed_tmp_vars_num:
        logger.debug('{0} temporary variables were removed'.format(removed_tmp_vars_num))


def _remove_tmp_vars(error_trace, edge):
    removed_tmp_vars_num = 0

    # Normal function scope.
    if 'enter' in edge:
        func_id = edge['enter']
        # Move forward to declarations or statements.
        edge = error_trace.next_edge(edge)

    # Scan variable declarations to find temporary variable names and corresponding edge ids.
    tmp_var_names = dict()
    edges_map = dict()
    while True:
        # Declarations are considered to finish when returning from current function, some function is entered, some
        # condition is checked or some assigment is performed (except for entry point which "contains" many
        # assignemts to global variabels). It is well enough for this optimization.
        if edge.get('return') == func_id or 'enter' in edge or 'condition' in edge or\
                (func_id != -1 and '=' in edge['source']):
            break

        m = re.search(r'(tmp\w*);$', edge['source'])
        if m:
            edges_map[id(edge)] = edge
            tmp_var_names[m.group(1)] = id(edge)

        edge = error_trace.next_edge(edge)

    # Remember what temporary varibles aren't used after all.
    unused_tmp_var_decl_ids = set(list(tmp_var_names.values()))

    # Scan other statements to find function calls which results are stored into temporary variables.
    while True:
        # Reach error trace end.
        if not edge:
            break

        # Reach end of function.
        if edge.get('return') == func_id:
            break

        # Reach some function call which result is stored into temporary variable.
        m = re.search(r'^(tmp\w*)\s+=\s+(.+);$', edge['source'])
        if m:
            func_call_edge = edge

        # Remain all edges belonging to a given function as is in any case.
        if 'enter' in edge:
            removed_tmp_vars_num_tmp, edge = _remove_tmp_vars(error_trace, edge)
            removed_tmp_vars_num += removed_tmp_vars_num_tmp

            # Replace
            #    tmp func(...);
            # with:
            #    func(...);
            if m:
                # Detrmine that there is no retun from the function
                # Keep in mind that each pair enter-return has an identifier, but such identifier is not unique
                # across the trace, so we need to go through the whole trace and guarantee that for particular enter
                # there is no pair.
                level_under_concideration = None
                level = 0
                for e in error_trace.trace_iterator(begin=func_call_edge):
                    if 'enter' in e and e['enter'] == func_call_edge['enter']:
                        level += 1
                        if e == func_call_edge:
                            level_under_concideration = level
                    if 'return' in e and e['return'] == func_call_edge['enter']:
                        if level_under_concideration and level_under_concideration == level:
                            level = -1
                            break
                        else:
                            level = -1

                # Do replacement
                if level >= level_under_concideration:
                    func_call_edge['source'] = m.group(2) + ';'

            if not edge:
                break

        # Try to find temorary variable usages on edges following corresponding function calls.
        if m:
            tmp_var_name = m.group(1)
            func_call = m.group(2)
            if tmp_var_name in tmp_var_names:
                tmp_var_decl_id = tmp_var_names[tmp_var_name]
                tmp_var_use_edge = error_trace.next_edge(edge)

                # Skip simplification of the following sequence:
                #   ... tmp...;
                #   ...
                #   tmp... = func(...);
                #   ... gunc(... tmp... ...);
                # since it requires two entered functions from one edge.
                if 'enter' in tmp_var_use_edge:
                    unused_tmp_var_decl_ids.remove(tmp_var_decl_id)
                else:
                    m = re.search(r'^(.*){0}(.*)$'.format(tmp_var_name), tmp_var_use_edge['source'])
                    if m:
                        func_call_edge['source'] = m.group(1) + func_call + m.group(2)

                        for attr in ('condition', 'return'):
                            if attr in tmp_var_use_edge:
                                func_call_edge[attr] = tmp_var_use_edge[attr]

                        # Remove edge corresponding to temporary variable usage.
                        error_trace.remove_edge_and_target_node(tmp_var_use_edge)

                        removed_tmp_vars_num += 1

                        # Do not increase edges counter since we could merge edge corresponding to call to some
                        # function and edge corresponding to return from current function.
                        if func_call_edge.get('return') == func_id:
                            break

        edge = error_trace.next_edge(edge)

    # Remove all temporary variable declarations in any case.
    for tmp_var_decl_id in reversed(list(unused_tmp_var_decl_ids)):
        error_trace.remove_edge_and_target_node(edges_map[tmp_var_decl_id])

    return removed_tmp_vars_num, edge


def _parse_func_call_actual_args(actual_args_str):
    return [aux_actual_arg.strip() for aux_actual_arg in actual_args_str.split(',')] if actual_args_str else []


def _remove_aux_functions(logger, error_trace):
    # Get rid of auxiliary functions if possible. Replace:
    #   [... = ]aux_func(...)
    #     [return ]func(...)
    # with:
    #   [... = ]func(...)
    # accurately replacing arguments if required.
    removed_aux_funcs_num = 0
    for edge in error_trace.trace_iterator():
        # Begin to match pattern just for edges that represent calls of auxiliary functions.
        if 'enter' not in edge or edge['enter'] not in error_trace.aux_funcs:
            continue

        aux_func_call_edge = edge

        next_edge = error_trace.next_edge(edge)

        # Do not proceed if next edge doesn't represent function call.
        if 'enter' not in next_edge:
            continue

        func_call_edge = next_edge

        # Get lhs and actual arguments of called auxiliary function if so.
        m = re.search(r'^(.*){0}\s*\((.*)\);$'.format(error_trace.resolve_function(aux_func_call_edge['enter'])),
                      aux_func_call_edge['source'])

        # Do not proceed if meet unexpected format of function call.
        if not m:
            continue

        lhs = m.group(1)
        aux_actual_args = _parse_func_call_actual_args(m.group(2))

        # Get name and actual arguments of called function if so.
        m = re.search(r'^(return )?(.+)\s*\((.*)\);$', func_call_edge['source'])

        # Do not proceed if meet unexpected format of function call.
        if not m:
            continue

        func_name = m.group(2)
        actual_args = _parse_func_call_actual_args(m.group(3))

        # Do not proceed if names of actual arguments of called function don't correspond to ones obtained during model
        # comments parsing or/and hold their positions. Without this we won't be able to replace them with corresponding
        # actual arguments of called auxiliary function.
        is_all_replaced = True
        for i, actual_arg in enumerate(actual_args):
            is_replaced = False

            for j, formal_arg_name in enumerate(error_trace.aux_funcs[aux_func_call_edge['enter']]):
                if formal_arg_name == actual_arg:
                    actual_args[i] = aux_actual_args[j]
                    is_replaced = True
                    break

            if is_replaced:
                continue

            m = re.search(r'arg(\d+)', actual_arg)

            if not m:
                is_all_replaced = False
                break

            actual_arg_position = int(m.group(1)) - 1

            if actual_arg_position >= len(aux_actual_args):
                is_all_replaced = False
                break

            actual_args[i] = aux_actual_args[actual_arg_position]

        if not is_all_replaced:
            continue

        aux_func_call_edge['source'] = lhs + func_name + '(' + (', '.join(actual_args) if actual_args else '') + ');'
        aux_func_call_edge['enter'] = func_call_edge['enter']

        if 'note' in func_call_edge:
            aux_func_call_edge['note'] = func_call_edge['note']

        error_trace.remove_edge_and_target_node(func_call_edge)

        removed_aux_funcs_num += 1

    if removed_aux_funcs_num:
        logger.debug('{0} auxiliary functions were removed'.format(removed_aux_funcs_num))
