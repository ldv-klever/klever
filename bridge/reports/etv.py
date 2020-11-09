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

import json

from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _

from reports.source import SourceLine


class GetETV:
    tab_length = 4
    global_thread = 'global'
    condition_class = 'SrcHlAssume'
    THREAD_COLORS = [
        '#5f54cb', '#85ff47', '#69c8ff', '#ff5de5', '#dfa720',
        '#0b67bf', '#fa92ff', '#57bfa8', '#bf425a', '#7d909e'
    ]

    def __init__(self, error_trace, user):
        self.user = user
        self.trace = json.loads(error_trace)
        self._max_line_len = 0
        self._curr_scope = 0
        self.shown_scopes = set()
        self.assumptions = {}
        self._scope_assumptions = {}

        self._threads = self.__get_threads()
        self.globals = self.__get_global_vars()
        self.html_trace = []
        if self.trace['trace']:
            self.html_trace = self.__parse_node(self.trace['trace'])

    def __get_threads(self):
        threads = []
        if self.trace.get('global variable declarations'):
            threads.append(self.global_thread)
            for node in self.trace['global variable declarations']:
                self._max_line_len = max(self._max_line_len, len(str(node['line'])))
        if self.trace['trace']:
            threads.extend(self.__get_child_threads(self.trace['trace']))
        return threads

    def __get_child_threads(self, node_obj):
        threads = []
        if node_obj.get('line'):
            self._max_line_len = max(self._max_line_len, len(str(node_obj['line'])))
        if node_obj['type'] == 'thread':
            assert node_obj['thread'] != self.global_thread
            threads.append(node_obj['thread'])
        if 'children' in node_obj:
            for child in node_obj['children']:
                for thread_id in self.__get_child_threads(child):
                    if thread_id not in threads:
                        threads.append(thread_id)
        return threads

    def __get_global_vars(self):
        if 'global variable declarations' not in self.trace:
            return None
        global_data = {
            'thread': self._html_thread['global'],
            'line': self.__get_line(),
            'offset': ' ',
            'source': _('Global variable declarations'),
            'lines': []
        }
        assert isinstance(self.trace['global variable declarations'], list), 'Not a list'
        for node in self.trace['global variable declarations']:
            global_data['lines'].append({
                'thread': self._html_thread['global'],
                'line': self.__get_line(node['line']),
                'file': self.trace['files'][node['file']],
                'offset': ' ',
                'source': self.__parse_source(node),
                'note': node.get('note'),
                'display': node.get('display')
            })
        return global_data

    @property
    def _new_scope(self):
        self._curr_scope += 1
        return self._curr_scope

    def __parse_node(self, node, depth=0, thread=None, has_asc_note=False, scope=0):
        # TODO: Like in reports.UploadReport.ReportUnsafeSerializer.__check_node().
        if node['type'] == 'declaration':
            node['type'] = 'statement'

        # Statement
        if node['type'] == 'statement':
            node_data = self.__parse_statement(node, depth, thread, scope)
            if node_data.get('warn'):
                # If statement has warn, show current scope
                self.shown_scopes.add(scope)
            elif node_data.get('note') and not has_asc_note:
                # If statement has note and there are no notes in ascendants then show current scope
                self.shown_scopes.add(scope)
            return [node_data]

        # Thread
        if node['type'] == 'thread':
            thread_scope = self._new_scope

            # Always show functions of each thread root scope
            self.shown_scopes.add(thread_scope)

            children_trace = []
            for child_node in node['children']:
                children_trace.extend(self.__parse_node(
                    child_node, depth=0, thread=node['thread'], has_asc_note=False, scope=thread_scope
                ))
            return children_trace

        # Function call
        if node['type'] == 'function call':
            enter_data = self.__parse_function(node, depth, thread, scope)
            if enter_data.get('warn') or enter_data.get('note') and not has_asc_note:
                self.shown_scopes.add(scope)
            return self.__parse_body(enter_data, node, depth, thread, has_asc_note, scope)

        # Action
        if node['type'] == 'action':
            enter_data = self.__parse_action(node, depth, thread, scope)
            if enter_data['relevant']:
                # Show all relevant actions
                self.shown_scopes.add(scope)
            return self.__parse_body(enter_data, node, depth, thread, has_asc_note, scope)

    def __parse_body(self, enter_data, node, depth, thread, has_asc_note, scope):
        new_scope = self._new_scope
        enter_data['inner_scope'] = new_scope

        child_depth = depth + 1
        child_asc_note = has_asc_note or bool(enter_data.get('note')) or bool(enter_data.get('warn'))
        children_trace = []
        for child_node in node['children']:
            children_trace.extend(self.__parse_node(
                child_node, depth=child_depth, thread=thread, has_asc_note=child_asc_note, scope=new_scope
            ))

        # New scope can be added while children parsing
        if new_scope in self.shown_scopes:
            # Open scope by default if its scope is shown and show action scope
            self.shown_scopes.add(scope)
            enter_data['opened'] = True

        if not self.user.triangles:
            return [enter_data] + children_trace

        # Closing triangle
        exit_data = self.__parse_exit(depth, thread, new_scope)
        return [enter_data] + children_trace + [exit_data]

    def __parse_statement(self, node, depth, thread, scope):
        statement_data = {
            'type': node['type'],
            'thread': self._html_thread[thread],
            'line': self.__get_line(node['line']),
            'file': self.trace['files'][node['file']],
            'offset': ' ' * (self.tab_length * depth + 1),
            'source': self.__parse_source(node),
            'display': node.get('display'),
            'scope': scope
        }

        # Add note/warn
        if node.get('note'):
            if node.get('violation'):
                statement_data['warn'] = node['note']
            else:
                statement_data['note'] = node['note']

        # Add assumptions
        if self.user.assumptions:
            statement_data['old_assumptions'], statement_data['new_assumptions'] = self.__get_assumptions(node, scope)

        return statement_data

    def __parse_function(self, node, depth, thread, scope):
        func_data = self.__parse_statement(node, depth, thread, scope)
        func_data['opened'] = False
        return func_data

    def __parse_action(self, node, depth, thread, scope):
        return {
            'type': node['type'],
            'relevant': node.get('relevant', False),
            'thread': self._html_thread[thread],
            'line': self.__get_line(node['line']),
            'file': self.trace['files'][node['file']],
            'offset': ' ' * (self.tab_length * depth + 1),
            'display': node['display'],
            'scope': scope,
            'opened': False
        }

    def __parse_exit(self, depth, thread, scope):
        return {
            'type': 'exit',
            'line': self.__get_line(),
            'thread': self._html_thread[thread],
            'offset': ' ' * (self.tab_length * depth + 1),
            'scope': scope
        }

    def __parse_source(self, node):
        src_line = SourceLine(node['source'], highlights=node.get('highlight', []), filename='error trace',
                              line=node['line'])
        source_html = src_line.html_code

        # Wrap to assume() conditions
        if node.get('condition'):
            source_html = '<span class="{}">assume</span>({})'.format(self.condition_class, source_html)
        return source_html

    def __get_line(self, line=None):
        line_str = '' if line is None else str(line)
        line_offset = ' ' * (self._max_line_len - len(line_str))
        return '{0}{1}'.format(line_offset, line_str)

    @cached_property
    def _html_thread(self):
        html_pattern = '{prefix}<span style="background-color:{color};"> </span>{postfix}'
        threads_num = len(self._threads)
        threads_html = {}
        for i, th in enumerate(self._threads):
            threads_html[th] = html_pattern.format(
                prefix=' ' * i,
                color=self.THREAD_COLORS[i % len(self.THREAD_COLORS)],
                postfix=' ' * (threads_num - i - 1)
            )
        threads_html['global'] = ' ' * threads_num
        return threads_html

    def __get_assumptions(self, node, scope):
        if not self.user.assumptions:
            return None, None

        old_assumptions = None
        if scope in self._scope_assumptions:
            old_assumptions = '_'.join(self._scope_assumptions[scope])

        cnt = len(self.assumptions)
        new_assumptions = None
        if node.get('assumption'):
            new_assumptions = []
            self._scope_assumptions.setdefault(scope, [])
            for assume in node['assumption'].split(';'):
                if assume not in self.assumptions:
                    self.assumptions[assume] = cnt
                    cnt += 1
                assume_id = str(self.assumptions[assume])
                new_assumptions.append(assume_id)
                self._scope_assumptions[scope].append(assume_id)
            new_assumptions = '_'.join(new_assumptions)

        return old_assumptions, new_assumptions
