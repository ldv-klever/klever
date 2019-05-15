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

from django.utils.translation import ugettext_lazy as _
from django.utils.functional import cached_property

from rest_framework.generics import get_object_or_404

from bridge.vars import USER_ROLES
from bridge.utils import logger, BridgeException

from users.models import User
from marks.models import SafeTag, UnsafeTag, SafeTagAccess, UnsafeTagAccess, MarkSafeHistory, MarkUnsafeHistory
from marks.serializers import SafeTagSerializer, UnsafeTagSerializer
from caches.utils import UpdateSafeMarksTags, UpdateUnsafeMarksTags


class TagsTree:
    def __init__(self, tags_type, tags_ids=None):
        self.type = tags_type
        self._tags_ids = tags_ids
        self._data = {}
        self._tree = self.__get_tree()
        self._max_col = 0

    @cached_property
    def table(self):
        self.__fill_matrix()
        if not len(self._data):
            return []
        table_rows = []
        for row in range(max(self._data) + 1):
            row_list = []
            for col in range(self._max_col + 1):
                if row in self._data and col in self._data[row]:
                    row_list.append(self._data[row][col])
                else:
                    row_list.append(None)
            table_rows.append(row_list)
        return table_rows

    @cached_property
    def selected_tags(self):
        if not self._tags_ids:
            return []
        return list(t['object'].id for t in self._tree.values())

    @cached_property
    def available_tags(self):
        if self.type == 'safe':
            tags_qs = SafeTag.objects
        elif self.type == 'unsafe':
            tags_qs = UnsafeTag.objects
        else:
            raise BridgeException()
        if self.selected_tags:
            tags_qs = tags_qs.exclude(id__in=self.selected_tags)
        return list({'id': t.id, 'name': t.name} for t in tags_qs.only('id', 'name'))

    def tag_data(self, tag):
        return {'type': 'tag', 'value': tag}

    def __get_tree(self):
        if self.type == 'safe':
            tags_qs = SafeTag.objects
        elif self.type == 'unsafe':
            tags_qs = UnsafeTag.objects
        else:
            raise BridgeException()
        if isinstance(self._tags_ids, (list, set)):
            tags_qs = tags_qs.filter(id__in=self._tags_ids)

        data = {}
        for tag in tags_qs.select_related('author').order_by('id'):
            if tag.parent_id and tag.parent_id not in data:
                logger.error('Tag {} does not have parent'.format(tag.name))
                continue
            data[tag.pk] = {
                'object': tag,
                'parent': tag.parent_id,
                'children': []
            }
            if tag.parent_id:
                data[tag.parent_id]['children'].append(tag.pk)
        return data

    def __fill_matrix(self):
        root_tags = []
        for t_id in self._tree:
            if self._tree[t_id]['parent'] is None:
                root_tags.append((t_id, self._tree[t_id]['object'].name))
        tag_row = 0
        for t_id, __ in sorted(root_tags, key=lambda x: x[1]):
            last_row = self.__add_tag(t_id, row=tag_row)
            tag_row = last_row + 2

    def __add_lines(self, row, col, lines):
        self._data.setdefault(row, {})
        if col in self._data[row]:
            for line_id in lines:
                if line_id in self._data[row][col]['value']:
                    continue
                self._data[row][col]['value'] += line_id
        else:
            self._data[row][col] = {'type': 'link', 'value': lines}

    def __link(self, row1, row2, col):
        if row1 == row2:
            self.__add_lines(row1, col, 'LR')
            return
        elif row1 > row2:
            row1, row2 = row2, row1

        self.__add_lines(row1, col, 'LB')
        for r in range(row1 + 1, row2):
            self.__add_lines(r, col, 'TB')
        self.__add_lines(row2, col, 'TR')

    def __add_tag(self, tag_id, row=0, col=0):
        if col > self._max_col:
            self._max_col = col

        self._data.setdefault(row, {})
        self._data[row][col] = self.tag_data(self._tree[tag_id]['object'])
        child_row = row
        last_row = child_row
        for child_id in self._tree[tag_id]['children']:
            last_row = self.__add_tag(child_id, row=child_row, col=col + 2)
            self.__link(row, child_row, col + 1)
            child_row = last_row + 2
        return last_row


class AllTagsTree(TagsTree):
    def __init__(self, user, tags_type):
        super().__init__(tags_type)
        self.user = user
        self.can_create = self._is_manager

    def tag_data(self, tag):
        data = super().tag_data(tag)
        data['access'] = self.__get_access(tag)
        return data

    def __get_access(self, tag):
        if not isinstance(self.user, User):
            raise BridgeException()
        if self._is_manager:
            return dict((f, True) for f in ['edit', 'add_child', 'delete', 'change_access'])
        access = dict((f, False) for f in ['edit', 'add_child', 'delete'])
        if tag.id in self._access_data:
            access.update(self._access_data[tag.id])
        if access['edit'] and tag.id in self._leaves:
            access['delete'] = True
        return access

    @cached_property
    def _leaves(self):
        return set(t_id for t_id in self._tree if len(self._tree[t_id]['children']) == 0)

    @cached_property
    def _access_data(self):
        if self.type == 'safe':
            access_qs = SafeTagAccess.objects
        else:
            access_qs = UnsafeTagAccess.objects
        data = {}
        for tag_access in access_qs.filter(user=self.user):
            data[tag_access.tag_id] = {
                'edit': tag_access.modification,
                'add_child': tag_access.child_creation,
            }
        return data

    @cached_property
    def _is_manager(self):
        return isinstance(self.user, User) and self.user.role == USER_ROLES[2][0]


class MarkTagsTree(TagsTree):
    def __init__(self, mark_version):
        if isinstance(mark_version, MarkSafeHistory):
            tags_type = 'safe'
        elif isinstance(mark_version, MarkUnsafeHistory):
            tags_type = 'unsafe'
        else:
            raise ValueError('Wrong mark version type')
        super().__init__(tags_type, tags_ids=list(mark_version.tags.values_list('tag_id', flat=True)))


class SelectedTagsTree(TagsTree):
    def __init__(self, tags_type, selected, deleted, added):
        super().__init__(tags_type, tags_ids=self.__get_ids(tags_type, selected, deleted, added))

    def __get_ids(self, tags_type, selected, deleted, added):
        selected_tags = set(int(x) for x in selected)

        if tags_type == 'safe':
            tag_qs = SafeTag.objects
        else:
            tag_qs = UnsafeTag.objects

        if deleted:
            selected_tags -= set(tag_qs.get(id=deleted).get_descendants(include_self=True).values_list('id', flat=True))
        elif added:
            selected_tags |= set(tag_qs.get(id=added).get_ancestors(include_self=True).values_list('id', flat=True))
        return selected_tags


class TagAccess:
    def __init__(self, user, tag):
        self.user = user
        self.tag = tag

    @cached_property
    def _args_valid(self):
        return isinstance(self.user, User) and isinstance(self.tag, (SafeTag, UnsafeTag))

    @cached_property
    def _is_manager(self):
        return isinstance(self.user, User) and self.user.role == USER_ROLES[2][0]

    @cached_property
    def _has_edit_access(self):
        if not self._args_valid:
            return False
        if isinstance(self.tag, SafeTag):
            access_qs = SafeTagAccess.objects
        else:
            access_qs = UnsafeTagAccess.objects
        return access_qs.filter(tag=self.tag, user=self.user, modification=True).exists()

    @cached_property
    def _has_child_access(self):
        if not self._args_valid:
            return False
        if isinstance(self.tag, SafeTag):
            access_qs = SafeTagAccess.objects
        else:
            access_qs = UnsafeTagAccess.objects
        return access_qs.filter(tag=self.tag, user=self.user, child_creation=True).exists()

    @cached_property
    def _is_leaf(self):
        return self._args_valid and self.tag.children.count() == 0

    @property
    def edit(self):
        return self._is_manager or self._has_edit_access

    @property
    def create(self):
        return self._is_manager or self._has_child_access

    @property
    def delete(self):
        return self._is_manager or self._is_leaf and self._has_edit_access

    @property
    def change_access(self):
        return self._is_manager


class ChangeTagsAccess:
    def __init__(self, tags_type, tag_id, ):
        self._type = tags_type
        self.tag = self.__get_tag(tag_id)

    def __get_tag(self, tag_id):
        return get_object_or_404(SafeTag if self._type == 'safe' else UnsafeTag, id=tag_id)

    def save(self, data):
        if self._type == 'safe':
            access_model = SafeTagAccess
        else:
            access_model = UnsafeTagAccess

        can_edit = set()
        if data.get('can_edit'):
            can_edit = set(int(x) for x in data['can_edit'])
        can_create = set()
        if data.get('can_create'):
            can_create = set(int(x) for x in data['can_create'])
        new_access_objects = list(access_model(
            user=user, tag=self.tag,
            modification=(user.id in can_edit),
            child_creation=(user.id in can_create)
        ) for user in User.objects.filter(id__in=can_edit | can_create))
        access_model.objects.filter(tag=self.tag).delete()
        access_model.objects.bulk_create(new_access_objects)

    @property
    def data(self):
        if self._type == 'safe':
            access_qs = SafeTagAccess.objects.filter(tag=self.tag)
        else:
            access_qs = UnsafeTagAccess.objects.filter(tag=self.tag)
        can_edit = set(obj.user_id for obj in access_qs if obj.modification)
        can_create = set(obj.user_id for obj in access_qs if obj.child_creation)
        all_users = []
        for user in User.objects.exclude(role=USER_ROLES[2][0]).order_by('last_name', 'first_name'):
            all_users.append({
                'id': user.id,
                'name': user.get_full_name(),
                'can_edit': user.id in can_edit,
                'can_create': user.id in can_create
            })
        return all_users


class DownloadTags:
    def __init__(self, tags_type):
        self._type = tags_type
        self._data = self.__get_tags_data()
        self.name = 'Tags-{}.json'.format(self._type)
        self.size = len(self._data)

    def __iter__(self):
        yield self._data

    def __get_tags_data(self):
        if self._type == 'safe':
            tags_model = SafeTag
        elif self._type == 'unsafe':
            tags_model = UnsafeTag
        else:
            return b''
        tags_data = []
        for tag in tags_model.objects.select_related('parent').order_by('id'):
            tag_data = {'name': tag.name, 'description': tag.description}
            if tag.parent is not None:
                tag_data['parent'] = tag.parent.name
            tags_data.append(tag_data)
        return json.dumps(tags_data, ensure_ascii=False, sort_keys=True, indent=2).encode('utf8')


class UploadTags:
    def __init__(self, user, tags_type, file):
        self.user = user
        self._type = tags_type
        self._data = json.loads(file.read().decode('utf8'))
        self._db_tags = self.__get_db_tags()
        self.number = self.__create_tags()
        self.__update_caches()

    def __get_serialiser(self, data):
        if self._type == 'safe':
            return SafeTagSerializer(data=data)
        return UnsafeTagSerializer(data=data)

    def __get_db_tags(self):
        if self._type == 'safe':
            queryset = SafeTag.objects.all()
        else:
            queryset = UnsafeTag.objects.all()
        return dict((t.name, t.id) for t in queryset)

    def __create_tags(self):
        number = 0
        if not isinstance(self._data, list):
            raise BridgeException(_('Wrong tags format'))
        for tag_data in self._data:
            if not isinstance(tag_data, dict):
                raise BridgeException(_('Wrong tags format'))
            parent = None
            if 'parent' in tag_data:
                if tag_data['parent'] not in self._db_tags:
                    raise BridgeException(_('Tag parent does not exist'))
                parent = self._db_tags[tag_data.pop('parent')]
            serializer = self.__get_serialiser(tag_data)
            serializer.is_valid(raise_exception=True)
            if serializer.validated_data['name'] in self._db_tags:
                # Already exists
                continue
            new_tag = serializer.save(parent_id=parent, author=self.user, populated=False)
            self._db_tags[new_tag.name] = new_tag.id
            number += 1
        return number

    def __update_caches(self):
        if self.number == 0:
            # Nothing was uploaded
            return
        if self._type == 'safe':
            UpdateSafeMarksTags()
        else:
            UpdateUnsafeMarksTags()
