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
import hashlib
import tarfile
import tempfile
from io import BytesIO
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import ugettext_lazy as _
from django.utils.timezone import now
from bridge.utils import file_get_or_create, logger
from marks.utils import NewMark, UpdateTags, ConnectMarkWithReports, DeleteMark
from marks.ConvertTrace import ET_FILE_NAME
from marks.models import *


class CreateMarkTar(object):

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
        self.name = 'Mark-%s-%s.tar.gz' % (self.type, self.mark.identifier[:10])
        self.tempfile = tempfile.TemporaryFile()
        self.__full_tar()
        self.tempfile.flush()
        self.size = self.tempfile.tell()
        self.tempfile.seek(0)

    def __full_tar(self):

        def write_file_str(jobtar, file_name, file_content):
            file_content = file_content.encode('utf-8')
            t = tarfile.TarInfo(file_name)
            t.size = len(file_content)
            jobtar.addfile(t, BytesIO(file_content))

        marktar_obj = tarfile.open(fileobj=self.tempfile, mode='w:gz', encoding='utf8')
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
            write_file_str(marktar_obj, 'version-%s' % markversion.version,
                           json.dumps(version_data, ensure_ascii=False, sort_keys=True, indent=4))
        common_data = {
            'is_modifiable': self.mark.is_modifiable,
            'mark_type': self.type,
            'format': self.mark.format,
            'identifier': self.mark.identifier
        }
        if self.type == 'unknown':
            common_data['component'] = self.mark.component.name
        write_file_str(marktar_obj, 'markdata', json.dumps(common_data, ensure_ascii=False, sort_keys=True, indent=4))
        if self.type == 'unsafe':
            marktar_obj.add(os.path.join(settings.MEDIA_ROOT, self.mark.error_trace.file.name), arcname='error-trace')
        marktar_obj.close()


class AllMarksTar(object):
    def __init__(self):
        self.tempfile = tempfile.TemporaryFile()
        self.__create_tar()
        self.tempfile.flush()
        self.size = self.tempfile.tell()
        self.tempfile.seek(0)
        curr_time = now()
        self.name = 'Marks--%s-%s-%s.tar.gz' % (curr_time.day, curr_time.month, curr_time.year)

    def __create_tar(self):
        with tarfile.open(fileobj=self.tempfile, mode='w:gz', encoding='utf8') as arch:
            for mark in MarkSafe.objects.all():
                marktar = CreateMarkTar(mark)
                t = tarfile.TarInfo(marktar.name)
                t.size = marktar.size
                arch.addfile(t, marktar.tempfile)
            for mark in MarkUnsafe.objects.all():
                marktar = CreateMarkTar(mark)
                t = tarfile.TarInfo(marktar.name)
                t.size = marktar.size
                arch.addfile(t, marktar.tempfile)
            for mark in MarkUnknown.objects.all():
                marktar = CreateMarkTar(mark)
                t = tarfile.TarInfo(marktar.name)
                t.size = marktar.size
                arch.addfile(t, marktar.tempfile)
            arch.close()


class ReadTarMark(object):

    def __init__(self, user, tar_archive):
        self.mark = None
        self.type = None
        self.user = user
        self.tar_arch = tar_archive
        self.error = self.__create_mark_from_tar()

    class UploadMark(object):

        def __init__(self, user, mark_type, args):
            self.mark = None
            self.mark_version = None
            self.user = user
            self.type = mark_type
            if not isinstance(args, dict) or not isinstance(user, User):
                self.error = _("Unknown error")
            else:
                self.error = self.__create_mark(args)

        def __create_mark(self, args):
            if self.type == 'unsafe':
                mark = MarkUnsafe()
            elif self.type == 'safe':
                mark = MarkSafe()
            else:
                mark = MarkUnknown()
            mark.author = self.user

            if self.type == 'unsafe':
                mark.error_trace = file_get_or_create(args['error_trace'], ET_FILE_NAME, ConvertedTraces)[0]
                try:
                    mark.function = MarkUnsafeCompare.objects.get(pk=args['compare_id'])
                except ObjectDoesNotExist:
                    return _("The error traces comparison function was not found")
            mark.format = int(args['format'])
            if mark.format != FORMAT:
                return _('The mark format is not supported')

            if 'identifier' in args:
                mark.identifier = args['identifier']
            else:
                time_encoded = now().strftime("%Y%m%d%H%M%S%f%z").encode('utf8')
                mark.identifier = hashlib.md5(time_encoded).hexdigest()

            if isinstance(args['is_modifiable'], bool):
                mark.is_modifiable = args['is_modifiable']

            if self.type == 'unsafe' and args['verdict'] in list(x[0] for x in MARK_UNSAFE):
                mark.verdict = args['verdict']
            elif self.type == 'safe' and args['verdict'] in list(x[0] for x in MARK_SAFE):
                mark.verdict = args['verdict']
            elif self.type == 'unknown':
                if len(MarkUnknown.objects.filter(component__name=args['component'],
                                                  problem_pattern=args['problem'])) > 0:
                    return _('Could not upload the mark archive since the similar mark exists already')
                mark.component = Component.objects.get_or_create(name=args['component'])[0]
                mark.function = args['function']
                mark.problem_pattern = args['problem']
                if 'link' in args and len(args['link']) > 0:
                    mark.function = args['link']

            if args['status'] in list(x[0] for x in MARK_STATUS):
                mark.status = args['status']

            tags = []
            if 'tags' in args and self.type != 'unknown':
                tags = args['tags']
            if 'description' in args:
                mark.description = args['description']
            mark.type = MARK_TYPE[2][0]

            try:
                mark.save()
            except Exception as e:
                logger.exception("Saving mark to DB failed: %s" % e, stack_info=True)
                return 'Unknown error'

            res = self.__update_mark(mark, tags=tags)
            if res is not None:
                return res
            if self.type != 'unknown':
                res = self.__create_attributes(args['attrs'])
                if res is not None:
                    mark.delete()
                    return res
            self.mark = mark
            return None

        def __update_mark(self, mark, comment='', tags=None):
            if self.type == 'unsafe':
                new_version = MarkUnsafeHistory()
            elif self.type == 'safe':
                new_version = MarkSafeHistory()
            else:
                new_version = MarkUnknownHistory()

            new_version.mark = mark
            if self.type == 'unsafe':
                new_version.function = mark.function
            if self.type == 'unknown':
                new_version.function = mark.function
                new_version.problem_pattern = mark.problem_pattern
                new_version.link = mark.link
            else:
                new_version.verdict = mark.verdict
            new_version.version = mark.version
            new_version.status = mark.status
            new_version.change_date = mark.change_date
            new_version.comment = comment
            new_version.author = mark.author
            new_version.description = mark.description
            new_version.save()
            if isinstance(tags, list):
                for tag in tags:
                    if self.type == 'safe':
                        try:
                            safetag = SafeTag.objects.get(tag=tag)
                        except ObjectDoesNotExist:
                            return _('One of tags was not found')
                        MarkSafeTag.objects.get_or_create(tag=safetag, mark_version=new_version)
                        newtag = safetag.parent
                        while newtag is not None:
                            MarkSafeTag.objects.get_or_create(tag=newtag, mark_version=new_version)
                            newtag = newtag.parent
                    elif self.type == 'unsafe':
                        try:
                            unsafetag = UnsafeTag.objects.get(tag=tag)
                        except ObjectDoesNotExist:
                            return _('One of tags was not found')
                        MarkUnsafeTag.objects.get_or_create(tag=unsafetag, mark_version=new_version)
                        newtag = unsafetag.parent
                        while newtag is not None:
                            MarkUnsafeTag.objects.get_or_create(tag=newtag, mark_version=new_version)
                            newtag = newtag.parent
            self.mark_version = new_version
            return None

        def __create_attributes(self, attrs):
            if not isinstance(attrs, list):
                return _('The attributes have wrong format')
            for a in attrs:
                if any(x not in a for x in ['attr', 'value', 'is_compare']):
                    return _('The attributes have wrong format')
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
            return None

    def __create_mark_from_tar(self):

        def get_func_id(func_name):
            try:
                return MarkUnsafeCompare.objects.get(name=func_name).pk
            except ObjectDoesNotExist:
                return 0

        inmemory = BytesIO(self.tar_arch.read())
        marktar_file = tarfile.open(fileobj=inmemory, mode='r', encoding='utf8')
        mark_data = None
        err_trace = None

        versions_data = {}
        for f in marktar_file.getmembers():
            file_name = f.name
            file_obj = marktar_file.extractfile(f)
            if file_name == 'markdata':
                try:
                    mark_data = json.loads(file_obj.read().decode('utf-8'))
                except ValueError:
                    return _("The mark archive is corrupted")
            elif file_name == 'error-trace':
                err_trace = file_obj
            elif file_name.startswith('version-'):
                version_id = int(file_name.replace('version-', ''))
                try:
                    versions_data[version_id] = json.loads(file_obj.read().decode('utf-8'))
                except ValueError:
                    return _("The mark archive is corrupted")

        if not isinstance(mark_data, dict) or any(x not in mark_data for x in ['mark_type', 'is_modifiable', 'format']):
            return _("The mark archive is corrupted")
        self.type = mark_data['mark_type']
        if self.type not in ['safe', 'unsafe', 'unknown']:
            return _("The mark archive is corrupted")
        if self.type == 'unsafe' and err_trace is None:
            return _("The mark archive is corrupted: the pattern error trace is not found")
        elif self.type == 'unknown' and 'component' not in mark_data:
            return _("The mark archive is corrupted")

        mark_table = {'unsafe': MarkUnsafe, 'safe': MarkSafe, 'unknown': MarkUnknown}
        if 'identifier' in mark_data:
            if isinstance(mark_data['identifier'], str) and len(mark_data['identifier']) > 0:
                if len(mark_table[self.type].objects.filter(identifier=mark_data['identifier'])) > 0:
                    return _("The mark with identifier specified in the archive already exists")
            else:
                del mark_data['identifier']

        version_list = list(versions_data[v] for v in sorted(versions_data))
        for version in version_list:
            if any(x not in version for x in ['status', 'comment']):
                return _("The mark archive is corrupted")
            if self.type == 'unsafe' and 'function' not in version:
                return _("The mark archive is corrupted")
            if self.type != 'unknown' and any(x not in version for x in ['verdict', 'attrs', 'tags']):
                return _("The mark archive is corrupted")
            if self.type == 'unknown' and any(x not in version for x in ['problem', 'function']):
                return _("The mark archive is corrupted")

        new_m_args = mark_data.copy()
        new_m_args.update(version_list[0])
        if self.type == 'unsafe':
            new_m_args['error_trace'] = err_trace
            new_m_args['compare_id'] = get_func_id(version_list[0]['function'])
            del new_m_args['function'], new_m_args['mark_type']

        umark = self.UploadMark(self.user, self.type, new_m_args)
        if umark.error is not None:
            return umark.error
        mark = umark.mark
        if not isinstance(mark, mark_table[self.type]):
            return _("Unknown error")
        for version_data in version_list[1:]:
            if 'tags' in version_data:
                if self.type == 'safe':
                    tag_table = SafeTag
                elif self.type == 'unsafe':
                    tag_table = UnsafeTag
                else:
                    return 'Unknown error'
                tag_ids = []
                for t_name in version_data['tags']:
                    try:
                        tag_ids.append(tag_table.objects.get(tag=t_name).pk)
                    except ObjectDoesNotExist:
                        return _('One of tags was not found')
                version_data['tags'] = tag_ids
            if len(version_data['comment']) == 0:
                version_data['comment'] = '1'
            if self.type == 'unsafe':
                version_data['compare_id'] = get_func_id(version_data['function'])
                del version_data['function']
            upd_mark = NewMark(mark, self.user, self.type, version_data, False)
            if upd_mark.error is not None:
                mark.delete()
                return upd_mark.error

        UpdateTags(mark, changes=ConnectMarkWithReports(mark).changes)
        self.mark = mark
        return None


class UploadAllMarks(object):
    def __init__(self, user, marks_dir, delete_all_marks):
        self.error = None
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
                    res = ReadTarMark(self.user, fp)
                if res.error is None and res.type in self.numbers:
                    self.numbers[res.type] += 1
                else:
                    self.numbers['fail'] += 1
