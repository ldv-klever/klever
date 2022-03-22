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

from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from bridge.vars import MARK_SAFE, MARK_UNSAFE, MARK_STATUS, COMPARE_FUNCTIONS, CONVERT_FUNCTIONS, DEFAULT_COMPARE

from marks.tags import TagsTree, MarkTagsTree

from reports.verdicts import safe_color, unsafe_color, bug_status_color


class MarkVersionFormData:
    def __init__(self, mark_type, mark_version=None):
        self.type = mark_type
        self.object = mark_version

    @property
    def title(self):
        if self.type == 'safe':
            return _('Safes mark')
        elif self.type == 'unsafe':
            return _('Unsafes mark')
        return _('Unknowns mark')

    @property
    def action(self):
        return 'edit' if self.object else 'create'

    @cached_property
    def is_modifiable(self):
        return self.object.mark.is_modifiable if self.object else True

    @cached_property
    def version(self):
        # Should not be called on mark creation
        return self.object.version if self.object else None

    @cached_property
    def status(self):
        if self.type != 'unsafe':
            return None
        return self.object.status if self.object else None

    @property
    def description(self):
        return self.object.description if self.object else ''

    @cached_property
    def verdict(self):
        if self.type == 'safe':
            return self.object.verdict if self.object else MARK_SAFE[0][0]
        elif self.type == 'unsafe':
            return self.object.verdict if self.object else MARK_UNSAFE[0][0]
        return None

    @cached_property
    def verdicts(self):
        if self.type == 'safe':
            return list({'id': v_id, 'text': v_text, 'color': safe_color(v_id)} for v_id, v_text in MARK_SAFE)
        elif self.type == 'unsafe':
            return list({'id': v_id, 'text': v_text, 'color': unsafe_color(v_id)} for v_id, v_text in MARK_UNSAFE)
        return None

    @cached_property
    def statuses(self):
        if self.type != 'unsafe':
            return None
        return list({'id': s_id, 'text': s_text, 'color': bug_status_color(s_id)} for s_id, s_text in MARK_STATUS)

    @cached_property
    def function(self):
        if self.type == 'safe':
            return None
        if self.object:
            return self.object.function
        return DEFAULT_COMPARE if self.type == 'unsafe' else ''

    @cached_property
    def functions(self):
        functions_data = []
        for name in sorted(COMPARE_FUNCTIONS):
            functions_data.append({
                'name': name,
                'desc': COMPARE_FUNCTIONS[name]['desc'],
                'convert': {
                    'name': COMPARE_FUNCTIONS[name]['convert'],
                    'desc': CONVERT_FUNCTIONS[COMPARE_FUNCTIONS[name]['convert']]
                }
            })
        return functions_data

    @property
    def compare_desc(self):
        return COMPARE_FUNCTIONS[self.function]['desc']

    @property
    def convert_func(self):
        return {
            'name': COMPARE_FUNCTIONS[self.function]['convert'],
            'desc': CONVERT_FUNCTIONS[COMPARE_FUNCTIONS[self.function]['convert']],
        }

    @property
    def problem_pattern(self):
        return self.object.problem_pattern if self.object else ''

    @property
    def is_regexp(self):
        return self.object.is_regexp if self.object else False

    @property
    def link(self):
        return self.object.link if self.object and self.object.link else ''

    @cached_property
    def tags(self):
        if self.type == 'unknown':
            return None
        if self.object:
            return MarkTagsTree(self.object)
        return TagsTree(tags_ids=[])

    @cached_property
    def error_trace(self):
        if not self.object or self.type != 'unsafe':
            return
        with self.object.error_trace.file.file as fp:
            return fp.read().decode('utf-8')

    @cached_property
    def threshold(self):
        if not self.object or self.type != 'unsafe':
            return
        return self.object.threshold_percentage
