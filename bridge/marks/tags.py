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
from django.db.models import Q
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import ugettext_lazy as _
from bridge.vars import USER_ROLES
from bridge.utils import logger, BridgeException

from users.models import User
from marks.models import SafeTag, UnsafeTag, SafeTagAccess, UnsafeTagAccess


class TagAccess:
    def __init__(self, user, tag):
        self.user = user
        self.tag = tag
        self._is_manager = self.__is_manager()

    def __is_manager(self):
        return self.user is not None and self.user.role == USER_ROLES[2][0]

    def __has_edit_access(self):
        if self.tag is None or self.user is None:
            return False
        access_table = SafeTagAccess if isinstance(self.tag, SafeTag) else UnsafeTagAccess
        try:
            return access_table.objects.get(user=self.user, tag=self.tag).modification
        except ObjectDoesNotExist:
            return False

    def __has_child_access(self):
        if self.tag is None or self.user is None:
            return False
        access_table = SafeTagAccess if isinstance(self.tag, SafeTag) else UnsafeTagAccess
        try:
            return access_table.objects.get(user=self.user, tag=self.tag).child_creation
        except ObjectDoesNotExist:
            return False

    def __is_leaf(self):
        return self.tag.children.count() == 0

    def edit(self):
        return self._is_manager or self.__has_edit_access()

    def create(self):
        return self._is_manager or self.__has_child_access()

    def delete(self):
        return self._is_manager or self.__is_leaf() and self.__has_edit_access()


class TagTable(object):
    def __init__(self):
        self.rows = 0
        self.columns = 0
        self.data = {}
        self.added = []

    def add(self, column, row, tag):
        self.data["%s_%s" % (column, row)] = tag
        self.added.append(tag.id)
        self.rows = max(self.rows, row)
        self.columns = max(self.columns, column)

    def fill_other(self):
        for c in range(1, self.columns + 1):
            for r in range(1, self.rows + 1):
                if ("%s_%s" % (c, r)) not in self.data:
                    self.data["%s_%s" % (c, r)] = None
        for c in range(1, self.columns + 1):
            for r in range(1, self.rows + 1):
                if isinstance(self.data["%s_%s" % (c, r)], TagData):
                    self.__connect_with_children(c, r)

    def __connect_with_children(self, col, row):
        if col > (self.columns - 2):
            return
        children_rows = []
        for r in list(range(1, self.rows + 1))[(row - 1):]:
            if isinstance(self.data["%s_%s" % (col + 2, r)], TagData):
                if self.data["%s_%s" % (col + 2, r)].parent == self.data["%s_%s" % (col, row)].id:
                    children_rows.append(r)
        if len(children_rows) == 0:
            return

        if len(children_rows) > 1:
            self.data["%s_%s" % (col + 1, row)] = 'LRB'
            self.data["%s_%s" % (col + 1, children_rows[-1])] = 'TR'
        else:
            self.data["%s_%s" % (col + 1, row)] = 'LR'

        for r in reversed(range(row + 1, children_rows[-1])):
            if r in children_rows:
                self.data["%s_%s" % (col + 1, r)] = 'TRB'
            else:
                self.data["%s_%s" % (col + 1, r)] = 'TB'

    def prepare_for_vis(self):
        newdata = []
        for row in range(1, self.rows + 1):
            datarow = []
            for col in range(1, self.columns + 1):
                datarow.append(self.data['%s_%s' % (col, row)])
            newdata.append(datarow)
        self.data = newdata


class TagData:
    def __init__(self, user, tag):
        self.id = tag.pk
        self.parent = tag.parent_id
        self.name = tag.tag
        self.children = list(child.pk for child in tag.children.all())
        self.description = tag.description
        self.populated = tag.populated
        self.author = tag.author.get_full_name()
        self._access = TagAccess(user, tag)
        self.can_edit = self._access.edit()
        self.can_delete = self._access.delete()
        self.can_create_the_child = self._access.create()

    def __repr__(self):
        return "<Tag: '%s'>" % self.name


class GetTagsData:
    def __init__(self, tags_type, tag_ids=None, user=None):
        self._type = tags_type
        self.user = user
        self.tags = []
        self.tag_ids = tag_ids
        if self._type not in {'safe', 'unsafe'}:
            raise BridgeException()
        self.__get_tags()
        self.table = TagTable()
        self.__fill_table()

    def __get_tags(self):
        parents = []
        while True:
            if len(parents) > 0:
                tags_filter = {'parent_id__in': parents}
            else:
                tags_filter = {'parent': None}
            if self.tag_ids is not None:
                tags_filter['id__in'] = self.tag_ids
            if self._type == 'safe':
                next_level = [TagData(self.user, tag) for tag in SafeTag.objects.filter(**tags_filter).order_by('tag')]
            else:
                next_level = \
                    [TagData(self.user, tag) for tag in UnsafeTag.objects.filter(**tags_filter).order_by('tag')]
            if len(next_level) == 0:
                return
            self.tags.append(next_level)
            parents = list(x.id for x in next_level)

    def __fill_table(self):
        if len(self.tags) == 0:
            return
        curr_col = -1
        curr_row = 1
        id1 = -1
        id2 = 0
        while True:
            if id1 == -2:
                break
            new_tag_added = False
            while True:
                child_ind = self.__get_next_child(id1, id2)
                if child_ind is None:
                    break
                id1 += 1
                id2 = child_ind
                curr_col += 2
                self.table.add(curr_col, curr_row, self.tags[id1][id2])
                new_tag_added = True
            parent_ind = self.__get_parent(id1, id2)
            if parent_ind is None:
                id1 -= 1
                id2 = 0
                curr_col -= 2
            else:
                id1 -= 1
                id2 = parent_ind
                curr_col -= 2
            if new_tag_added:
                curr_row += 2
        self.table.fill_other()
        self.table.prepare_for_vis()

    def __get_next_child(self, id1, id2):
        if len(self.tags) < id1 + 2:
            return None
        for i in range(0, len(self.tags[id1 + 1])):
            if id1 == -1:
                if self.tags[id1 + 1][i].id not in self.table.added:
                    return i
                continue
            if self.tags[id1 + 1][i].id in self.tags[id1][id2].children \
                    and self.tags[id1 + 1][i].id not in self.table.added:
                return i
        return None

    def __get_parent(self, id1, id2):
        if id1 <= 0:
            return None
        for i in range(0, len(self.tags[id1 - 1])):
            if self.tags[id1 - 1][i].id == self.tags[id1][id2].parent:
                return i
        return None


class GetParents:
    def __init__(self, tag_id, tag_type):
        self._tag_table = None
        self.tag = self.__get_tag(tag_id, tag_type)
        self._black_parents = self.__get_black_parents()
        self.parents_ids = self.__get_parents()

    def __get_tag(self, tag_id, tag_type):
        if tag_type == 'safe':
            self._tag_table = SafeTag
        elif tag_type == 'unsafe':
            self._tag_table = UnsafeTag
        else:
            raise BridgeException()
        try:
            return self._tag_table.objects.get(pk=tag_id)
        except ObjectDoesNotExist:
            raise BridgeException(_('The tag was not found'))

    def __get_black_parents(self):
        black = [self.tag.pk]
        while True:
            old_len = len(black)
            black.extend(
                list(child.pk for child in self._tag_table.objects.filter(Q(parent_id__in=black) & ~Q(id__in=black)))
            )
            if old_len == len(black):
                break
        if self.tag.parent is not None:
            black.append(self.tag.parent_id)
        return black

    def __get_parents(self):
        return list(tag.pk for tag in self._tag_table.objects.filter(~Q(id__in=self._black_parents)).order_by('tag'))


class SaveTag:
    def __init__(self, user, data):
        self.user = user
        self.data = data
        if 'action' not in self.data or self.data['action'] not in ['edit', 'create']:
            raise BridgeException()
        if 'tag_type' not in self.data or self.data['tag_type'] not in ['safe', 'unsafe']:
            raise BridgeException()
        if self.data['tag_type'] == 'unsafe':
            self.table = UnsafeTag
            self.access_model = UnsafeTagAccess
        else:
            self.table = SafeTag
            self.access_model = SafeTagAccess
        if self.data['action'] == 'edit':
            self.tag = self.__edit_tag()
        else:
            self.tag = self.__create_tag()
        self.__create_access()

    def __create_tag(self):
        if any(x not in self.data for x in ['description', 'name', 'parent_id']):
            raise BridgeException()
        parent = None
        if self.data['parent_id'] != '0':
            try:
                parent = self.table.objects.get(pk=self.data['parent_id'])
            except ObjectDoesNotExist:
                raise BridgeException(_('The tag parent was not found'))
        if not TagAccess(self.user, parent).create():
            raise BridgeException(_("You don't have an access to create this tag"))

        if len(self.data['name']) == 0:
            raise BridgeException(_('The tag name is required'))
        if len(self.data['name']) > 32:
            raise BridgeException(_('The maximum length of a tag must be 32 characters'))
        if len(self.table.objects.filter(tag=self.data['name'])) > 0:
            raise BridgeException(_('The tag name is used already'))
        return self.table.objects.create(
            author=self.user, tag=self.data['name'], parent=parent, description=self.data['description']
        )

    def __edit_tag(self):
        if any(x not in self.data for x in ['tag_id', 'description', 'name', 'parent_id']):
            raise BridgeException()
        try:
            tag = self.table.objects.get(pk=self.data['tag_id'])
        except ObjectDoesNotExist:
            raise BridgeException(_('The tag was not found'))
        if not TagAccess(self.user, tag).edit():
            raise BridgeException(_("You don't have an access to edit this tag"))

        if len(self.data['name']) == 0:
            raise BridgeException(_('The tag name is required'))
        if len(self.data['name']) > 32:
            raise BridgeException(_('The maximum length of a tag must be 32 characters'))
        if len(self.table.objects.filter(Q(tag=self.data['name']) & ~Q(id=self.data['tag_id']))) > 0:
            raise BridgeException(_('The tag name is used already'))
        parent = None
        if self.data['parent_id'] != '0':
            try:
                parent = self.table.objects.get(pk=self.data['parent_id'])
            except ObjectDoesNotExist:
                raise BridgeException(_('The tag parent was not found'))
        if not self.__check_parent(tag, parent):
            raise BridgeException(_('Choose another tag parent'))
        tag.description = self.data['description']
        tag.tag = self.data['name']
        tag.parent = parent
        tag.save()
        return tag

    def __check_parent(self, tag, parent):
        self.ccc = 0
        while parent is not None:
            if parent.pk == tag.pk:
                return False
            parent = parent.parent
        return True

    def __create_access(self):
        if self.data['action'] == 'create' and self.user.role != USER_ROLES[2][0]:
            self.access_model.objects.create(tag=self.tag, user=self.user, modification=True, child_creation=True)

        if self.user.role != USER_ROLES[2][0] or 'access' not in self.data:
            return
        access = json.loads(self.data['access'])
        if access['edit'] is None:
            access['edit'] = []
        if access['child'] is None:
            access['child'] = []
        can_edit = list(int(x) for x in access['edit'])
        can_create = list(int(x) for x in access['child'])

        self.access_model.objects.filter(tag=self.tag).delete()
        access_to_create = []
        for u in User.objects.filter(id__in=(can_edit + can_create)):
            access_to_create.append(self.access_model(
                tag=self.tag, user=u, modification=(u.id in can_edit), child_creation=(u.id in can_create)
            ))
        self.access_model.objects.bulk_create(access_to_create)


class TagsInfo:
    def __init__(self, tag_type, selected_tags, deleted_tag=None):
        self.tag_type = tag_type
        self.tag_table = {'safe': SafeTag, 'unsafe': UnsafeTag}
        if self.tag_type not in self.tag_table:
            raise BridgeException()
        self.available = []
        self.selected = []
        self.__get_selected(selected_tags, deleted_tag)
        self.__get_available()
        self.table = GetTagsData(self.tag_type, self.selected).table.data

    def __get_selected(self, selected, deleted):
        tags_for_del = []
        if deleted is not None:
            tags_for_del.append(int(deleted))
            old_len = 0
            while old_len < len(tags_for_del):
                old_len = len(tags_for_del)
                for t in self.tag_table[self.tag_type].objects.filter(parent_id__in=tags_for_del):
                    if t.pk not in tags_for_del:
                        tags_for_del.append(t.pk)
        for sel_id in selected:
            try:
                tag = self.tag_table[self.tag_type].objects.get(pk=sel_id)
            except ObjectDoesNotExist:
                raise BridgeException(_('The tag was not found'))
            if tag.pk not in tags_for_del:
                self.selected.append(tag.pk)
            while tag.parent is not None:
                if tag.parent_id not in self.selected and tag.parent_id not in tags_for_del:
                    self.selected.append(tag.parent_id)
                tag = tag.parent

    def __get_available(self):
        for tag in self.tag_table[self.tag_type].objects.filter(~Q(id__in=self.selected)).order_by('tag'):
            self.available.append([tag.pk, tag.tag])


class CreateTagsFromFile:
    def __init__(self, user, fp, tags_type, population=False):
        self.user = user
        self.fp = fp
        self.tags_type = tags_type
        self.number_of_created = 0
        self.__create_tags(population)

    def __read_json(self):
        try:
            return json.loads(self.fp.read().decode('utf8'))
        except Exception as e:
            logger.exception("Error while parsing tag's data: %s" % e, stack_info=True)
            raise BridgeException()

    def __create_tags(self, population):
        tag_table = {'unsafe': UnsafeTag, 'safe': SafeTag}
        if self.tags_type not in tag_table:
            raise BridgeException()
        newtags = {}
        list_of_tags = self.__read_json()
        if not isinstance(list_of_tags, list):
            raise BridgeException(_('Wrong tags format'))
        for data in list_of_tags:
            if 'name' not in data:
                raise BridgeException(_('Tag name is required'))
            tag_name = str(data['name'])
            if len(tag_name) > 32 or len(tag_name) == 0:
                raise BridgeException(_("The tag name length must be 1-32 (%(name)s)") % {'name': tag_name})
            if tag_name in newtags:
                raise BridgeException(_("The name must be unique (%(name)s)") % {'name': tag_name})

            parent = data.get('parent', None)
            if parent is not None:
                parent = str(parent)

            newtags[tag_name] = {'parent': parent, 'description': str(data.get('description', ''))}

        parents = [None]
        created_tags = {None: None}
        while len(parents) > 0:
            new_parents = []
            for tag_name in newtags:
                if newtags[tag_name]['parent'] in parents:
                    try:
                        created_tags[tag_name] = tag_table[self.tags_type].objects.get(tag=tag_name)
                    except ObjectDoesNotExist:
                        created_tags[tag_name] = tag_table[self.tags_type].objects.create(
                            author=self.user,
                            tag=tag_name,
                            parent=created_tags[newtags[tag_name]['parent']],
                            description=newtags[tag_name]['description'],
                            populated=population
                        )
                        self.number_of_created += 1
                    new_parents.append(tag_name)
            parents = new_parents
