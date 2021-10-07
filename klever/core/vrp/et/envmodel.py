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


def envmodel_simplifications(logger, error_trace):
    logger.info('Start environment model driven error trace simplifications')
    data, main_data, main = _collect_action_diapasons(logger, error_trace)
    _set_thread(data, error_trace)

    # This is quite tricky code and it is ensure that before deleting any edges the trace was correct
    error_trace.final_checks()
    _remove_control_func_aux_code(data, error_trace)
    try:
        error_trace.final_checks()
    except ValueError as e:
        raise RuntimeError("Edges from error trace has been deleted incorrectly and it cannot be visualized: {}".
                           format(e))
    _wrap_actions(data, error_trace)


def _collect_action_diapasons(logger, error_trace):
    main = None
    main_data = None

    # Determine control functions and allowed intervals
    data = dict()
    for file in error_trace.emg_comments.keys():
        data[file] = dict()
        # Set control function start point
        # todo: track action names
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

                # Search for main function
                if error_trace.emg_comments[file][line]['thread'] == 1:
                    main_data = data[file][error_trace.emg_comments[file][line]['function']]
                    main = error_trace.emg_comments[file][line]['function']

        # Set control function end point
        for line in (l for l in error_trace.emg_comments[file]
                     if error_trace.emg_comments[file][l]['type'] == 'CONTROL_FUNCTION_END'):
            data[file][error_trace.emg_comments[file][line]['function']]['end'] = line

        # Determine actions and allowed intervals
        for func in data[file]:
            inside_action = False
            for line in range(data[file][func]['begin'], data[file][func]['end']):
                if not inside_action and line in error_trace.emg_comments[file] and \
                                error_trace.emg_comments[file][line]['type'] == 'ACTION_BEGIN':
                    if 'type' not in error_trace.emg_comments[file][line] or \
                            'comment' not in error_trace.emg_comments[file][line]:
                        logger.warning("Incomplete EMG comment at line {} of file {!r}".format(line, file))
                        error_trace.emg_comments[file][line].setdefault('comment', 'EMG action')
                    data[file][func]['actions'].append({
                        'begin': line,
                        'comment': error_trace.emg_comments[file][line]['comment'],
                        'type': error_trace.emg_comments[file][line]['type']})
                    if error_trace.emg_comments[file][line].get('relevant'):
                        data[file][func]['actions'][-1]['relevant'] = True
                    inside_action = True
                elif inside_action and line in error_trace.emg_comments[file] and \
                        error_trace.emg_comments[file][line]['type'] == 'ACTION_END':
                    data[file][func]['actions'][-1]['end'] = line
                    inside_action = False

    return data, main_data, main


def _inside_this_control_function(cf, file, line):
    """Determine action to which string belong."""
    if cf['file'] == file and cf['begin'] <= line <= cf['end']:
        return True
    else:
        return False


def _inside_control_function(stack, file, line, thread=None):
    """Determine action to which string belong."""
    # Keep in mind that threads may interleave
    suits = []
    for index in reversed(range(0, len(stack))):
        if _inside_this_control_function(stack[index]['cf'], file, line):
            suits.append(index)

    if thread:
        suits = [i for i in suits if stack[i]['thread'] == thread]

    if len(suits) > 0:
        return stack[suits[0]]
    else:
        return None


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
            if 'thread' in edge:
                cf_data['thread'] = edge['thread']
            stack.append(cf_data)
            return cf_data

    return None


def _match_exit_function(edge, stack):
    """Exit function."""
    if len(stack) > 0:
        for index in reversed(range(0, len(stack))):
            if stack[index]['enter id'] == edge['return']:
                # Exit control function
                stack.pop(index)
                return True

    return False


def _set_thread(data, error_trace):
    def update_thread(stack):
        having_thread = [f for f in stack if 'thread' in f['cf']]
        if len(having_thread) > 0:
            return having_thread[-1]['cf']['thread']
        else:
            return 0

    cf_stack = list()

    already_set = False
    for edge in error_trace.trace_iterator():
        if "thread" in edge:
            already_set = True
            break

    if not already_set:
        current_thread = update_thread(cf_stack)
        for edge in error_trace.trace_iterator():
            # Dict changes its size, so keep it in mind
            m = None
            if 'enter' in edge:
                m = _match_control_function(error_trace, edge, cf_stack, data)
                if m:
                    # Update current thread if a transition has happen
                    current_thread = update_thread(cf_stack)
                edge['thread'] = current_thread
            if 'return' in edge:
                m = _match_exit_function(edge, cf_stack)
                edge['thread'] = current_thread
                if m:
                    # Update current thread if a transition has happen
                    current_thread = update_thread(cf_stack)
            if 'thread' not in edge:
                edge['thread'] = current_thread
    else:
        # Shift all existing thread identifiers to keep 0 thread identifier for global initialization edges
        scope = False
        for edge in error_trace.trace_iterator():
            if not scope and 'enter' in edge:
                scope = True
            if scope:
                edge['thread'] = str(int(edge['thread']) + 1)

    return


def _remove_control_func_aux_code(data, error_trace):
    # Search in error trace for control function code and cut all code outside allowed intervals
    cf_stack = list()

    def if_enter_function(e, stack, data):
        """Enter function."""
        # Stepping into a control function?
        match = _match_control_function(error_trace, e, stack, data)
        if match:
            # Add note on each control function entry
            e['entry_point'] = match['cf']['comment']
            return

        if len(stack) != 0:
            # todo: here we need actually should be sure that we are still within an action but it is hard to check
            cf = _inside_control_function(stack, e['file'], e['line'], e['thread'])
            if cf:
                act = _inside_action(cf['cf'], e['line'])
                if not act:
                    cf['action'] = None
                    cf['in aux code'] = True
                    # TODO: FIXME!
                    # error_trace.remove_edge_and_target_node(e)
                else:
                    cf['action'] = act
                    cf['in aux code'] = False
            else:
                cfs = [cf for cf in stack if cf['thread'] == e['thread'] and cf['in aux code']]
                # TODO: FIXME!
                # if len(cfs) > 0:
                #     error_trace.remove_edge_and_target_node(e)

    def if_simple_state(e, stack):
        """Simple e."""
        cf = _inside_control_function(stack, e['file'], e['line'], e['thread'])
        if cf:
            cf['in aux code'] = False
            act = _inside_action(cf['cf'], e['line'])
            if (act and cf['action'] and cf['action'] != act) or \
                    (act and not cf['action']):
                # First action or another action
                cf['action'] = act
            elif not act:
                # Not in action
                cf['action'] = None
                # TODO: FIXME!
                # error_trace.remove_edge_and_target_node(e)
        else:
            # Check whether there are control functions from this thread which have stack stopped in aux code
            cfs = [cf for cf in stack if cf['thread'] == e['thread'] and cf['in aux code']]
            # TODO: FIXME!
            # if len(cfs) > 0:
            #     error_trace.remove_edge_and_target_node(e)

        return

    for edge in error_trace.trace_iterator():
        # Dict changes its size, so keep it in mind
        if 'return' in edge:
            m = _match_exit_function(edge, cf_stack)
            if not m and len(cf_stack) > 0:
                if_simple_state(edge, cf_stack)
        if 'enter' in edge:
            if_enter_function(edge, cf_stack, data)
        if 'enter' not in edge and 'return' not in edge:
            if_simple_state(edge, cf_stack)


def _wrap_actions(data, error_trace):
    cf_stack = list()
    for edge in error_trace.trace_iterator():
        if len(cf_stack) > 0:
            cf = _inside_control_function(cf_stack, edge['file'], edge['line'], edge['thread'])
            if cf:
                act = _inside_action(cf['cf'], edge['line'])
                if act:
                    if act.get('relevant'):
                        relevant_flag = True
                    else:
                        relevant_flag = False
                    edge['action'] = error_trace.add_action(act['comment'], relevant_flag)
        if 'enter' in edge:
            _match_control_function(error_trace, edge, cf_stack, data)
        elif len(cf_stack) > 0 and 'return' in edge:
            _match_exit_function(edge, cf_stack)
