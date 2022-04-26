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

import os
import io
import json
import zipfile
from wsgiref.util import FileWrapper

from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _

from bridge.vars import MARK_SOURCE, SAFE_VERDICTS, UNSAFE_VERDICTS
from bridge.utils import logger, BridgeException
from bridge.ZipGenerator import ZipStream, CHUNK_SIZE

from marks.models import (
    MarkSafe, MarkUnsafe, MarkUnknown, MarkSafeTag, MarkUnsafeTag, MarkSafeAttr, MarkUnsafeAttr, MarkUnknownAttr
)
from caches.models import ReportSafeCache, ReportUnsafeCache, ReportUnknownCache

from marks.tags import get_all_tags
from marks.serializers import SafeMarkSerializer, UnsafeMarkSerializer, UnknownMarkSerializer
from marks.SafeUtils import ConnectSafeMark
from marks.UnsafeUtils import ConnectUnsafeMark
from marks.UnknownUtils import ConnectUnknownMark
from caches.utils import UpdateCachesOnMarkPopulate


class MarkGeneratorBase:
    type = None
    attrs_model = None
    tags_model = None

    def __init__(self, mark):
        assert self.type is not None, 'Wrong usage'
        self.mark = mark
        self.name = 'Mark-{}-{}.zip'.format(self.type, self.mark.identifier)
        self.stream = ZipStream()

    def common_data(self):
        return {
            'type': self.type,
            'identifier': str(self.mark.identifier),
            'is_modifiable': self.mark.is_modifiable
        }

    def version_data(self, version):
        data = {
            'comment': version.comment,
            'description': version.description,
            'attrs': self.attrs.get(version.id, []),
        }
        if self.tags is not None:
            data['tags'] = self.tags.get(version.id, [])
        return data

    @cached_property
    def attrs(self):
        assert self.attrs_model is not None, 'Wrong usage'
        mark_attrs = {}
        for mattr in self.attrs_model.objects.filter(mark_version__mark=self.mark).order_by('id'):
            mark_attrs.setdefault(mattr.mark_version_id, [])
            mark_attrs[mattr.mark_version_id].append({
                'name': mattr.name, 'value': mattr.value, 'is_compare': mattr.is_compare
            })
        return mark_attrs

    @cached_property
    def tags(self):
        if not self.tags_model:
            return None
        all_tags = {}
        for version_id, tag_name in self.tags_model.objects.filter(mark_version__mark=self.mark) \
                .values_list('mark_version_id', 'tag__name'):
            all_tags.setdefault(version_id, [])
            all_tags[version_id].append(tag_name)
        return all_tags

    def versions_queryset(self):
        return self.mark.versions.all()

    def __iter__(self):
        # Add main mark data
        content = json.dumps(self.common_data(), ensure_ascii=False, sort_keys=True, indent=4)
        for data in self.stream.compress_string('mark.json', content):
            yield data

        # Add versions data
        for markversion in self.versions_queryset():
            content = json.dumps(self.version_data(markversion), ensure_ascii=False, sort_keys=True, indent=4)
            for data in self.stream.compress_string('version-{}.json'.format(markversion.version), content):
                yield data

        yield self.stream.close_stream()


class SafeMarkGenerator(MarkGeneratorBase):
    type = 'safe'
    attrs_model = MarkSafeAttr
    tags_model = MarkSafeTag

    def version_data(self, version):
        data = super().version_data(version)
        data['verdict'] = version.verdict
        return data


class UnsafeMarkGenerator(MarkGeneratorBase):
    type = 'unsafe'
    attrs_model = MarkUnsafeAttr
    tags_model = MarkUnsafeTag

    def versions_queryset(self):
        return self.mark.versions.select_related('error_trace')

    def common_data(self):
        data = super().common_data()
        data['function'] = self.mark.function
        return data

    def version_data(self, version):
        data = super().version_data(version)

        data.update({
            'verdict': version.verdict,
            'status': version.status,
            'threshold': version.threshold_percentage
        })

        if version.error_trace:
            with version.error_trace.file.file as fp:
                data['error_trace'] = fp.read().decode('utf8')
        else:
            data['regexp'] = version.regexp

        return data


class UnknownMarkGenerator(MarkGeneratorBase):
    type = 'unknown'
    attrs_model = MarkUnknownAttr

    def common_data(self):
        data = super().common_data()
        data['component'] = self.mark.component
        return data

    def version_data(self, version):
        data = super().version_data(version)
        data.update({
            'function': version.function,
            'problem_pattern': version.problem_pattern,
            'is_regexp': version.is_regexp,
            'link': version.link
        })
        return data


class SeveralMarksGenerator:
    def __init__(self, marks):
        self.marks = marks
        self.stream = ZipStream()
        self.name = 'KleverMarks.zip'

    def generate_mark(self, markgen):
        buf = b''
        for data in self.stream.compress_stream(markgen.name, markgen):
            buf += data
            if len(buf) > CHUNK_SIZE:
                yield buf
                buf = b''
        if len(buf) > 0:
            yield buf

    def __iter__(self):
        for mark in self.marks:
            if isinstance(mark, MarkSafe):
                markgen = SafeMarkGenerator(mark)
            elif isinstance(mark, MarkUnsafe):
                markgen = UnsafeMarkGenerator(mark)
            elif isinstance(mark, MarkUnknown):
                markgen = UnknownMarkGenerator(mark)
            else:
                continue
            yield from self.generate_mark(markgen)
        yield self.stream.close_stream()


class PresetMarkFile(FileWrapper):
    attrs_model = None

    def __init__(self, mark):
        self.mark = mark
        self.name = '{}.json'.format(self.mark.identifier)
        content = json.dumps(self.get_data(), indent=2, sort_keys=True).encode('utf8')
        self.size = len(content)
        super().__init__(io.BytesIO(content), 8192)

    @cached_property
    def last_version(self):
        return self.mark.versions.filter(version=self.mark.version).first()

    def get_data(self):
        return {
            'is_modifiable': self.mark.is_modifiable,
            'description': self.last_version.description,
            'attrs': list(self.attrs_model.objects.filter(mark_version=self.last_version, is_compare=True)
                          .order_by('id').values('name', 'value', 'is_compare'))
        }


class SafePresetFile(PresetMarkFile):
    attrs_model = MarkSafeAttr

    def get_data(self):
        data = super().get_data()
        data.update({
            'verdict': self.mark.verdict,
            'tags': list(MarkSafeTag.objects.filter(mark_version=self.last_version)
                         .values_list('tag__name', flat=True))
        })
        return data


class UnsafePresetFile(PresetMarkFile):
    attrs_model = MarkUnsafeAttr

    def get_data(self):
        data = super().get_data()
        data.update({
            'verdict': self.mark.verdict,
            'status': self.mark.status,
            'function': self.mark.function,
            'threshold': self.mark.threshold_percentage,
            'tags': list(MarkUnsafeTag.objects.filter(mark_version=self.last_version)
                         .values_list('tag__name', flat=True))
        })
        if self.mark.error_trace:
            with self.mark.error_trace.file.file as fp:
                data['error_trace'] = json.loads(fp.read().decode('utf8'))
        else:
            data['regexp'] = self.mark.regexp
        return data


class UnknownPresetFile(PresetMarkFile):
    attrs_model = MarkUnknownAttr

    def get_data(self):
        data = super().get_data()
        data.update({
            'function': self.mark.function,
            'problem_pattern': self.mark.problem_pattern,
            'is_regexp': self.mark.is_regexp,
            'link': self.mark.link
        })
        return data


class AllMarksGenerator:
    def __init__(self):
        curr_time = now()
        self.name = 'Marks--%s-%s-%s.zip' % (curr_time.day, curr_time.month, curr_time.year)
        self.stream = ZipStream()

    def generators(self):
        for mark in MarkSafe.objects.all():
            yield SafeMarkGenerator(mark)
        for mark in MarkUnsafe.objects.all():
            yield UnsafeMarkGenerator(mark)
        for mark in MarkUnknown.objects.all():
            yield UnknownMarkGenerator(mark)

    def __iter__(self):
        for markgen in self.generators():
            buf = b''
            for data in self.stream.compress_stream(markgen.name, markgen):
                buf += data
                if len(buf) > CHUNK_SIZE:
                    yield buf
                    buf = b''
            if len(buf) > 0:
                yield buf
        yield self.stream.close_stream()


class MarksUploader:
    def __init__(self, user):
        self._user = user
        self._tags_names = self._tags_tree = None

    def __create_safe_mark(self, mark_data, versions_data):
        if self._tags_names is None or self._tags_tree is None:
            self._tags_tree, self._tags_names = get_all_tags()

        mark = None
        for version_number in sorted(versions_data):
            mark_version = versions_data[version_number]
            if mark is None:
                # Get identifier and is_modifiable from mark_data
                mark_version.update(mark_data)
                serializer_fields = ('identifier', 'is_modifiable', 'verdict', 'mark_version')
                save_kwargs = {'source': MARK_SOURCE[2][0], 'author': self._user}
            else:
                serializer_fields = ('verdict', 'mark_version')
                save_kwargs = {}

            serializer = SafeMarkSerializer(instance=mark, data=mark_version, context={
                'tags_names': self._tags_names, 'tags_tree': self._tags_tree
            }, fields=serializer_fields)
            serializer.is_valid(raise_exception=True)
            mark = serializer.save(**save_kwargs)

        # Calculate mark caches
        res = ConnectSafeMark(mark)
        UpdateCachesOnMarkPopulate(mark, res.new_links).update()
        return reverse('marks:safe', args=[mark.id])

    def __create_unsafe_mark(self, mark_data, versions_data):
        if self._tags_names is None or self._tags_tree is None:
            self._tags_tree, self._tags_names = get_all_tags()

        mark = None
        for version_number in sorted(versions_data):
            mark_version = versions_data[version_number]
            if mark is None:
                # Get identifier and is_modifiable from mark_data
                mark_version.update(mark_data)
                serializer_fields = (
                    'identifier', 'is_modifiable', 'verdict', 'mark_version', 'function', 'error_trace', 'regexp'
                )
                save_kwargs = {'source': MARK_SOURCE[2][0], 'author': self._user}
            else:
                serializer_fields = ('verdict', 'mark_version', 'error_trace', 'regexp')
                save_kwargs = {}

            serializer = UnsafeMarkSerializer(instance=mark, data=mark_version, context={
                'tags_names': self._tags_names, 'tags_tree': self._tags_tree
            }, fields=serializer_fields)
            serializer.is_valid(raise_exception=True)
            mark = serializer.save(**save_kwargs)

        # Calculate mark caches
        res = ConnectUnsafeMark(mark)
        UpdateCachesOnMarkPopulate(mark, res.new_links).update()
        return reverse('marks:unsafe', args=[mark.id])

    def __create_unknown_mark(self, mark_data, versions_data):
        mark = None
        for version_number in sorted(versions_data):
            mark_version = versions_data[version_number]
            if mark is None:
                # Get identifier, component and is_modifiable from mark_data
                mark_version.update(mark_data)
                serializer_fields = (
                    'identifier', 'component', 'is_modifiable', 'mark_version',
                    'function', 'is_regexp', 'problem_pattern', 'link'
                )
                save_kwargs = {'source': MARK_SOURCE[2][0], 'author': self._user}
            else:
                serializer_fields = ('mark_version', 'function', 'is_regexp', 'problem_pattern', 'link')
                save_kwargs = {}

            serializer = UnknownMarkSerializer(instance=mark, data=mark_version, fields=serializer_fields)
            serializer.is_valid(raise_exception=True)
            mark = serializer.save(**save_kwargs)

        # Calculate mark caches
        res = ConnectUnknownMark(mark)
        UpdateCachesOnMarkPopulate(mark, res.new_links).update()
        return reverse('marks:unknown', args=[mark.id])

    def upload_mark(self, archive):
        mark_data = None
        versions_data = {}
        with zipfile.ZipFile(archive, 'r') as zfp:
            for file_name in zfp.namelist():
                if file_name == 'mark.json':
                    mark_data = json.loads(zfp.read(file_name).decode('utf8'))
                elif file_name.startswith('version-'):
                    try:
                        version_id = int(os.path.splitext(file_name)[0].replace('version-', ''))
                        versions_data[version_id] = json.loads(zfp.read(file_name).decode('utf8'))
                    except ValueError:
                        raise BridgeException(_("The mark archive is corrupted"))

        if mark_data is None or len(versions_data) == 0:
            raise BridgeException(_("The mark archive is corrupted: it doesn't contain necessary data"))
        if not isinstance(mark_data, dict):
            raise ValueError('Unsupported mark data type: %s' % type(mark_data))

        mark_type = mark_data.pop('type', None)
        if mark_type == 'safe':
            return mark_type, self.__create_safe_mark(mark_data, versions_data)
        elif mark_type == 'unsafe':
            return mark_type, self.__create_unsafe_mark(mark_data, versions_data)
        elif mark_type == 'unknown':
            return mark_type, self.__create_unknown_mark(mark_data, versions_data)
        raise ValueError('Unsupported mark type: %s' % mark_type)


class UploadAllMarks:
    def __init__(self, user, marks_dir, delete_all_marks):
        self._uploader = MarksUploader(user)
        if delete_all_marks:
            self.__clear_old_marks()
        self.numbers = self.__upload_all(marks_dir)

    def __clear_old_marks(self):
        MarkSafe.objects.all().delete()
        MarkUnsafe.objects.all().delete()
        MarkUnknown.objects.all().delete()
        ReportSafeCache.objects.update(
            marks_confirmed=0, marks_automatic=0, marks_total=0, verdict=SAFE_VERDICTS[4][0], tags={}
        )
        ReportUnsafeCache.objects.update(
            marks_confirmed=0, marks_automatic=0, marks_total=0, verdict=UNSAFE_VERDICTS[5][0], tags={}
        )
        ReportUnknownCache.objects.update(
            marks_confirmed=0, marks_automatic=0, marks_total=0, problems={}
        )

    def __upload_all(self, marks_dir):
        upload_result = {'safe': 0, 'unsafe': 0, 'unknown': 0, 'fail': 0}

        for file_name in os.listdir(marks_dir):
            mark_path = os.path.join(marks_dir, file_name)
            if os.path.isfile(mark_path):
                with open(mark_path, mode='rb') as fp:
                    try:
                        mark_type = self._uploader.upload_mark(fp)[0]
                    except Exception as e:
                        logger.exception(e)
                        logger.error('Uploading of mark "{}" has failed.'.format(file_name))
                        mark_type = 'fail'
                    upload_result.setdefault(mark_type, 0)
                    upload_result[mark_type] += 1
        return upload_result
