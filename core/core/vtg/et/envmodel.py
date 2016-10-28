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


def envmodel_simplifications(logger, error_trace):
    logger.info('Start environment model driven error trace simplifications')
    data = _collect_action_diaposons(error_trace)
    _set_thread(data, error_trace)
    _remove_control_func_aux_code(data, error_trace)
    _wrap_actions(data, error_trace)
    _remove_callback_wrappers(error_trace)


def _collect_action_diaposons(error_trace):
    # Determine control functions and allowed intervals
    intervals = ['CONTROL_FUNCTION_INIT', 'CALL', 'DISPATCH', 'RECEIVE', 'SUBPROCESS', 'CONDITION']
    data = dict()
    for file in error_trace.emg_comments.keys():
        data[file] = dict()
        # Set control function start point
        for line in (l for l in error_trace.emg_comments[file]
                     if error_trace.emg_comments[file][l]['type'] == 'CONTROL_FUNCTION_BEGIN'):
            data[file][error_trace.emg_comments[file][line]['function']] = {
                'begin': line,
                'actions': list(),
                'comment': error_trace.emg_comments[file][line]['comment'],
                'file': file
            }
            if 'thread' in error_trace.emg_comments[file][line]:
                data[file][error_trace.emg_comments[file][line]['function']]['thread'] = \
                    error_trace.emg_comments[file][line]['thread']

        # Set control function end point
        for line in (l for l in error_trace.emg_comments[file]
                     if error_trace.emg_comments[file][l]['type'] == 'CONTROL_FUNCTION_END'):
            data[file][error_trace.emg_comments[file][line]['function']]['end'] = line

        # Deterine actions and allowed intervals
        for function in data[file]:
            inside_action = False
            for line in range(data[file][function]['begin'], data[file][function]['end']):
                if not inside_action and line in error_trace.emg_comments[file] and \
                                error_trace.emg_comments[file][line]['type'] in {t + '_BEGIN' for t in intervals}:
                    data[file][function]['actions'].append({'begin': line,
                                                            'comment': error_trace.emg_comments[file][line]['comment'],
                                                            'type': error_trace.emg_comments[file][line]['type']})
                    if 'callback' in error_trace.emg_comments[file][line] and \
                            error_trace.emg_comments[file][line]['callback']:
                        data[file][function]['actions'][-1]['callback'] = True
                    inside_action = True
                elif inside_action and line in error_trace.emg_comments[file] and \
                        error_trace.emg_comments[file][line]['type'] in {t + '_END' for t in intervals}:
                    data[file][function]['actions'][-1]['end'] = line
                    inside_action = False

    return data


def _inside_control_function(cf, file, line):
    """Determine action to which string belong."""
    if cf['file'] == file and cf['begin'] <= line <= cf['end']:
        return True
    else:
        return False


def _inside_action(cf, line):
    """Determine action to which string belong."""
    for act in cf['actions']:
        if act['begin'] <= line <= act['end']:
            return act

    return None


def _match_control_function(error_trace, edge, stack, data):
    func_name = error_trace.resolve_function(edge['enter'])
    for file in data:
        if func_name in data[file]:
            cf_data = {
                'action': None,
                'functions': list(),
                'cf': data[file][func_name],
                'enter id': edge['enter'],
                'in aux code': False
            }
            stack.append(cf_data)
            return cf_data

    return None


def _match_exit_function(edge, stack):
    """Exit function."""
    if len(stack) > 0:
        if stack[-1]['enter id'] == edge['return']:
            # Exit control function
            stack.pop()
            return True

    return False


def _set_thread(data, error_trace):
    thread = 0
    cf_stack = list()
    for edge in error_trace.trace_iterator():
        # Dict changes its size, so keep it in mind
        if 'enter' in edge:
            m = _match_control_function(error_trace, edge, cf_stack, data)
            if m and 'thread' in cf_stack[-1]['cf']:
                thread = cf_stack[-1]['cf']['thread']
        elif 'return' in edge:
            m = _match_exit_function(edge, cf_stack)
            if m and 'thread' in cf_stack[-1]['cf']:
                thread = cf_stack[-1]['cf']['thread']

        edge['thread'] = thread

    return


def _remove_control_func_aux_code(data, error_trace):
    # Search in error trace for control function code and cut all code outside allowed intervals
    cf_stack = list()

    def if_enter_function(e, stack, data):
        """Enter function."""
        # Stepping into a control function?
        match = _match_control_function(error_trace, e, stack, data)
        if match:
            # TODO do we really need this? Environment model actions are described by means of attribute action now. Moreover I don't think that corresponding comments even should become actions since they are too low level. It would be better to print them as usual comments.
            # Add note on each control function entry
            #e['note'] = match['cf']['comment']
            return

        if len(stack) != 0:
            # todo: here we need actually should be sure that we are still withtin an action but it is hard to check
            if _inside_control_function(stack[-1]['cf'], e['file'], e['start line']):
                act = _inside_action(stack[-1]['cf'], e['start line'])
                if not act:
                    cf_stack[-1]['action'] = None
                    stack[-1]['in aux code'] = True
                    error_trace.remove_edge_and_target_node(e)
                else:
                    cf_stack[-1]['action'] = act
                    stack[-1]['in aux code'] = False
            else:
                if stack[-1]['in aux code']:
                    error_trace.remove_edge_and_target_node(e)

    def if_simple_state(e, stack):
        """Simple e."""
        if len(stack) > 0 and _inside_control_function(stack[-1]['cf'], e['file'], e['start line']):
            stack[-1]['in aux code'] = False
            act = _inside_action(stack[-1]['cf'], e['start line'])
            if (act and cf_stack[-1]['action'] and cf_stack[-1]['action'] != act) or \
                    (act and not cf_stack[-1]['action']):
                # First action or another action
                cf_stack[-1]['action'] = act
            elif not act:
                # Not in action
                cf_stack[-1]['action'] = None
                error_trace.remove_edge_and_target_node(e)
        elif len(stack) > 0 and stack[-1]['in aux code']:
            error_trace.remove_edge_and_target_node(e)

        return

    for edge in error_trace.trace_iterator():
        # Dict changes its size, so keep it in mind
        if 'enter' in edge:
            if_enter_function(edge, cf_stack, data)
        elif 'return' in edge:
            m = _match_exit_function(edge, cf_stack)
            if not m and len(cf_stack) > 0:
                if_simple_state(edge, cf_stack)
        else:
            if_simple_state(edge, cf_stack)


def _wrap_actions(data, error_trace):
    cf_stack = list()
    for edge in error_trace.trace_iterator():
        if len(cf_stack) > 0:
            if _inside_control_function(cf_stack[-1]['cf'], edge['file'], edge['start line']):
                act = _inside_action(cf_stack[-1]['cf'], edge['start line'])
                if act:
                    if 'callback' in act and act['callback']:
                        callback_flag = True
                    else:
                        callback_flag = False
                    edge['action'] = error_trace.add_action(act['comment'], callback_flag)
        if 'enter' in edge:
            _match_control_function(error_trace, edge, cf_stack, data)
        elif len(cf_stack) > 0 and 'return' in edge and edge['return'] == cf_stack[-1]['enter id']:
            cf_stack.pop()


# TODO is it really necessary? See tmpvars._remove_aux_functions().
def _remove_callback_wrappers(error_trace):
    def is_aux_callback_call(edge, error_trace):
        if 'enter' in edge and edge['enter'] in error_trace.aux_funcs and \
                edge['file'] in error_trace.emg_comments and \
                int(edge['start line'] - 1) in error_trace.emg_comments[edge['file']] and \
                error_trace.emg_comments[edge['file']][int(edge['start line'] - 1)]['type'] == 'CALLBACK':
            return True
        else:
            return False

    def replace_callback_call(edge, true_call):
        expected_ret = edge['enter']
        callback_ret = None
        in_callback = 0
        error_trace.remove_edge_and_target_node(edge)
        while True:
            edge = error_trace.next_edge(edge)
            if not edge:
                break
            elif not callback_ret:
                if 'return' in edge and edge['return'] == expected_ret:
                    edge['source'] = true_call
                    del edge['return']
                    break
                elif 'enter' not in edge:
                    error_trace.remove_edge_and_target_node(edge)
                else:
                    edge['source'] = true_call
                    callback_ret = edge['enter']
                    in_callback += 1
            elif in_callback:
                if 'enter' in edge and edge['enter'] == callback_ret:
                    in_callback += 1
                elif 'return' in edge and edge['return'] == callback_ret:
                    in_callback -= 1
                elif is_aux_callback_call(edge, error_trace):
                    ntc = error_trace.emg_comments[edge['file']][edge['start line'] - 1]['comment']
                    edge = replace_callback_call(edge, ntc)
                    if not edge:
                        break
            elif in_callback == 0:
                error_trace.remove_edge_and_target_node(edge)
                if 'return' in edge and edge['return'] == expected_ret:
                    break

        return edge

    # Go through trace
    edge = error_trace.entry_node['out'][0]
    while True:
        if is_aux_callback_call(edge, error_trace):
            true_call = error_trace.emg_comments[edge['file']][edge['start line'] - 1]['comment']
            edge = replace_callback_call(edge, true_call)
            if not edge:
                break
        edge = error_trace.next_edge(edge)
        if not edge:
            break

    return