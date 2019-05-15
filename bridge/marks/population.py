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
import uuid

from django.conf import settings
from django.utils.translation import ugettext as _

from bridge.vars import MARK_SOURCE
from bridge.utils import BridgeException

from marks.models import SafeTag, MarkSafe, UnsafeTag, MarkUnsafe, MarkUnknown
from marks.serializers import (
    SafeMarkSerializer, UnsafeMarkSerializer, UnknownMarkSerializer,
    SafeTagSerializer, UnsafeTagSerializer
)

from marks.SafeUtils import ConnectSafeMark
from marks.UnsafeUtils import ConnectUnsafeMark
from marks.UnknownUtils import ConnectUnknownMark

from caches.utils import UpdateCachesOnMarkPopulate


class PopulateSafeMarks:
    def __init__(self, user=None):
        self.created = 0
        self.total = 0
        self._author = user
        self._tags_tree, self._tags_names = self.__get_all_tags()
        self.__populate()

    def __get_all_tags(self):
        tags_tree = {}
        tags_names = {}
        for t_id, parent_id, t_name in SafeTag.objects.values_list('id', 'parent_id', 'name'):
            tags_tree[t_id] = parent_id
            tags_names[t_name] = t_id
        return tags_tree, tags_names

    def __populate(self):
        presets_dir = os.path.join(settings.BASE_DIR, 'marks', 'presets', 'safes')
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
        self._tags_tree, self._tags_names = self.__get_all_tags()
        self.__populate()

    def __get_all_tags(self):
        tags_tree = {}
        tags_names = {}
        for t_id, parent_id, t_name in UnsafeTag.objects.values_list('id', 'parent_id', 'name'):
            tags_tree[t_id] = parent_id
            tags_names[t_name] = t_id
        return tags_tree, tags_names

    def __populate(self):
        presets_dir = os.path.join(settings.BASE_DIR, 'marks', 'presets', 'unsafes')
        serializer_fields = ('is_modifiable', 'verdict', 'mark_version', 'function')

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
            mark_data['error_trace'] = json.dumps(mark_data.pop('error_trace'))

            serializer = UnsafeMarkSerializer(data=mark_data, context={
                'tags_names': self._tags_names, 'tags_tree': self._tags_tree
            }, fields=serializer_fields)
            serializer.is_valid(raise_exception=True)
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
        presets_dir = os.path.join(settings.BASE_DIR, 'marks', 'presets', 'unknowns')
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


class PopulateSafeTags:
    def __init__(self, user=None):
        self.user = user
        self.created = 0
        self.total = 0
        self.__create_tags()

    def __create_tags(self):
        db_tags = dict((t.name, t) for t in SafeTag.objects.all())
        preset_tags = os.path.join(settings.BASE_DIR, 'marks', 'presets', 'tags', 'safe.json')
        with open(preset_tags, mode='r', encoding='utf-8') as fp:
            list_of_tags = json.load(fp)
            assert isinstance(list_of_tags, list), 'Not a list'
            for data in list_of_tags:
                self.total += 1
                assert isinstance(data, dict), 'Not a dict'
                assert 'name' in data and isinstance(data['name'], str), _('Tag name is required')
                parent = None
                if 'parent' in data:
                    if data['parent'] not in db_tags:
                        raise BridgeException(_('Tag parent should be defined before its children'))
                    parent = db_tags[data.pop('parent')]
                serializer = SafeTagSerializer(data=data)
                serializer.is_valid(raise_exception=True)
                if serializer.validated_data['name'] in db_tags:
                    # Already exists
                    continue
                new_tag = serializer.save(parent=parent, author=self.user, populated=True)
                db_tags[serializer.validated_data['name']] = new_tag
                self.created += 1


class PopulateUnsafeTags:
    def __init__(self, user=None):
        self.user = user
        self.created = 0
        self.total = 0
        self.__create_tags()

    def __create_tags(self):
        db_tags = dict((t.name, t) for t in UnsafeTag.objects.all())
        preset_tags = os.path.join(settings.BASE_DIR, 'marks', 'presets', 'tags', 'unsafe.json')
        with open(preset_tags, mode='r', encoding='utf-8') as fp:
            list_of_tags = json.load(fp)
            assert isinstance(list_of_tags, list), 'Not a list'
            for data in list_of_tags:
                self.total += 1
                assert isinstance(data, dict), 'Not a dict'
                assert 'name' in data and isinstance(data['name'], str), _('Tag name is required')
                parent = None
                if 'parent' in data:
                    if data['parent'] not in db_tags:
                        raise BridgeException(_('Tag parent should be defined before its children'))
                    parent = db_tags[data.pop('parent')]
                serializer = UnsafeTagSerializer(data=data)
                serializer.is_valid(raise_exception=True)
                if serializer.validated_data['name'] in db_tags:
                    # Already exists
                    continue
                new_tag = serializer.save(parent=parent, author=self.user, populated=True)
                db_tags[serializer.validated_data['name']] = new_tag
                self.created += 1
