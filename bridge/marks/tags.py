from django.db.models import Q
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import ugettext_lazy as _
from marks.models import SafeTag, UnsafeTag


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


class TagData(object):
    def __init__(self, tag):
        self.id = tag.pk
        self.parent = tag.parent_id
        self.name = tag.tag
        self.children = list(child.pk for child in tag.children.all())
        self.description = tag.description

    def __repr__(self):
        return "<Tag: '%s'>" % self.name


class GetTagsData(object):
    def __init__(self, tags_type):
        self.error = None
        self.__type = tags_type
        self.tags = []
        if self.__type not in ['safe', 'unsafe']:
            self.error = 'Unknown error'
            return
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
            if self.__type == 'safe':
                next_level = [TagData(tag) for tag in SafeTag.objects.filter(**tags_filter).order_by('tag')]
            else:
                next_level = [TagData(tag) for tag in UnsafeTag.objects.filter(**tags_filter).order_by('tag')]
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


class GetParents(object):
    def __init__(self, tag_id, tag_type):
        self.error = None
        self._tag_table = None
        self.tag = self.__get_tag(tag_id, tag_type)
        if self.error is not None:
            return
        self._black_parents = self.__get_black_parents()
        self.parents_ids = self.__get_parents()

    def __get_tag(self, tag_id, tag_type):
        if tag_type == 'safe':
            self._tag_table = SafeTag
        elif tag_type == 'unsafe':
            self._tag_table = UnsafeTag
        else:
            self.error = 'Unknown error'
            return None
        try:
            return self._tag_table.objects.get(pk=tag_id)
        except ObjectDoesNotExist:
            self.error = _('The tag was not found')
        return None

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
        return list(tag.pk for tag in self._tag_table.objects.filter(~Q(id__in=self._black_parents)))


def fill_test_data():
    SafeTag.objects.all().delete()
    hierarhy = [
        [(1, None)],
        [(2, 1), (3, 1)],
        [(12, 2), (5, 2), (6, 3), (4, 3)],
        [(13, 12), (14, 12), (15, 12), (7, 5), (8, 5), (9, 5), (23, 6)],
        [(16, 14), (17, 14), (10, 9), (11, 9), (18, 23), (19, 23)],
        [(20, 18), (21, 19), (22, 19)]
    ]
    saved_data = {
        None: None
    }
    tag_description = """
Description for safe tag with id {0} and parent with id {1}<br>
<span style="color: red;">It is red text</span><br>
<a href="http://google.com/">This this link to google</a><br>
"""
    for row in hierarhy:
        for c in row:
            newtag = SafeTag.objects.create(
                tag="safe:t%s" % c[0],
                parent=saved_data[c[1]],
                description=tag_description.format(c[0], c[1])
            )
            saved_data[c[0]] = newtag
