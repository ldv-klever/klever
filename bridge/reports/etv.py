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
from bridge.utils import ArchiveFileContent
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
    '__based', 'static', 'if', 'sizeof', 'double', 'typedef', 'unsigned', 'new', 'this', 'break', 'inline', 'explicit',
    'template', 'bool', 'for', 'private', 'default', 'else', 'const', '__pascal', 'delete', 'switch', 'continue', 'do',
    '__fastcall', 'union', 'extern', '__cdecl', 'friend', '__inline', 'int', '__virtual_inheritance', 'void', 'case',
    '__multiple_inheritance', 'enum', 'short', 'operator', '__asm', 'float', 'struct', 'cout', 'public', 'auto', 'long',
    'goto', '__single_inheritance', 'volatile', 'throw', 'namespace', 'protected', 'virtual', 'return', 'signed',
    'register', 'while', 'try', 'char', 'catch', 'cerr', 'cin'
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


class ParseErrorTrace:
    def __init__(self, data, include_assumptions, thread_id, triangles):
        self.cnt = 0
        self.has_main = False
        self.max_line_length = 5
        self.scope_stack = ['global']
        self.assume_scopes = {'global': []}
        self.scopes_to_show = set()
        self.scopes_to_hide = set()
        self.double_return = set()
        self.function_stack = []
        self.curr_file = None
        self.curr_action = None
        self.action_stack = []
        self.global_lines = []
        self.lines = []
        self.thread_id = thread_id
        self.files = list(data['files']) if 'files' in data else []
        self.actions = list(data['actions']) if 'actions' in data else []
        self.callback_actions = list(data['callback actions']) if 'callback actions' in data else []
        self.functions = list(data['funcs']) if 'funcs' in data else []
        self.include_assumptions = include_assumptions
        self.triangles = triangles

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
            'scope': self.scope_stack[-1],
            'type': 'normal'
        }
        if line is not None and 'assumption' not in edge and self.include_assumptions:
            line_data.update(self.__fill_assumptions())
        line_data.update(self.__add_assumptions(edge.get('assumption'), edge.get('assumption scope')))
        line_data.update(self.__update_line_data())
        if len(self.scope_stack) == 1 and all(x not in edge for x in ['return', 'enter']):
            if line_data['code'] is not None:
                self.global_lines.append(line_data)
            return
        elif len(self.scope_stack) == 1:
            self.scope_stack.append('scope__klever_main__0')
            self.scopes_to_show.add(self.scope_stack[-1])
            line_data['scope'] = self.scope_stack[-1]
        elif len(self.scope_stack) == 3 and self.scope_stack[-1] not in self.scopes_to_show:
            self.scopes_to_show.add(self.scope_stack[-1])
        if 'action' not in edge:
            line_data.update(self.__get_note(edge.get('note')))
            line_data.update(self.__get_warn(edge.get('warn')))
        if 'condition' in edge:
            line_data['code'] = self.__get_condition_code(line_data['code'])

        if 'action' in edge:
            if self.curr_action != 'action__%s' % edge['action']:
                if self.curr_action is None and edge['action'] in self.callback_actions:
                    self.__show_scope('callback action')
                if self.curr_action is not None:
                    self.lines.append(self.__return_from_function({
                        'code': None, 'line': None, 'scope': line_data['scope'], 'offset': line_data['offset']
                    }, False))
                    if edge['action'] in self.callback_actions:
                        self.__show_scope('callback action')
                enter_action_data = line_data.copy()
                if 'note' in enter_action_data:
                    del enter_action_data['note']
                if 'warn' in enter_action_data:
                    del enter_action_data['warn']
                enter_action_data.update(self.__update_line_data())
                enter_action_data['code'] = '<span class="%s">%s</span>' % (
                    'ETV_CallbackAction' if edge['action'] in self.callback_actions else 'ETV_Action',
                    self.actions[edge['action']]
                )
                enter_action_data.update(self.__enter_function('action__%s' % edge['action'], None))
                if edge['action'] in self.callback_actions:
                    enter_action_data['type'] = 'callback'
                self.lines.append(enter_action_data)
                line_data.update(self.__get_note(edge.get('note')))
                line_data.update(self.__get_warn(edge.get('warn')))
                line_data.update(self.__update_line_data())

        if 'enter' in edge:
            if 'action' not in edge and self.curr_action is not None:
                self.lines.append(self.__return_from_function({
                    'code': None, 'line': None, 'scope': line_data['scope'], 'offset': line_data['offset']
                }, False))
                line_data.update(self.__update_line_data())
            line_data.update(self.__enter_function(self.functions[edge['enter']], line_data['code']))
            if any(x in edge for x in ['note', 'warn']):
                self.scopes_to_hide.add(self.scope_stack[-1])
            if 'return' in edge:
                if edge['enter'] == edge['return']:
                    line_data = self.__return_from_function(line_data)
                else:
                    self.double_return.add(self.scope_stack[-2])
        elif 'return' in edge:
            for i in range(len(self.action_stack)):
                if self.action_stack[-1 - i] is None:
                    if self.functions[edge['return']] != self.function_stack[-1 - i]:
                        raise ValueError('Return from function "%s" without entering it (current scope is %s)' % (
                            self.functions[edge['return']], self.function_stack[-1 - i]
                        ))
                    break
            line_data = self.__return_from_function(line_data)
        elif 'action' not in edge and self.curr_action is not None:
            self.lines.append(self.__return_from_function({
                'code': None, 'line': None, 'scope': line_data['scope'], 'offset': line_data['offset']
            }, False))
            line_data.update(self.__update_line_data())
        if line_data['code'] is not None:
            self.lines.append(line_data)

    def __update_line_data(self):
        return {'offset': self.__curr_offset(), 'scope': self.scope_stack[-1]}

    def __enter_function(self, func, code):
        enter_data = {}
        if code is None:
            self.action_stack.append(func)
            self.curr_action = func
        elif len(self.action_stack) > 0:
            self.action_stack.append(None)
            self.curr_action = None

        self.cnt += 1
        self.scope_stack.append('scope__%s__%s__%s' % (func, str(self.cnt), self.thread_id))
        enter_data['hide_id'] = self.scope_stack[-1]
        if code is not None:
            enter_data['code'] = re.sub(
                '(^|\W)' + func + '(\W|$)', '\g<1><span class="ETV_Fname">' + func + '</span>\g<2>', code
            )
        enter_data['type'] = 'enter'
        if code is not None:
            enter_data['func'] = func
        self.function_stack.append(func)
        return enter_data

    def __return_from_function(self, line_data, return_from_func=True):
        if line_data['code'] is not None:
            self.lines.append(line_data)
        if len(self.action_stack) > 0:
            last_action = self.action_stack.pop()
            if last_action is not None and len(self.action_stack) > 1 and return_from_func:
                self.lines.append(self.__return_from_function({
                    'code': None, 'line': None, 'hide_id': None,
                    'offset': self.__curr_offset(), 'scope': line_data['scope']
                }, False))
        last_scope = self.scope_stack.pop()
        self.function_stack.pop()
        if len(self.scope_stack) == 0:
            raise ValueError('The error trace is corrupted')
        line_data = {
            'code': '<span class="ETV_DownHideLink"><i class="ui mini icon violet caret up link"></i></span>',
            'line': None, 'hide_id': None, 'offset': self.__curr_offset(), 'scope': last_scope, 'type': 'return'
        }
        if last_scope in self.scopes_to_show:
            line_data['code'] = '<span><i class="ui mini icon blue caret up"></i></span>'
            if not self.triangles:
                line_data['type'] = 'hidden-return'
        curr_scope = self.scope_stack[-1]
        if curr_scope in self.double_return:
            self.double_return.remove(curr_scope)
            line_data = self.__return_from_function(line_data)
        self.curr_action = self.action_stack[-1] if len(self.action_stack) > 0 else None
        return line_data

    def __show_scope(self, comment_type):
        if comment_type == 'note':
            if all(ss not in self.scopes_to_hide for ss in self.scope_stack):
                for ss in self.scope_stack[1:]:
                    if ss not in self.scopes_to_show:
                        self.scopes_to_show.add(ss)
        elif comment_type in ['warning', 'callback action']:
            for ss in self.scope_stack[1:]:
                if ss not in self.scopes_to_show:
                    self.scopes_to_show.add(ss)

    def __get_note(self, note):
        if note is None:
            return {}
        self.__show_scope('note')
        return {'note': note}

    def __get_warn(self, warn):
        if warn is None:
            return {}
        self.__show_scope('warning')
        return {'warning': warn}

    def __add_assumptions(self, assumption, assumption_scope):
        assumption_data = {}
        if assumption is None:
            return assumption_data
        if len(self.scope_stack) == 1:
            self.scope_stack.append('scope__klever_main__0')
            self.scopes_to_show.add(self.scope_stack[-1])
        if not self.include_assumptions:
            return assumption_data
        if assumption_scope is None:
            ass_scope = 'global'
        else:
            ass_scope = self.scope_stack[-1]

        if ass_scope not in self.assume_scopes:
            self.assume_scopes[ass_scope] = []
        curr_assumes = []
        for assume in assumption.split(';'):
            if len(assume) == 0:
                continue
            self.assume_scopes[ass_scope].append(assume)
            curr_assumes.append('%s_%s' % (ass_scope, str(len(self.assume_scopes[ass_scope]) - 1)))
        assumption_data.update(self.__fill_assumptions(curr_assumes))
        return assumption_data

    def __fill_assumptions(self, current_assumptions=None):
        assumptions = []
        if self.scope_stack[-1] in self.assume_scopes:
            for j in range(0, len(self.assume_scopes[self.scope_stack[-1]])):
                assume_id = '%s_%s' % (self.scope_stack[-1], j)
                if isinstance(current_assumptions, list) and assume_id in current_assumptions:
                    continue
                assumptions.append(assume_id)
        return {
            'assumptions': ';'.join(reversed(assumptions)),
            'current_assumptions': ';'.join(current_assumptions) if isinstance(current_assumptions, list) else None
        }

    def __get_condition_code(self, code):
        self.ccc = 0
        m = re.match('^\s*\[(.*)\]\s*$', code)
        if m is not None:
            code = m.group(1)
        return '<span class="ETV_CondAss">assume(</span>' + str(code) + '<span class="ETV_CondAss">);</span>'

    def __curr_offset(self):
        if len(self.scope_stack) < 2:
            return ' '
        return ((len(self.scope_stack) - 2) * TAB_LENGTH + 1) * ' '

    def finish_error_lines(self, thread, thread_id):
        while len(self.scope_stack) > 2:
            poped_scope = self.scope_stack.pop()
            if self.triangles:
                if poped_scope in self.scopes_to_show:
                    ret_code = '<span><i class="ui mini icon blue caret up"></i></span>'
                else:
                    ret_code = '<span class="ETV_DownHideLink"><i class="ui mini icon violet caret up link"></i></span>'
                end_triangle = {
                    'code': ret_code, 'line': None, 'hide_id': None,
                    'offset': self.__curr_offset(), 'scope': poped_scope, 'type': 'return'
                }
            else:
                end_triangle = {
                    'code': None, 'line': None, 'hide_id': None, 'offset': '',
                    'scope': poped_scope, 'type': 'hidden-return'
                }
            self.lines.append(end_triangle)
        if len(self.global_lines) > 0:
            self.lines = [{
                'code': '<span class="ETV_GlobalExpander">Global variable declarations</span>',
                'line': None, 'file': None, 'offset': ' ', 'hide_id': 'global_scope',
                'scope': 'global', 'type': 'normal'
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
            # other_line_offset = '\n  ' + self.lines[i]['offset'] + ' ' * self.max_line_length
            # self.lines[i]['code'] = other_line_offset.join(self.lines[i]['code'].split('\n'))
            self.lines[i]['code'] = self.__parse_code(self.lines[i]['code'])

            if self.lines[i]['scope'] != 'scope__klever_main__0':
                if self.lines[i]['type'] == 'normal' and self.lines[i]['scope'] in self.scopes_to_show:
                    self.lines[i]['type'] = 'eye-control'
                elif self.lines[i]['type'] == 'enter' and self.lines[i]['hide_id'] not in self.scopes_to_show:
                    self.lines[i]['type'] = 'eye-control'
                    if 'func' in self.lines[i]:
                        del self.lines[i]['func']
            a = 'warning' in self.lines[i]
            b = 'note' in self.lines[i]
            c = self.lines[i]['scope'] not in self.scopes_to_show
            d = 'hide_id' not in self.lines[i] or self.lines[i]['hide_id'] is None
            e = 'hide_id' in self.lines[i] and self.lines[i]['hide_id'] is not None \
                and self.lines[i]['hide_id'] not in self.scopes_to_show
            f = self.lines[i]['type'] == 'eye-control'
            if a or b and (d or e or c) or not a and not b and c and (d or e) or f:
                self.lines[i]['hidden'] = True
                if e:
                    self.lines[i]['collapsed'] = True
            elif e:
                self.lines[i]['collapsed'] = True
            if a or b:
                self.lines[i]['commented'] = True
                self.lines[i]['note_line_offset'] = ' ' * self.max_line_length
            if b and c:
                self.lines[i]['note_hidden'] = True
        if len(self.global_lines) > 0:
            self.lines.append({'scope': 'ETV_End_of_trace', 'thread_id': thread_id})

    def __wrap_code(self, code, code_type):
        self.ccc = 0
        if code_type in SOURCE_CLASSES:
            return '<span class="%s">%s</span>' % (SOURCE_CLASSES[code_type], code)
        return code

    def __parse_code(self, code):
        m = re.match('^(.*?)(<span.*?</span>)(.*)$', code)
        if m is not None:
            return "%s%s%s" % (
                self.__parse_code(m.group(1)),
                m.group(2),
                self.__parse_code(m.group(3))
            )
        m = re.match('^(.*?)<(.*)$', code)
        while m is not None:
            code = m.group(1) + '&lt;' + m.group(2)
            m = re.match('^(.*?)<(.*)$', code)
        m = re.match('^(.*?)>(.*)$', code)
        while m is not None:
            code = m.group(1) + '&gt;' + m.group(2)
            m = re.match('^(.*?)>(.*)$', code)
        m = re.match('^(.*?)(/\*.*?\*/)(.*)$', code)
        if m is not None:
            return "%s%s%s" % (
                self.__parse_code(m.group(1)),
                self.__wrap_code(m.group(2), 'comment'),
                self.__parse_code(m.group(3))
            )
        m = re.match('^(.*?)([\'\"])(.*)$', code)
        if m is not None:
            m2 = re.match('^(.*?)%s(.*)$' % m.group(2), m.group(3))
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


class GetETV(object):
    def __init__(self, error_trace, user):
        self.include_assumptions = user.extended.assumptions
        self.triangles = user.extended.triangles
        self.data = json.loads(error_trace)
        self.err_trace_nodes = get_error_trace_nodes(self.data)
        self.threads = []
        self.html_trace, self.assumes = self.__html_trace()
        self.attributes = []

    def __get_attributes(self):
        # TODO: return list of error trace attributes like [<attr name>, <attr value>]. Ignore 'programfile'.
        pass

    def __html_trace(self):
        for n in self.err_trace_nodes:
            if 'thread' not in self.data['edges'][n]:
                # self.data['edges'][n]['thread'] = 'fake'
                raise ValueError('All error trace edges should have thread')
            if self.data['edges'][n]['thread'] not in self.threads:
                self.threads.append(self.data['edges'][n]['thread'])
        return self.__add_thread_lines(0)

    def __add_thread_lines(self, i):
        parsed_trace = ParseErrorTrace(self.data, self.include_assumptions, i, self.triangles)
        prev_t = i
        trace_assumes = []
        for n in self.err_trace_nodes:
            edge_data = self.data['edges'][n]
            curr_t = self.threads.index(edge_data['thread'])
            if prev_t == i and curr_t != i and curr_t > i:
                (new_lines, new_assumes) = self.__add_thread_lines(curr_t)
                parsed_trace.lines.extend(new_lines)
                trace_assumes.extend(new_assumes)
            prev_t = curr_t
            if edge_data['thread'] == self.threads[i]:
                parsed_trace.add_line(edge_data)
        parsed_trace.finish_error_lines(self.__get_thread(i), i)

        for sc in parsed_trace.assume_scopes:
            as_cnt = 0
            for a in parsed_trace.assume_scopes[sc]:
                trace_assumes.append(['%s_%s' % (sc, as_cnt), a])
                as_cnt += 1
        return parsed_trace.lines, trace_assumes

    def __get_thread(self, thread):
        return '%s<span style="background-color:%s;"> </span>%s' % (
            ' ' * thread, THREAD_COLORS[thread % len(THREAD_COLORS)], ' ' * (len(self.threads) - thread - 1)
        )


class GetSource(object):
    def __init__(self, report_id, file_name):
        self.error = None
        self.report = self.__get_report(report_id)
        if self.error is not None:
            return
        self.is_comment = False
        self.is_text = False
        self.text_quote = None
        self.data = self.__get_source(file_name)

    def __get_report(self, report_id):
        try:
            return ReportUnsafe.objects.get(pk=int(report_id))
        except ObjectDoesNotExist:
            self.error = _("Could not find the corresponding unsafe")
            return None
        except ValueError:
            self.error = _("Unknown error")
            return None

    def __get_source(self, file_name):
        data = ''
        if file_name.startswith('/'):
            file_name = file_name[1:]
        try:
            source_content = ArchiveFileContent(self.report, file_name).content.decode('utf8')
        except Exception as e:
            self.error = _("Error while extracting source from archive: %(error)s") % {'error': str(e)}
            return None
        cnt = 1
        lines = source_content.split('\n')
        for line in lines:
            line = line.replace('\t', ' ' * TAB_LENGTH)
            line_num = ' ' * (len(str(len(lines))) - len(str(cnt))) + str(cnt)
            data += '<span>%s %s</span><br>' % (
                self.__wrap_line(line_num, 'line', 'ETVSrcL_%s' % cnt), self.__parse_line(line)
            )
            cnt += 1
        return data

    def parse_line(self, line):
        return self.__parse_line(line)

    def __parse_line(self, line):
        m = re.match('(.*?)<(.*)', line)
        while m is not None:
            line = m.group(1) + '&lt;' + m.group(2)
            m = re.match('(.*?)<(.*)', line)
        m = re.match('(.*?)>(.*)', line)
        while m is not None:
            line = m.group(1) + '&gt;' + m.group(2)
            m = re.match('(.*?)>(.*)', line)

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

        m = re.match('(.*?)"(.*)', line)
        if m is not None:
            new_line = self.__parse_line(m.group(1))
            self.text_quote = '"'
            before, after = self.__parse_text(m.group(2))
            new_line += self.__wrap_line('"' + before, 'text')
            if after is None:
                self.is_text = True
                return new_line
            self.is_text = False
            return new_line + self.__parse_line(after)
        m = re.match("(.*?)'(.*)", line)
        if m is not None:
            new_line = self.__parse_line(m.group(1))
            self.text_quote = "'"
            before, after = self.__parse_text(m.group(2))
            new_line += self.__wrap_line("'" + before, 'text')
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
        self.ccc = 0
        if text_type not in SOURCE_CLASSES:
            return line
        if line_id is not None:
            return '<span id="%s" class="%s">%s</span>' % (line_id, SOURCE_CLASSES[text_type], line)
        return '<span class="%s">%s</span>' % (SOURCE_CLASSES[text_type], line)


def is_tag(tag, name):
    return bool(re.match('^({.*})*' + name + '$', tag))


# Returns json serializable data in case of success or Exception
def error_trace_callstack(error_trace):
    data = json.loads(error_trace)
    call_stack = []
    for edge_id in get_error_trace_nodes(data):
        edge_data = data['edges'][edge_id]
        if 'enter' in edge_data:
            call_stack.append(data['funcs'][edge_data['enter']])
        if 'return' in edge_data:
            call_stack.pop()
        if 'warn' in edge_data:
            break
    return call_stack


# Some constants for internal representation of error traces.
_CALL = 'CALL'
_RET = 'RET'


# Extracts model functions in specific format with some heuristics.
def error_trace_model_functions(error_trace):
    data = json.loads(error_trace)

    # TODO: Very bad method.
    err_trace_nodes = get_error_trace_nodes(data)
    model_funcs = set()
    for edge_id in err_trace_nodes:
        edge_data = data['edges'][edge_id]
        if 'enter' in edge_data:
            res = re.search(r'ldv_linux_(.*)', data['funcs'][edge_data['enter']])
            if res:
                model_funcs.add(res.group(1))
    call_tree = [{'entry_point': _CALL}]
    for edge_id in err_trace_nodes:
        edge_data = data['edges'][edge_id]
        if 'enter' in edge_data:
            call_tree.append({data['funcs'][edge_data['enter']]: _CALL})
        if 'return' in edge_data:
            is_done = False
            for mf in model_funcs:
                if data['funcs'][edge_data['return']].__contains__(mf):
                    call_tree.append({data['funcs'][edge_data['return']]: _CALL})
                    is_done = True
            if not is_done:
                is_save = False
                sublist = []
                for elem in reversed(call_tree):
                    sublist.append(elem)
                    func_name = list(elem.keys()).__getitem__(0)
                    for mf in model_funcs:
                        if func_name.__contains__(mf):
                            is_save = True
                    if elem == {data['funcs'][edge_data['return']]: _CALL}:
                        sublist.reverse()
                        break
                if is_save:
                    call_tree.append({data['funcs'][edge_data['return']]: _RET})
                else:
                    call_tree = call_tree[:-sublist.__len__()]

    # Maybe for debug print?
    level = 0
    for elem in call_tree:
        func_name, op = list(elem.items())[0]
        spaces = ""
        for i in range(0, level):
            spaces += " "
        if op == _CALL:
            level += 1
            print(spaces + func_name)
        else:
            level -= 1

    return call_tree


class ErrorTraceCallstackTree(object):
    def __init__(self, error_trace):
        self.data = json.loads(error_trace)
        self.trace = self.__get_tree(get_error_trace_nodes(self.data))

    def __get_tree(self, edge_trace):
        tree = []
        call_level = 0
        call_stack = []
        model_functions = []
        for edge_id in edge_trace:
            edge_data = self.data['edges'][edge_id]
            if 'enter' in edge_data:
                call_stack.append(self.data['funcs'][edge_data['enter']])
                call_level += 1
                while len(tree) <= call_level:
                    tree.append([])
                if 'note' in edge_data:
                    model_functions.append(self.data['funcs'][edge_data['enter']])
                tree[call_level].append({
                    'name': self.data['funcs'][edge_data['enter']],
                    'parent': call_stack[-2] if len(call_stack) > 1 else None
                })
            if 'return' in edge_data:
                call_stack.pop()
                call_level -= 1

        def not_model_leaf(ii, jj):
            if tree[ii][jj]['name'] in model_functions:
                return False
            elif len(tree) > ii + 1:
                for ch_j in range(0, len(tree[ii + 1])):
                    if tree[ii + 1][ch_j]['parent'] == tree[ii][jj]['name']:
                        return False
            return True

        for i in reversed(range(0, len(tree))):
            new_level = []
            for j in range(0, len(tree[i])):
                if not not_model_leaf(i, j):
                    new_level.append(tree[i][j])
            if len(new_level) == 0:
                del tree[i]
            else:
                tree[i] = new_level
        just_names = []
        for level in tree:
            new_level = []
            for f_data in level:
                new_level.append(f_data['name'])
            just_names.append(' '.join(sorted(str(x) for x in new_level)))
        return just_names


class Forest:
    def __init__(self):
        self._cnt = 1
        self._level = 0
        self.call_stack = []
        self._forest = []
        self._model_functions = []

    def scope(self):
        return self.call_stack[-1] if len(self.call_stack) > 0 else None

    def enter_func(self, func_name, is_model=False):
        while len(self._forest) <= self._level:
            self._forest.append([])
        new_scope = '%s__%s' % (self._cnt, func_name)
        self._forest[self._level].append({
            'name': new_scope,
            'parent': self.scope()
        })
        if is_model:
            self._model_functions.append(new_scope)
        self.call_stack.append(new_scope)
        self._level += 1
        self._cnt += 1

    def return_from_func(self):
        self._level -= 1
        self.call_stack.pop()

    def get_forest(self):
        self.__exclude_functions()
        if len(self._forest) == 0:
            return None
        final_forest = self.__convert_forest_3()
        self.__init__()
        return final_forest

    def __not_model_leaf(self, i, j):
        if self._forest[i][j]['name'] in self._model_functions:
            return False
        elif len(self._forest) > i + 1:
            for ch_j in range(0, len(self._forest[i + 1])):
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

    def __get_children_1(self, lvl, j):
        children = []
        if len(self._forest) > lvl + 1:
            for ch_j in range(0, len(self._forest[lvl + 1])):
                if self._forest[lvl + 1][ch_j]['parent'] == self._forest[lvl][j]['name']:
                    children.append([
                        re.sub('^\d+__', '', self._forest[lvl + 1][ch_j]['name']),
                        self.__get_children_1(lvl + 1, ch_j)
                    ])
        return children

    def __get_children_2(self, lvl, j):
        children = ''
        if len(self._forest) > lvl + 1:
            for ch_j in range(0, len(self._forest[lvl + 1])):
                if self._forest[lvl + 1][ch_j]['parent'] == self._forest[lvl][j]['name']:
                    children += '%s{%s}' % (
                        re.sub('^\d+__', '', self._forest[lvl + 1][ch_j]['name']),
                        self.__get_children_2(lvl + 1, ch_j)
                    )
        return children

    def __get_children_3(self, lvl, j):
        children = []
        if len(self._forest) > lvl + 1:
            for ch_j in range(0, len(self._forest[lvl + 1])):
                if self._forest[lvl + 1][ch_j]['parent'] == self._forest[lvl][j]['name']:
                    children.append({
                        re.sub('^\d+__', '', self._forest[lvl + 1][ch_j]['name']): self.__get_children_3(lvl + 1, ch_j)
                    })
        return children

    def __convert_forest_1(self):
        final_forest = []
        for j in range(len(self._forest[0])):
            final_forest.append([
                re.sub('^\d+__', '', self._forest[0][j]['name']),
                self.__get_children_1(0, j)
            ])
        return final_forest

    def __convert_forest_2(self):
        final_forest = ''
        for j in range(len(self._forest[0])):
            final_forest += '%s{%s}' % (
                re.sub('^\d+__', '', self._forest[0][j]['name']),
                self.__get_children_2(0, j)
            )
        return final_forest

    def __convert_forest_3(self):
        final_forest = []
        for j in range(len(self._forest[0])):
            final_forest.append({
                re.sub('^\d+__', '', self._forest[0][j]['name']): self.__get_children_3(0, j)
            })
        return final_forest


class ErrorTraceForests:
    def __init__(self, error_trace):
        self.data = json.loads(error_trace)
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
        for t in thread_order:
            forests.extend(self.__get_thread_forests(threads[t]))
        return forests

    def __get_thread_forests(self, edge_trace):
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
                if 'enter' in edge_data:
                    forest.enter_func(self.data['funcs'][edge_data['enter']], 'note' in edge_data)
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
        if collect_names:
            curr_forest = forest.get_forest()
            if curr_forest is not None:
                forests.append(curr_forest)
        return forests
