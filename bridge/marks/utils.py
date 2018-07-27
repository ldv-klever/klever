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
from difflib import unified_diff

from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import ugettext_lazy as _

from bridge.vars import USER_ROLES, JOB_ROLES
from bridge.utils import BridgeException

import marks.SafeUtils as SafeUtils
import marks.UnsafeUtils as UnsafeUtils
import marks.UnknownUtils as UnknownUtils

from users.models import User
from reports.models import ReportUnsafe, ReportSafe, ReportUnknown
from marks.models import MarkSafe, MarkUnsafe, MarkUnknown, MarkSafeHistory, MarkUnsafeHistory, MarkUnknownHistory,\
    SafeTag, UnsafeTag, ConvertedTraces, MarkSafeReport, MarkUnsafeReport, MarkUnknownReport


STATUS_COLOR = {
    '0': '#e81919',
    '1': '#FF8533',
    '2': '#FF8533',
    '3': '#00c600',
}

UNSAFE_COLOR = {
    '0': '#cb58ec',
    '1': '#e81919',
    '2': '#e81919',
    '3': '#FF8533',
    '4': '#D11919',  # Incompatible marks
    '5': '#000000',  # Without marks
}

SAFE_COLOR = {
    '0': '#cb58ec',
    '1': '#FF8533',
    '2': '#e81919',
    '3': '#D11919',  # Incompatible marks
    '4': '#000000',  # Without marks
}


class MarkAccess:

    def __init__(self, user, mark=None, report=None):
        self.user = user
        self.mark = mark
        self.report = report

    def can_edit(self):
        if not isinstance(self.user, User):
            return False
        if self.user.extended.role == USER_ROLES[2][0]:
            return True
        if not self.mark.is_modifiable or self.mark.version == 0:
            return False
        if self.user.extended.role == USER_ROLES[3][0]:
            return True
        if isinstance(self.mark, (MarkUnsafe, MarkSafe, MarkUnknown)):
            first_vers = self.mark.versions.order_by('version').first()
        else:
            return False
        if first_vers.author == self.user:
            return True
        if self.mark.job is not None:
            first_v = self.mark.job.versions.order_by('version').first()
            if first_v.change_author == self.user:
                return True
            last_v = self.mark.job.versions.get(version=self.mark.job.version)
            if last_v.global_role in [JOB_ROLES[2][0], JOB_ROLES[4][0]]:
                return True
            try:
                user_role = last_v.userrole_set.get(user=self.user)
                if user_role.role in [JOB_ROLES[2][0], JOB_ROLES[4][0]]:
                    return True
            except ObjectDoesNotExist:
                return False
        return False

    def can_create(self):
        if not isinstance(self.user, User):
            return False
        if isinstance(self.report, (ReportUnsafe, ReportSafe, ReportUnknown)):
            if isinstance(self.report, ReportSafe) and not self.report.root.job.safe_marks:
                return False
            if self.user.extended.role in [USER_ROLES[2][0], USER_ROLES[3][0]]:
                return True
            first_v = self.report.root.job.versions.order_by('version').first()
            if first_v.change_author == self.user:
                return True
            try:
                last_v = self.report.root.job.versions.get(version=self.report.root.job.version)
            except ObjectDoesNotExist:
                return False
            if last_v.global_role in [JOB_ROLES[2][0], JOB_ROLES[4][0]]:
                return True
            try:
                user_role = last_v.userrole_set.get(user=self.user)
                if user_role.role in [JOB_ROLES[2][0], JOB_ROLES[4][0]]:
                    return True
            except ObjectDoesNotExist:
                return False
        elif self.user.extended.role in [USER_ROLES[2][0], USER_ROLES[3][0]]:
            return True
        return False

    def can_delete(self):
        if not isinstance(self.user, User):
            return False
        if self.user.extended.role == USER_ROLES[2][0]:
            return True
        if not self.mark.is_modifiable or self.mark.version == 0:
            return False
        if self.user.extended.role == USER_ROLES[3][0]:
            return True
        authors = list(set(v_id for v_id, in self.mark.versions.values_list('author_id') if v_id is not None))
        if len(authors) == 1 and authors[0] == self.user.id:
            return True
        return False

    def can_remove_version(self, mark_version):
        if not isinstance(self.user, User) or not isinstance(self.mark, (MarkUnsafe, MarkSafe, MarkUnknown)):
            return False
        # Nobody can remove first or last version. Also while mark is being deleted users can't clear versions.
        if mark_version.version in {1, self.mark.version} or self.mark.version == 0:
            return False
        # Manager can remove all other versions
        if self.user.extended.role == USER_ROLES[2][0]:
            return True
        # Others can't remove versions if mark is frozen.
        if not self.mark.is_modifiable:
            return False
        # Expert can remove all versions.
        if self.user.extended.role == USER_ROLES[3][0]:
            return True
        # Others can remove version only if they are authors of it.
        if mark_version.author == self.user:
            return True
        return False

    def can_freeze(self):
        if not isinstance(self.user, User):
            return False
        return self.user.extended.role == USER_ROLES[2][0]


class TagsInfo:
    def __init__(self, mark_type, mark=None):
        self.mark = mark
        self.type = mark_type
        self.tags_old = []
        self.tags_available = []
        self.__get_tags()

    def __get_tags(self):
        if self.type not in ['unsafe', 'safe']:
            return
        if isinstance(self.mark, (MarkUnsafe, MarkSafe)):
            last_v = self.mark.versions.get(version=self.mark.version)
            self.tags_old = list(t['tag__tag'] for t in last_v.tags.order_by('tag__tag').values('tag__tag'))
        elif isinstance(self.mark, (MarkUnsafeHistory, MarkSafeHistory)):
            self.tags_old = list(t['tag__tag'] for t in self.mark.tags.order_by('tag__tag').values('tag__tag'))
        if self.type == 'unsafe':
            table = UnsafeTag
        else:
            table = SafeTag
        self.tags_available = list(t['tag'] for t in table.objects.values('tag') if t['tag'] not in self.tags_old)


class NewMark:
    def __init__(self, user, inst, data):
        self._user = user
        self._data = data
        self._inst = inst
        self._handler = self.__get_handler()
        self.changes = {}
        self.mark = None

    def __get_handler(self):
        if isinstance(self._inst, (ReportSafe, MarkSafe)):
            return SafeUtils.NewMark(self._user, self._data)
        elif isinstance(self._inst, (ReportUnsafe, MarkUnsafe)):
            return UnsafeUtils.NewMark(self._user, self._data)
        elif isinstance(self._inst, (ReportUnknown, MarkUnknown)):
            return UnknownUtils.NewMark(self._user, self._data)
        else:
            raise ValueError('Unsupported type: %s' % type(self._inst))

    def create_mark(self):
        self.mark = self._handler.create_mark(self._inst)
        self.changes = self._handler.changes

    def change_mark(self):
        self.mark = self._handler.change_mark(self._inst)
        self.changes = self._handler.changes


class CompareMarkVersions:
    def __init__(self, mark_type, version1, version2):
        self.type = mark_type
        self.v1 = version1
        self.v2 = version2
        self.verdict = self.__verdict_change()
        self.status = self.__status_change()
        self.tags = self.__tags_change()
        self.et_func = self.__et_func_change()
        self.et = self.__et_change()
        self.attrs = self.__attr_change()
        self.unknown_func = self.__unknown_func_change()
        self.problem = self.__problem_change()

    def __verdict_change(self):
        if self.type == 'unknown' or self.v1.verdict == self.v2.verdict:
            return None
        if self.type == 'safe':
            return [{'title': self.v1.get_verdict_display(), 'color': SAFE_COLOR[self.v1.verdict]},
                    {'title': self.v2.get_verdict_display(), 'color': SAFE_COLOR[self.v2.verdict]}]
        else:
            return [{'title': self.v1.get_verdict_display(), 'color': UNSAFE_COLOR[self.v1.verdict]},
                    {'title': self.v2.get_verdict_display(), 'color': UNSAFE_COLOR[self.v2.verdict]}]

    def __status_change(self):
        if self.v1.status == self.v2.status:
            return None
        return [{'title': self.v1.get_status_display(), 'color': STATUS_COLOR[self.v1.status]},
                {'title': self.v2.get_status_display(), 'color': STATUS_COLOR[self.v2.status]}]

    def __tags_change(self):
        if self.type == 'unknown':
            return None
        tags1 = set(t for t, in self.v1.tags.values_list('tag__tag'))
        tags2 = set(t for t, in self.v2.tags.values_list('tag__tag'))
        if tags1 == tags2:
            return None
        return ['; '.join(sorted(tags1)), '; '.join(sorted(tags2))]

    def __et_func_change(self):
        if self.type != 'unsafe' or self.v1.function_id == self.v2.function_id:
            return None
        return [{
            'compare_name': self.v1.function.name, 'compare_desc': self.v1.function.description,
            'convert_name': self.v1.function.convert.name, 'convert_desc': self.v1.function.convert.description
        }, {
            'compare_name': self.v2.function.name, 'compare_desc': self.v2.function.description,
            'convert_name': self.v2.function.convert.name, 'convert_desc': self.v2.function.convert.description
        }]

    def __et_change(self):
        if self.type != 'unsafe' or self.v1.error_trace_id == self.v2.error_trace_id:
            return None
        diff_result = []
        f1 = ConvertedTraces.objects.get(id=self.v1.error_trace_id)
        f2 = ConvertedTraces.objects.get(id=self.v2.error_trace_id)
        with f1.file as fp1, f2.file as fp2:
            for line in unified_diff(fp1.read().decode('utf8').split('\n'), fp2.read().decode('utf8').split('\n')):
                diff_result.append(line)

        return '\n'.join(diff_result)

    def __attr_change(self):
        attrs1 = set(a_id for a_id, in self.v1.attrs.filter(is_compare=True).values_list('attr_id'))
        attrs2 = set(a_id for a_id, in self.v2.attrs.filter(is_compare=True).values_list('attr_id'))
        if attrs1 == attrs2:
            return None
        return [
            list((a.attr.name.name, a.attr.value) for a in self.v1.attrs.filter(is_compare=True)
                 .select_related('attr', 'attr__name').order_by('id')),
            list((a.attr.name.name, a.attr.value) for a in self.v2.attrs.filter(is_compare=True)
                 .select_related('attr', 'attr__name').order_by('id'))
        ]

    def __unknown_func_change(self):
        if self.type != 'unknown':
            return None
        if self.v1.is_regexp == self.v2.is_regexp and self.v1.function == self.v2.function:
            return None
        return [{'is_regexp': self.v1.is_regexp, 'func': self.v1.function},
                {'is_regexp': self.v2.is_regexp, 'func': self.v2.function}]

    def __problem_change(self):
        if self.type != 'unknown':
            return None
        if self.v1.problem_pattern == self.v2.problem_pattern and self.v1.link == self.v2.link:
            return None
        return [{'pattern': self.v1.problem_pattern, 'link': self.v1.link},
                {'pattern': self.v2.problem_pattern, 'link': self.v2.link}]


def delete_marks(user, marks_type, mark_ids, report_id=None):
    if marks_type == 'safe':
        marks = MarkSafe.objects.filter(id__in=mark_ids)
    elif marks_type == 'unsafe':
        marks = MarkUnsafe.objects.filter(id__in=mark_ids)
    elif marks_type == 'unknown':
        marks = MarkUnknown.objects.filter(id__in=mark_ids)
    else:
        raise ValueError('Unsupported marks type: %s' % marks_type)
    if not all(MarkAccess(user, mark=mark).can_delete() for mark in marks):
        if len(marks) > 1:
            raise BridgeException(_("You can't delete one of the selected marks"))
        elif len(marks) == 1:
            raise BridgeException(_("You don't have an access to delete this mark"))
        else:
            raise BridgeException(_('Nothing to delete'))
    if marks_type == 'safe':
        SafeUtils.delete_marks(marks)
        reports_model = ReportSafe
    elif marks_type == 'unsafe':
        UnsafeUtils.delete_marks(marks)
        reports_model = ReportUnsafe
    else:
        UnknownUtils.delete_marks(marks)
        reports_model = ReportUnknown
    if report_id:
        try:
            report = reports_model.objects.get(id=report_id)
        except ObjectDoesNotExist:
            return None
        return report.id if not isinstance(report, ReportUnsafe) else report.trace_id



class DownloadTags:
    def __init__(self, tags_type):
        self._type = tags_type
        self._data = self.__get_tags_data()

    def __iter__(self):
        yield self._data

    def file_size(self):
        return len(self._data)

    def __get_tags_data(self):
        if self._type == 'safe':
            tags_model = SafeTag
        elif self._type == 'unsafe':
            tags_model = UnsafeTag
        else:
            return b''
        tags_data = []
        for tag in tags_model.objects.all():
            tag_data = {'name': tag.tag, 'description': tag.description}
            if tag.parent is not None:
                tag_data['parent'] = tag.parent.tag
            tags_data.append(tag_data)
        return json.dumps(tags_data, ensure_ascii=False, sort_keys=True, indent=4).encode('utf8')


class UpdateAssociationCache:
    def __init__(self, association, recalc):
        self._association = association
        self._recalc = recalc

    def __update(self):
        if isinstance(self._association, MarkSafeReport):
            self.__update_cache(SafeUtils)
        elif isinstance(self._association, MarkUnsafeReport):
            self.__update_cache(UnsafeUtils)
        elif isinstance(self._association, MarkUnknownReport) and self._recalc:
            UnknownUtils.update_unknowns_cache([self._association.report])

    def __update_cache(self, leaf_lib):
        if self._recalc:
            changes = leaf_lib.UpdateVerdicts({self._association.mark_id: {
                self._association.report: {'kind': '=', 'verdict1': self._association.report.verdict}
            }}).changes.get(self._association.mark_id, {})
            leaf_lib.RecalculateTags(list(changes))
        leaf_lib.update_confirmed_cache([self._association.report])
