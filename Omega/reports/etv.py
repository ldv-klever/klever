import re
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import ugettext_lazy as _
from Omega.utils import print_err
from reports.models import ReportUnsafe
from reports.graphml_parser import GraphMLParser


TAB_LENGTH = 4
SOURCE_CLASSES = {
    'comment': "ETVSrcC",
    'number': "ETVSrcN",
    'line': "ETVSrcL",
    'text': "ETVSrcT",
    'key1': "ETVSrcI",
    'key2': "ETVSrcO"
}

KEY1_WORDS = [
    '#ifndef', '#elif', '#undef', '#ifdef', '#include', '#else', '#define',
    '#if', '#pragma', '#error', '#endif', '#line'
]

KEY2_WORDS = [
    '__based', 'static', 'if', 'sizeof', 'double', 'typedef', 'unsigned', 'new',
    'this', 'break', 'inline', 'explicit', 'template', 'bool', 'for', 'private',
    'default', 'else', 'const', '__pascal', 'delete', 'class', 'continue', 'do',
    '__fastcall', 'union', 'extern', '__cdecl', 'friend', '__inline', 'int',
    '__virtual_inheritance', 'void', 'case', '__multiple_inheritance', 'enum',
    'short', 'operator', '__asm', 'float', 'struct', 'cout', 'public', 'auto',
    'long', 'goto', '__single_inheritance', 'volatile', 'throw', 'namespace',
    'protected', 'virtual', 'return', 'signed', 'register', 'while', 'try',
    'switch', 'char', 'catch', 'cerr', 'cin'
]


class GetETV(object):
    def __init__(self, graphml_file):
        self.error = None

        self.g = self.__parse_graph(graphml_file)
        if self.error is not None:
            return

        self.traces = self.__get_traces()
        if self.error is not None:
            return

        if len(self.traces) == 0:
            self.error = _('Wrong error trace file format')
            return
        elif len(self.traces) > 2:
            self.error = _('Error trace with more than two '
                           'error pathes are not supported')
            return

        self.html_traces = []
        self.assumes = []

        self._cnt = 0
        for trace in self.traces:
            self._cnt += 1
            self.__html_trace(trace)
        self.attributes = self.__get_attributes()

    def __get_attributes(self):
        attrs = []
        for a in self.g.attributes():
            if a.name != 'programfile':
                attrs.append([a.name, a.value])
        return attrs

    def __parse_graph(self, graphml_file):
        try:
            return GraphMLParser().parse(graphml_file)
        except Exception as e:
            print_err(e)
            self.error = _('Wrong error trace file format')
        return None

    def __get_traces(self):
        traces = []
        if self.g.set_root_by_attribute('true', 'isEntryNode') is None:
            self.error = _('Trace entry was not found')
            return traces

        for path in self.g.bfs():
            if 'isViolationNode' in path[-1].attr and path[-1]['isViolationNode'] == 'true':
                traces.append(path)
        return traces

    def __html_trace(self, node_trace):
        lines_data = []

        edge_trace = []
        prev_node = node_trace[0]
        for n in node_trace[1:]:
            e = self.g.edge(prev_node, n)
            if e is not None:
                edge_trace.append(e)
            prev_node = n

        max_line_length = 1
        for n in edge_trace:
            if 'startline' in n.attr:
                if len(n['startline']) > max_line_length:
                    max_line_length = len(n['startline'])

        cnt = 0
        file = None
        has_main = False
        curr_offset = 1
        scope_stack = ['global']
        assume_scopes = {'global': []}
        scopes_to_show = []
        scopes_to_hide = []

        def add_fake_line(fake_code, hide_id=None):
            lines_data.append({
                'code': fake_code,
                'line': None,
                'line_offset': ' ' * max_line_length,
                'offset': curr_offset * ' ',
                'class': scope_stack[-1],
                'hide_id': hide_id
            })

        def fill_assumptions(current_assumptions=None):
            assumptions = []
            if scope_stack[-1] in assume_scopes:
                for j in range(0, len(assume_scopes[scope_stack[-1]])):
                    assume_id = '%s_%s' % (scope_stack[-1], j)
                    if isinstance(current_assumptions, list) and assume_id in current_assumptions:
                        continue
                    assumptions.append(assume_id)
            return {
                'assumptions': ';'.join(reversed(assumptions)),
                'current_assumptions': ';'.join(current_assumptions) if isinstance(current_assumptions, list) else None
            }

        lines_data.append({
            'code': '<span class="ETV_GlobalExpander">Global initialization</span>',
            'line': None,
            'line_offset': ' ' * max_line_length,
            'offset': curr_offset * ' ',
            'hide_id': 'global_scope'
        })

        for n in edge_trace:
            line = n.attr.get('startline', None)
            if line is None:
                line_offset = max_line_length
            else:
                line = line.value
                line_offset = max_line_length - len(line)
            if 'sourcecode' in n.attr:
                code = n.attr['sourcecode'].value
            else:
                code = ''
            line_data = {
                'line_offset': ' ' * line_offset,
                'line': line,
                'code': code,
                'offset': curr_offset * ' ',
                'class': scope_stack[-1]
            }
            if 'originFileName' in n.attr:
                file = n['originFileName']
            if file is None:
                line_data['line'] = None
            line_data['file'] = file
            if line_data['line'] is not None and 'assumption' not in n.attr:
                line_data.update(fill_assumptions())
            if 'note' in n.attr:
                line_data['note'] = n['note']
                if all(ss not in scopes_to_hide for ss in scope_stack) and scope_stack[-1] not in scopes_to_show:
                    scopes_to_show.append(scope_stack[-1])
            if 'warning' in n.attr:
                line_data['warning'] = n['warning']
                for ss in scope_stack[1:]:
                    if ss not in scopes_to_show:
                        scopes_to_show.append(ss)

            if 'assumption' in n.attr:
                if not has_main and 'assumption.scope' in n.attr and n['assumption.scope'] == 'main':
                    cnt += 1
                    # TODO: remove comments, refactoring
                    main_id = 'scope__main__%s' % str(cnt)
                    # scope_stack.append('')
                    # add_fake_line('<span class="ETV_Fname">main</span>();', main_id)
                    # scope_stack.pop()
                    scope_stack.append(main_id)
                    scopes_to_show.append(scope_stack[-1])
                    add_fake_line('main() {')
                    curr_offset += TAB_LENGTH
                    line_data['offset'] = ' ' * curr_offset
                    line_data['class'] = scope_stack[-1]
                    has_main = True
                if 'assumption.scope' in n.attr:
                    ass_scope = scope_stack[-1]
                else:
                    ass_scope = 'global'

                if ass_scope not in assume_scopes:
                    assume_scopes[ass_scope] = []
                curr_assumes = []
                for assume in n['assumption'].split(';'):
                    if len(assume) == 0:
                        continue
                    assume_scopes[ass_scope].append(assume)
                    curr_assumes.append('%s_%s' % (ass_scope, str(len(assume_scopes[ass_scope]) - 1)))
                line_data.update(fill_assumptions(curr_assumes))
                lines_data.append(line_data)
            elif 'enterFunction' in n.attr:
                cnt += 1
                scope_stack.append('scope__%s__%s' % (n['enterFunction'], str(cnt)))
                line_data['hide_id'] = scope_stack[-1]
                if 'note' in n.attr or 'warning' in n.attr:
                    scopes_to_hide.append(scope_stack[-1])
                line_data['code'] = re.sub(
                    '(^|\W)' + n['enterFunction'] + '(\W|$)',
                    '\g<1><span class="ETV_Fname">' + n['enterFunction'] + '</span>\g<2>',
                    line_data['code']
                )
                lines_data.append(line_data)
                add_fake_line('{')
                curr_offset += TAB_LENGTH
            elif 'returnFromFunction' in n.attr:
                lines_data.append(line_data)
                if curr_offset >= TAB_LENGTH:
                    curr_offset -= TAB_LENGTH
                add_fake_line('}')
                try:
                    scope_stack.pop()
                    if len(scope_stack) == 0:
                        self.error = _('Error trace is corrupted')
                        return None
                except IndexError:
                    self.error = _('Error trace is corrupted')
                    return None
            elif 'control' in n.attr:
                line_data['code'] = '<span class="ETV_CondAss">assume(</span>' + \
                                    str(line_data['code']) + \
                                    ' == %s<span class="ETV_CondAss">);</span>' % (
                    'True' if n['control'] == 'condition-true' else 'False'
                )
                lines_data.append(line_data)
            else:
                lines_data.append(line_data)

        while len(scope_stack) > 1:
            if curr_offset >= TAB_LENGTH:
                curr_offset -= TAB_LENGTH
            add_fake_line('}')
            scope_stack.pop()
        for i in range(0, len(lines_data)):
            if 'class' not in lines_data[i]:
                continue
            if lines_data[i]['class'] != 'global':
                print_line = 'Scope: ' + lines_data[i]['class'] + '; '
                if 'hide_id' in lines_data[i]:
                    if lines_data[i]['hide_id'] is not None:
                        print_line += 'Hide id: ' + lines_data[i]['hide_id'] + '; '
                    else:
                        print_line += 'Hide is None!!!; '
                if 'note' in lines_data[i]:
                    print_line += 'Has note; '
                if 'warning' in lines_data[i]:
                    print_line += 'Has warning; '
                print_line += 'CODE: "%s"' % lines_data[i]['code']
                print(print_line)
            a = 'warning' in lines_data[i]
            b = 'note' in lines_data[i]
            c = lines_data[i]['class'] not in scopes_to_show
            d = 'hide_id' not in lines_data[i] or lines_data[i]['hide_id'] is None
            e = 'hide_id' in lines_data[i] and lines_data[i]['hide_id'] is not None \
                and lines_data[i]['hide_id'] not in scopes_to_show
            if a or b and (d or e or c) or not a and not b and c and (d or e):
                lines_data[i]['hidden'] = True
                if e:
                    lines_data[i]['collapsed'] = True
            elif e:
                lines_data[i]['collapsed'] = True
            if a or b:
                lines_data[i]['commented'] = True
            if b and c:
                lines_data[i]['note_hidden'] = True
        lines_data.append({'class': 'ETV_End_of_trace'})
        self.html_traces.append(lines_data)

        trace_assumes = []
        for sc in assume_scopes:
            as_cnt = 0
            for a in assume_scopes[sc]:
                trace_assumes.append(['%s_%s' % (sc, as_cnt), a])
                as_cnt += 1
        self.assumes.append(trace_assumes)


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
            self.error = _("Report was not found")
            return None
        except ValueError:
            self.error = _("Unknown error")
            return None

    def __get_source(self, file_name):
        data = ''
        try:
            src = self.report.files.get(name=file_name)
        except ObjectDoesNotExist:
            self.error = _("Source code was not found")
            return
        cnt = 1
        lines = src.file.file.read().decode('utf8').split('\n')
        for line in lines:
            line = line.replace('\t', ' ' * TAB_LENGTH)
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
        if m is not None:
            new_line = self.__parse_line(m.group(1))
            self.is_comment = True
            new_line += self.__parse_line('/*' + m.group(2))
            return new_line
        m = re.match('(.*?)//(.*)', line)
        if m is not None:
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
