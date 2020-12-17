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

import json
from collections import OrderedDict

from django.utils.functional import cached_property

from rest_framework import fields
from rest_framework.generics import get_object_or_404

from bridge.vars import USER_ROLES
from bridge.utils import logger, BridgeException

from users.models import User
from marks.models import MAX_TAG_LEN, Tag, TagAccess


def get_all_tags():
    tags_tree = {}
    tags_names = {}
    for t_id, parent_id, t_name in Tag.objects.values_list('id', 'parent_id', 'name'):
        tags_tree[t_id] = parent_id
        tags_names[t_name] = t_id
    return tags_tree, tags_names


class TagsTree:
    def __init__(self, tags_ids=None):
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
        tags_qs = Tag.objects
        if self.selected_tags:
            tags_qs = tags_qs.exclude(id__in=self.selected_tags)
        return list({'id': t.id, 'name': t.name} for t in tags_qs.only('id', 'name'))

    def tag_data(self, tag):
        return {'type': 'tag', 'value': tag}

    def __get_tree(self):
        tags_qs = Tag.objects
        if isinstance(self._tags_ids, (list, set)):
            tags_qs = tags_qs.filter(id__in=self._tags_ids)

        data = OrderedDict()
        for tag in tags_qs.select_related('author').order_by('id'):
            data[tag.pk] = {
                'object': tag,
                'parent': tag.parent_id,
                'children': []
            }
        for t_id in data:
            if not data[t_id]['parent']:
                continue
            if data[t_id]['parent'] not in data:
                logger.error('Tag {} does not have parent'.format(data[t_id]['object'].name))
                continue
            data[data[t_id]['parent']]['children'].append(data[t_id]['object'].id)
        return data

    def __fill_matrix(self):
        root_tags = []
        for t_id in self._tree:
            if self._tree[t_id]['parent'] is None:
                root_tags.append((t_id, self._tree[t_id]['object'].name))
        tag_row = 0
        for t_id, __ in sorted(root_tags, key=lambda x: x[0]):
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
    def __init__(self, user):
        super().__init__()
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
        data = {}
        for tag_access in TagAccess.objects.filter(user=self.user):
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
        super().__init__(tags_ids=list(mark_version.tags.values_list('tag_id', flat=True)))


class SelectedTagsTree(TagsTree):
    def __init__(self, selected, deleted, added):
        super().__init__(tags_ids=self.__get_ids(selected, deleted, added))

    def __get_ids(self, selected, deleted, added):
        tags_ids = set(int(x) for x in selected)

        if deleted:
            tags_ids -= set(Tag.objects.get(id=deleted).get_descendants(include_self=True).values_list('id', flat=True))
        elif added:
            tags_ids |= set(Tag.objects.get(id=added).get_ancestors(include_self=True).values_list('id', flat=True))
        return tags_ids


class TagAccessInfo:
    def __init__(self, user, tag):
        self.user = user
        self.tag = tag

    @cached_property
    def _args_valid(self):
        return isinstance(self.user, User) and isinstance(self.tag, Tag)

    @cached_property
    def _is_manager(self):
        return isinstance(self.user, User) and self.user.role == USER_ROLES[2][0]

    @cached_property
    def _has_edit_access(self):
        if not self._args_valid:
            return False
        return TagAccess.objects.filter(tag=self.tag, user=self.user, modification=True).exists()

    @cached_property
    def _has_child_access(self):
        if not self._args_valid:
            return False
        return TagAccess.objects.filter(tag=self.tag, user=self.user, child_creation=True).exists()

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
    def __init__(self, tag_id):
        self.tag = self.__get_tag(tag_id)

    def __get_tag(self, tag_id):
        return get_object_or_404(Tag, id=tag_id)

    def save(self, data):
        can_edit = set()
        if data.get('can_edit'):
            can_edit = set(int(x) for x in data['can_edit'])
        can_create = set()
        if data.get('can_create'):
            can_create = set(int(x) for x in data['can_create'])
        new_access_objects = list(TagAccess(
            user=user, tag=self.tag,
            modification=(user.id in can_edit),
            child_creation=(user.id in can_create)
        ) for user in User.objects.filter(id__in=can_edit | can_create))
        TagAccess.objects.filter(tag=self.tag).delete()
        TagAccess.objects.bulk_create(new_access_objects)

    @property
    def data(self):
        access_qs = TagAccess.objects.filter(tag=self.tag)
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
    def __init__(self):
        self._data = json.dumps(self.__get_children(None), ensure_ascii=False, indent=2).encode('utf8')
        self.name = 'Tags.json'
        self.size = len(self._data)

    def __iter__(self):
        yield self._data

    @cached_property
    def _db_tags(self):
        db_tags = OrderedDict()
        for tag in Tag.objects.order_by('id'):
            db_tags[tag.id] = {
                'parent': tag.parent_id,
                'name': tag.shortname
            }
            if tag.description:
                db_tags[tag.id]['description'] = tag.description
        return db_tags

    def __get_children(self, parent_id):
        children = []
        for t_id in self._db_tags:
            if self._db_tags[t_id]['parent'] != parent_id:
                continue
            child = OrderedDict()
            child['name'] = self._db_tags[t_id]['name']
            if 'description' in self._db_tags[t_id]:
                child['description'] = self._db_tags[t_id]['description']
            child_children = self.__get_children(t_id)
            if child_children:
                child['children'] = child_children
            children.append(child)
        return children


class UploadTagsTree:
    def __init__(self, user, tags_tree, populated=False):
        self.user = user
        self.total = 0
        self.created = 0
        self._populated = populated
        self.__upload_tags(None, tags_tree)

    @cached_property
    def _db_tags(self):
        return dict((t.name, t) for t in Tag.objects.all())

    def __upload_tags(self, parent, tags):
        assert isinstance(tags, list), 'Not a list'
        for tag_data in tags:
            assert isinstance(tag_data, dict), 'Not a dict'
            tag = self.__create_tag(parent, tag_data)

            if 'children' in tag_data:
                # Recursively create all children
                self.__upload_tags(tag, tag_data['children'])

    def __create_tag(self, parent, tag_data):
        self.total += 1
        name = fields.CharField(max_length=MAX_TAG_LEN).run_validation(tag_data.get('name', ''))
        if parent is not None:
            name = '{} - {}'.format(parent.name, name)
        if name in self._db_tags:
            # The tag already exists
            return self._db_tags[name]
        description = fields.CharField(allow_blank=True).run_validation(tag_data.get('description', ''))

        new_tag = Tag.objects.create(
            parent=parent, name=name, description=description, author=self.user, populated=self._populated
        )
        self.created += 1
        self._db_tags[new_tag.name] = new_tag
        return new_tag
