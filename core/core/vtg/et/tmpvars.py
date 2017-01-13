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
    _remove_artificial_edges(logger, trace)
    _remove_aux_functions(logger, trace)


def _basic_simplification(logger, error_trace):
    # Remove all edges without source (at the modmen only enterLoopHead expected)
    for edge in (e for e in error_trace.trace_iterator() if 'source' not in e):
        if 'enterLoopHead' in edge and edge['enterLoopHead']:
            error_trace.remove_edge_and_target_node(edge)
        else:
            # Now we do need source code to be presented with all edges. Otherwise visualization will be very poor.
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

        # Replace "!(... ==/!=/</> ...)" with "... !=/==/>/< ...".
        edge['source'] = re.sub(r'^!\((.+)==(.+)\)$', '\g<1>!=\g<2>', edge['source'])
        edge['source'] = re.sub(r'^!\((.+)!=(.+)\)$', '\g<1>==\g<2>', edge['source'])
        edge['source'] = re.sub(r'^!\((.+)<(.+)\)$', '\g<1>>\g<2>', edge['source'])
        edge['source'] = re.sub(r'^!\((.+)>(.+)\)$', '\g<1><\g<2>', edge['source'])

        # Remove unnessary "(...)" around returned values/expressions.
        edge['source'] = re.sub(r'^return \((.*)\);$', 'return \g<1>;', edge['source'])

        # Make source code and assumptions more human readable (common improvements).
        for source_kind in ('source', 'assumption'):
            if source_kind in edge:
                # Remove unnessary "(...)" around integers.
                edge[source_kind] = re.sub(r' \((-?[0-9]+\w*)\)', ' \g<1>', edge[source_kind])

                # Replace "& " with "&".
                edge[source_kind] = re.sub(r'& ', '&', edge[source_kind])


def _remove_artificial_edges(logger, error_trace):
    # More advanced transformations.
    # Get rid of artificial edges added after returning from functions.
    removed_edges_num = 0
    for edge in error_trace.trace_iterator():
        if 'return' in edge:
            next_edge = error_trace.next_edge(edge)
            if 'return' in next_edge and next_edge['return'] == edge['return']:
                error_trace.remove_edge_and_target_node(next_edge)
                removed_edges_num += 1
    if removed_edges_num:
        logger.debug('{0} useless edges were removed'.format(removed_edges_num))

    # Get rid of temporary variables. Replace:
    #   ... tmp...;
    #   ...
    #   tmp... = func(...);
    #   [... tmp... ...;]
    # with (removing first and last statements if so):
    #   ...
    #   ... func(...) ...;
    # Skip global initialization that doesn't introduce any temporary variable or at least they don't fit pattern above.
    first_entry_point_edge = None
    for edge in error_trace.trace_iterator():
        if 'assumption' in edge:
            first_entry_point_edge = edge
            break

    removed_tmp_vars_num = _remove_tmp_vars(error_trace, first_entry_point_edge)[0]

    if removed_tmp_vars_num:
        logger.debug('{0} temporary variables were removed'.format(removed_tmp_vars_num))


def _remove_tmp_vars(error_trace, edge):
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

        # Recursively get rid of temporary variables inside called function.
        if 'enter' in edge:
            removed_tmp_vars_num_tmp, next_edge = _remove_tmp_vars(error_trace, func_call_edge)
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
        if 'enter' in tmp_var_use_edge and tmp_var_decl_id in unused_tmp_var_decl_ids:
            unused_tmp_var_decl_ids.remove(tmp_var_decl_id)
        else:
            m = re.search(r'^(.*){0}(.*)$'.format(tmp_var_name), tmp_var_use_edge['source'])

            # Do not proceed if pattern wasn't matched.
            if not m:
                continue

            func_call_edge['source'] = m.group(1) + func_call + m.group(2)

            for attr in ('condition', 'return'):
                if attr in tmp_var_use_edge:
                    func_call_edge[attr] = tmp_var_use_edge[attr]

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
    return [aux_actual_arg.strip() for aux_actual_arg in actual_args_str.split(',')] if actual_args_str else []


def _remove_aux_functions(logger, error_trace):
    # Get rid of auxiliary functions if possible. Replace:
    #   ... = aux_func(...)
    #     return func(...)
    # with:
    #   ... = func(...)
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

            for j, formal_arg_name in enumerate(error_trace.aux_funcs[aux_func_call_edge['enter']]['formal arg names']):
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

        # Second pattern. For first pattern it is enough that second edge returns from function since this function can
        # be just the parent auxiliary one.
        if 'return' not in func_call_edge:
            return_edge = error_trace.get_func_return_edge(func_call_edge)

            if return_edge:
                aux_func_return_edge = error_trace.next_edge(return_edge)

                if 'return' not in aux_func_return_edge or aux_func_return_edge['source'] != 'return;':
                    continue

                error_trace.remove_edge_and_target_node(aux_func_return_edge)

        if error_trace.aux_funcs[aux_func_call_edge['enter']]['is callback']:
            for attr in ('file', 'start line'):
                aux_func_call_edge[attr] = error_trace.next_edge(next_edge)[attr]

        aux_func_call_edge['source'] = lhs + func_name + '(' + (', '.join(actual_args) if actual_args else '') + ');'
        aux_func_call_edge['enter'] = func_call_edge['enter']

        if 'note' in func_call_edge:
            aux_func_call_edge['note'] = func_call_edge['note']

        error_trace.remove_edge_and_target_node(func_call_edge)

        removed_aux_funcs_num += 1

    if removed_aux_funcs_num:
        logger.debug('{0} auxiliary functions were removed'.format(removed_aux_funcs_num))
