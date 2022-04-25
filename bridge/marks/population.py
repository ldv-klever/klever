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
import json
import uuid

from django.conf import settings
from django.utils.translation import gettext as _

from bridge.vars import MARK_SOURCE
from bridge.utils import logger, BridgeException

from marks.models import MarkSafe, MarkUnsafe, MarkUnknown

from marks.serializers import SafeMarkSerializer, UnsafeMarkSerializer, UnknownMarkSerializer
from marks.SafeUtils import ConnectSafeMark
from marks.UnsafeUtils import ConnectUnsafeMark
from marks.UnknownUtils import ConnectUnknownMark
from marks.tags import get_all_tags, UploadTagsTree
from caches.utils import UpdateCachesOnMarkPopulate


def get_presets_dir():
    presets_path = os.path.join(settings.BASE_DIR, 'marks', 'presets')
    if os.path.isdir(presets_path):
        return presets_path
    with open(presets_path, mode='r', encoding='utf-8') as fp:
        presets_path = fp.read()
    return os.path.abspath(os.path.join(settings.BASE_DIR, 'marks', presets_path))


def populate_tags():
    preset_tags = os.path.join(get_presets_dir(), 'tags.json')
    with open(preset_tags, mode='r', encoding='utf-8') as fp:
        res = UploadTagsTree(None, json.load(fp), populated=True)
    return res.created, res.total


class PopulateSafeMarks:
    def __init__(self, user=None):
        self.created = 0
        self.total = 0
        self._author = user
        self._tags_tree, self._tags_names = get_all_tags()
        self.__populate()

    def __populate(self):
        presets_dir = os.path.join(get_presets_dir(), 'safes')
        serializer_fields = ('is_modifiable', 'verdict', 'mark_version')

        for mark_filename in os.listdir(presets_dir):
            mark_path = os.path.join(presets_dir, mark_filename)
            if not os.path.isfile(mark_path):
                continue
            self.total += 1
            identifier = uuid.UUID(os.path.splitext(mark_filename)[0])

            # The mark was already uploaded
            if MarkSafe.objects.filter(identifier=identifier).exists():
                continue

            with open(mark_path, encoding='utf8') as fp:
                mark_data = json.load(fp)

            if not isinstance(mark_data, dict):
                raise BridgeException(_('Corrupted preset safe mark: wrong format'))

            if settings.POPULATE_JUST_PRODUCTION_PRESETS and not mark_data.get('production'):
                # Do not populate non-production marks
                continue

            serializer = SafeMarkSerializer(data=mark_data, context={
                'tags_names': self._tags_names, 'tags_tree': self._tags_tree
            }, fields=serializer_fields)
            serializer.is_valid(raise_exception=True)
            mark = serializer.save(identifier=identifier, author=self._author, source=MARK_SOURCE[1][0])
            res = ConnectSafeMark(mark)
            UpdateCachesOnMarkPopulate(mark, res.new_links).update()
            self.created += 1


class PopulateUnsafeMarks:
    def __init__(self, user=None):
        self.created = 0
        self.total = 0
        self._author = user
        self._tags_tree, self._tags_names = get_all_tags()
        self.__populate()

    def __populate(self):
        presets_dir = os.path.join(get_presets_dir(), 'unsafes')
        serializer_fields = ('is_modifiable', 'verdict', 'mark_version', 'function', 'error_trace', 'regexp')

        for mark_filename in os.listdir(presets_dir):
            mark_path = os.path.join(presets_dir, mark_filename)
            if not os.path.isfile(mark_path):
                continue
            self.total += 1
            identifier = uuid.UUID(os.path.splitext(mark_filename)[0])

            # The mark was already uploaded
            if MarkUnsafe.objects.filter(identifier=identifier).exists():
                continue

            with open(mark_path, encoding='utf8') as fp:
                mark_data = json.load(fp)

            if not isinstance(mark_data, dict):
                raise BridgeException(_('Corrupted preset unsafe mark: wrong format'))

            if settings.POPULATE_JUST_PRODUCTION_PRESETS and not mark_data.get('production'):
                # Do not populate non-production marks
                continue

            # For serializer
            error_trace = mark_data.pop('error_trace', None)
            if error_trace is not None:
                mark_data['error_trace'] = json.dumps(error_trace)

            serializer = UnsafeMarkSerializer(data=mark_data, context={
                'tags_names': self._tags_names, 'tags_tree': self._tags_tree
            }, fields=serializer_fields)
            try:
                serializer.is_valid(raise_exception=True)
            except Exception:
                logger.error(f'Population of mark "{mark_filename}" failed!')
                raise
            mark = serializer.save(identifier=identifier, author=self._author, source=MARK_SOURCE[1][0])
            res = ConnectUnsafeMark(mark)
            UpdateCachesOnMarkPopulate(mark, res.new_links).update()
            self.created += 1


class PopulateUnknownMarks:
    def __init__(self, user=None):
        self.created = 0
        self.total = 0
        self._author = user
        self.__populate()

    def __populate(self):
        presets_dir = os.path.join(get_presets_dir(), 'unknowns')
        serializer_fields = (
            'component', 'is_modifiable', 'mark_version',
            'function', 'is_regexp', 'problem_pattern', 'link'
        )

        for component in os.listdir(presets_dir):
            component_dir = os.path.join(presets_dir, component)
            if not os.path.isdir(component_dir):
                continue
            for mark_filename in os.listdir(component_dir):
                mark_path = os.path.join(component_dir, mark_filename)
                if not os.path.isfile(mark_path):
                    continue
                self.total += 1
                identifier = uuid.UUID(os.path.splitext(mark_filename)[0])

                # The mark was already uploaded
                if MarkUnknown.objects.filter(identifier=identifier).exists():
                    continue

                with open(mark_path, encoding='utf8') as fp:
                    mark_data = json.load(fp)

                if not isinstance(mark_data, dict):
                    raise BridgeException(_('Corrupted preset unknown mark: wrong format'))

                if settings.POPULATE_JUST_PRODUCTION_PRESETS and not mark_data.get('production'):
                    # Do not populate non-production marks
                    continue

                # Use component from data if provided
                mark_data['component'] = mark_data.pop('component', component)

                serializer = UnknownMarkSerializer(data=mark_data, fields=serializer_fields)
                serializer.is_valid(raise_exception=True)
                mark = serializer.save(identifier=identifier, author=self._author, source=MARK_SOURCE[1][0])
                res = ConnectUnknownMark(mark)
                UpdateCachesOnMarkPopulate(mark, res.new_links).update()
                self.created += 1
