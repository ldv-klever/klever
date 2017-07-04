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

import os
import json
import zipfile
import xml.etree.ElementTree as ETree
from xml.dom import minidom

from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.urlresolvers import reverse
from django.db.models import Q, Count, Case, When
from django.utils.translation import ugettext_lazy as _

from bridge.vars import UNSAFE_VERDICTS, SAFE_VERDICTS, JOB_WEIGHT, VIEW_TYPES
from bridge.tableHead import Header
from bridge.utils import logger, BridgeException, ArchiveFileContent
from bridge.ZipGenerator import ZipStream

from reports.models import ReportComponent, Attr, AttrName, ReportAttr, ReportUnsafe, ReportSafe, ReportUnknown,\
    ReportRoot
from marks.models import UnknownProblem, UnsafeReportTag, SafeReportTag

from users.utils import DEF_NUMBER_OF_ELEMENTS, ViewData
from jobs.utils import get_resource_data, get_user_time
from reports.utils import get_parents
from marks.tables import SAFE_COLOR, UNSAFE_COLOR


SOURCE_CLASSES = {
    'comment': "COVComment",
    'number': "COVNumber",
    'line': "COVSrcL",
    'text': "COVText",
    'key1': "COVKey1",
    'key2': "COVKey2"
}


class GetCoverage:
    def __init__(self, user, report_id):
        self.user = user
        self.type = None
        self.report = self.__get_report(report_id)
        self.job = self.report.root.job
        self.parent = ReportComponent.objects.get(id=self.report.parent_id)
        self.parents = get_parents(self.report)
        self._files = []
        self._curr_i = 0
        self._sum = 0

    def __get_report(self, report_id):
        try:
            self.type = 'safe'
            return ReportSafe.objects.get(id=report_id)
        except ObjectDoesNotExist:
            try:
                self.type = 'unsafe'
                return ReportUnsafe.objects.get(id=report_id)

            except ObjectDoesNotExist:
                try:
                    self.type = 'unknown'
                    return ReportUnknown.objects.get(id=report_id)
                except ObjectDoesNotExist:
                    raise BridgeException(_('The report was not found'))

    def get_coverage(self):
        if not self.parent.verification or self.parent.coverage is None:
            raise ValueError("The parent doesn't have coverage")
        with self.parent.archive as fp:
            if os.path.splitext(fp.name)[-1] != '.zip':
                raise ValueError('Archive type is not supported')
            with zipfile.ZipFile(fp, 'r') as zfp:
                return json.loads(zfp.read(self.parent.coverage))

    def __get_files(self):
        if not self.parent.verification:
            raise ValueError("The parent is not verification report")
        with self.parent.archive as fp:
            if os.path.splitext(fp.name)[-1] != '.zip':
                raise ValueError('Archive type is not supported')
            with zipfile.ZipFile(fp, 'r') as zfp:
                for filename in zfp.namelist():
                    if filename.endswith('/'):
                        continue
                    if filename not in {self.parent.coverage, self.parent.log}:
                        self._files.append(os.path.normpath(filename))

    def __wrap_item(self, title, item, header):
        self.__is_not_used()
        if header:
            return '<div class="item" data-value="%s" style="color:#bcbcbc;">%s</div>' % (title, item)
        else:
            return '<div class="item" data-value="%s">%s</div>' % (title, item)

    def __wrap_items(self, title, items):
        self.__is_not_used()
        return '<i class="dropdown icon"></i><span class="text">%s</span><div class="menu">%s</div>' % (
            title, ''.join(items)
        )

    def __get_children_list(self, path):
        children = []
        headers_dir = True
        for f in self._files[self._curr_i:]:
            if f.startswith(path):
                relpath = os.path.relpath(f, path)
                childpath = relpath.split(os.path.sep)
                if len(childpath) == 1:
                    self._sum += 1
                    is_header = False
                    if childpath[0].endswith('.h'):
                        is_header = True
                    else:
                        headers_dir = False
                    children.append(self.__wrap_item(f, childpath[0], is_header))
                    self._curr_i += 1
                elif len(childpath) > 1:
                    children_html, children_are_headers = self.__get_children_list(os.path.join(path, childpath[0]))
                    if len(children_html) > 0:
                        if not children_are_headers:
                            headers_dir = False
                        children.append(self.__wrap_item('', children_html, children_are_headers))
            else:
                break
        if len(children) > 0:
            return self.__wrap_items(os.path.basename(path), children), headers_dir
        return '', headers_dir

    def files_tree(self):
        self.__get_files()
        self._files = list(sorted(self._files))

        root_dirs = []
        children_html, children_are_headers = self.__get_children_list('generated')
        if len(children_html) > 0:
            root_dirs.append(self.__wrap_item('generated', children_html, children_are_headers))
            children_html, children_are_headers = self.__get_children_list('specifications')
        if len(children_html) > 0:
            root_dirs.insert(0, self.__wrap_item('specifications', children_html, children_are_headers))
            children_html, children_are_headers = self.__get_children_list('src')
        if len(children_html) > 0:
            root_dirs.insert(0, self.__wrap_item('src', children_html, children_are_headers))

        if self._sum != len(self._files):
            raise ValueError('Something is wrong')

        return self.__wrap_items('Select file', root_dirs)

    def get_file_content(self, filename):
        with self.parent.archive as fp:
            if os.path.splitext(fp.name)[-1] != '.zip':
                raise ValueError('Archive type is not supported')
            with zipfile.ZipFile(fp, 'r') as zfp:
                filename = os.path.normpath(filename).replace('\\', '/')
                return GetCoverageSrcHTML(zfp.read(filename).decode('utf8')).data

    def __is_not_used(self):
        pass


class GetCoverageSrcHTML:
    def __init__(self, content):
        self.is_comment = False
        self.is_text = False
        self.text_quote = None
        self.data = self.__get_source(content)

    def __get_report(self, report_id):
        self.__is_not_used()
        try:
            return ReportUnsafe.objects.get(pk=report_id)
        except ObjectDoesNotExist:
            raise BridgeException(_("Could not find the corresponding unsafe"))

    def __get_source(self, source_content):
        from reports.etv import TAB_LENGTH
        data = ''
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
        import re
        from reports.etv import KEY1_WORDS, KEY2_WORDS
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
