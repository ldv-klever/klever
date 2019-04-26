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
import json
from collections import OrderedDict
from urllib.parse import quote, unquote

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import ugettext_lazy as _
from django.utils.functional import cached_property

from bridge.utils import ArchiveFileContent, BridgeException

from reports.models import ReportUnsafe, ReportComponent, ReportComponentLeaf


HIGHLIGHT_CLASSES = {
    'number': 'ETVNumber',
    'comment': 'ETVComment',
    'text': 'ETVText',
    'key1': 'ETVKey1',
    'key2': 'ETVKey2'
}


TAB_LENGTH = 4
SOURCE_CLASSES = {
    'comment': "ETVComment",
    'number': "ETVNumber",
    'line': "ETVSrcL",
    'text': "ETVText",
    'key1': "ETVKey1",
    'key2': "ETVKey2"
}

KEY1_WORDS = [
    '#ifndef', '#elif', '#undef', '#ifdef', '#include', '#else', '#define',
    '#if', '#pragma', '#error', '#endif', '#line'
]

KEY2_WORDS = [
    'static', 'if', 'sizeof', 'double', 'typedef', 'unsigned', 'break', 'inline', 'for', 'default', 'else', 'const',
    'switch', 'continue', 'do', 'union', 'extern', 'int', 'void', 'case', 'enum', 'short', 'float', 'struct', 'auto',
    'long', 'goto', 'volatile', 'return', 'signed', 'register', 'while', 'char'
]

THREAD_COLORS = [
    '#5f54cb', '#85ff47', '#69c8ff', '#ff5de5', '#dfa720', '#0b67bf', '#fa92ff', '#57bfa8', '#bf425a', '#7d909e'
]


def fix_for_html(source):
    return source.replace('\t', ' ' * TAB_LENGTH).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def highlight_source(source, highlights):
    if not highlights:
        return fix_for_html(source)

    h_dict = OrderedDict()

    # Validate highlights
    source_len = len(source)
    prev_end = 0
    for h_name, start, end in sorted(highlights, key=lambda x: (x[1], x[2])):
        assert isinstance(start, int) and isinstance(end, int)
        assert prev_end <= start < end
        assert h_name in HIGHLIGHT_CLASSES
        if prev_end < start:
            h_dict[(prev_end, start)] = None
        h_dict[(start, end)] = HIGHLIGHT_CLASSES[h_name]
        prev_end = end
    if prev_end < source_len:
        h_dict[(prev_end, source_len)] = None
    elif prev_end > source_len:
        raise ValueError

    result = ''
    for start, end in reversed(h_dict):
        code = fix_for_html(source[start:end])
        code_class = h_dict[(start, end)]
        if code_class is not None:
            code = '<span class="%s">%s</span>' % (code_class, code)
        result = code + result
    return result


def get_error_trace_nodes(data):
    err_path = []
    must_have_thread = False
    curr_node = data['violation nodes'][0]
    if not isinstance(data['nodes'][curr_node][0], int):
        raise ValueError('Error traces with one path are supported')
    while curr_node != data['entry node']:
        if not isinstance(data['nodes'][curr_node][0], int):
            raise ValueError('Error traces with one path are supported')
        curr_in_edge = data['edges'][data['nodes'][curr_node][0]]
        if 'thread' in curr_in_edge:
            must_have_thread = True
        elif must_have_thread:
            raise ValueError("All error trace edges must have thread identifier ('0' or '1')")
        err_path.insert(0, data['nodes'][curr_node][0])
        curr_node = curr_in_edge['source node']
    return err_path


class ScopeInfo:
    def __init__(self, cnt, thread_id):
        self.initialised = False
        self._cnt = cnt
        # (index, is_action, thread, counter)
        self._stack = []
        # Klever main
        self._main_scope = (0, 0, thread_id, 0)
        self._shown = {self._main_scope}
        self._hidden = set()

    def current(self):
        if len(self._stack) == 0:
            if self.initialised:
                return '_'.join(str(x) for x in self._main_scope)
            else:
                return 'global'
        return '_'.join(str(x) for x in self._stack[-1])

    def add(self, index, thread_id, is_action=False):
        self._cnt += 1
        scope_id = (index, int(is_action), thread_id, self._cnt)
        self._stack.append(scope_id)
        if len(self._stack) == 1:
            self._shown.add(scope_id)

    def remove(self):
        curr_scope = self.current()
        self._stack.pop()
        return curr_scope

    def show_current_scope(self, comment_type):
        if not self.initialised:
            return
        if comment_type == 'note':
            if all(ss not in self._hidden for ss in self._stack):
                for ss in self._stack:
                    if ss not in self._shown:
                        self._shown.add(ss)
        elif comment_type in {'warning', 'callback action', 'entry_point'}:
            for ss in self._stack:
                if ss not in self._shown:
                    self._shown.add(ss)

    def hide_current_scope(self):
        self._hidden.add(self._stack[-1])

    def offset(self):
        if len(self._stack) == 0:
            return ' '
        return (len(self._stack) * TAB_LENGTH + 1) * ' '

    def is_shown(self, scope_str):
        try:
            return tuple(int(x) for x in scope_str.split('_')) in self._shown
        except ValueError:
            return scope_str == 'global' and scope_str in self._shown

    def current_action(self):
        if len(self._stack) > 0 and self._stack[-1][1]:
            return self._stack[-1][0]
        return None

    def is_return_correct(self, func_id):
        if len(self._stack) == 0:
            return False
        if self._stack[-1][1]:
            return False
        if func_id is None or self._stack[-1][0] == func_id:
            return True
        return False

    def is_double_return_correct(self, func_id):
        if len(self._stack) < 2:
            return False
        if self._stack[-2][1]:
            if len(self._stack) < 3:
                return False
            if self._stack[-3][0] == func_id:
                return True
        elif self._stack[-2][0] == func_id:
            return True
        return False

    def can_return(self):
        if len(self._stack) > 0:
            return True
        return False

    def is_main(self, scope_str):
        if scope_str == '_'.join(str(x) for x in self._main_scope):
            return True
        return False


class ParseErrorTrace:
    def __init__(self, data, include_assumptions, thread_id, triangles, cnt=0):
        self.files = list(data['files']) if 'files' in data else []
        self.actions = list(data['actions']) if 'actions' in data else []
        self.callback_actions = list(data['callback actions']) if 'callback actions' in data else []
        self.functions = list(data['funcs']) if 'funcs' in data else []
        self.include_assumptions = include_assumptions
        self.triangles = triangles
        self.thread_id = thread_id
        self.scope = ScopeInfo(cnt, thread_id)
        self.global_lines = []
        self.lines = []
        self.curr_file = None
        self.max_line_length = 5
        self.assume_scopes = {}
        self.double_return = set()
        self._amp_replaced = False

    def add_line(self, edge):
        line = str(edge['start line']) if 'start line' in edge else None
        code = edge['source'] if 'source' in edge and len(edge['source']) > 0 else None
        if 'file' in edge:
            self.curr_file = self.files[edge['file']]
        if self.curr_file is None:
            line = None
        if line is not None and len(line) > self.max_line_length:
            self.max_line_length = len(line)
        line_data = {
            'line': line,
            'file': self.curr_file,
            'code': code,
            'offset': self.scope.offset(),
            'type': 'normal'
        }

        line_data.update(self.__add_assumptions(edge.get('assumption')))
        line_data['scope'] = self.scope.current()
        if not self.scope.initialised:
            if 'enter' in edge:
                raise ValueError("Global initialization edge can't contain enter")
            if line_data['code'] is not None:
                line_data.update(self.__get_comment(edge.get('note'), edge.get('warn')))
                self.global_lines.append(line_data)
            return

        if 'condition' in edge:
            line_data['code'] = self.__get_condition_code(line_data['code'])

        curr_action = self.scope.current_action()
        new_action = edge.get('action')
        if curr_action != new_action:
            if curr_action is not None:
                # Return from action
                self.lines.append(self.__triangle_line(self.scope.remove()))
                line_data['offset'] = self.scope.offset()
                line_data['scope'] = self.scope.current()
            action_line = line_data['line']
            action_file = None
            if 'original start line' in edge and 'original file' in edge:
                action_line = str(edge['original start line'])
                if len(action_line) > self.max_line_length:
                    self.max_line_length = len(action_line)
                action_file = self.files[edge['original file']]
            line_data.update(self.__enter_action(new_action, action_line, action_file))

        line_data.update(self.__get_comment(edge.get('note'), edge.get('warn')))

        if 'enter' in edge:
            line_data.update(self.__enter_function(
                edge['enter'], code=line_data['code'], comment=edge.get('entry_point')
            ))
            if any(x in edge for x in ['note', 'warn']):
                self.scope.hide_current_scope()
            if 'return' in edge:
                if edge['enter'] == edge['return']:
                    self.__return()
                    return
                else:
                    if not self.scope.is_double_return_correct(edge['return']):
                        raise ValueError('Double return from "%s" is not allowed while entering "%s"' % (
                            self.functions[edge['return']], self.functions[edge['enter']]
                        ))
                    self.double_return.add(self.scope.current())
        elif 'return' in edge:
            self.lines.append(line_data)
            self.__return(edge['return'])
            return
        if line_data['code'] is not None:
            self.lines.append(line_data)

    def __update_line_data(self):
        return {'offset': self.scope.offset(), 'scope': self.scope.current()}

    def __enter_action(self, action_id, line, file):
        if action_id is None:
            return {}
        if file is None:
            file = self.curr_file
        if action_id in self.callback_actions:
            self.scope.show_current_scope('callback action')
        enter_action_data = {
            'line': line, 'file': file, 'offset': self.scope.offset(), 'scope': self.scope.current(),
            'code': '<span class="%s">%s</span>' % (
                'ETV_CallbackAction' if action_id in self.callback_actions else 'ETV_Action',
                self.actions[action_id]
            )
        }
        enter_action_data.update(self.__enter_function(action_id))
        if action_id in self.callback_actions:
            enter_action_data['type'] = 'callback'
        self.lines.append(enter_action_data)
        return {'offset': self.scope.offset(), 'scope': self.scope.current()}

    def __enter_function(self, func_id, code=None, comment=None):
        self.scope.add(func_id, self.thread_id, (code is None))
        enter_data = {'type': 'enter', 'hide_id': self.scope.current()}
        if code is not None:
            if comment is None:
                enter_data['comment'] = self.functions[func_id]
                enter_data['comment_class'] = 'ETV_Fname'
            else:
                self.scope.show_current_scope('entry_point')
                enter_data['comment'] = comment
                enter_data['comment_class'] = 'ETV_Fcomment'
            enter_data['code'] = re.sub(
                '(^|\W)' + self.functions[func_id] + '(\W|$)',
                '\g<1><span class="ETV_Fname">' + self.functions[func_id] + '</span>\g<2>',
                code
            )
        return enter_data

    def __triangle_line(self, return_scope):
        data = {'offset': self.scope.offset(), 'line': None, 'scope': return_scope, 'type': 'return'}
        if self.scope.is_shown(return_scope):
            data['code'] = '<span><i class="ui mini icon blue caret up"></i></span>'
            if not self.triangles:
                data['type'] = 'hidden-return'
        else:
            data['code'] = '<span class="ETV_DownHideLink"><i class="ui mini icon violet caret up link"></i></span>'
        return data

    def __return(self, func_id=None, if_possible=False):
        if self.scope.current_action() is not None:
            # Return from action first
            self.lines.append(self.__triangle_line(self.scope.remove()))
        if not self.scope.is_return_correct(func_id):
            if if_possible:
                return
            func_name = 'NONE'
            if func_id is not None:
                func_name = self.functions[func_id]
            raise ValueError('Return from function "%s" without entering it (current scope is %s)' % (
                func_name, self.scope.current()
            ))
        return_scope = self.scope.remove()
        self.lines.append(self.__triangle_line(return_scope))
        if return_scope in self.double_return:
            self.double_return.remove(return_scope)
            self.__return()

    def __return_all(self):
        while self.scope.can_return():
            self.__return(if_possible=True)

    def __get_comment(self, note, warn):
        new_data = {}
        if warn is not None:
            self.scope.show_current_scope('warning')
            new_data['warning'] = warn
        elif note is not None:
            self.scope.show_current_scope('note')
            new_data['note'] = note
        return new_data

    def __add_assumptions(self, assumption):
        if self.include_assumptions and assumption is None:
            return self.__fill_assumptions([])

        if not self.include_assumptions:
            return {}

        ass_scope = self.scope.current()
        if ass_scope not in self.assume_scopes:
            self.assume_scopes[ass_scope] = []

        curr_assumes = []
        for assume in assumption.split(';'):
            if len(assume) == 0:
                continue
            self.assume_scopes[ass_scope].append(assume)
            curr_assumes.append('%s_%s' % (ass_scope, str(len(self.assume_scopes[ass_scope]) - 1)))
        return self.__fill_assumptions(curr_assumes)

    def __fill_assumptions(self, current_assumptions):
        assumptions = []
        curr_scope = self.scope.current()
        if curr_scope in self.assume_scopes:
            for j in range(len(self.assume_scopes[curr_scope])):
                assume_id = '%s_%s' % (curr_scope, j)
                if assume_id in current_assumptions:
                    continue
                assumptions.append(assume_id)
        return {'assumptions': ';'.join(reversed(assumptions)), 'current_assumptions': ';'.join(current_assumptions)}

    def __get_condition_code(self, code):
        self.__is_not_used()
        m = re.match('^\s*\[(.*)\]\s*$', code)
        if m is not None:
            code = m.group(1)
        return '<span class="ETV_CondAss">assume(</span>' + str(code) + '<span class="ETV_CondAss">);</span>'

    def finish_error_lines(self, thread, thread_id):
        self.__return_all()
        if len(self.global_lines) > 0:
            self.lines = [{
                'code': '', 'line': None, 'file': None, 'offset': ' ',
                'hide_id': 'global', 'scope': 'global', 'type': 'normal'
            }] + self.global_lines + self.lines
        for i in range(0, len(self.lines)):
            if 'thread_id' in self.lines[i]:
                continue
            self.lines[i]['thread_id'] = thread_id
            self.lines[i]['thread'] = thread
            if self.lines[i]['code'] is None:
                continue
            if self.lines[i]['line'] is None:
                self.lines[i]['line_offset'] = ' ' * self.max_line_length
            else:
                self.lines[i]['line_offset'] = ' ' * (self.max_line_length - len(self.lines[i]['line']))
            self.lines[i]['code'] = self.__parse_code(self.lines[i]['code'])
            self._amp_replaced = False

            if not self.scope.is_main(self.lines[i]['scope']):
                if self.lines[i]['type'] == 'normal' and self.scope.is_shown(self.lines[i]['scope']):
                    self.lines[i]['type'] = 'eye-control'
                elif self.lines[i]['type'] == 'enter' and not self.scope.is_shown(self.lines[i]['hide_id']):
                    self.lines[i]['type'] = 'eye-control'
                    if 'comment' in self.lines[i]:
                        del self.lines[i]['comment']
                    if 'comment_class' in self.lines[i]:
                        del self.lines[i]['comment_class']
            a = 'warning' in self.lines[i]
            b = 'note' in self.lines[i]
            c = not self.scope.is_shown(self.lines[i]['scope'])
            d = 'hide_id' not in self.lines[i]
            e = 'hide_id' in self.lines[i] and not self.scope.is_shown(self.lines[i]['hide_id'])
            f = self.lines[i]['type'] == 'eye-control' and self.lines[i]['scope'] != 'global'
            if a or b and (c or d or e) or not a and not b and c and (d or e) or f:
                self.lines[i]['hidden'] = True
            if e:
                self.lines[i]['collapsed'] = True
            if a or b:
                self.lines[i]['commented'] = True
            if b and c and self.lines[i]['scope'] != 'global':
                self.lines[i]['note_hidden'] = True

    def __wrap_code(self, code, code_type):
        self.__is_not_used()
        if code_type in SOURCE_CLASSES:
            return '<span class="%s">%s</span>' % (SOURCE_CLASSES[code_type], code)
        return code

    def __parse_code(self, code):
        if len(code) > 512:
            return '<span style="color: red;">The line is too long to visualize</span>'
        m = re.match('^(.*?)(<span.*?</span>)(.*)$', code)
        if m is not None:
            return "%s%s%s" % (
                self.__parse_code(m.group(1)),
                m.group(2),
                self.__parse_code(m.group(3))
            )
        if not self._amp_replaced:
            code = code.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            self._amp_replaced = True
        m = re.match('^(.*?)(/\*.*?\*/)(.*)$', code)
        if m is not None:
            return "%s%s%s" % (
                self.__parse_code(m.group(1)),
                self.__wrap_code(m.group(2), 'comment'),
                self.__parse_code(m.group(3))
            )
        m = re.match('^(.*?)([\'\"])(.*)$', code)
        if m is not None:
            m2 = re.match(r'^(.*?)(?<!\\)(?:\\\\)*%s(.*)$' % m.group(2), m.group(3))
            if m2 is not None:
                return "%s%s%s" % (
                    self.__parse_code(m.group(1)),
                    self.__wrap_code(m.group(2) + m2.group(1) + m.group(2), 'text'),
                    self.__parse_code(m2.group(2))
                )
        m = re.match('^(.*?\W)(\d+)(\W.*)$', code)
        if m is not None:
            return "%s%s%s" % (
                self.__parse_code(m.group(1)),
                self.__wrap_code(m.group(2), 'number'),
                self.__parse_code(m.group(3))
            )
        words = re.split('([^a-zA-Z0-9-_#])', code)
        new_words = []
        for word in words:
            if word in KEY1_WORDS:
                new_words.append(self.__wrap_code(word, 'key1'))
            elif word in KEY2_WORDS:
                new_words.append(self.__wrap_code(word, 'key2'))
            else:
                new_words.append(word)
        return ''.join(new_words)

    def __is_not_used(self):
        pass


class GetETVOld:
    def __init__(self, error_trace, user=None):
        self.include_assumptions = user.assumptions if user else settings.DEF_USER['assumptions']
        self.triangles = user.triangles if user else settings.DEF_USER['triangles']
        self.data = json.loads(error_trace)
        self.err_trace_nodes = get_error_trace_nodes(self.data)
        self.threads = []
        self._has_global = True
        self.html_trace, self.assumes = self.__html_trace()
        self.attributes = []

    def __get_attributes(self):
        # TODO: return list of error trace attributes like [<attr name>, <attr value>]. Ignore 'programfile'.
        pass

    def __html_trace(self):
        for n in self.err_trace_nodes:
            if 'thread' not in self.data['edges'][n]:
                raise ValueError('All error trace edges should have thread')
            if self.data['edges'][n]['thread'] not in self.threads:
                self.threads.append(self.data['edges'][n]['thread'])
            if self.threads[0] == self.data['edges'][n]['thread'] and 'enter' in self.data['edges'][n]:
                self._has_global = False

        return self.__add_thread_lines(0, 0)[0:2]

    def __add_thread_lines(self, i, start_index):
        parsed_trace = ParseErrorTrace(self.data, self.include_assumptions, i, self.triangles, start_index)
        if i > 0 or not self._has_global:
            parsed_trace.scope.initialised = True
        trace_assumes = []
        j = start_index
        while j < len(self.err_trace_nodes):
            edge_data = self.data['edges'][self.err_trace_nodes[j]]
            curr_t = self.threads.index(edge_data['thread'])
            if curr_t > i:
                (new_lines, new_assumes, j) = self.__add_thread_lines(curr_t, j)
                parsed_trace.lines.extend(new_lines)
                trace_assumes.extend(new_assumes)
            elif curr_t < i:
                break
            else:
                parsed_trace.add_line(edge_data)
                j += 1
        parsed_trace.finish_error_lines(self.__get_thread(i), i)

        for sc in parsed_trace.assume_scopes:
            as_cnt = 0
            for a in parsed_trace.assume_scopes[sc]:
                trace_assumes.append(['%s_%s' % (sc, as_cnt), a])
                as_cnt += 1
        return parsed_trace.lines, trace_assumes, j

    def __get_thread(self, thread):
        return '%s<span style="background-color:%s;"> </span>%s' % (
            ' ' * thread, THREAD_COLORS[thread % len(THREAD_COLORS)], ' ' * (len(self.threads) - thread - 1)
        )


class GetETV:
    global_thread = 'global'

    def __init__(self, error_trace, user=None):
        self.include_assumptions = user.assumptions if user else settings.DEF_USER['assumptions']
        self.triangles = user.triangles if user else settings.DEF_USER['triangles']
        self.trace = json.loads(error_trace)
        self._max_line_len = 0
        self._curr_scope = 0
        self.shown_scopes = set()
        self.assumptions = {}
        self._scope_assumptions = {}

        self._threads = self.__get_threads()
        self.globals = self.__get_global_vars()
        self.html_trace = self.__parse_node(self.trace['trace'])

    def __get_threads(self):
        threads = []
        if self.trace.get('global variable declarations'):
            threads.append(self.global_thread)
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
        # TODO: remove support of "global"
        if 'global' in self.trace:
            self.trace['global variable declarations'] = self.trace['global']

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
            func_scope = self._new_scope
            enter_data['inner_scope'] = func_scope

            if enter_data.get('warn') or enter_data.get('note') and not has_asc_note:
                self.shown_scopes.add(scope)

            child_depth = depth + 1
            child_asc_note = bool(has_asc_note or enter_data.get('note') or enter_data.get('warn'))
            children_trace = []
            for child_node in node['children']:
                children_trace.extend(self.__parse_node(
                    child_node, depth=child_depth, thread=thread, has_asc_note=child_asc_note, scope=func_scope
                ))

            # Function scope can be added while children parsing
            if func_scope in self.shown_scopes:
                self.shown_scopes.add(scope)
                # Open function by default if its scope is shown
                enter_data['opened'] = True

            if not self.triangles:
                return [enter_data] + children_trace

            # Closing triangle
            exit_data = self.__parse_exit(depth, thread, func_scope)

            return [enter_data] + children_trace + [exit_data]

        # Action
        if node['type'] == 'action':
            enter_data = self.__parse_action(node, depth, thread, scope)
            act_scope = self._new_scope
            enter_data['inner_scope'] = act_scope

            if enter_data['callback']:
                # Show all callback actions
                self.shown_scopes.add(scope)

            child_depth = depth + 1
            child_asc_note = has_asc_note or bool(enter_data.get('note') or enter_data.get('warn'))
            children_trace = []
            for child_node in node['children']:
                children_trace.extend(self.__parse_node(
                    child_node, depth=child_depth, thread=thread, has_asc_note=child_asc_note, scope=act_scope
                ))

            # Action scope can be added while children parsing
            if act_scope in self.shown_scopes:
                # Open action by default if its scope is shown and show action scope
                self.shown_scopes.add(scope)
                enter_data['opened'] = True

            if not self.triangles:
                return [enter_data] + children_trace

            # Closing triangle
            exit_data = self.__parse_exit(depth, thread, act_scope)
            return [enter_data] + children_trace + [exit_data]

    def __parse_statement(self, node, depth, thread, scope):
        statement_data = {
            'type': node['type'],
            'thread': self._html_thread[thread],
            'line': self.__get_line(node['line']),
            'file': self.trace['files'][node['file']],
            'offset': ' ' * (TAB_LENGTH * depth + 1),
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
        if self.include_assumptions:
            statement_data['old_assumptions'], statement_data['new_assumptions'] = self.__get_assumptions(node, scope)

        return statement_data

    def __parse_function(self, node, depth, thread, scope):
        func_data = self.__parse_statement(node, depth, thread, scope)
        func_data['opened'] = False
        return func_data

    def __parse_action(self, node, depth, thread, scope):
        return {
            'type': node['type'],
            'callback': node.get('callback', False),
            'thread': self._html_thread[thread],
            'line': self.__get_line(node['line']),
            'file': self.trace['files'][node['file']],
            'offset': ' ' * (TAB_LENGTH * depth + 1),
            'display': node['display'],
            'scope': scope,
            'opened': False
        }

    def __parse_exit(self, depth, thread, scope):
        return {
            'type': 'exit',
            'line': self.__get_line(),
            'thread': self._html_thread[thread],
            'offset': ' ' * (TAB_LENGTH * depth + 1),
            'scope': scope
        }

    def __parse_source(self, node):
        source = node['source']
        highlights = node.get('highlight', [])
        h_dict = OrderedDict()

        # Validate highlights
        source_len = len(source)
        prev_end = 0
        for h_name, start, end in sorted(highlights, key=lambda x: (x[1], x[2])):
            assert isinstance(start, int) and isinstance(end, int)
            assert prev_end <= start < end
            assert h_name in HIGHLIGHT_CLASSES
            if prev_end < start:
                h_dict[(prev_end, start)] = None
            h_dict[(start, end)] = HIGHLIGHT_CLASSES[h_name]
            prev_end = end
        if prev_end < source_len:
            h_dict[(prev_end, source_len)] = None
        elif prev_end > source_len:
            raise ValueError

        result = ''
        for start, end in reversed(h_dict):
            result = self.__wrap_code(source[start:end], h_dict[(start, end)]) + result
        return result

    def __wrap_code(self, code, code_class=None):
        if code_class is None:
            return code
        return '<span class="%s">%s</span>' % (code_class, code)

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
                color=THREAD_COLORS[i % len(THREAD_COLORS)],
                postfix=' ' * (threads_num - i - 1)
            )
        threads_html['global'] = ' ' * threads_num
        return threads_html

    def __get_assumptions(self, node, scope):
        if not self.include_assumptions:
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


class GetSource:
    index_postfix = '.idx.json'

    def __init__(self, unsafe, file_name):
        self.report = unsafe
        self.is_comment = False
        self.is_text = False
        self.text_quote = None
        self._file_name = self.__parse_file_name(file_name)
        self.data = self.__get_source()

    def __parse_file_name(self, file_name):
        name = unquote(file_name)
        if name.startswith('/'):
            name = name[1:]
        return name

    def __extract_file(self, obj):
        source_content = index_data = None
        try:
            res = ArchiveFileContent(obj, 'archive', self._file_name, not_exists_ok=True)
        except Exception as e:
            raise BridgeException(_("Error while extracting source: %(error)s") % {'error': str(e)})
        if res.content is not None:
            source_content = res.content.decode('utf8')

            index_name = self._file_name + self.index_postfix
            try:
                index_res = ArchiveFileContent(obj, 'archive', index_name, not_exists_ok=True)
            except Exception as e:
                raise BridgeException(_("Error while extracting source: %(error)s") % {'error': str(e)})
            if index_res.content is not None:
                index_data = json.loads(res.content.decode('utf8'))
        return source_content, index_data

    def __get_source(self):
        ctype = ContentType.objects.get_for_model(ReportUnsafe)
        leaves_qs = ReportComponentLeaf.objects\
            .filter(content_type=ctype, object_id=self.report.id)\
            .order_by('-report_id')\
            .select_related('report__original', 'report__additional')\
            .only('report__original_id', 'report__additional_id',
                  'report__original__archive', 'report__additional__archive')

        file_content = index_data = None
        for leaf in leaves_qs:
            if leaf.report.additional:
                file_content, index_data = self.__extract_file(leaf.report.additional)
            if file_content is None and leaf.report.original:
                file_content, index_data = self.__extract_file(leaf.report.original)
            if file_content is not None:
                break
        else:
            raise BridgeException(_('The source file was not found'))

        highlights = {}
        if index_data and 'highlight' in index_data:
            for h_name, line_num, start, end in index_data['highlight']:
                highlights[line_num] = [h_name, start, end]

        data = ''
        cnt = 1
        lines = file_content.split('\n')
        total_lines_len = len(str(len(lines)))
        for code in lines:
            data += '<span><span id="{line_id}" class="{line_class}">{prefix}{number}</span> {code}</span><br>'.format(
                line_id='ETVSrcL_{}'.format(cnt), line_class=SOURCE_CLASSES['line'],
                prefix=' ' * (total_lines_len - len(str(cnt))), number=cnt,
                code=highlight_source(code, highlights.get(cnt))
            )
            cnt += 1
        return data
