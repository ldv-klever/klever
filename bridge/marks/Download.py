#
# Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
# Institute for System Programming of the Russian Academy of Sciences
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
from io import BytesIO

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _

from bridge.vars import MARK_TYPE, MARK_STATUS, FORMAT, MARK_SAFE, MARK_UNSAFE
from bridge.utils import file_get_or_create, logger, unique_id, BridgeException
from bridge.ZipGenerator import ZipStream, CHUNK_SIZE

from users.models import User
from reports.models import  Component, AttrName, Attr
from marks.models import MarkSafe, MarkUnsafe, MarkUnknown, MarkSafeTag, MarkUnsafeTag, SafeTag, UnsafeTag,\
    MarkSafeHistory, MarkUnsafeHistory, MarkUnknownHistory, ConvertedTraces, MarkSafeAttr, MarkUnsafeAttr,\
    MarkUnsafeCompare

import marks.SafeUtils as SafeUtils
import marks.UnsafeUtils as UnsafeUtils
import marks.UnknownUtils as UnknownUtils
from marks.ConvertTrace import ET_FILE_NAME

class MarkArchiveGenerator(object):
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
                if markversion.link is not None:
                    version_data['link'] = markversion.link
            else:
                version_data['attrs'] = []
                version_data['tags'] = []
                version_data['verdict'] = markversion.verdict
                if self.type == 'unsafe':
                    version_data['function'] = markversion.function.name
                for tag in markversion.tags.all():
                    version_data['tags'].append(tag.tag.tag)
                for attr in markversion.attrs.order_by('id'):
                    version_data['attrs'].append({
                        'attr': attr.attr.name.name,
                        'value': attr.attr.value,
                        'is_compare': attr.is_compare
                    })
            content = json.dumps(version_data, ensure_ascii=False, sort_keys=True, indent=4)
            for data in self.stream.compress_string('version-%s' % markversion.version, content):
                yield data
            if self.type == 'unsafe':
                err_trace_file = os.path.join(settings.MEDIA_ROOT, markversion.error_trace.file.name)
                for data in self.stream.compress_file(err_trace_file, 'error_trace_%s' % str(markversion.version)):
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


class ReadMarkArchive:
    def __init__(self, user, archive):
        self.mark = None
        self.type = None
        self._user = user
        self._archive = archive
        self.__create_mark_from_archive()

    class UploadMark(object):
        def __init__(self, user, mark_type, args):
            self.mark = None
            self.mark_version = None
            self.user = user
            self.type = mark_type
            if not isinstance(args, dict) or not isinstance(user, User):
                raise BridgeException()
            self.__create_mark(args)

        def __create_mark(self, args):
            mark_model = {'unsafe': MarkUnsafe, 'safe': MarkSafe, 'unknown': MarkUnknown}
            mark = mark_model[self.type](
                author=self.user, format=int(args['format']),
                identifier=args['identifier'] if 'identifier' in args else unique_id(),
                is_modifiable=bool(args['is_modifiable']),
                status=MARK_STATUS[int(args['status'])][0],
                description=args.get('description', ''), type=MARK_TYPE[2][0]
            )
            if mark.format != FORMAT:
                raise BridgeException(_('The mark format is not supported'))

            if self.type == 'unsafe':
                mark.verdict = MARK_UNSAFE[int(args['verdict'])][0]
                mark.function_id = args['compare_id']
            elif self.type == 'safe':
                mark.verdict = MARK_SAFE[int(args['verdict'])][0]
            elif self.type == 'unknown':
                if len(MarkUnknown.objects.filter(component__name=args['component'],
                                                  problem_pattern=args['problem'])) > 0:
                    raise BridgeException(_('Could not upload the mark archive since the similar mark exists already'))
                mark.component = Component.objects.get_or_create(name=args['component'])[0]
                mark.function = args['function']
                mark.problem_pattern = args['problem']
                if 'link' in args and len(args['link']) > 0:
                    mark.link = args['link']

            try:
                mark.save()
            except Exception as e:
                logger.exception("Saving mark to DB failed: %s" % e, stack_info=True)
                raise BridgeException()

            self.__update_mark(mark, args.get('error_trace'), args.get('tags'))
            if self.type != 'unknown':
                try:
                    self.__create_attributes(args['attrs'])
                except Exception:
                    mark.delete()
                    raise
            self.mark = mark

        def __update_mark(self, mark, error_trace, tags):
            version_model = {'unsafe': MarkUnsafeHistory, 'safe': MarkSafeHistory, 'unknown': MarkUnknownHistory}
            self.mark_version = version_model[self.type](
                mark=mark, author=mark.author, comment='', change_date=mark.change_date, status=mark.status,
                version=mark.version, description=mark.description
            )
            if self.type == 'unsafe':
                self.mark_version.function = mark.function
                self.mark_version.error_trace = file_get_or_create(BytesIO(
                    json.dumps(json.loads(error_trace), ensure_ascii=False, sort_keys=True, indent=4).encode('utf8')
                ), ET_FILE_NAME, ConvertedTraces)[0]
            if self.type == 'unknown':
                self.mark_version.function = mark.function
                self.mark_version.problem_pattern = mark.problem_pattern
                self.mark_version.link = mark.link
            else:
                self.mark_version.verdict = mark.verdict
            self.mark_version.save()
            if isinstance(tags, list):
                for tag in tags:
                    if self.type == 'safe':
                        try:
                            safetag = SafeTag.objects.get(tag=tag)
                        except ObjectDoesNotExist:
                            raise BridgeException(_('One of tags was not found'))
                        MarkSafeTag.objects.get_or_create(tag=safetag, mark_version=self.mark_version)
                        newtag = safetag.parent
                        while newtag is not None:
                            MarkSafeTag.objects.get_or_create(tag=newtag, mark_version=self.mark_version)
                            newtag = newtag.parent
                    elif self.type == 'unsafe':
                        try:
                            unsafetag = UnsafeTag.objects.get(tag=tag)
                        except ObjectDoesNotExist:
                            raise BridgeException(_('One of tags was not found'))
                        MarkUnsafeTag.objects.get_or_create(tag=unsafetag, mark_version=self.mark_version)
                        newtag = unsafetag.parent
                        while newtag is not None:
                            MarkUnsafeTag.objects.get_or_create(tag=newtag, mark_version=self.mark_version)
                            newtag = newtag.parent

        def __create_attributes(self, attrs):
            if not isinstance(attrs, list):
                raise BridgeException(_('The attributes have wrong format'))
            for a in attrs:
                if any(x not in a for x in ['attr', 'value', 'is_compare']):
                    raise BridgeException(_('The attributes have wrong format'))
            for a in attrs:
                attr_name = AttrName.objects.get_or_create(name=a['attr'])[0]
                attr = Attr.objects.get_or_create(name=attr_name, value=a['value'])[0]
                create_args = {
                    'mark': self.mark_version,
                    'attr': attr,
                    'is_compare': a['is_compare']
                }
                if self.type == 'unsafe':
                    MarkUnsafeAttr.objects.get_or_create(**create_args)
                else:
                    MarkSafeAttr.objects.get_or_create(**create_args)

    def __create_mark_from_archive(self):

        def get_func_id(func_name):
            try:
                return MarkUnsafeCompare.objects.get(name=func_name).pk
            except ObjectDoesNotExist:
                return 0

        mark_data = None
        err_traces = {}
        versions_data = {}
        with zipfile.ZipFile(self._archive, 'r') as zfp:
            for file_name in zfp.namelist():
                if file_name == 'markdata':
                    try:
                        mark_data = json.loads(zfp.read(file_name).decode('utf8'))
                    except ValueError:
                        raise BridgeException(_("The mark archive is corrupted"))
                elif file_name.startswith('version-'):
                    version_id = int(file_name.replace('version-', ''))
                    try:
                        versions_data[version_id] = json.loads(zfp.read(file_name).decode('utf8'))
                    except ValueError:
                        raise BridgeException(_("The mark archive is corrupted"))
                elif file_name.startswith('error_trace_'):
                    err_traces[int(file_name.replace('error_trace_', ''))] = zfp.read(file_name).decode('utf8')

        if not isinstance(mark_data, dict):
            raise BridgeException(_("The mark archive is corrupted"))
        self.type = mark_data.get('mark_type')
        if self.type not in {'safe', 'unsafe', 'unknown'}:
            raise BridgeException(_("The mark archive is corrupted"))

        mark_table = {'unsafe': MarkUnsafe, 'safe': MarkSafe, 'unknown': MarkUnknown}

        if self.type == 'unsafe':
            for v_id in versions_data:
                if v_id not in err_traces:
                    raise BridgeException(_("The mark archive is corrupted"))
                versions_data[v_id]['error_trace'] = err_traces[v_id]

        version_list = list(versions_data[v] for v in sorted(versions_data))
        for version in version_list:
            if self.type == 'unsafe' and 'function' not in version:
                raise BridgeException(_("The mark archive is corrupted"))

        mark_data.update(version_list[0])
        if self.type == 'unsafe':
            mark_data['compare_id'] = get_func_id(version_list[0]['function'])
            del mark_data['function'], mark_data['mark_type']

        if self.type == 'safe':
            tags = self.__safe_tags(mark_data['tags'])
            res = SafeUtils.NewMark(self._user, mark_data)
            mark = res.upload_mark()

        elif self.type == 'unsafe':
            res = UnsafeUtils.NewMark(self._user, mark_data)
            mark = res.upload_mark()
        elif self.type == 'unknown':
            res = UnknownUtils.NewMark(self._user, mark_data)
            mark = res.upload_mark()
        else:
            raise BridgeException(_("The mark archive is corrupted"))

        # mark = self.UploadMark(self._user, self.type, mark_data).mark
        # if not isinstance(mark, mark_table[self.type]):
        #     raise BridgeException()
        for version_data in version_list[1:]:
            if 'tags' in version_data:
                if self.type == 'safe':
                    tag_table = SafeTag
                elif self.type == 'unsafe':
                    tag_table = UnsafeTag
                else:
                    raise BridgeException()
                tag_ids = []
                for t_name in version_data['tags']:
                    try:
                        tag_ids.append(tag_table.objects.get(tag=t_name).pk)
                    except ObjectDoesNotExist:
                        raise BridgeException(_('One of tags was not found'))
                version_data['tags'] = tag_ids
            if len(version_data['comment']) == 0:
                version_data['comment'] = '1'
            if self.type == 'unsafe':
                version_data['compare_id'] = get_func_id(version_data['function'])
                del version_data['function']
            try:
                NewMark(mark, self._user, self.type, version_data, False)
            except Exception:
                mark.delete()
                raise

        for report in ConnectMarkWithReports(mark).changes:
            RecalculateTags(report)
        self.mark = mark

    def __upload_safe_mark(self, data):
        pass

    def __safe_tags(self, tags):
        tag_ids = set()
        for tag in SafeTag.objects.all():
            if tag.tag in tags:
                tag_ids.add(tag.id)
        return tag_ids

    def __unsafe_tags(self, tags):
        tag_ids = set()
        for tag in SafeTag.objects.all():
            if tag.tag in tags:
                tag_ids.add(tag.id)
        return tag_ids

    def __is_not_used(self):
        pass


class UploadAllMarks:
    def __init__(self, user, marks_dir, delete_all_marks):
        self.user = user
        self.numbers = {'safe': 0, 'unsafe': 0, 'unknown': 0, 'fail': 0}
        self.delete_all = delete_all_marks
        self.__delete_all_marks()
        self.__upload_all(marks_dir)

    def __delete_all_marks(self):
        if self.delete_all:
            for mark in MarkSafe.objects.all():
                DeleteMark(mark)
            for mark in MarkUnsafe.objects.all():
                DeleteMark(mark)
            for mark in MarkUnknown.objects.all():
                DeleteMark(mark)

    def __upload_all(self, marks_dir):
        for file_name in os.listdir(marks_dir):
            mark_path = os.path.join(marks_dir, file_name)
            if os.path.isfile(mark_path):
                with open(mark_path, mode='rb') as fp:
                    try:
                        mark_type = ReadMarkArchive(self.user, fp).type
                        if mark_type in self.numbers:
                            self.numbers[mark_type] += 1
                    except Exception as e:
                        logger.exception(e)
                        self.numbers['fail'] += 1
