import os
import json
import shutil
import uuid

from django.conf import settings
from django.utils.translation import ugettext as _

from bridge.vars import MARK_SOURCE
from bridge.utils import BridgeException

from marks.models import SafeTag, MarkSafe, UnsafeTag, MarkUnsafe, MarkUnknown
from marks.serializers import SafeMarkSerializer, UnsafeMarkSerializer, UnknownMarkSerializer,\
    SafeTagSerializer, UnsafeTagSerializer
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
            })
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
            })
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

                # Use component from data if provided
                component = mark_data.pop('component', component)

                if settings.POPULATE_JUST_PRODUCTION_PRESETS and not mark_data.get('production'):
                    # Do not populate non-production marks
                    continue

                serializer = UnknownMarkSerializer(data=mark_data)
                serializer.is_valid(raise_exception=True)
                mark = serializer.save(
                    identifier=identifier, author=self._author,
                    source=MARK_SOURCE[1][0], component=component
                )
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


def get_new_attrs(attrs):
    new_attrs = []
    if attrs is None:
        return new_attrs
    for old_a in attrs:
        new_attrs.append({'name': old_a['attr'], 'value': old_a['value'], 'is_compare': old_a['is_compare']})
    return new_attrs


def move_safe_marks():
    presets_dir = os.path.join(settings.BASE_DIR, 'marks', 'presets', 'safes')
    new_dir = os.path.join(settings.BASE_DIR, 'marks', 'presets', 'safes_old')
    changes_file = os.path.join(settings.BASE_DIR, 'marks', 'presets', 'safes-changes.json')
    os.mkdir(new_dir)

    changes = {}
    for mark_filename in os.listdir(presets_dir):
        mark_path = os.path.join(presets_dir, mark_filename)
        if not os.path.isfile(mark_path):
            continue

        old_identifier = os.path.splitext(mark_filename)[0]
        new_identifier = str(uuid.uuid4())
        changes[old_identifier] = new_identifier

        shutil.copy2(mark_path, os.path.join(new_dir, mark_filename))
        with open(mark_path, mode='r', encoding='utf-8') as fp:
            mark_data = json.load(fp)
        mark_data['attrs'] = get_new_attrs(mark_data.get('attrs'))
        with open(mark_path, mode='w', encoding='utf-8') as fp:
            json.dump(mark_data, fp, indent=2, sort_keys=True, ensure_ascii=False)
        shutil.move(mark_path, os.path.join(presets_dir, "{}.json".format(new_identifier)))
    with open(changes_file, mode='w', encoding='utf-8') as fp:
        json.dump(changes, fp, indent=2, sort_keys=True, ensure_ascii=False)


def move_unsafe_marks():
    presets_dir = os.path.join(settings.BASE_DIR, 'marks', 'presets', 'unsafes')
    new_dir = os.path.join(settings.BASE_DIR, 'marks', 'presets', 'unsafes_old')
    changes_file = os.path.join(settings.BASE_DIR, 'marks', 'presets', 'unsafes-changes.json')
    os.mkdir(new_dir)

    changes = {}
    for mark_filename in os.listdir(presets_dir):
        mark_path = os.path.join(presets_dir, mark_filename)
        if not os.path.isfile(mark_path):
            continue

        old_identifier = os.path.splitext(mark_filename)[0]
        new_identifier = str(uuid.uuid4())
        changes[old_identifier] = new_identifier

        shutil.copy2(mark_path, os.path.join(new_dir, mark_filename))
        with open(mark_path, mode='r', encoding='utf-8') as fp:
            mark_data = json.load(fp)

        mark_data['function'] = mark_data.pop('comparison')
        mark_data['error_trace'] = mark_data.pop('error trace')
        mark_data['attrs'] = get_new_attrs(mark_data.get('attrs'))
        with open(mark_path, mode='w', encoding='utf-8') as fp:
            json.dump(mark_data, fp, indent=2, sort_keys=True, ensure_ascii=False)

        shutil.move(mark_path, os.path.join(presets_dir, "{}.json".format(new_identifier)))

    with open(changes_file, mode='w', encoding='utf-8') as fp:
        json.dump(changes, fp, indent=2, sort_keys=True, ensure_ascii=False)


def move_unknown_marks():
    presets_dir = os.path.join(settings.BASE_DIR, 'marks', 'presets', 'unknowns')
    new_dir = os.path.join(settings.BASE_DIR, 'marks', 'presets', 'unknowns_old')
    changes_file = os.path.join(settings.BASE_DIR, 'marks', 'presets', 'unknowns-changes.json')
    os.mkdir(new_dir)

    changes = {}
    for component in os.listdir(presets_dir):
        component_dir = os.path.join(presets_dir, component)
        if not os.path.isdir(component_dir):
            continue
        os.mkdir(os.path.join(new_dir, component))
        changes[component] = {}
        for mark_filename in os.listdir(component_dir):
            mark_path = os.path.join(component_dir, mark_filename)
            if not os.path.isfile(mark_path):
                continue
            old_identifier = os.path.splitext(mark_filename)[0]
            new_identifier = str(uuid.uuid4())
            changes[component][old_identifier] = new_identifier

            shutil.copy2(mark_path, os.path.join(new_dir, component, mark_filename))
            with open(mark_path, mode='r', encoding='utf-8') as fp:
                mark_data = json.load(fp)

            mark_data['function'] = mark_data.pop('pattern')
            mark_data['problem_pattern'] = mark_data.pop('problem')
            mark_data['is_regexp'] = mark_data.pop('is regexp', False)
            mark_data['attrs'] = get_new_attrs(mark_data.get('attrs'))
            with open(mark_path, mode='w', encoding='utf-8') as fp:
                json.dump(mark_data, fp, indent=2, sort_keys=True, ensure_ascii=False)

            shutil.move(mark_path, os.path.join(presets_dir, component, "{}.json".format(new_identifier)))

    with open(changes_file, mode='w', encoding='utf-8') as fp:
        json.dump(changes, fp, indent=2, sort_keys=True, ensure_ascii=False)


def check_unknown_marks():
    presets_dir = os.path.join(settings.BASE_DIR, 'marks', 'presets', 'unknowns')

    for component in os.listdir(presets_dir):
        component_dir = os.path.join(presets_dir, component)
        if not os.path.isdir(component_dir):
            continue
        for mark_filename in os.listdir(component_dir):
            mark_path = os.path.join(component_dir, mark_filename)
            if not os.path.isfile(mark_path):
                continue

            with open(mark_path, mode='r', encoding='utf-8') as fp:
                mark_data = json.load(fp)

            mark_data['function'] = mark_data.pop('pattern', None)
            mark_data['problem_pattern'] = mark_data.pop('problem', None)
            mark_data['attrs'] = get_new_attrs(mark_data.get('attrs'))
            s = UnknownMarkSerializer(data=mark_data)
            if not s.is_valid():
                print(s.errors)
                print(mark_path)
