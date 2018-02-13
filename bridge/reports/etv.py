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
import json

from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import ugettext_lazy as _

from bridge.vars import ERROR_TRACE_FILE
from bridge.utils import ArchiveFileContent, BridgeException

from reports.models import ReportUnsafe


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
        elif comment_type in {'warning', 'callback action'}:
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
        if self.scope.current_action():
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


class GetETV:
    def __init__(self, error_trace, user):
        self.include_assumptions = user.extended.assumptions
        self.triangles = user.extended.triangles
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


class GetSource:
    def __init__(self, report_id, file_name):
        self.report = self.__get_report(report_id)
        self.is_comment = False
        self.is_text = False
        self.text_quote = None
        self.data = self.__get_source(file_name)

    def __get_report(self, report_id):
        self.__is_not_used()
        try:
            return ReportUnsafe.objects.get(pk=report_id)
        except ObjectDoesNotExist:
            raise BridgeException(_("Could not find the corresponding unsafe"))

    def __get_source(self, file_name):
        data = ''
        if file_name.startswith('/'):
            file_name = file_name[1:]
        try:
            source_content = ArchiveFileContent(self.report.source, 'archive', file_name).content.decode('utf8')
        except Exception as e:
            raise BridgeException(_("Error while extracting source from archive: %(error)s") % {'error': str(e)})
        cnt = 1
        lines = source_content.split('\n')
        for line in lines:
            line = line.replace('\t', ' ' * TAB_LENGTH).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            line_num = ' ' * (len(str(len(lines))) - len(str(cnt))) + str(cnt)
            data += '<span>%s %s</span><br>' % (
                self.__wrap_line(line_num, 'line', 'ETVSrcL_%s' % cnt), self.__parse_line(line)
            )
            cnt += 1
        return data

    def __parse_line(self, line):
        if self.is_comment:
            m = re.match('(.*?)\*/(.*)', line)
            if m is None:
                return self.__wrap_line(line, 'comment')
            self.is_comment = False
            new_line = self.__wrap_line(m.group(1) + '*/', 'comment')
            return new_line + self.__parse_line(m.group(2))

        if self.is_text:
            before, after = self.__parse_text(line)
            if after is None:
                return self.__wrap_line(before, 'text')
            self.is_text = False
            return self.__wrap_line(before, 'text') + self.__parse_line(after)

        m = re.match('(.*?)/\*(.*)', line)
        if m is not None and m.group(1).find('"') == -1 and m.group(1).find("'") == -1:
            new_line = self.__parse_line(m.group(1))
            self.is_comment = True
            new_line += self.__parse_line('/*' + m.group(2))
            return new_line
        m = re.match('(.*?)//(.*)', line)
        if m is not None and m.group(1).find('"') == -1 and m.group(1).find("'") == -1:
            new_line = self.__parse_line(m.group(1))
            new_line += self.__wrap_line('//' + m.group(2), 'comment')
            return new_line

        m = re.match('(.*?)([\'\"])(.*)', line)
        if m is not None:
            new_line = self.__parse_line(m.group(1))
            self.text_quote = m.group(2)
            before, after = self.__parse_text(m.group(3))
            new_line += self.__wrap_line(self.text_quote + before, 'text')
            if after is None:
                self.is_text = True
                return new_line
            self.is_text = False
            return new_line + self.__parse_line(after)

        m = re.match("(.*\W)(\d+)(\W.*)", line)
        if m is not None:
            new_line = self.__parse_line(m.group(1))
            new_line += self.__wrap_line(m.group(2), 'number')
            new_line += self.__parse_line(m.group(3))
            return new_line
        words = re.split('([^a-zA-Z0-9-_#])', line)
        new_words = []
        for word in words:
            if word in KEY1_WORDS:
                new_words.append(self.__wrap_line(word, 'key1'))
            elif word in KEY2_WORDS:
                new_words.append(self.__wrap_line(word, 'key2'))
            else:
                new_words.append(word)
        return ''.join(new_words)

    def __parse_text(self, text):
        escaped = False
        before = ''
        after = ''
        end_found = False
        for c in text:
            if end_found:
                after += c
                continue
            if not escaped and c == self.text_quote:
                end_found = True
            elif escaped:
                escaped = False
            elif c == '\\':
                escaped = True
            before += c
        if end_found:
            return before, after
        return before, None

    def __wrap_line(self, line, text_type, line_id=None):
        self.__is_not_used()
        if text_type not in SOURCE_CLASSES:
            return line
        if line_id is not None:
            return '<span id="%s" class="%s">%s</span>' % (line_id, SOURCE_CLASSES[text_type], line)
        return '<span class="%s">%s</span>' % (SOURCE_CLASSES[text_type], line)

    def __is_not_used(self):
        pass


class Forest:
    def __init__(self):
        self._cnt = 1
        self._level = 0
        self.call_stack = []
        self._forest = []

    def scope(self):
        return self.call_stack[-1] if len(self.call_stack) > 0 else None

    def enter_func(self, func_name, is_model=False):
        while len(self._forest) <= self._level:
            self._forest.append([])
        new_scope = '%s__%s' % (self._cnt, func_name)
        self._forest[self._level].append({
            'name': new_scope,
            'parent': self.scope(),
            'model': is_model
        })
        self.call_stack.append(new_scope)
        self._level += 1
        self._cnt += 1

    def mark_current_scope(self):
        if self._level < 1:
            return
        for i in range(len(self._forest[self._level - 1])):
            if self._forest[self._level - 1][i]['name'] == self.call_stack[-1]:
                self._forest[self._level - 1][i]['model'] = True
                break

    def return_from_func(self):
        self._level -= 1
        self.call_stack.pop()

    def get_forest(self):
        self.__exclude_functions()
        if len(self._forest) == 0:
            return None
        final_forest = self.__convert_forest()
        self.__init__()
        return final_forest

    def add_note(self, note):
        while len(self._forest) <= self._level:
            self._forest.append([])
        self._forest[self._level].append({
            'name': note,
            'parent': self.scope(),
            'model': True
        })

    def __not_model_leaf(self, i, j):
        if self._forest[i][j]['model']:
            return False
        elif len(self._forest) > i + 1:
            for ch_j in range(len(self._forest[i + 1])):
                if self._forest[i + 1][ch_j]['parent'] == self._forest[i][j]['name']:
                    return False
        return True

    def __exclude_functions(self):
        for i in reversed(range(0, len(self._forest))):
            new_level = []
            for j in range(0, len(self._forest[i])):
                if not self.__not_model_leaf(i, j):
                    new_level.append(self._forest[i][j])
            if len(new_level) == 0:
                del self._forest[i]
            else:
                self._forest[i] = new_level

    def __get_children(self, lvl, j):
        children = []
        if len(self._forest) > lvl + 1:
            for ch_j in range(0, len(self._forest[lvl + 1])):
                if self._forest[lvl + 1][ch_j]['parent'] == self._forest[lvl][j]['name']:
                    children.append({
                        re.sub('^\d+__', '', self._forest[lvl + 1][ch_j]['name']): self.__get_children(lvl + 1, ch_j)
                    })
        return children

    def __convert_forest(self):
        final_forest = []
        for j in range(len(self._forest[0])):
            final_forest.append({
                re.sub('^\d+__', '', self._forest[0][j]['name']): self.__get_children(0, j)
            })
        return final_forest


class ErrorTraceForests:
    def __init__(self, error_trace, all_threads=False):
        self.data = json.loads(error_trace)
        self.all_threads = all_threads
        self.trace = self.__get_forests(get_error_trace_nodes(self.data))

    def __get_forests(self, edge_trace):
        threads = {}
        thread_order = []
        for edge_id in edge_trace:
            if 'thread' not in self.data['edges'][edge_id]:
                raise ValueError('All error trace edges should have thread')
            if self.data['edges'][edge_id]['thread'] not in threads:
                thread_order.append(self.data['edges'][edge_id]['thread'])
                threads[self.data['edges'][edge_id]['thread']] = []
            threads[self.data['edges'][edge_id]['thread']].append(edge_id)
        forests = []
        if self.all_threads:
            for t in thread_order:
                forests.extend(self.__collect_forests(threads[t]))
        else:
            for t in thread_order:
                forests.extend(self.__get_callback_forests(threads[t]))
        return forests

    def __get_callback_forests(self, edge_trace):
        forests = []
        forest = Forest()
        collect_names = False
        double_return = set()
        curr_action = -1
        for edge_id in edge_trace:
            edge_data = self.data['edges'][edge_id]
            if len(forest.call_stack) == 0 and edge_data.get('action', -1) != curr_action >= 0:
                collect_names = False
                curr_action = -1
                curr_forest = forest.get_forest()
                if curr_forest is not None:
                    forests.append(curr_forest)
            if curr_action == -1 and 'action' in edge_data and edge_data['action'] in self.data['callback actions']:
                collect_names = True
                curr_action = edge_data['action']
            if collect_names:
                is_model = 'note' in edge_data or 'warn' in edge_data
                if 'enter' in edge_data:
                    forest.enter_func(self.data['funcs'][edge_data['enter']], is_model)
                    if 'return' in edge_data:
                        if edge_data['enter'] == edge_data['return']:
                            forest.return_from_func()
                        else:
                            double_return.add(forest.scope())
                elif 'return' in edge_data:
                    old_scope = forest.scope()
                    forest.return_from_func()
                    while old_scope in double_return:
                        double_return.remove(old_scope)
                        old_scope = forest.scope()
                        forest.return_from_func()
                elif is_model:
                    forest.mark_current_scope()

        if collect_names:
            curr_forest = forest.get_forest()
            if curr_forest is not None:
                forests.append(curr_forest)
        return forests

    def __collect_forests(self, edge_trace):
        forests = []
        forest = {'full': Forest(), 'callback': Forest()}
        fname = 'full'
        curr_action = -1
        double_return = set()
        for edge_id in edge_trace:
            edge_data = self.data['edges'][edge_id]
            if fname == 'callback' and len(forest['callback'].call_stack) == 0 \
                    and edge_data.get('action', -1) != curr_action:
                curr_action = -1
                curr_forest = forest['callback'].get_forest()
                if curr_forest is not None:
                    forests.append(curr_forest)
                fname = 'full'
            if curr_action == -1 and 'action' in edge_data and edge_data['action'] in self.data['callback actions']:
                fname = 'callback'
                curr_action = edge_data['action']

            is_model = 'note' in edge_data or 'warn' in edge_data
            if 'enter' in edge_data:
                forest[fname].enter_func(self.data['funcs'][edge_data['enter']], is_model)
                if 'return' in edge_data:
                    if edge_data['enter'] == edge_data['return']:
                        forest[fname].return_from_func()
                    else:
                        double_return.add(forest[fname].scope())
            elif 'return' in edge_data:
                old_scope = forest[fname].scope()
                forest[fname].return_from_func()
                while old_scope in double_return:
                    double_return.remove(old_scope)
                    old_scope = forest[fname].scope()
                    forest[fname].return_from_func()
            elif is_model:
                forest[fname].mark_current_scope()

        if fname == 'callback':
            curr_forest = forest['callback'].get_forest()
            if curr_forest is not None:
                forests.append(curr_forest)
        curr_forest = forest['full'].get_forest()
        if curr_forest is not None:
            forests.append(curr_forest)
        return forests

    def __get_thread_forest(self, edge_trace):
        forest = Forest()
        double_return = set()
        for edge_id in edge_trace:
            edge_data = self.data['edges'][edge_id]
            is_model = 'note' in edge_data or 'warn' in edge_data
            if 'enter' in edge_data:
                forest.enter_func(self.data['funcs'][edge_data['enter']], is_model)
                if 'return' in edge_data:
                    if edge_data['enter'] == edge_data['return']:
                        forest.return_from_func()
                    else:
                        double_return.add(forest.scope())
            elif 'return' in edge_data:
                old_scope = forest.scope()
                forest.return_from_func()
                while old_scope in double_return:
                    double_return.remove(old_scope)
                    old_scope = forest.scope()
                    forest.return_from_func()
            elif is_model:
                forest.mark_current_scope()

        curr_forest = forest.get_forest()
        if curr_forest is not None and len(curr_forest) > 0:
            return curr_forest
        return []


def etv_callstack(unsafe_id=None, file_name='test.txt'):
    if unsafe_id:
        unsafe = ReportUnsafe.objects.get(id=unsafe_id)
    else:
        unsafe = ReportUnsafe.objects.all().first()
    content = ArchiveFileContent(unsafe, 'error_trace', ERROR_TRACE_FILE).content.decode('utf8')
    data = json.loads(content)
    trace = ''
    double_returns = set()
    ind = 0
    for x in data['edges']:
        if 'enter' in x:
            if 'action' in x:
                trace += '%s%s(%s)[action_%s] {\n' % (' ' * ind, data['funcs'][x['enter']], x['enter'], x['action'])
            else:
                trace += '%s%s(%s) {\n' % (' ' * ind, data['funcs'][x['enter']], x['enter'])
            ind += 2
            if 'return' in x:
                double_returns.add(x['enter'])
        elif 'return' in x:
            ind -= 2
            if 'action' in x:
                trace += '%s}(%s)[action_%s]\n' % (' ' * ind, x['return'], x['action'])
            else:
                trace += '%s}(%s)\n' % (' ' * ind, x['return'])
            if x['return'] in double_returns:
                ind -= 2
                trace += '%s}(DOUBLE)\n' % (' ' * ind)
                double_returns.remove(x['return'])
        elif 'action' in x:
            trace += '%sACTION(%s)\n' % (' ' * ind, x['action'])
    with open(file_name, mode='w', encoding='utf8') as fp:
        fp.write(trace)
