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

import json
from collections import OrderedDict
from urllib.parse import unquote

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import ugettext_lazy as _
from django.utils.functional import cached_property

from bridge.utils import ArchiveFileContent, BridgeException

from reports.models import ReportUnsafe, ReportComponentLeaf

ETV_FORMAT = 1

HIGHLIGHT_CLASSES = {
    'number': 'ETVNumber',
    'comment': 'ETVComment',
    'text': 'ETVText',
    'key1': 'ETVKey1',
    'key2': 'ETVKey2',
    'function': 'ETVKey3'
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

# TODO: remove
KEY1_WORDS = [
    '#ifndef', '#elif', '#undef', '#ifdef', '#include', '#else', '#define',
    '#if', '#pragma', '#error', '#endif', '#line'
]

# TODO: remove
KEY2_WORDS = [
    'static', 'if', 'sizeof', 'double', 'typedef', 'unsigned', 'break', 'inline', 'for', 'default', 'else', 'const',
    'switch', 'continue', 'do', 'union', 'extern', 'int', 'void', 'case', 'enum', 'short', 'float', 'struct', 'auto',
    'long', 'goto', 'volatile', 'return', 'signed', 'register', 'while', 'char'
]

THREAD_COLORS = [
    '#5f54cb', '#85ff47', '#69c8ff', '#ff5de5', '#dfa720', '#0b67bf', '#fa92ff', '#57bfa8', '#bf425a', '#7d909e'
]


class SourceLine:
    ref_to_class = 'ETVRefToLink'
    ref_from_class = 'ETVRefFromLink'

    def __init__(self, source, highlights=None, references_to=None, references_from=None):
        self._source = source
        self._source_len = len(source)
        self._highlights = self.__get_highlights(highlights)
        self.references_data = {}
        self._references = self.__get_references(references_to, references_from)
        self.html_code = self.__to_html()

    def __get_highlights(self, highlights):
        if not highlights:
            highlights = []

        h_dict = OrderedDict()
        prev_end = 0
        for h_name, start, end in sorted(highlights, key=lambda x: (x[1], x[2])):
            assert isinstance(start, int) and isinstance(end, int)
            assert prev_end <= start < end
            assert h_name in HIGHLIGHT_CLASSES
            if prev_end < start:
                h_dict[(prev_end, start)] = None
            h_dict[(start, end)] = HIGHLIGHT_CLASSES[h_name]
            prev_end = end
        if prev_end < self._source_len:
            h_dict[(prev_end, self._source_len)] = None
        elif prev_end > self._source_len:
            raise ValueError('Sources length is not enough to highlight code')
        return h_dict

    def __get_references(self, references_to, references_from):
        if not references_to:
            references_to = []
        if not references_from:
            references_from = []
        references = []
        for (line_num, ref_start, ref_end), (file_ind, file_line) in references_to:
            references.append([ref_start, ref_end, {
                'span_class': self.ref_to_class,
                'span_data': {'file': file_ind, 'line': file_line}
            }])

        for ref_data in references_from:
            line_num, ref_start, ref_end = ref_data[0]
            ref_from_id = 'reflink_{}_{}_{}'.format(*ref_data[0])
            references.append([ref_start, ref_end, {
                'span_class': self.ref_from_class,
                'span_data': {'id': ref_from_id}
            }])

            self.references_data[ref_from_id] = []
            for file_ind, file_lines in ref_data[1:]:
                for file_line in file_lines:
                    self.references_data[ref_from_id].append((file_ind, file_line))
        references.sort(key=lambda x: (x[0], x[1]), reverse=True)

        prev_end = 0
        for ref_start, ref_end, span_kwargs in references:
            assert prev_end <= ref_start < ref_end
            prev_end = ref_end
        assert prev_end <= self._source_len
        return references

    def __get_code(self, start, end):
        code = self._source[start:end]
        code_list = []
        for ref_start, ref_end, span_kwargs in self._references:
            if start <= ref_end < end:
                ref_end_rel = ref_end - start
                code_list.append(self.__fix_for_html(code[ref_end_rel:]))
                code_list.append(self._span_close)
                code = code[:ref_end_rel]
            if start <= ref_start < end:
                ref_start_rel = ref_start - start
                code_list.append(self.__fix_for_html(code[ref_start_rel:]))
                code_list.append(self.__span_open(**span_kwargs))
                code = code[:ref_start_rel]
        code_list.append(self.__fix_for_html(code))
        return ''.join(reversed(code_list))

    def __to_html(self):
        result = ''
        for start, end in reversed(self._highlights):
            code = self.__get_code(start, end)
            code_class = self._highlights[(start, end)]
            if code_class is not None:
                code = '{}{}{}'.format(self.__span_open(span_class=code_class), code, self._span_close)
            result = code + result
        return result

    def __fix_for_html(self, code):
        return code.replace('\t', ' ' * TAB_LENGTH).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    def __span_open(self, span_class=None, span_data=None):
        span_str = '<span'
        if span_class:
            span_str += ' class="{}"'.format(span_class)
        if span_data:
            for data_key, data_value in span_data.items():
                span_str += ' data-{}="{}"'.format(
                    data_key, data_value if data_value is not None else 'null'
                )
        span_str += '>'
        return span_str

    @property
    def _span_close(self):
        return '</span>'


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
        src_line = SourceLine(node['source'], highlights=node.get('highlight', []))
        return src_line.html_code

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
                raise BridgeException(_("Error while extracting source indexing: %(error)s") % {'error': str(e)})
            if index_res.content is not None:
                index_data = json.loads(index_res.content.decode('utf8'))
                if index_data.get('format') != ETV_FORMAT:
                    raise BridgeException(_('Sources indexing format is not supported'))
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
                highlights.setdefault(line_num, [])
                highlights[line_num].append((h_name, start, end))

        references_to = {}
        if index_data and 'referencesto' in index_data:
            for ref_data in index_data['referencesto']:
                line_num = ref_data[0][0]
                references_to.setdefault(line_num, [])
                references_to[line_num].append(ref_data)

        references_from = {}
        if index_data and 'referencesfrom' in index_data:
            for ref_data in index_data['referencesfrom']:
                line_num = ref_data[0][0]
                references_from.setdefault(line_num, [])
                references_from[line_num].append(ref_data)

        references_data = {}

        data = ''
        cnt = 1
        lines = file_content.split('\n')
        total_lines_len = len(str(len(lines)))
        for code in lines:
            src_line = SourceLine(
                code, highlights=highlights.get(cnt),
                references_to=references_to.get(cnt),
                references_from=references_from.get(cnt)
            )
            references_data.update(src_line.references_data)
            data += '<span><span id="{line_id}" class="{line_class}">{prefix}{number}</span> {code}</span><br>'.format(
                line_id='ETVSrcL_{}'.format(cnt), line_class=SOURCE_CLASSES['line'],
                prefix=' ' * (total_lines_len - len(str(cnt))), number=cnt,
                code=src_line.html_code
            )
            cnt += 1

        for ref_id, ref_links in references_data.items():
            data += '<span id="{}" hidden>'.format(ref_id)
            for ref_file_ind, ref_file_line in ref_links:
                data += '<span class="ETVRefLink" data-file={file} data-line={line}>{file}: {line}</span><br>'.format(
                    file=index_data['source files'][ref_file_ind], line=ref_file_line
                )
            data += '</span>'
        if references_data:
            data += '<div id="source_references_links" class="ui small popup"></div>'

        if index_data and 'source files' in index_data:
            for file_ind, file_name in enumerate(index_data['source files']):
                data += '<span id="source_file_{}" hidden>{}</span>'.format(file_ind, file_name)
        return data
