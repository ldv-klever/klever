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

import re
import os
import json

import core.utils
from core.highlight import Highlight


class ErrorTrace:
    MODEL_COMMENT_TYPES = 'AUX_FUNC|AUX_FUNC_CALLBACK|MODEL_FUNC|NOTE|ASSERT'
    ERROR_TRACE_FORMAT_VERSION = 1

    def __init__(self, logger):
        self._attrs = list()
        self._nodes = dict()
        self._files = list()
        self._funcs = list()
        self._logger = logger
        self._entry_node_id = None
        self._violation_node_ids = set()
        self._violation_edges = list()
        self._model_funcs = dict()
        self._notes = dict()
        self._asserts = dict()
        self._actions = list()
        self._callback_actions = list()
        self.aux_funcs = dict()
        self.emg_comments = dict()

    @property
    def functions(self):
        return enumerate(self._funcs)

    @property
    def files(self):
        return enumerate(self._files)

    @property
    def violation_nodes(self):
        return ([key, self._nodes[key]] for key in sorted(self._violation_node_ids))

    @property
    def entry_node(self):
        if self._entry_node_id:
            return self._nodes[self._entry_node_id]
        else:
            raise KeyError('Entry node has not been set yet')

    def highlight(self, src):
        highlight = Highlight(self._logger, src)
        highlight.highlight()

        return {
            'source': src,
            'highlight': [[h[0], h[2], h[3]] for h in highlight.highlights]
        }

    def serialize(self):
        core.utils.capitalize_attr_names(self._attrs)

        # TODO: perhaps it would be easier to operate with such the tree above as well.
        # Convert list of edges to global variable declarations list and to error trace tree.
        global_var_decls = list()
        trace = dict()
        # References to thread nodes for their simple update.
        thread_node_refs = dict()
        prev_thread_id = None
        # References to thread function call stacks.
        thread_func_call_stacks = dict()
        for edge in self.trace_iterator():
            # TODO: new witness format will have another marker for global variable declarations.
            if edge['thread'] == 0:
                global_var_decl = {
                    'line': edge['start line'],
                    'file': edge['file']
                }
                global_var_decl.update(self.highlight(edge['source']))
                global_var_decls.append(global_var_decl)
                continue

            if edge['thread'] not in thread_node_refs:
                # Create node representing given tread.
                thread_node = {
                    'type': 'thread',
                    'thread': edge['thread'],
                    'children': list()
                }

                # Remember reference to it.
                thread_node_refs[edge['thread']] = thread_node

                # First created thread node is tree root.
                if not trace:
                    trace.update(thread_node)
                # Add reference to created thread node to last function call node from previous thread function call
                # stack.
                else:
                    thread_func_call_stacks[prev_thread_id][-1]['children'].append(thread_node)

            # Actions can group together some statements and function calls. They do not intersect within one thread
            # and all corresponding statements and function calls of each action are within one function. Actions can
            # not appear without some function call node within corresponding thread function call stack.
            if 'action' in edge:
                if not thread_func_call_stacks[edge['thread']][-1]['children'] \
                        or not thread_func_call_stacks[edge['thread']][-1]['children'][-1]['type'] == 'action'\
                        or self.resolve_action(edge['action']) != thread_func_call_stacks[edge['thread']][-1]['children'][-1]['display']:
                    # Create node representing given action. Action source file and line are the same as for first its
                    # edge.
                    action_node = {
                        'type': 'action',
                        'file': edge['file'],
                        'line': edge['start line'],
                        'display': self.resolve_action(edge['action']),
                        'children': list()
                    }

                    if edge['action'] in self._callback_actions:
                        action_node['callback'] = True

                    # Add created action node to last function call node from corresponding thread function call stack
                    # like for statement node below.
                    thread_func_call_stacks[edge['thread']][-1]['children'].append(action_node)

            if 'enter' in edge:
                # Create node representing given function call.
                func_call_node = {
                    'type': 'function call',
                    'file': edge['file'],
                    # TODO: like below.
                    'line': edge['start line'] if 'start line' in edge else 0,
                    'display': self.resolve_function(edge['enter']),
                    'children': list()
                }

                # TODO: remove this redundant check after switching to new violation witness format since "bad" edge is artificial.
                if 'source' in edge:
                    func_call_node.update(self.highlight(edge['source']))
                else:
                    func_call_node['source'] = 'Unknown'

                if 'note' in edge:
                    func_call_node['note'] = edge['note']

                if 'warn' in edge:
                    func_call_node['note'] = edge['warn']
                    func_call_node['violation'] = True

                if 'entry_point' in edge:
                    func_call_node['display'] = edge['entry_point']

                # Each thread can have its own function call stack.
                if edge['thread'] not in thread_func_call_stacks:
                    thread_func_call_stacks[edge['thread']] = list()

                # Add reference to created function call node for corresponding thread node since given function call is
                # on top of corresponding function call stack.
                if not thread_func_call_stacks[edge['thread']]:
                    thread_node_refs[edge['thread']]['children'].append(func_call_node)
                # Add reference to created function call node to action node of last function call node from
                # corresponding thread function call stack or to last function call node itself like for statement node
                # below when we are not on top of corresponding function call stack.
                else:
                    if 'action' in edge:
                        thread_func_call_stacks[edge['thread']][-1]['children'][-1]['children'].append(func_call_node)
                    else:
                        thread_func_call_stacks[edge['thread']][-1]['children'].append(func_call_node)

                if 'return' not in edge:
                    # Add created function call node to the end of corresponding thread call stack if function does not
                    # return immediately.
                    thread_func_call_stacks[edge['thread']].append(func_call_node)
            else:
                # Create node representing given statement that is any edge except for function call enter/return.
                stmt_node = {
                    'type': 'statement',
                    'file': edge['file'],
                    'line': edge['start line']
                }

                stmt_node.update(self.highlight(edge['source']))

                if 'note' in edge:
                    stmt_node['note'] = edge['note']

                if 'warn' in edge:
                    stmt_node['note'] = edge['warn']
                    stmt_node['violation'] = True

                if 'condition' in edge:
                    stmt_node['condition'] = True

                # Add created statement node to action node of last function call node from corresponding thread
                # function call stack or to last function call node itself.
                if 'action' in edge:
                    thread_func_call_stacks[edge['thread']][-1]['children'][-1]['children'].append(stmt_node)
                else:
                    thread_func_call_stacks[edge['thread']][-1]['children'].append(stmt_node)

                if 'return' in edge:
                    # Remove last function call node from corresponding thread function call stack.
                    thread_func_call_stacks[edge['thread']].pop()

            # Remember current thread identifier to track thread switches.
            prev_thread_id = edge['thread']

        data = {
            'format': self.ERROR_TRACE_FORMAT_VERSION,
            'files': self._files,
            'global variable declarations': global_var_decls,
            'trace': trace
        }

        return data, self._attrs

    def add_attr(self, name, value, associate, compare):
        self._attrs.append({
            'name': name,
            'value': value,
            'associate': associate,
            'compare': compare
        })

    def add_entry_node_id(self, node_id):
        self._entry_node_id = node_id

    def add_node(self, node_id):
        if node_id in self._nodes:
            raise ValueError('There is already added node with an identifier {!r}'.format(node_id))
        self._nodes[node_id] = {'in': list(), 'out': list()}
        return self._nodes[node_id]

    def add_edge(self, source, target):
        source_node = self._nodes[source]
        target_node = self._nodes[target]

        edge = {'source node': source_node, 'target node': target_node}
        source_node['out'].append(edge)
        target_node['in'].append(edge)
        return edge

    def add_violation_node_id(self, identifier):
        self._violation_node_ids.add(identifier)

    def remove_violation_node_id(self, identifier):
        self._violation_node_ids.remove(identifier)

    def add_file(self, file_name):
        if file_name not in self._files:
            if not os.path.isfile(file_name):
                raise FileNotFoundError("There is no file {!r}".format(file_name))
            self._files.append(file_name)
            return self.resolve_file_id(file_name)
        else:
            return self.resolve_file_id(file_name)

    def add_function(self, name):
        if name not in self._funcs:
            self._funcs.append(name)
            return len(self._funcs) - 1
        else:
            return self.resolve_function_id(name)

    def add_action(self, comment, callback=False):
        if comment not in self._actions:
            self._actions.append(comment)
            action_id = len(self._actions) - 1
            if callback:
                self._callback_actions.append(action_id)
        else:
            action_id = self.resolve_action_id(comment)

        return action_id

    def add_aux_func(self, identifier, is_callback, formal_arg_names):
        self.aux_funcs[identifier] = {'is callback': is_callback, 'formal arg names': formal_arg_names}

    def add_emg_comment(self, file, line, data):
        if file not in self.emg_comments:
            self.emg_comments[file] = dict()
        self.emg_comments[file][line] = data

    def resolve_file_id(self, file):
        return self._files.index(file)

    def resolve_file(self, identifier):
        return self._files[identifier]

    def resolve_function_id(self, name):
        return self._funcs.index(name)

    def resolve_function(self, identifier):
        return self._funcs[identifier]

    def resolve_action_id(self, comment):
        return self._actions.index(comment)

    def resolve_action(self, identifier):
        return self._actions[identifier]

    def trace_iterator(self, begin=None, end=None, backward=False):
        # todo: Warning! This does work only if you guarantee:
        # *having no nore than one input edge for all nodes
        # *existance of at least one violation node and at least one input node
        if backward:
            if not begin:
                begin = [node for identifier, node in self.violation_nodes][0]['in'][0]
            if not end:
                end = self.entry_node['out'][0]
            getter = self.previous_edge
        else:
            if not begin:
                begin = self.entry_node['out'][0]
            if not end:
                end = [node for identifier, node in self.violation_nodes][0]['in'][0]
            getter = self.next_edge

        current = None
        while True:
            if not current:
                current = begin
                yield current
            if current is end:
                return
            else:
                current = getter(current)
                if not current:
                    return
                else:
                    yield current

    def insert_edge_and_target_node(self, edge, after=True):
        new_edge = {
            'target node': None,
            'source node': None,
            'file': 0
        }
        new_node = self.add_node(int(len(self._nodes)))

        if after:
            edge['target node']['in'].remove(edge)
            edge['target node']['in'].append(new_edge)
            new_edge['target node'] = edge['target node']
            edge['target node'] = new_node
            new_node['in'] = [edge]
            new_node['out'] = [new_edge]
            new_edge['source node'] = new_node
        else:
            edge['source node']['out'].remove(edge)
            edge['source node']['out'].append(new_edge)
            new_edge['source node'] = edge['source node']
            edge['source node'] = new_node
            new_node['out'] = [edge]
            new_node['in'] = [new_edge]
            new_edge['target node'] = new_node

        if 'thread' in new_edge['target node']['out'][0]:
            # Keep already set thread identifiers
            new_edge['thread'] = new_edge['target node']['out'][0]['thread']

        return new_edge

    def remove_edge_and_target_node(self, edge):
        # Do not delete edge with a warning
        if 'warn' in edge:
            raise ValueError('Cannot delete edge with warning: {!r}'.format(edge['source']))

        source = edge['source node']
        target = edge['target node']

        # Make source node violation node if target node is violation node.
        for i, v in self.violation_nodes:
            if id(target) == id(v):
                if len(source['out']) > 1:
                    raise ValueError('Is not allowed to delete violation nodes')
                self.remove_violation_node_id(i)
                is_replaced = False
                for j, u in self._nodes.items():
                    if id(source) == id(u):
                        self.add_violation_node_id(j)
                        is_replaced = True
                        break
                if not is_replaced:
                    raise RuntimeError('Cannot add new violation node')
                break

        source['out'].remove(edge)
        target['in'].remove(edge)

        for out_edge in target['out']:
            out_edge['source node'] = source
            source['out'].append(out_edge)

        del target

    @staticmethod
    def next_edge(edge):
        if len(edge['target node']['out']) > 0:
            return edge['target node']['out'][0]
        else:
            return None

    @staticmethod
    def previous_edge(edge):
        if len(edge['source node']['in']) > 0:
            return edge['source node']['in'][0]
        else:
            return None
        
    def find_violation_path(self):
        self._find_violation_path()
        self._mark_witness()
        
    def _find_violation_path(self):
        self._logger.info('Get violation path')

        iterator = self.trace_iterator()
        for edge in iterator:
            if 'enter' in edge:
                return_edge = self.get_func_return_edge(edge)

                # Skip edges of functions that are both entered and returned.
                if return_edge:
                    while True:
                        edge = next(iterator)
                        if edge is return_edge:
                            break

                    continue

            # Everything else comprizes violation path.
            self._violation_edges.insert(0, edge)

    def parse_model_comments(self):
        self._logger.info('Parse model comments from source files referred by witness')
        emg_comment = re.compile('/\*\sLDV\s(.*)\s\*/')

        for file_id, file in self.files:
            if not os.path.isfile(file):
                raise FileNotFoundError('File {!r} referred by witness does not exist'.format(file))

            self._logger.debug('Parse model comments from {!r}'.format(file))

            with open(file, encoding='utf8') as fp:
                line = 0
                for text in fp:
                    line += 1

                    # Try match EMG comment
                    # Expect comment like /* TYPE Instance Text */
                    match = emg_comment.search(text)
                    if match:
                        data = json.loads(match.group(1))
                        self.add_emg_comment(file_id, line, data)

                    # Match rest comments
                    match = re.search(r'/\*\s+({0})\s+(.*)\*/'.format(self.MODEL_COMMENT_TYPES), text)
                    if match:
                        kind, comment = match.groups()

                        comment = comment.rstrip()

                        if kind in ('AUX_FUNC', 'AUX_FUNC_CALLBACK', 'MODEL_FUNC'):
                            # Get necessary function declaration located on following line.
                            try:
                                func_decl = next(fp)
                                # Don't forget to increase counter.
                                line += 1

                                if kind in ('AUX_FUNC', 'AUX_FUNC_CALLBACK'):
                                    func_name = comment
                                else:
                                    match = re.search(r'(ldv_\w+|LDV\w+)', func_decl)
                                    if match:
                                        func_name = match.group(1)
                                    else:
                                        raise ValueError(
                                            'Auxiliary/model function definition is not specified in {!r}'.format(
                                                func_decl))

                                # Try to get names for formal arguments (in form "type name") that is required for
                                # removing auxiliary function calls.
                                formal_arg_names = []
                                match = re.search(r'{0}\s*\((.+)\)'.format(func_name), func_decl)
                                if match:
                                    formal_args_str = match.group(1)

                                    # Remove arguments of function pointers and braces around corresponding argument
                                    # names.
                                    formal_args_str = re.sub(r'\((.+)\)\(.+\)', '\g<1>', formal_args_str)

                                    for formal_arg in formal_args_str.split(','):
                                        match = re.search(r'^.*\W+(\w+)\s*$', formal_arg)

                                        # Give up if meet complicated formal argument.
                                        if not match:
                                            formal_arg_names = []
                                            break

                                        formal_arg_names.append(match.group(1))
                            except StopIteration:
                                raise ValueError('Auxiliary/model function definition does not exist')

                            # Deal with functions referenced by witness.
                            try:
                                func_id = self.resolve_function_id(func_name)
                            except ValueError:
                                self.add_function(func_name)
                                func_id = self.resolve_function_id(func_name)

                            if kind == 'AUX_FUNC':
                                self.add_aux_func(func_id, False, formal_arg_names)
                                self._logger.debug("Get auxiliary function '{0}' from '{1}:{2}'".
                                                   format(func_name, file, line))
                            elif kind == 'AUX_FUNC_CALLBACK':
                                self.add_aux_func(func_id, True, formal_arg_names)
                                self._logger.debug("Get auxiliary function '{0}' for callback from '{1}:{2}'".
                                                   format(func_name, file, line))
                            else:
                                self._model_funcs[func_id] = comment
                                self._logger.debug("Get note '{0}' for model function '{1}' from '{2}:{3}'".
                                                   format(comment, func_name, file, line))
                        else:
                            if file_id not in self._notes:
                                self._notes[file_id] = dict()
                            self._notes[file_id][line + 1] = comment
                            self._logger.debug(
                                "Get note '{0}' for statement from '{1}:{2}'".format(comment, file, line + 1))
                            # Some assertions will become warnings.
                            if kind == 'ASSERT':
                                if file_id not in self._asserts:
                                    self._asserts[file_id] = dict()
                                self._asserts[file_id][line + 1] = comment
                                self._logger.debug("Get assertiom '{0}' for statement from '{1}:{2}'".
                                                   format(comment, file, line + 1))

        return

    def sanity_checks(self):
        # Check:
        # * branching
        # * todo: unexpected function transitions with threads
        # * todo: unexpected file changes
        self._logger.info("Perform sanity checks of the error trace")
        call_stack = []
        for edge in self.trace_iterator():
            if len(edge['target node']['out']) > 1:
                raise ValueError('Witness contains branching which is not supported')

    def final_checks(self):
        # Iterate over the trace
        threads = {}
        last_thread = None
        for edge in self.trace_iterator():
            if 'thread' in edge and (not last_thread or last_thread != edge['thread']):
                if edge['thread'] not in threads:
                    threads[edge['thread']] = []
                data = threads[edge['thread']]

            if 'return' in edge:
                if len(data) == 0:
                    raise ValueError('Unexpected return from function {!r} in thread {}'.
                                     format(self.resolve_function(edge['return']), edge['thread']))
                elif edge['return'] != data[-1]:
                    raise ValueError('Unexpected return from function {!r} in thread {}, expected last entered '
                                     'function {}'.
                                     format(self.resolve_function(edge['return']), edge['thread'],
                                            self.resolve_function(data[-1])))
                else:
                    data.pop(-1)
            if 'enter' in edge:
                data.append(edge['enter'])
            if 'source' not in edge:
                if 'enter' not in edge and 'return' not in edge:
                    self.remove_edge_and_target_node(edge)
                elif 'return' in edge:
                    edge['source'] = 'return;'

            last_thread = edge['thread']

    def _mark_witness(self):
        self._logger.info('Mark witness with model comments')

        # Two stages are required since for marking edges with warnings we need to know whether there notes at violation
        # path below.
        warn_edges = list()
        for edge in self.trace_iterator():
            file_id = edge['file']
            file = self.resolve_file(file_id)

            if 'warn' in edge:
                continue
            start_line = edge['start line']

            if 'enter' in edge:
                func_id = edge['enter']
                if func_id in self._model_funcs:
                    note = self._model_funcs[func_id]
                    self._logger.debug("Add note {!r} for model function '{}'".format(note,
                                                                                      self.resolve_function(func_id)))
                    edge['note'] = note

            if file_id in self._notes and start_line in self._notes[file_id]:
                note = self._notes[file_id][start_line]
                self._logger.debug("Add note {!r} for statement from '{}:{}'".format(note, file, start_line))
                edge['note'] = note

        for edge in self.trace_iterator(backward=True):
            file_id = edge['file']
            file = self.resolve_file(file_id)
            start_line = edge['start line']

            if file_id in self._asserts and start_line in self._asserts[file_id]:
                # Add warning just if there are no more edges with notes at violation path below.
                track_notes = False
                note_found = False
                for violation_edge in reversed(self._violation_edges):
                    if track_notes:
                        if 'note' in violation_edge:
                            note_found = True
                            break
                    if id(violation_edge) == id(edge):
                        track_notes = True

                if not note_found:
                    warn = self._asserts[file_id][start_line]
                    self._logger.debug(
                        "Add warning {!r} for statement from '{}:{}'".format(warn, file, start_line))
                    # Add warning either to edge itself or to first edge that enters function and has note at
                    # violation path. If don't do the latter warning will be hidden by error trace visualizer.
                    warn_edge = edge
                    # TODO: at the moment warnings are always added to edges themselves.
                    # for violation_edge in self._violation_edges:
                    #     if 'enter' in violation_edge and 'note' in violation_edge:
                    #         warn_edge = violation_edge
                    warn_edge['warn'] = warn
                    warn_edges.append(warn_edge)

                    # Do not try to add any warnings any more. We don't know how several violations are encoded in
                    # witnesses.
                    break

        # Remove notes from edges marked with warnings. Otherwise error trace visualizer will be confused.
        for warn_edge in warn_edges:
            if 'note' in warn_edge:
                del warn_edge['note']

        del self._violation_edges, self._model_funcs, self._notes, self._asserts

    def get_func_return_edge(self, func_enter_edge):
        next_edge = self.next_edge(func_enter_edge)

        # Do not proceed if function call terminates error trace.
        if not next_edge:
            return None

        # Keep in mind that each pair enter-return has identifier (function name), but such identifier is not unique
        # across error trace, so we need to ignore all intermediate calls to the same function.
        func_id = func_enter_edge['enter']

        subcalls = 0
        for edge in self.trace_iterator(begin=next_edge):
            if edge.get('enter') == func_id:
                subcalls += 1
            if edge.get('return') == func_id:
                if subcalls == 0:
                    return edge
                subcalls -= 1

        return None


def get_original_file(edge):
    return edge.get('original file', edge['file'])


def get_original_start_line(edge):
    return edge.get('original start line', edge['start line'])
