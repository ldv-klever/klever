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
            # Remove "[...]" around conditions.
            if 'condition' in edge:
                edge['source'] = edge['source'].strip('list()')

            # Get rid of continues spaces if they aren't placed at line beginnings.
            edge['source'] = re.sub(r'(\S) +', '\g<1> ', edge['source'])

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
    removed_tmp_vars_num = _remove_tmp_vars(error_trace, enter_edge)

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


def _remove_aux_functions(logger, error_trace):
    # Get rid of auxiliary functions if possible. Replace:
    #   ... = aux_func(...)
    #     return func(...)
    # with:
    #   ... = func(...)
    # accurately replacing arguments if required.
    removed_aux_funcs_num = 0
    for edge in error_trace.trace_iterator():
        enter_edge = edge

        if 'enter' in enter_edge:
            func_id = enter_edge['enter']
            if func_id in error_trace.aux_funcs:
                return_edge = error_trace.next_edge(edge)
                if return_edge.get('return') == func_id and 'enter' in return_edge:
                    # Get lhs and actual arguments of called auxiliary function.
                    m = re.search(r'^(.*){0}\s*\((.+)\);$'.format(error_trace.resolve_function(func_id)),
                                  enter_edge['source'].replace('\n', ' '))
                    if m:
                        lhs = m.group(1)
                        aux_actual_args = [aux_actual_arg.strip() for aux_actual_arg in m.group(2).split(',')]

                        # Get name and actual arguments of called function.
                        m = re.search(r'^return (.+)\s*\((.*)\);$', return_edge['source'].replace('\n', ' '))
                        if m:
                            func_name = m.group(1)
                            actual_args = [actual_arg.strip() for actual_arg in m.group(2).split(',')]\
                                if m.group(2) else None

                            if not actual_args \
                                    or all([re.match(r'arg\d+', actual_arg) for actual_arg in actual_args]):
                                is_replaced = True
                                if actual_args:
                                    for i, actual_arg in enumerate(actual_args):
                                        m = re.match(r'arg(\d+)', actual_arg)
                                        if m:
                                            if int(m.group(1)) >= len(aux_actual_args):
                                                is_replaced = False
                                                break
                                            actual_args[i] = aux_actual_args[int(m.group(1))]
                                        else:
                                            is_replaced = False
                                            break

                                if is_replaced:
                                    enter_edge['source'] = lhs + func_name + '(' + \
                                                           (', '.join(actual_args) if actual_args else '') + ');'
                                    enter_edge['enter'] = return_edge['enter']

                                    if 'note' in return_edge:
                                        enter_edge['note'] = return_edge['note']

                                    next_edge = error_trace.next_edge(edge)
                                    error_trace.remove_edge_and_target_node(next_edge)

                                    removed_aux_funcs_num += 1

    if removed_aux_funcs_num:
        logger.debug('{0} auxiliary functions were removed'.format(removed_aux_funcs_num))
