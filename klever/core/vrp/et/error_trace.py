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

import re
import os
import json

import klever.core.utils
from klever.core.highlight import Highlight


class ErrorTrace:
    ERROR_TRACE_FORMAT_VERSION = 1
    MODEL_COMMENT_TYPES = r'NOTE\d?|ASSERT|CIF|EMG_WRAPPER'
    MAX_NOTE_LEVEl = 3

    def __init__(self, logger):
        self._attrs = []
        self._nodes = {}
        self._files = []
        self._funcs = []
        self._logger = logger
        self._entry_node_id = None
        self._violation_node_ids = set()
        self._violation_edges = []
        self._notes = {}
        self._asserts = {}
        self._actions = []
        self._callback_actions = []
        self.emg_comments = {}
        self.displays = {}
        self.programfile_content = ''
        self.programfile_line_map = {}

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

        raise KeyError('Entry node has not been set yet')

    def highlight(self, src, func_name=None):
        highlight = Highlight(self._logger, src)
        highlight.highlight()

        if func_name:
            idx = src.find(func_name)
            if idx != -1:
                if func_name.startswith('cif_'):
                    highlight_kind = 'CIFAuxFunc'
                elif func_name.startswith('emg_'):
                    highlight_kind = 'LDVEnvModelFunc'
                elif func_name.startswith('ldv_'):
                    highlight_kind = 'LDVModelFunc'
                else:
                    highlight_kind = 'FuncDefRefTo'
                highlight.extra_highlight([[highlight_kind, 1, idx, idx + len(func_name)]])

        return {
            'source': src,
            'highlight': [[h[0], h[2], h[3]] for h in highlight.highlights]
        }

    def convert_notes(self, edge):
        # Error trace notes should be ordered in the descending order of levels so that the most important notes will be
        # shown on the bottom, closely to related sources. Moreover, we should select one note among the most important
        # notes that hides sources if so.
        if 'notes' in edge:
            level_notes = {}
            min_notes_level = self.MAX_NOTE_LEVEl
            notes = []
            hide = False

            # Split all notes into buckets with appropriate levels.
            for note_level in range(self.MAX_NOTE_LEVEl, -1, -1):
                level_notes[note_level] = []
            for note in edge['notes']:
                level_notes[note['level']].append(note)
                min_notes_level = min(note['level'], min_notes_level)

            # Add notes from buckets according to comment above.
            for note_level in range(self.MAX_NOTE_LEVEl, -1, -1):
                # Try to find note that hides sources. If there are several such notes than it is not defined what
                # note will be chosen.
                note_with_hide = None
                if note_level == min_notes_level:
                    for note in level_notes[note_level]:
                        if note['hide']:
                            note_with_hide = note
                            break

                for note in level_notes[note_level]:
                    if note != note_with_hide:
                        notes.append({
                            'text': note['text'],
                            'level': note_level
                        })

                if note_with_hide:
                    notes.append({
                        'text': note_with_hide['text'],
                        'level': note_level
                    })
                    hide = True
                    # There is no more notes, so, we can break the loop.
                    break
            return {
                'notes': notes,
                'hide': hide
            }

        return {}

    def serialize(self):
        klever.core.utils.capitalize_attr_names(self._attrs)

        # TODO: perhaps it would be easier to operate with such the tree above as well.
        # Convert list of edges to global variable declarations list and to error trace tree.
        is_first_edge = True
        is_global_var_decls = False
        global_var_decls = []
        trace = {}
        # References to thread nodes for their simple update.
        thread_node_refs = {}
        prev_thread_id = None
        # References to thread function call stacks.
        thread_func_call_stacks = {}
        # Node for accumulating current local declarations.
        declarations_node = None
        # First declaration edge.
        declarations_edge = None
        for edge in self.trace_iterator():
            # All declaration edges starting from the firts one correspond to global declarations.
            if is_first_edge:
                is_first_edge = False
                if 'declaration' in edge:
                    is_global_var_decls = True

            if 'declaration' in edge and is_global_var_decls:
                global_var_decl = {
                    'line': edge['line'],
                    'file': edge['file']
                }
                global_var_decl.update(self.highlight(edge['source']))
                global_var_decl.update(self.convert_notes(edge))
                global_var_decls.append(global_var_decl)
                continue

            is_global_var_decls = False

            if declarations_node and 'declaration' not in edge:
                # TODO: make a function for this since there are two more similar places below.
                if 'action' in declarations_edge:  # pylint: disable=unsupported-membership-test
                    thread_func_call_stacks[declarations_edge['thread']][-1]['children'][-1]['children'].append(  # pylint: disable=unsubscriptable-object
                        declarations_node)
                else:
                    thread_func_call_stacks[declarations_edge['thread']][-1]['children'].append(declarations_node)  # pylint: disable=unsubscriptable-object

                declarations_node = None
                declarations_edge = None

            if edge['thread'] not in thread_node_refs:
                # Create node representing given tread.
                thread_node = {
                    'type': 'thread',
                    'thread': edge['thread'],
                    'children': []
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
                        or not thread_func_call_stacks[edge['thread']][-1]['children'][-1]['type'] == 'action' \
                        or self.resolve_action(edge['action']) != \
                        thread_func_call_stacks[edge['thread']][-1]['children'][-1]['display']:
                    # Create node representing given action. Action source file and line are the same as for first its
                    # edge.
                    action_node = {
                        'type': 'action',
                        'file': edge['file'],
                        'line': edge['line'],
                        'display': self.resolve_action(edge['action']),
                        'children': []
                    }

                    if edge['action'] in self._callback_actions:
                        action_node['relevant'] = True

                    # Add created action node to last function call node from corresponding thread function call stack
                    # like for statement node below.
                    thread_func_call_stacks[edge['thread']][-1]['children'].append(action_node)

            def display(func_name):
                if func_name.startswith('ldv_'):
                    return "LDV model '{0}'".format(func_name[4:])
                return func_name

            if 'enter' in edge:
                # Create node representing given function call.
                func_call_node = {
                    'type': 'function call',
                    'file': edge['file'],
                    # TODO: like below.
                    'line': edge['line'] if 'line' in edge else 0,
                    'display': edge.get('display', display(self.resolve_function(edge['enter']))),
                    'children': []
                }

                # TODO: remove this redundant check after switching to new violation witness format since "bad" edge is artificial.
                if 'source' in edge:
                    func_call_node.update(self.highlight(edge['source'], self.resolve_function(edge['enter'])))
                else:
                    func_call_node['source'] = 'Unknown'

                func_call_node.update(self.convert_notes(edge))

                if 'entry_point' in edge:
                    func_call_node['display'] = edge['entry_point']

                if 'assumption' in edge:
                    func_call_node['assumption'] = edge['assumption']

                # Each thread can have its own function call stack.
                if edge['thread'] not in thread_func_call_stacks:
                    thread_func_call_stacks[edge['thread']] = []

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
                # Create node representing given declaration or statement that is any edge of original violation
                # witnesses except for function call enters/returns.
                decl_or_stmt_node = {
                    'type': 'declaration' if 'declaration' in edge else 'statement',
                    'file': edge['file'],
                    'line': edge['line']
                }

                decl_or_stmt_node.update(self.highlight(edge['source']))
                decl_or_stmt_node.update(self.convert_notes(edge))

                if 'condition' in edge:
                    decl_or_stmt_node['condition'] = True

                if 'assumption' in edge:
                    decl_or_stmt_node['assumption'] = edge['assumption']

                # Declarations are added altogether as a block after it is completely handled.
                if 'declaration' in edge:
                    if not declarations_node:
                        declarations_node = {
                            'type': 'declarations',
                            'children': []
                        }
                        declarations_edge = edge
                    declarations_node['children'].append(decl_or_stmt_node)
                else:
                    # Add created statement node to action node of last function call node from corresponding thread
                    # function call stack or to last function call node itself.
                    if 'action' in edge:
                        thread_func_call_stacks[edge['thread']][-1]['children'][-1]['children'].append(
                            decl_or_stmt_node)
                    else:
                        thread_func_call_stacks[edge['thread']][-1]['children'].append(decl_or_stmt_node)

                if 'return' in edge:
                    # Remove last function call node from corresponding thread function call stack.
                    thread_func_call_stacks[edge['thread']].pop()

            # Remember current thread identifier to track thread switches.
            prev_thread_id = edge['thread']

        # Add remaining declarations. This can happen when last edges in violation witnesses correspond to declarations.
        if declarations_node:
            if 'action' in declarations_edge:
                thread_func_call_stacks[declarations_edge['thread']][-1]['children'][-1]['children'].append(
                    declarations_node)
            else:
                thread_func_call_stacks[declarations_edge['thread']][-1]['children'].append(declarations_node)

        data = {
            'format': self.ERROR_TRACE_FORMAT_VERSION,
            'files': self._files,
            'global variable declarations': global_var_decls,
            'trace': trace
        }

        return data, self._attrs

    def add_attr(self, name, value, associate, compare):
        m = re.match(r'(.*) (__anonstruct_[^ ]*) (.*)', value)
        if m:
            anon_struct_name = m.group(2)
            anon_struct_name = re.sub(r'_\d+$', '', anon_struct_name)
            value = "{0} {1} {2}".format(m.group(1), anon_struct_name, m.group(3))

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
        self._nodes[node_id] = {'id': node_id, 'in': [], 'out': []}
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
            # Violation witnesses can refer auxiliary files created at weaving in all aspect files for models. But these
            # auxiliary files could be removed if one will not keep intermediate files. Taking into account that
            # auxiliary files are not very important, we can silently work further. You can see
            # https://forge.ispras.ru/issues/10994 for more details.
            if not file_name.endswith(".aux") and not os.path.isfile(file_name):
                raise FileNotFoundError("There is no file {!r}".format(file_name))
            self._files.append(file_name)

        return self.resolve_file_id(file_name)

    def add_function(self, name):
        if name not in self._funcs:
            self._funcs.append(name)
            return len(self._funcs) - 1

        return self.resolve_function_id(name)

    def add_action(self, comment, relevant=False):
        if comment not in self._actions:
            self._actions.append(comment)
            action_id = len(self._actions) - 1
            if relevant:
                self._callback_actions.append(action_id)
        else:
            action_id = self.resolve_action_id(comment)

        return action_id

    def add_emg_comment(self, file, line, data):
        if file not in self.emg_comments:
            self.emg_comments[file] = {}
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
        # *having no more than one input edge for all nodes
        # *existence of at least one violation node and at least one input node
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

            current = getter(current)
            if not current:
                return

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

        if new_edge['target node']['out'] and 'thread' in new_edge['target node']['out'][0]:  # pylint: disable=unsubscriptable-object
            # Keep already set thread identifiers
            new_edge['thread'] = new_edge['target node']['out'][0]['thread']  # pylint: disable=unsubscriptable-object

        return new_edge

    @staticmethod
    def is_warning(edge):
        if 'notes' in edge:
            return any(note['level'] == 0 for note in edge['notes'])
        return False

    def remove_edge_and_target_node(self, edge):
        # Do not delete edge with a warning
        if self.is_warning(edge):
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

    def remove_non_referred_files(self, referred_file_ids):
        for file_id, _ in enumerate(self._files):
            if file_id not in referred_file_ids:
                # This is not a complete removing. But error traces will not hold absolute paths of files that are not
                # referred by witness.
                self._files[file_id] = ''

    @staticmethod
    def next_edge(edge):
        if len(edge['target node']['out']) > 0:
            return edge['target node']['out'][0]

        return None

    @staticmethod
    def previous_edge(edge):
        if len(edge['source node']['in']) > 0:
            return edge['source node']['in'][0]

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

            # Everything else comprises violation path.
            self._violation_edges.insert(0, edge)

    def parse_model_comments(self):
        self._logger.info('Parse model comments from source files referred by witness')
        emg_comment = re.compile(r'/\*\sEMG_ACTION\s(.*)\s\*/')

        for file_id, file in self.files:
            # Files without names are not referred by witness.
            if not file:
                continue

            # Like for klever.core.vrp.et.error_trace.ErrorTrace.add_file. BTW, there is a data race here since the
            # necessary file can be removed after this check will pass. Let's hope that this will not happen ever.
            if file.endswith(".aux") and not os.path.isfile(file):
                continue

            self._logger.debug('Parse model comments from {!r}'.format(file))

            with open(file, encoding='utf-8') as fp:
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

                        if kind.startswith("NOTE"):
                            level = None
                            # Notes of level 1 does not require the level to be explicitly specified.
                            if len(kind) == 4:
                                level = 1
                            elif len(kind) == 5 and kind[4].isdigit():
                                level = int(kind[4])

                            # Incorrect format of note.
                            if not level:
                                continue

                            if level not in self._notes:
                                self._notes[level] = {}
                            if file_id not in self._notes[level]:
                                self._notes[level][file_id] = {}
                            self._notes[level][file_id][line + 1] = comment
                            self._logger.debug("Get note '{0}' of level '{1}' for statement from '{2}:{3}'"
                                               .format(comment, level, file, line + 1))
                        elif kind == 'ASSERT':
                            if file_id not in self._asserts:
                                self._asserts[file_id] = {}
                            self._asserts[file_id][line + 1] = comment
                            self._logger.debug(
                                "Get assertion '{0}' for statement from '{1}:{2}'".format(comment, file, line + 1))
                        elif kind == 'CIF':
                            m = re.match(r'Original function \"([^"]+)\"\. Instrumenting function \"([^"]+)\"', comment)
                            if m:
                                orig_func_name = m.group(1)
                                instr_func_name = m.group(2)

                                try:
                                    instr_func_id = self.resolve_function_id(instr_func_name)
                                except ValueError:
                                    self.add_function(instr_func_name)
                                    instr_func_id = self.resolve_function_id(instr_func_name)

                                self.displays[instr_func_id] = "Instrumented function '{0}'".format(orig_func_name)
                                self._logger.debug("Get display '{0}' for function '{1}' from '{2}:{3}'"
                                                   .format(comment, orig_func_name, file, line + 1))
                            else:
                                raise RuntimeError('Invalid format of CIF comment "{0}"'.format(comment))
                        elif kind == 'EMG_WRAPPER':
                            try:
                                emg_wrapper_id = self.resolve_function_id(comment)
                            except ValueError:
                                self.add_function(comment)
                                emg_wrapper_id = self.resolve_function_id(comment)

                            self.displays[emg_wrapper_id] = "EMG wrapper"
                            self._logger.debug(f"Get display '{comment}' for EMG wrapper '{emg_wrapper_id}' from '{file}:{line+1}'")

    def remove_switch_cases(self):
        # Get rid of redundant switch cases. Replace:
        #   assume(x != A)
        #   assume(x != B)
        #   ...
        #   assume(x == Z)
        # with:
        #   assume(x == Z)
        removed_switch_cases_num = 0
        for edge in self.trace_iterator():
            # Begin to match pattern just for edges that represent conditions.
            if 'condition' not in edge:
                continue

            # Get all continues conditions.
            cond_edges = []
            for cond_edge in self.trace_iterator(begin=edge):
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
                if x != m.group(1):
                    x = None
                    continue

                # Finish to collect conditions. Pattern matches.
                if x is not None and m.group(2) == '==':
                    cond_edges_to_remove.extend(cond_edges[start_idx:idx])
                    x = None
                    continue

            for cond_edge in reversed(cond_edges_to_remove):
                self.remove_edge_and_target_node(cond_edge)
                removed_switch_cases_num += 1

        if removed_switch_cases_num:
            self._logger.debug('{0} switch cases were removed'.format(removed_switch_cases_num))

    def merge_func_entry_and_exit(self):
        # For each function call with return there is an edge corresponding to function entry and an edge
        # corresponding to function exit. Both edges are located at a function call. The second edge can contain an
        # assignment of result to some variable.
        # This is good for analysis, but this is redundant for visualization. Let's merge these edges together.
        edges_to_remove = []
        for edge in self.trace_iterator():
            if 'enter' not in edge:
                continue

            return_edge = self.get_func_return_edge(edge)
            if not return_edge:
                continue

            exit_edge = self.next_edge(return_edge)
            if not exit_edge:
                continue

            edges_to_remove.insert(0, exit_edge)
            next_to_exit_edge = self.next_edge(exit_edge)

            # Do not overwrite source code of function entry with the one of function exit when function is
            # called within if statement. In that case there is no useful assignments most likely while source
            # code of function exit includes some part of this if statement.
            if not next_to_exit_edge \
                    or 'condition' not in next_to_exit_edge \
                    or exit_edge['line'] != next_to_exit_edge['line']:
                edge['source'] = exit_edge['source']

            # Copy notes if so from function exit edge to be removed to function entry edge.
            if 'notes' not in edge:
                edge['notes'] = []

            if 'notes' in exit_edge:
                edge['notes'].extend(exit_edge['notes'])
                del exit_edge['notes']

        for edge_to_remove in edges_to_remove:
            self.remove_edge_and_target_node(edge_to_remove)

    def sanity_checks(self):
        # Check:
        # * branching
        # * todo: unexpected function transitions with threads
        # * todo: unexpected file changes
        self._logger.info("Perform sanity checks of the error trace")
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
                if edge['return'] != data[-1]:
                    raise ValueError('Unexpected return from function {!r} in thread {}, expected last entered '
                                     'function {}'.
                                     format(self.resolve_function(edge['return']), edge['thread'],
                                            self.resolve_function(data[-1])))

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

        note_levels = list(self._notes.keys())
        for edge in self.trace_iterator():
            line = edge['line']
            file_id = edge['file']
            file = self.resolve_file(file_id)

            if 'enter' in edge:
                func_id = edge['enter']
                unmerged_func_id = edge.get('unmerged enter')
                display = None

                # First of all try to find out displays for unmerged function names/ids.
                if unmerged_func_id in self.displays:
                    display = self.displays[unmerged_func_id]
                elif func_id in self.displays:
                    display = self.displays[func_id]

                if display:
                    self._logger.debug("Add display {!r} for function '{}'"
                                       .format(display, self.resolve_function(func_id)))
                    edge['display'] = display

            for level in note_levels:
                if file_id in self._notes[level] and line in self._notes[level][file_id]:
                    note = self._notes[level][file_id][line]
                    self._logger.debug("Add note {!r} of level {} for statement from '{}:{}'"
                                       .format(note, level, file, line))
                    if 'notes' not in edge:
                        edge['notes'] = []

                    # Model comments are rather essential and they are designed to hide model implementation details.
                    # That's why corresponding expressions and statements are hidden.
                    # Unfortunately, some model comments are not perfect yet, but we should fix them rather than make
                    # some workarounds to encourage developers of bad model comments.
                    edge['notes'].append({
                        'text': note,
                        'level': level,
                        'hide': True
                    })

            if file_id in self._asserts and line in self._asserts[file_id]:
                warn = self._asserts[file_id][line]
                self._logger.debug("Add warning {!r} for statement from '{}:{}'".format(warn, file, line))
                if 'notes' not in edge:
                    edge['notes'] = []
                else:
                    # There may be already warning from the verification tool, but it is not so specific as the one
                    # that is based on model comments. So, just remove it.
                    for note_idx, note in enumerate(edge['notes']):
                        if note['level'] == 0:
                            del edge['notes'][note_idx]
                            break

                edge['notes'].append({
                    'text': warn,
                    'level': 0,
                    'hide': True
                })

        del self._violation_edges, self._notes, self._asserts, self.displays

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
