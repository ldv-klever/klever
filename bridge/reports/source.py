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

import hashlib
import io
import json
from collections import OrderedDict
from urllib.parse import unquote

from django.core.files import File
from django.db import transaction
from django.template import loader
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _, get_language
from django.utils.functional import cached_property

from bridge.vars import ETV_FORMAT
from bridge.utils import ArchiveFileContent, BridgeException, logger

from reports.models import ReportComponent, CoverageArchive, CoverageStatistics, SourceCodeCache

TAB_LENGTH = 4

HIGHLIGHT_CLASSES = {
    'C': 'SrcHlC',
    'CM': 'SrcHlCM',
    'CP': 'SrcHlCP',
    'CPF': 'SrcHlCPF',
    'CS': 'SrcHlCS',
    'K': 'SrcHlK',
    'KR': 'SrcHlKR',
    'KT': 'SrcHlKT',
    'LNF': 'SrcHlLNF',
    'LNI': 'SrcHlLNI',
    'LNH': 'SrcHlLNH',
    'LNO': 'SrcHlLNO',
    'LS': 'SrcHlLS',
    'LSA': 'SrcHlLSA',
    'LSC': 'SrcHlLSC',
    'LSE': 'SrcHlLSE',
    'N': 'SrcHlN',
    'NB': 'SrcHlNB',
    'NC': 'SrcHlNC',
    'NF': 'SrcHlNF',
    'NL': 'SrcHlNL',
    'O': 'SrcHlO',
    'FuncDefRefTo': 'SrcHlFuncDefRefTo',
    'FuncDeclRefTo': 'SrcHlFuncDeclRefTo',
    'MacroDefRefTo': 'SrcHlMacroDefRefTo',
    'FuncCallRefFrom': 'SrcHlFuncCallRefFrom',
    'MacroExpansionRefFrom': 'SrcHlMacroExpansionRefFrom',
    'LDVModelFunc': 'SrcHlLDVModelFunc',
    'LDVEnvModelFunc': 'SrcHlLDVEnvModelFunc',
    'CIFAuxFunc': 'SrcHlCIFAuxFunc'
}

COVERAGE_CLASSES = {
    'Verifier assumption': "SrcCovVA",
    'Verifier operation statistics': "SrcCovVOS",
    'Environment modelling hint': "SrcCovEMH",
    'Multiple notes': "SrcCovMN"
}


def coverage_color(curr_cov, max_cov, delta=0):
    if curr_cov == 0:
        return 'rgb(255, 200, 200)'
    red = 130 + int(110 * (1 - curr_cov / max_cov))
    blue = 130 + int(110 * (1 - curr_cov / max_cov)) - delta
    return 'rgb(%s, 255, %s)' % (red, blue)


class EmptyCoverage:
    def __init__(self):
        self.value = {'value': 0, 'color': coverage_color(0, 0)}

    def get(self, line_number):
        assert line_number
        return self.value


class SourceNotFound(Exception):
    pass


class SourceLine:
    max_ref_links = 7
    ref_to_class = 'SrcRefToLink'
    ref_from_class = 'SrcRefFromLink'
    declaration_class = 'SrcRefToDeclLink'

    def __init__(self, source, highlights=None, filename=None, line=None,
                 references_to=None, references_from=None, references_declarations=None):
        self._source = source
        self._source_len = len(source)
        try:
            self._highlights = self.__get_highlights(highlights)
        except Exception as e:
            logger.error('Source highlights error ({}:{}): {}'.format(filename, line, e))
            self._highlights = OrderedDict([((0, self._source_len), None)])
        try:
            self.references_data = []
            self.declarations = {}
            self._references = self.__get_references(references_to, references_from, references_declarations)
        except Exception as e:
            logger.error('Source references error ({}:{}): {}'.format(filename, line, e))
            self.references_data = []
            self.declarations = {}
            self._references = []
        self.html_code = self.__to_html()

    def __get_highlights(self, highlights):
        if not highlights:
            highlights = []

        h_dict = OrderedDict()
        prev_end = 0
        for h_name, start, end in sorted(highlights, key=lambda x: (x[1], x[2])):
            self.__assert_int(start, end)
            self.__check_range(start, end, prev_end)
            if h_name not in HIGHLIGHT_CLASSES:
                raise ValueError('class "{}" is not supported'.format(h_name))
            if prev_end < start:
                h_dict[(prev_end, start)] = None
            h_dict[(start, end)] = HIGHLIGHT_CLASSES[h_name]
            prev_end = end
        if prev_end < self._source_len:
            h_dict[(prev_end, self._source_len)] = None
        elif prev_end > self._source_len:
            raise ValueError('source line is too short to highlight code')
        return h_dict

    def __get_source_links(self, data):
        source_links = []
        for file_ind, file_lines in data:
            if not isinstance(file_lines, list):
                raise ValueError('file lines is not a list')
            curr_lines = []
            for file_line in file_lines:
                self.__assert_int(file_line)
                curr_lines.append(file_line)
                if len(curr_lines) >= self.max_ref_links:
                    source_links.append([file_ind, curr_lines])
                    curr_lines = []
            if len(curr_lines):
                source_links.append([file_ind, curr_lines])
        return source_links

    def __get_links_number(self, data):
        number = 0
        for file_ind, file_lines in data:
            number += len(file_lines)
        return number

    def __get_references(self, references_to, references_from, references_declarations):
        if not references_to:
            references_to = []
        if not references_from:
            references_from = []
        if not references_declarations:
            references_declarations = []

        # Collect declarations
        for ref_data in references_declarations:
            line_num, ref_start, ref_end = ref_data[0]
            self.__assert_int(line_num, ref_start, ref_end)
            self.declarations[(ref_start, ref_end)] = {
                'id': 'declarations_{}_{}_{}'.format(*ref_data[0]),
                'sources': self.__get_source_links(ref_data[1:])
            }

        # Collect references to
        mixed_declarations = set()
        references = []
        for (line_num, ref_start, ref_end), (file_ind, file_line) in references_to:
            self.__assert_int(line_num, ref_start, ref_end, file_line)
            span_data = {'file': file_ind, 'line': file_line}

            if (ref_start, ref_end) in self.declarations:
                span_class = '{} {}'.format(self.declaration_class, self.ref_to_class)
                span_data['declaration'] = self.declarations[(ref_start, ref_end)]['id']
                span_data['declnumber'] = self.__get_links_number(self.declarations[(ref_start, ref_end)]['sources'])
                mixed_declarations.add((ref_start, ref_end))
            else:
                span_class = self.ref_to_class
            references.append([ref_start, ref_end, {'span_class': span_class, 'span_data': span_data}])

        # Collect declarations that are not used together with "references to"
        for ref_start, ref_end in set(self.declarations) - mixed_declarations:
            references.append([ref_start, ref_end, {
                'span_class': self.declaration_class,
                'span_data': {
                    'declaration': self.declarations[(ref_start, ref_end)]['id'],
                    'declnumber': self.__get_links_number(self.declarations[(ref_start, ref_end)]['sources'])
                }
            }])

        # Collect references from
        for ref_data in references_from:
            line_num, ref_start, ref_end = ref_data[0]
            self.__assert_int(line_num, ref_start, ref_end)
            ref_from_id = 'reflink_{}_{}_{}'.format(*ref_data[0])
            references.append([ref_start, ref_end, {
                'span_class': self.ref_from_class,
                'span_data': {'id': ref_from_id}
            }])
            self.references_data.append({'id': ref_from_id, 'sources': self.__get_source_links(ref_data[1:])})

        references.sort(key=lambda x: (x[0], x[1]), reverse=True)

        prev_end = 0
        for ref_start, ref_end, span_kwargs in reversed(references):
            self.__check_range(ref_start, ref_end, prev_end)
            prev_end = ref_end
        if self._source_len < prev_end:
            raise ValueError('source line is too short to add reference')
        return references

    def __get_code(self, start, end):
        code = self._source[start:end]
        code_list = []
        for ref_start, ref_end, span_kwargs in self._references:
            if start <= ref_start < ref_end <= end:
                ref_start_rel = ref_start - start
                ref_end_rel = ref_end - start
                code_list.extend([
                    self.__fix_for_html(code[ref_end_rel:]),
                    self._span_close,
                    self.__fix_for_html(code[ref_start_rel:ref_end_rel]),
                    self.__span_open(**span_kwargs)
                ])
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

    def __check_range(self, start, end, prev_end):
        if prev_end > start:
            raise ValueError('ranges are overlapping')
        if start >= end:
            raise ValueError('range is incorrect')

    def __assert_int(self, *args):
        for value in args:
            if not isinstance(value, int):
                raise ValueError('type of "{}" is "{}", int expected'.format(value, type(value)))


class ParseSource:
    index_postfix = '.idx.json'
    coverage_postfix = '.cov.json'

    def __init__(self, user, file_name, ancestors, coverage_qs, with_legend):
        self._user = user
        self._ancestors = ancestors
        self.file_name = file_name
        self._coverage_qs = coverage_qs
        self.with_legend = with_legend

        self._source_lines = self._references = self.coverage_id = None

        self.file_content = self.__get_source_code()

    def __extract_file(self, obj, name, field_name='archive'):
        if obj is None:
            return None
        try:
            res = ArchiveFileContent(obj, field_name, name, not_exists_ok=True)
        except Exception as e:
            raise BridgeException(_("Error while extracting source file: %(error)s") % {'error': str(e)})
        if res.content is None:
            return None
        return res.content.decode('utf8')

    def __get_source_code(self):
        for report in self._ancestors:
            for file_obj in [report.additional_sources, report.original_sources]:
                content = self.__extract_file(file_obj, self.file_name)
                if content:
                    return content
        raise SourceNotFound('The source file was not found')

    @cached_property
    def _indexes(self):
        index_name = self.file_name + self.index_postfix
        for report in self._ancestors:
            for file_obj in [report.additional_sources, report.original_sources]:
                content = self.__extract_file(file_obj, index_name)
                if content:
                    index_data = json.loads(content)
                    if index_data.get('format') != ETV_FORMAT:
                        raise BridgeException(_('Sources indexing format is not supported'))
                    return index_data
        return None

    @cached_property
    def _coverage(self):
        cov_name = self.file_name + self.coverage_postfix
        for cov_obj in self._coverage_qs:
            content = self.__extract_file(cov_obj, cov_name)
            if not content:
                continue
            coverage_data = json.loads(content)
            if coverage_data.get('format') != ETV_FORMAT:
                raise BridgeException(_('Code coverage format is not supported'))
            self.coverage_id = cov_obj.id
            return coverage_data
        return None

    @cached_property
    def _line_coverage(self):
        if not self._coverage or not self._coverage.get('line coverage'):
            if CoverageStatistics.objects.filter(path=self.file_name, coverage_id=self.coverage_id).exists():
                return EmptyCoverage()
            return {}
        coverage_data = {}
        max_cov = max(self._coverage['line coverage'].values())
        for line_num in self._coverage['line coverage']:
            cov_value = self._coverage['line coverage'][line_num]
            coverage_data[line_num] = {'value': cov_value, 'color': coverage_color(cov_value, max_cov)}
        return coverage_data

    @cached_property
    def _func_coverage(self):
        if not self._coverage or not self._coverage.get('function coverage'):
            return {}
        coverage_data = {}
        max_cov = max(self._coverage['function coverage'].values())
        for line_num in self._coverage['function coverage']:
            cov_value = self._coverage['function coverage'][line_num]
            coverage_data[line_num] = {
                'value': cov_value,
                'color': coverage_color(cov_value, max_cov, 40),
                'icon': 'blue check' if cov_value else 'red remove'
            }
        return coverage_data

    def __get_coverage_note(self, line):
        if self._coverage and 'notes' in self._coverage and line in self._coverage['notes']:
            return (
                COVERAGE_CLASSES.get(self._coverage['notes'][line]['kind']),
                self._coverage['notes'][line]['text']
            )
        return None

    @cached_property
    def _coverage_data(self):
        if not self._coverage or not self._user.coverage_data or not self._coverage.get('data'):
            return set()
        return set(self._coverage['data'])

    def __parse_source(self):
        highlights = {}
        if self._indexes and 'highlight' in self._indexes:
            for h_name, line_num, start, end in self._indexes['highlight']:
                highlights.setdefault(line_num, [])
                highlights[line_num].append((h_name, start, end))

        references_to = {}
        if self._indexes and 'referencesto' in self._indexes:
            for ref_data in self._indexes['referencesto']:
                line_num = ref_data[0][0]
                references_to.setdefault(line_num, [])
                references_to[line_num].append(ref_data)

        references_from = {}
        if self._indexes and 'referencesfrom' in self._indexes:
            for ref_data in self._indexes['referencesfrom']:
                line_num = ref_data[0][0]
                references_from.setdefault(line_num, [])
                references_from[line_num].append(ref_data)

        references_declarations = {}
        if self._indexes and 'referencestodeclarations' in self._indexes:
            for ref_data in self._indexes['referencestodeclarations']:
                line_num = ref_data[0][0]
                references_declarations.setdefault(line_num, [])
                references_declarations[line_num].append(ref_data)

        cnt = 1
        lines = self.file_content.split('\n')
        total_lines_len = len(str(len(lines)))

        lines_data = []
        references_data = []
        for code in lines:
            src_line = SourceLine(
                code, highlights=highlights.get(cnt), filename=self.file_name, line=cnt,
                references_to=references_to.get(cnt),
                references_from=references_from.get(cnt),
                references_declarations=references_declarations.get(cnt)
            )
            linenum_str = str(cnt)
            lines_data.append({
                'number': cnt, 'code': src_line.html_code,
                'number_prefix': ' ' * (total_lines_len - len(linenum_str)),
                'line_cov': self._line_coverage.get(linenum_str),
                'func_cov': self._func_coverage.get(linenum_str),
                'note': self.__get_coverage_note(linenum_str),
                'has_data': (linenum_str in self._coverage_data)
            })
            references_data.extend(src_line.references_data)
            references_data.extend(src_line.declarations.values())
            cnt += 1
        return lines_data, references_data

    @property
    def source_lines(self):
        if self._source_lines is None:
            self._source_lines, self._references = self.__parse_source()
        return self._source_lines

    @property
    def references(self):
        if self._references is None:
            self._source_lines, self._references = self.__parse_source()
        return self._references

    @cached_property
    def source_files(self):
        if self._indexes and 'source files' in self._indexes:
            return list(enumerate(self._indexes['source files'] + [self.file_name]))
        return []

    @cached_property
    def legend(self):
        max_lines_cov = max_funcs_cov = 0
        if self._coverage and self._coverage.get('line coverage'):
            max_lines_cov = max(self._coverage['line coverage'].values())
        if self._coverage and self._coverage.get('function coverage'):
            max_funcs_cov = max(self._coverage['function coverage'].values())
        return {
            'lines': self.__get_legend(max_lines_cov, 'lines', 5, True),
            'funcs': self.__get_legend(max_funcs_cov, 'funcs', 5, True),
        }

    def __get_legend(self, max_cov, leg_type, number=5, with_zero=False):
        if max_cov == 0:
            return [(0, coverage_color(0, max_cov, 0))]
        elif max_cov > 100:
            rounded_max = 100 * int(max_cov / 100)
        else:
            rounded_max = max_cov

        delta = 0
        if leg_type == 'funcs':
            delta = 40

        colors = []
        divisions = number - 1
        for i in reversed(range(divisions)):
            curr_cov = int(i * rounded_max / divisions)
            if curr_cov == 0:
                curr_cov = 1
            colors.append((curr_cov, coverage_color(curr_cov, max_cov, delta)))
        colors.insert(0, (rounded_max, coverage_color(rounded_max, max_cov, delta)))
        if with_zero:
            colors.append((0, coverage_color(0, max_cov, delta)))
        new_colors = []
        for i in reversed(range(len(colors))):
            if colors[i] not in new_colors:
                new_colors.insert(0, colors[i])
        return new_colors


class GetSource:
    def __init__(self, request, report):
        self._request = request
        self._report = report
        self.file_name = self.__parse_file_name()
        self.with_legend = (self._request.query_params.get('with_legend') == 'true')
        self.identifier = self.__get_cache_identifier()

    def __parse_file_name(self):
        file_name = self._request.query_params['file_name']
        name = unquote(file_name)
        if name.startswith('/'):
            name = name[1:]
        return name

    @cached_property
    def _ancestors(self):
        parents_ids = set(self._report.get_ancestors(include_self=True).exclude(
            reportcomponent__additional_sources=None, reportcomponent__original_sources=None
        ).values_list('id', flat=True))
        return ReportComponent.objects.filter(id__in=parents_ids) \
            .select_related('original_sources', 'additional_sources') \
            .only('id', 'verification', 'original_sources_id', 'additional_sources_id',
                  'original_sources__archive', 'additional_sources__archive') \
            .order_by('-id')

    @cached_property
    def _coverage_qs(self):
        qs_filters = {'report_id__in': list(r.id for r in self._ancestors)}

        # If coverage_id is set then it can be source for Sub-job or Core only,
        # Otherwise - for verification report or its leaf.
        coverage_id = self._request.query_params.get('coverage_id')
        if coverage_id:
            # For full coverage (Subjob reports) where there can be several coverages
            qs_filters['id'] = coverage_id
        else:
            # Do not use full coverage for sub-jobs
            qs_filters['identifier'] = ''

        return CoverageArchive.objects.filter(**qs_filters).order_by('-report_id')

    def __get_cache_identifier(self):
        identifier_data = json.dumps([
            get_language(), self.file_name, self.with_legend,
            list([r.id, r.original_sources_id, r.additional_sources_id] for r in self._ancestors),
            list(ca.id for ca in self._coverage_qs)
        ]).encode('utf-8')
        return hashlib.md5(identifier_data).hexdigest()[:256]

    def __render_html(self):
        try:
            data = ParseSource(self._request.user, self.file_name, self._ancestors, self._coverage_qs, self.with_legend)
        except SourceNotFound:
            data = None
        template = loader.get_template('reports/SourceCode.html')
        return template.render({'data': data}, self._request)

    @transaction.atomic
    def get_html(self):
        src_code = SourceCodeCache.objects.filter(identifier=self.identifier).select_for_update().first()
        if src_code:
            with open(src_code.file.path, mode='rb') as fp:
                html_content_b = fp.read()
            src_code.access_date = now()
            src_code.save()
        else:
            html_content_b = self.__render_html().encode('utf8')
            fp = io.BytesIO(html_content_b)
            fp.seek(0)
            src_code = SourceCodeCache(identifier=self.identifier)
            src_code.file.save('SourceCode.html', File(fp), save=True)
        return html_content_b
