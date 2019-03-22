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

import os
import json
import zipfile

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _

from bridge.utils import logger, BridgeException
from bridge.ZipGenerator import ZipStream, CHUNK_SIZE

from marks.models import MarkSafe, MarkUnsafe, MarkUnknown, SafeTag, UnsafeTag

import marks.SafeUtils as SafeUtils
import marks.UnsafeUtils as UnsafeUtils
import marks.UnknownUtils as UnknownUtils


class MarkArchiveGenerator:
    def __init__(self, mark):
        self.mark = mark
        if isinstance(self.mark, MarkUnsafe):
            self.type = 'unsafe'
        elif isinstance(self.mark, MarkSafe):
            self.type = 'safe'
        elif isinstance(self.mark, MarkUnknown):
            self.type = 'unknown'
        else:
            return
        self.name = 'Mark-%s-%s.zip' % (self.type, self.mark.identifier[:10])
        self.stream = ZipStream()

    def __iter__(self):
        for markversion in self.mark.versions.all():
            version_data = {
                'status': markversion.status,
                'comment': markversion.comment,
                'description': markversion.description
            }
            if self.type == 'unknown':
                version_data['function'] = markversion.function
                version_data['problem'] = markversion.problem_pattern
                version_data['is_regexp'] = markversion.is_regexp
                if markversion.link is not None:
                    version_data['link'] = markversion.link
            else:
                version_data['attrs'] = []
                for aname, aval, compare in markversion.attrs.order_by('id')\
                        .values_list('attr__name__name', 'attr__value', 'is_compare'):
                    version_data['attrs'].append({'attr': aname, 'value': aval, 'is_compare': compare})

                version_data['tags'] = list(tag for tag, in markversion.tags.values_list('tag__tag'))
                version_data['verdict'] = markversion.verdict

                if self.type == 'unsafe':
                    version_data['function'] = markversion.function.name
                    with markversion.error_trace.file.file as fp:
                        version_data['error_trace'] = fp.read().decode('utf8')

            content = json.dumps(version_data, ensure_ascii=False, sort_keys=True, indent=4)
            for data in self.stream.compress_string('version-%s' % markversion.version, content):
                yield data
        common_data = {
            'is_modifiable': self.mark.is_modifiable,
            'mark_type': self.type,
            'format': self.mark.format,
            'identifier': self.mark.identifier
        }
        if self.type == 'unknown':
            common_data['component'] = self.mark.component.name
        content = json.dumps(common_data, ensure_ascii=False, sort_keys=True, indent=4)
        for data in self.stream.compress_string('markdata', content):
            yield data
        yield self.stream.close_stream()


class PresetMarkFile:
    def __init__(self, mark):
        self._mark = mark
        self.data = json.dumps(self.__get_mark_data(), indent=2, sort_keys=True).encode('utf8')
        self.filename = "%s.json" % self._mark.identifier

    def __iter__(self):
        yield self.data

    def __get_mark_data(self):
        data = {
            'status': self._mark.status, 'is_modifiable': self._mark.is_modifiable,
            'description': self._mark.description, 'attrs': []
        }
        last_version = self._mark.versions.get(version=self._mark.version)
        for a_name, a_val, is_compare in last_version.attrs.order_by('id')\
                .values_list('attr__name__name', 'attr__value', 'is_compare'):
            data['attrs'].append({'attr': a_name, 'value': a_val, 'is_compare': is_compare})

        if isinstance(self._mark, MarkUnknown):
            data.update({
                'pattern': self._mark.function,
                'problem': self._mark.problem_pattern,
                'is regexp': self._mark.is_regexp
            })
            if self._mark.link:
                data['link'] = self._mark.link
        else:
            data.update({'verdict': self._mark.verdict, 'tags': []})
            for t, in last_version.tags.order_by('id').values_list('tag__tag'):
                data['tags'].append(t)

        if isinstance(self._mark, MarkUnsafe):
            data['comparison'] = last_version.function.name
            with last_version.error_trace.file.file as fp:
                data['error trace'] = json.loads(fp.read().decode('utf8'))
        return data


class AllMarksGen(object):
    def __init__(self):
        curr_time = now()
        self.name = 'Marks--%s-%s-%s.zip' % (curr_time.day, curr_time.month, curr_time.year)
        self.stream = ZipStream()

    def __iter__(self):
        for table in [MarkSafe, MarkUnsafe, MarkUnknown]:
            for mark in table.objects.filter(~Q(version=0)):
                markgen = MarkArchiveGenerator(mark)
                buf = b''
                for data in self.stream.compress_stream(markgen.name, markgen):
                    buf += data
                    if len(buf) > CHUNK_SIZE:
                        yield buf
                        buf = b''
                if len(buf) > 0:
                    yield buf
        yield self.stream.close_stream()


class UploadMark:
    def __init__(self, user, archive):
        self.type = None
        self._user = user
        self.mark = self.__upload_mark(archive)

    def __upload_mark(self, archive):

        def get_func_id(func_name):
            try:
                return MarkUnsafeCompare.objects.get(name=func_name).pk
            except ObjectDoesNotExist:
                raise BridgeException(
                    _('The mark comparison function "%(fname)s" is not supported anymore') % {'fname': func_name}
                )

        mark_data = None
        versions_data = {}
        with zipfile.ZipFile(archive, 'r') as zfp:
            for file_name in zfp.namelist():
                if file_name == 'markdata':
                    mark_data = json.loads(zfp.read(file_name).decode('utf8'))
                elif file_name.startswith('version-'):
                    try:
                        version_id = int(file_name.replace('version-', ''))
                        versions_data[version_id] = json.loads(zfp.read(file_name).decode('utf8'))
                    except ValueError:
                        raise BridgeException(_("The mark archive is corrupted"))

        if mark_data is None or len(versions_data) == 0:
            raise BridgeException(_("The mark archive is corrupted: it doesn't contain necessary data"))
        if not isinstance(mark_data, dict):
            raise ValueError('Unsupported mark data type: %s' % type(mark_data))
        self.type = mark_data.get('mark_type')
        if self.type == 'unsafe':
            for v_id in versions_data:
                if 'function' not in versions_data[v_id]:
                    raise BridgeException(_('The mark archive is corrupted'))

        version_list = list(versions_data[v] for v in sorted(versions_data))

        if self.type == 'safe':
            tags_in_db = dict(SafeTag.objects.values_list('tag', 'id'))
            for version in version_list:
                version['tags'] = list(tags_in_db[tname] for tname in version['tags'])
        elif self.type == 'unsafe':
            tags_in_db = dict(UnsafeTag.objects.values_list('tag', 'id'))
            for version in version_list:
                version['tags'] = list(tags_in_db[tname] for tname in version['tags'])
                version['compare_id'] = get_func_id(version['function'])
                del version['function']
        return self.__create_mark(mark_data, version_list)

    def __create_mark(self, mark_data, versions):
        mark_utils = {'safe': SafeUtils, 'unsafe': UnsafeUtils, 'unknown': UnknownUtils}
        versions[0].update(mark_data)
        res = mark_utils[self.type].NewMark(self._user, versions[0])
        mark = res.upload_mark()
        for version_data in versions[1:]:
            version_data.update(mark_data)
            try:
                mark_utils[self.type].NewMark(self._user, version_data).change_mark(mark, False)
            except Exception:
                mark.delete()
                raise
        if self.type == 'safe':
            SafeUtils.RecalculateTags(list(SafeUtils.ConnectMarks([mark]).changes.get(mark.id, {})))
        elif self.type == 'unsafe':
            UnsafeUtils.RecalculateTags(list(UnsafeUtils.ConnectMarks([mark]).changes.get(mark.id, {})))
        elif self.type == 'unknown':
            UnknownUtils.ConnectMark(mark)
        return mark

    def __is_not_used(self):
        pass


class UploadAllMarks:
    def __init__(self, user, marks_dir, delete_all_marks):
        self.user = user
        self.numbers = {'safe': 0, 'unsafe': 0, 'unknown': 0, 'fail': 0}
        self.delete_all = delete_all_marks
        self.__upload_all(marks_dir)

    def __upload_all(self, marks_dir):
        if self.delete_all:
            SafeUtils.delete_marks(MarkSafe.objects.all())
            UnsafeUtils.delete_marks(MarkUnsafe.objects.all())
            UnknownUtils.delete_marks(MarkUnknown.objects.all())
        for file_name in os.listdir(marks_dir):
            mark_path = os.path.join(marks_dir, file_name)
            if os.path.isfile(mark_path):
                with open(mark_path, mode='rb') as fp:
                    try:
                        mark_type = UploadMark(self.user, fp).type
                        if mark_type in self.numbers:
                            self.numbers[mark_type] += 1
                    except Exception as e:
                        logger.exception(e)
                        self.numbers['fail'] += 1
