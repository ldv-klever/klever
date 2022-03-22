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
from django.utils.translation import gettext_lazy as _

from reports.source import SourceLine


class GetETV:
    global_thread = 'global'

    def __init__(self, error_trace, user):
        self.user = user
        self.trace = json.loads(error_trace)
        self._max_line_len = 0
        self._curr_scope = 0
        self.shown_scopes = set()
        self.assumptions = {}
        self._scope_assumptions = {}

        self._threads = self.__get_threads()
        self._html_collector = ETVHtml(self._threads, self._max_line_len, self.trace['files'])

        self.html_trace = []
        if 'global variable declarations' in self.trace:
            self.html_trace.extend(self.__get_global_vars())
        if self.trace['trace']:
            self.html_trace.extend(self.__parse_node(self.trace['trace'], 0, None, 0))

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
        global_scope = 'global'
        self.shown_scopes.add(global_scope)

        assert isinstance(self.trace['global variable declarations'], list), 'Not a list'

        # Hack for global variable declarations
        for decl in self.trace['global variable declarations']:
            decl['type'] = 'declaration'
        global_node = {'type': 'declarations', 'children': self.trace['global variable declarations']}

        return self.__parse_node(global_node, 0, self.global_thread, global_scope)

    @property
    def _new_scope(self):
        self._curr_scope += 1
        return self._curr_scope

    def __parse_node(self, node, depth, thread, scope):

        # Statement
        if node['type'] == 'statement':
            return self.__parse_statement(node, depth, thread, scope)

        # Thread
        if node['type'] == 'thread':
            thread_scope = self._new_scope

            # Always show functions of each thread root scope
            self.shown_scopes.add(thread_scope)

            children_trace = []
            for child_node in node['children']:
                children_trace.extend(self.__parse_node(child_node, 0, node['thread'], thread_scope))
            return children_trace

        # Function call
        if node['type'] == 'function call':
            return self.__parse_function(node, depth, thread, scope)

        # Action
        if node['type'] == 'action':
            return self.__parse_action(node, depth, thread, scope)

        # Declarations
        if node['type'] == 'declarations':
            return self.__parse_declarations(node, depth, thread, scope)

    def __parse_statement(self, node, depth, thread, scope):
        notes_data = self.__parse_notes(node, depth, thread, scope)

        statement_data = {
            'type': node['type'],
            'scope': scope,
            'has_note': len(notes_data) > 0,
            'LN': self._html_collector.line_number(thread, line=node['line'], file=node['file']),
            'LC': self._html_collector.statement_content(depth, node),
        }
        if len(notes_data) and notes_data[-1]['hide']:
            statement_data['commented'] = True

        # Add assumptions
        if self.user.assumptions:
            statement_data['old_assumptions'], statement_data['new_assumptions'] = self.__get_assumptions(node, scope)

        if notes_data:
            return notes_data + [statement_data]
        return [statement_data]

    def __parse_declaration(self, node, depth, thread, scope, decl_scope):
        notes_data = self.__parse_notes(node, depth, thread, decl_scope)

        decl_data = {
            'type': node['type'],
            'scope': scope,
            'commented': False,
            'has_note': len(notes_data) > 0,
            'LN': self._html_collector.line_number(thread, line=node['line'], file=node['file']),
            'LC': self._html_collector.declaration_content(depth, node)
        }

        if len(notes_data):
            decl_data['commented'] = notes_data[-1]['hide']

            # Move all non-relevant notes to the declarations block
            for i in range(len(notes_data)):
                if notes_data[-1]['level'] > 1:
                    notes_data[i]['scope'] = decl_scope

            # Others are hidden under the "Delarations" eye
            if notes_data[-1]['level'] in {0, 1}:
                # Move declaration with relevant note out of the declarations block scope
                decl_data['scope'] = decl_scope

        # Add assumptions
        if self.user.assumptions:
            decl_data['old_assumptions'], decl_data['new_assumptions'] = self.__get_assumptions(node, decl_scope)

        if notes_data:
            return notes_data + [decl_data]
        return [decl_data]

    def __parse_function(self, node, depth, thread, scope):
        notes_data = self.__parse_notes(node, depth, thread, scope)

        func_enter = {
            'type': node['type'],
            'scope': scope,
            'body_scope': self._new_scope,
            'opened': False,
            'LN': self._html_collector.line_number(thread, line=node['line'], file=node['file'])
        }
        if len(notes_data) and notes_data[-1]['hide']:
            func_enter['commented'] = True

        # Get function body
        func_body = []
        for child_node in node['children']:
            func_body.extend(self.__parse_node(child_node, depth + 1, thread, func_enter['body_scope']))

        # New scope can be added while children parsing
        if func_enter['body_scope'] in self.shown_scopes:
            # Open scope by default if its scope is shown and show function scope
            self.shown_scopes.add(scope)
            func_enter['opened'] = True
        func_enter['LC'] = self._html_collector.function_content(depth, node, func_enter['opened'])

        # Add assumptions
        if self.user.assumptions:
            func_enter['old_assumptions'], func_enter['new_assumptions'] = self.__get_assumptions(node, scope)

        # Collect function trace
        func_trace = notes_data
        func_trace.append(func_enter)
        func_trace.extend(func_body)
        if self.user.triangles:
            # Closing triangle
            func_trace.append(self.__closing_triangle(depth, thread, func_enter['body_scope']))

        return func_trace

    def __parse_action(self, node, depth, thread, scope):
        if node.get('relevant'):
            # Show all relevant actions
            self.shown_scopes.add(scope)

        action_enter = {
            'type': node['type'],
            'scope': scope,
            'body_scope': self._new_scope,
            'opened': False,
            'LN': self._html_collector.line_number(thread, line=node['line'], file=node['file'])
        }

        # Get action body
        action_body = []
        for child_node in node['children']:
            action_body.extend(self.__parse_node(child_node, depth + 1, thread, action_enter['body_scope']))

        # New scope can be added while children parsing
        if action_enter['body_scope'] in self.shown_scopes:
            # Open scope by default if its scope is shown and show action scope
            self.shown_scopes.add(scope)
            action_enter['opened'] = True
        action_enter['LC'] = self._html_collector.action_content(depth, node, action_enter['opened'])

        # Collect action trace
        action_trace = [action_enter] + action_body
        if self.user.triangles:
            # Closing triangle
            action_trace.append(self.__closing_triangle(depth, thread, action_enter['body_scope']))

        return action_trace

    def __parse_declarations(self, node, depth, thread, scope):
        decl_enter = {
            'type': node['type'],
            'scope': scope,
            'body_scope': self._new_scope
        }

        decl_body = []
        for child_node in node['children']:
            if child_node['type'] != 'declaration':
                # Just declarations are supported inside "declarations" tree
                continue
            decl_body.extend(self.__parse_declaration(
                child_node, depth, thread, decl_enter['body_scope'], scope
            ))

        # Count number of declarations inside the declarations block
        decl_number = 0
        for child in decl_body:
            if child['type'] == 'declaration' and child['scope'] == decl_enter['body_scope']:
                decl_number += 1

        # If there low of them, then move everything outside the declarations scope and return it without header
        if decl_number <= self.user.declarations_number and scope != 'global':
            for child in decl_body:
                child['scope'] = scope
            return decl_body

        decl_enter['LN'] = self._html_collector.line_number(thread)
        display = _('Declarations') if scope != 'global' else _('Global variable declarations')
        decl_enter['LC'] = self._html_collector.declarations_content(depth, display)
        return [decl_enter] + decl_body

    def __closing_triangle(self, depth, thread, scope):
        return {
            'type': 'exit',
            'scope': scope,
            'LN': self._html_collector.line_number(thread),
            'LC': self._html_collector.exit_content(depth, scope in self.shown_scopes)
        }

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

    def __parse_notes(self, node, depth, thread, scope):
        if not node.get('notes'):
            return []

        node_notes = []
        for note in node['notes']:
            if note['level'] > self.user.notes_level:
                # Ignore the note
                continue
            if note['level'] == 0 or note['level'] == 1:
                self.shown_scopes.add(scope)
            node_notes.append(note)
        if not node_notes:
            return []

        notes_data = []
        for note in node_notes[:-1]:
            # Get note level and show current scope if needed
            if note['level'] == 0 or note['level'] == 1:
                self.shown_scopes.add(scope)
            notes_data.append({
                'type': 'note',
                'scope': scope,
                'level': note['level'],
                'relevant': note['level'] < 2,
                'hide': False,
                'LN': self._html_collector.line_number(thread, line=node['line'], note_level=note['level']),
                'LC': self._html_collector.note_content(depth, note['level'], note['text'], False)
            })

        last_note = node_notes[-1]
        note_hide = node.get('hide', False)
        if last_note['level'] == 0 or last_note['level'] == 1:
            self.shown_scopes.add(scope)
        notes_data.append({
            'type': 'note',
            'scope': scope,
            'level': last_note['level'],
            'relevant': last_note['level'] < 2,
            'hide': note_hide,
            'LN': self._html_collector.line_number(thread, line=node['line'], note_level=last_note['level']),
            'LC': self._html_collector.note_content(depth, last_note['level'], last_note['text'], note_hide)
        })
        return notes_data


class ETVHtml:
    max_source_length = 500
    tab_length = 4
    condition_class = 'SrcHlAssume'
    global_thread = 'global'
    THREAD_COLORS = [
        '#5f54cb', '#85ff47', '#69c8ff', '#ff5de5', '#dfa720',
        '#0b67bf', '#fa92ff', '#57bfa8', '#bf425a', '#7d909e'
    ]

    def __init__(self, threads, max_line_len, files):
        self._threads = threads
        self._max_line_len = max_line_len
        self._files = files

    def __parse_source(self, node):
        if len(node['source']) > self.max_source_length:
            source_html = '{}... (<span class="ETV_SourceTooLong">Source code is too long to visualize</span>)'\
                .format(node['source'][:50])
        else:
            src_line = SourceLine(
                node['source'], highlights=node.get('highlight', []), filename='error trace', line=node['line']
            )
            source_html = src_line.html_code

        # Wrap to assume() conditions
        if node.get('condition'):
            source_html = '<span class="{}">assume</span>({})'.format(self.condition_class, source_html)
        return source_html

    @cached_property
    def _html_thread(self):
        html_pattern = '<span class="ETV_THREAD">{}</span>'
        content_pattern = '{pre}<span style="background-color:{color};"> </span>{post}'
        threads_num = len(self._threads)
        threads_html = {}
        for i, th in enumerate(self._threads):
            content_html = content_pattern.format(
                pre=' ' * i,
                color=self.THREAD_COLORS[i % len(self.THREAD_COLORS)],
                post=' ' * (threads_num - i - 1)
            )
            threads_html[th] = html_pattern.format(content_html)
        threads_html[self.global_thread] = html_pattern.format(' ' * threads_num)
        return threads_html

    def line_number(self, thread, line=None, file=None, note_level=None):
        # Get line number with indentations
        line_str = '' if line is None else str(line)
        line_offset = ' ' * (self._max_line_len - len(line_str))
        line_str = ' {0}{1} '.format(line_offset, line_str)

        if note_level is not None:
            line_html = '<span class="ETV_LINE_Note ETV_Note{note_level}">{line_str}</span>'.format(
                note_level=note_level, line_str=line_str
            )
        elif file is None:
            line_html = '<span class="ETV_LINE">{line_str}</span>'.format(line_str=line_str)
        else:
            line_html = '<span class="ETV_LINE" data-file="{file_str}">{line_str}</span>'.format(
                file_str=self._files[file], line_str=line_str
            )
        return '<span class="ETV_LN">{}{}</span>'.format(self._html_thread[thread], line_html)

    @cached_property
    def _eye_html(self):
        return '<i class="ETV_OpenEye link small violet icon unhide"></i>'

    @cached_property
    def _enter_triangle_html(self):
        return '<i class="ETV_EnterLink link small icon violet caret right"></i>'

    def __line_content_html(self, depth, *args):
        return '<span class="ETV_LC">{offset}{display_html}</span>'.format(
            offset=' ' * (self.tab_length * depth + 1), display_html=''.join(args)
        )

    def __span_text(self, text_class, text_value, shown=True):
        return '<span class="{text_class}"{style}>{text_value}</span>'.format(
            text_class=text_class, text_value=text_value,
            style='' if shown else ' style="display:none;"'
        )

    def statement_content(self, depth, node):
        source = self.__parse_source(node)
        if not node.get('display'):
            return self.__line_content_html(depth, source)
        return self.__line_content_html(
            depth, self._eye_html,
            self.__span_text('ETV_Display', node['display']),
            self.__span_text('ETV_Source', source, shown=False)
        )

    def declaration_content(self, depth, node):
        return self.statement_content(depth, node)

    def function_content(self, depth, node, opened):
        return self.__line_content_html(
            depth, self._eye_html if opened else self._enter_triangle_html,
            self.__span_text('ETV_Display', node['display']),
            self.__span_text('ETV_Source', self.__parse_source(node), shown=False)
        )

    def exit_content(self, depth, scope_shown):
        return self.__line_content_html(depth, '<i class="ui small icon caret up {}"></i>'.format(
            'black' if scope_shown else 'violet link ETV_ExitLink'
        ))

    def action_content(self, depth, node, opened):
        return self.__line_content_html(
            depth, self._eye_html if opened else self._enter_triangle_html,
            self.__span_text('ETV_RelevantAction' if node.get('relevant') else 'ETV_Action', node['display'])
        )

    def declarations_content(self, depth, display):
        return self.__line_content_html(depth, self._eye_html, self.__span_text('ETV_Declarations_Text', display))

    def note_content(self, depth, level, display, hide):
        note_classes = ['ETV_Note{}_Text'.format(level)]
        if hide:
            note_classes.append('ETV_ShowCommentCode')
        return self.__line_content_html(depth, self.__span_text(' '.join(note_classes), display))
