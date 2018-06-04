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

import json

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import F
from django.http import JsonResponse, Http404
from django.template.defaulttags import register
from django.template.loader import get_template
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import ugettext as _, override
from django.utils.timezone import pytz
from django.views.generic.base import TemplateView
from django.views.generic.detail import SingleObjectMixin, DetailView

import bridge.CustomViews as Bview
from tools.profiling import LoggedCallMixin
from bridge.vars import USER_ROLES, MARK_STATUS, MARK_SAFE, MARK_UNSAFE, MARK_TYPE, ASSOCIATION_TYPE,\
    VIEW_TYPES, PROBLEM_DESC_FILE
from bridge.utils import logger, extract_archive, ArchiveFileContent, BridgeException
from users.utils import ViewData

from users.models import User
from reports.models import ReportSafe, ReportUnsafe, ReportUnknown
from marks.models import MarkSafe, MarkUnsafe, MarkUnknown, MarkSafeHistory, MarkUnsafeHistory, MarkUnknownHistory,\
    MarkUnsafeCompare, UnsafeTag, SafeTag, SafeTagAccess, UnsafeTagAccess,\
    MarkSafeReport, MarkUnsafeReport, MarkUnknownReport, MarkAssociationsChanges,\
    SafeAssociationLike, UnsafeAssociationLike, UnknownAssociationLike

import marks.utils as mutils
from marks.tags import GetTagsData, GetParents, SaveTag, TagsInfo, CreateTagsFromFile, TagAccess
from marks.Download import UploadMark, MarkArchiveGenerator, AllMarksGen, UploadAllMarks, PresetMarkFile
from marks.tables import MarkData, MarkChangesTable, MarkReportsTable, MarksList, AssociationChangesTable


@register.filter
def value_type(value):
    return str(type(value))


@method_decorator(login_required, name='dispatch')
class MarkPage(LoggedCallMixin, DetailView):
    template_name = 'marks/Mark.html'

    def get_queryset(self):
        if self.kwargs['type'] == 'safe':
            self.view_type = VIEW_TYPES[14][0]
            return MarkSafe.objects.all()
        elif self.kwargs['type'] == 'unsafe':
            self.view_type = VIEW_TYPES[13][0]
            return MarkUnsafe.objects.all()
        else:
            self.view_type = VIEW_TYPES[15][0]
            return MarkUnknown.objects.all()

    def get_context_data(self, **kwargs):
        if self.object.version == 0:
            raise BridgeException(code=605)
        history_set = self.object.versions.order_by('-version')

        versions = []
        for m in history_set:
            mark_time = m.change_date.astimezone(pytz.timezone(self.request.user.extended.timezone))
            title = mark_time.strftime("%d.%m.%Y %H:%M:%S")
            if m.author is not None:
                title += " (%s)" % m.author.get_full_name()
            if len(m.comment) > 0:
                title += ': ' + m.comment
            versions.append({'version': m.version, 'title': title})
        return {
            'mark': self.object, 'access': mutils.MarkAccess(self.request.user, mark=self.object),
            'markdata': MarkData(self.kwargs['type'], mark_version=history_set.first()),
            'reports': MarkReportsTable(self.request.user, self.object,
                                        ViewData(self.request.user, self.view_type, self.request.GET),
                                        page=self.request.GET.get('page', 1)),
            'versions': versions, 'report_id': self.request.GET.get('report_to_redirect'),
            'ass_types': ASSOCIATION_TYPE, 'view_tags': True
        }


@method_decorator(login_required, name='dispatch')
class AssociationChangesView(LoggedCallMixin, DetailView):
    model = MarkAssociationsChanges
    template_name = 'marks/SaveMarkResult.html'
    slug_field = 'identifier'
    slug_url_kwarg = 'association_id'

    def get_context_data(self, **kwargs):
        view_type_map = {'safe': VIEW_TYPES[16][0], 'unsafe': VIEW_TYPES[17][0], 'unknown': VIEW_TYPES[18][0]}
        return {'TableData': AssociationChangesTable(self.object, ViewData(
            self.request.user, view_type_map[self.kwargs['type']], self.request.GET
        ))}


@method_decorator(login_required, name='dispatch')
class MarksListView(LoggedCallMixin, TemplateView):
    template_name = 'marks/MarkList.html'

    def get_context_data(self, **kwargs):
        context = {'authors': User.objects.all(), 'statuses': MARK_STATUS, 'mark_types': MARK_TYPE}
        if self.kwargs['type'] == 'safe':
            view_type = VIEW_TYPES[8][0]
            context['verdicts'] = MARK_SAFE
        elif self.kwargs['type'] == 'unsafe':
            view_type = VIEW_TYPES[7][0]
            context['verdicts'] = MARK_UNSAFE
        else:
            view_type = VIEW_TYPES[9][0]
        context['tabledata'] = MarksList(self.request.user, self.kwargs['type'],
                                         ViewData(self.request.user, view_type, self.request.GET),
                                         page=self.request.GET.get('page', 1))
        return context


@method_decorator(login_required, name='dispatch')
class MarkFormView(LoggedCallMixin, DetailView):
    model_map = {
        'edit': {'safe': MarkSafe, 'unsafe': MarkUnsafe, 'unknown': MarkUnknown},
        'create': {'safe': ReportSafe, 'unsafe': ReportUnsafe, 'unknown': ReportUnknown}
    }
    template_name = 'marks/MarkForm.html'

    # TODO: only for post()
    unparallel = [MarkSafe, MarkUnsafe, MarkUnknown]

    def post(self, *args, **kwargs):
        self.is_not_used(*args, **kwargs)

        self.object = self.get_object()
        if self.kwargs['action'] == 'create' \
                and not mutils.MarkAccess(self.request.user, report=self.object).can_create():
            raise BridgeException(_("You don't have an access to create new marks"), response_type='json')
        elif self.kwargs['action'] == 'edit' \
                and not mutils.MarkAccess(self.request.user, mark=self.object).can_edit():
            raise BridgeException(_("You don't have an access to edit this mark"), response_type='json')

        try:
            res = mutils.NewMark(self.request.user, self.object, json.loads(self.request.POST['data']))
            if self.kwargs['action'] == 'edit':
                res.change_mark()
            else:
                res.create_mark()
            cache_id = MarkChangesTable(self.request.user, res.mark, res.changes).cache_id
        except BridgeException as e:
            raise BridgeException(str(e), response_type='json')
        except Exception as e:
            logger.exception(e)
            raise BridgeException(response_type='json')

        return JsonResponse({'cache_id': cache_id})

    def get_queryset(self):
        return self.model_map[self.kwargs['action']][self.kwargs['type']].objects.all()

    def get_context_data(self, **kwargs):
        context = {'versions': [], 'action': self.kwargs['action']}
        if self.kwargs['action'] == 'edit':
            access = mutils.MarkAccess(self.request.user, mark=self.object)
            if not access.can_edit():
                raise BridgeException(_("You don't have an access to edit this mark"))
            context['mark'] = self.object
            context['selected_version'] = int(self.request.GET.get('version', self.object.version))
            for m in self.object.versions.order_by('-version'):
                if m.version == self.object.version:
                    title = _("Current version")
                else:
                    change_time = m.change_date.astimezone(pytz.timezone(self.request.user.extended.timezone))
                    title = change_time.strftime("%d.%m.%Y %H:%M:%S")
                    if m.author is not None:
                        title += " (%s)" % m.author.get_full_name()
                    if len(m.comment) > 0:
                        title += ': ' + m.comment
                context['versions'].append({'version': m.version, 'title': title})
                if context['selected_version'] == m.version:
                    context['markdata'] = MarkData(self.kwargs['type'], mark_version=m)
            if 'markdata' not in context:
                raise BridgeException(_('The mark version was not found'))
            context['cancel_url'] = reverse('marks:mark', args=[self.kwargs['type'], self.object.id])
        else:
            if self.kwargs['type'] == 'unknown':
                try:
                    context['problem_description'] = \
                        ArchiveFileContent(self.object, 'problem_description', PROBLEM_DESC_FILE).content.decode('utf8')
                except Exception as e:
                    logger.exception("Can't get problem description for unknown '%s': %s" % (self.object.id, e))
                    raise BridgeException()

            access = mutils.MarkAccess(self.request.user, report=self.object)
            if not access.can_create():
                raise BridgeException(_("You don't have an access to create new marks"))
            context['report'] = self.object
            context['markdata'] = MarkData(self.kwargs['type'], report=self.object)
            context['cancel_url'] = reverse('reports:{0}'.format(self.kwargs['type']), args=[self.object.id])
        context['access'] = access
        return context


class InlineMarkForm(LoggedCallMixin, Bview.JSONResponseMixin, DetailView):
    model_map = {
        'edit': {'safe': MarkSafeHistory, 'unsafe': MarkUnsafeHistory, 'unknown': MarkUnknownHistory},
        'create': {'safe': ReportSafe, 'unsafe': ReportUnsafe, 'unknown': ReportUnknown}
    }
    template_name = 'marks/InlineMarkForm.html'

    def get_queryset(self):
        if self.kwargs['action'] == 'edit':
            return self.model_map['edit'][self.kwargs['type']].objects.filter(version=F('mark__version'))
        else:
            return self.model_map['create'][self.kwargs['type']].objects.all()

    def get_object(self, queryset=None):
        queryset = self.get_queryset()
        if self.kwargs['action'] == 'edit':
            queryset = queryset.filter(mark_id=self.kwargs['pk'])
        else:
            queryset = queryset.filter(pk=self.kwargs['pk'])
        try:
            return queryset.get()
        except queryset.model.DoesNotExist:
            raise Http404(_('The %(obj_name)s was not found') % {
                'obj_name': _('mark') if self.kwargs['action'] == 'edit' else _('report')
            })

    def get_context_data(self, **kwargs):
        context = {'action': self.kwargs['action'], 'obj_id': self.object.id}

        selected_tags = []
        if self.kwargs['action'] == 'edit':
            context['markdata'] = MarkData(self.kwargs['type'], mark_version=self.object)
            if self.kwargs['type'] != 'unknown':
                selected_tags = list(t_id for t_id, in self.object.tags.values_list('tag_id'))
        else:
            context['markdata'] = MarkData(self.kwargs['type'], report=self.object)
        if self.kwargs['type'] != 'unknown':
            context['tags'] = TagsInfo(self.kwargs['type'], selected_tags)
        return context


class RemoveVersionsView(LoggedCallMixin, Bview.JsonDetailPostView):
    model_map = {'safe': MarkSafe, 'unsafe': MarkUnsafe, 'unknown': MarkUnknown}
    unparallel = [MarkSafe, MarkUnsafe, MarkUnknown]

    def get_queryset(self):
        return self.model_map[self.kwargs['type']].objects.all()

    def get_context_data(self, **kwargs):
        if self.object.version == 0:
            raise BridgeException(_('The mark is being deleted'))
        if not mutils.MarkAccess(self.request.user, self.object).can_edit():
            raise BridgeException(_("You don't have an access to edit this mark"))

        checked_versions = self.object.versions.filter(version__in=json.loads(self.request.POST['versions']))
        for mark_version in checked_versions:
            if not mutils.MarkAccess(self.request.user, mark=self.object).can_remove_version(mark_version):
                raise BridgeException(_("You don't have an access to remove one of the selected version"))
        if len(checked_versions) == 0:
            raise BridgeException(_('There is nothing to delete'))
        checked_versions.delete()
        return {'success': _('Selected versions were successfully deleted')}


class CompareVersionsView(LoggedCallMixin, Bview.JSONResponseMixin, Bview.DetailPostView):
    model_map = {
        'safe': (MarkSafe, MarkSafeHistory),
        'unsafe': (MarkUnsafe, MarkUnsafeHistory),
        'unknown': (MarkUnknown, MarkUnknownHistory)
    }
    template_name = 'marks/markVCmp.html'

    def get_queryset(self):
        return self.model_map[self.kwargs['type']][0].objects.all()

    def get_context_data(self, **kwargs):
        versions = [int(self.request.POST['v1']), int(self.request.POST['v2'])]
        mark_versions = self.model_map[self.kwargs['type']][1].objects.filter(job=self.object, version__in=versions)\
            .order_by('change_date')
        if mark_versions.count() != 2:
            raise BridgeException(_('The page is outdated, reload it please'))
        return {'data': mutils.CompareMarkVersions(self.kwargs['type'], *list(mark_versions))}


@method_decorator(login_required, name='dispatch')
class DownloadMarkView(LoggedCallMixin, SingleObjectMixin, Bview.StreamingResponseView):
    model_map = {'safe': MarkSafe, 'unsafe': MarkUnsafe, 'unknown': MarkUnknown}

    def get_queryset(self):
        return self.model_map[self.kwargs['type']].objects.all()

    def get_generator(self):
        self.object = self.get_object()
        if self.object.version == 0:
            raise BridgeException(code=605)
        generator = MarkArchiveGenerator(self.object)
        self.file_name = generator.name
        return generator


@method_decorator(login_required, name='dispatch')
class DownloadPresetMarkView(LoggedCallMixin, SingleObjectMixin, Bview.StreamingResponseView):
    model_map = {'safe': MarkSafe, 'unsafe': MarkUnsafe, 'unknown': MarkUnknown}

    def get_queryset(self):
        return self.model_map[self.kwargs['type']].objects.all()

    def get_generator(self):
        self.object = self.get_object()
        if self.object.version == 0:
            raise BridgeException(code=605)
        generator = PresetMarkFile(self.object)
        self.file_name = generator.filename
        return generator


class UploadMarksView(LoggedCallMixin, Bview.JsonView):
    unparallel = [MarkSafe, MarkUnsafe, MarkUnknown]

    def get_context_data(self, **kwargs):
        if not mutils.MarkAccess(self.request.user).can_create():
            raise BridgeException(_("You don't have an access to create new marks"))

        new_marks = []
        for f in self.request.FILES.getlist('file'):
            res = UploadMark(self.request.user, f)
            new_marks.append((res.type, res.mark.id))

        if len(new_marks) == 1:
            return JsonResponse({'type': new_marks[0][0], 'id': str(new_marks[0][1])})
        return JsonResponse({'success': _('Number of created marks: %(number)s') % {'number': len(new_marks)}})


class DownloadAllMarksView(LoggedCallMixin, Bview.JSONResponseMixin, Bview.StreamingResponseView):
    def dispatch(self, request, *args, **kwargs):
        with override(settings.DEFAULT_LANGUAGE):
            return super().dispatch(request, *args, **kwargs)

    def get_generator(self):
        if self.request.user.extended.role not in [USER_ROLES[2][0], USER_ROLES[4][0]]:
            raise BridgeException("You don't have an access to download all marks")
        generator = AllMarksGen()
        self.file_name = generator.name
        return generator


class UploadAllMarksView(LoggedCallMixin, Bview.JsonView):
    unparallel = [MarkSafe, MarkUnsafe, MarkUnknown]

    def dispatch(self, request, *args, **kwargs):
        with override(settings.DEFAULT_LANGUAGE):
            return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        if self.request.user.extended.role not in [USER_ROLES[2][0], USER_ROLES[4][0]]:
            raise BridgeException("You don't have an access to upload marks")
        return UploadAllMarks(
            self.request.user, extract_archive(self.request.FILES['file']).name,
            bool(int(self.request.POST.get('delete', 0)))
        ).numbers


class SaveTagView(LoggedCallMixin, Bview.JsonView):
    unparallel = [UnsafeTag, SafeTag]

    def get_context_data(self, **kwargs):
        SaveTag(self.request.user, self.request.POST)
        return {}


@method_decorator(login_required, name='dispatch')
class TagsTreeView(LoggedCallMixin, TemplateView):
    template_name = 'marks/TagsTree.html'

    def get_context_data(self, **kwargs):
        return {
            'title': _('Safe tags') if self.kwargs['type'] == 'safe' else _('Unsafe tags'),
            'tags_type': self.kwargs['type'],
            'tags': GetTagsData(self.kwargs['type'], user=self.request.user).table.data,
            'can_create': TagAccess(self.request.user, None).create()
        }


@method_decorator(login_required, name='dispatch')
class DownloadTagsView(LoggedCallMixin, Bview.StreamingResponseView):
    model_map = {'safe': SafeTag, 'unsafe': UnsafeTag}

    def get_generator(self):
        generator = mutils.DownloadTags(self.kwargs['type'])
        self.file_name = 'Tags-%s.json' % self.kwargs['type']
        self.file_size = generator.file_size()
        return generator


class UploadTagsView(LoggedCallMixin, Bview.JsonView):
    def get_context_data(self, **kwargs):
        if not TagAccess(self.request.user, None).create():
            raise BridgeException(_("You don't have an access to upload tags"))
        if 'file' not in self.request.FILES:
            raise BridgeException()
        CreateTagsFromFile(self.request.user, self.request.FILES['file'], self.kwargs['type'])
        return {}


class TagDataView(LoggedCallMixin, Bview.JsonView):
    model_map = {'safe': (SafeTag, SafeTagAccess), 'unsafe': (UnsafeTag, UnsafeTagAccess)}

    def get_context_data(self, **kwargs):
        context = {}
        user_access = {'access_edit': [], 'access_child': [], 'all': []}

        if self.request.user.extended.role == USER_ROLES[2][0]:
            for u in User.objects.exclude(extended__role=USER_ROLES[2][0]).order_by('last_name', 'first_name'):
                user_access['all'].append([u.id, u.get_full_name()])

        if 'tag_id' in self.request.POST:
            res = GetParents(self.request.POST['tag_id'], self.kwargs['type'])
            context['parents'] = json.dumps(res.parents_ids)
            context['current'] = res.tag.parent_id if res.tag.parent_id is not None else 0
            if self.request.user.extended.role == USER_ROLES[2][0]:
                tag_access_model = self.model_map[self.kwargs['type']][1]
                user_access['access_edit'] = list(u_id for u_id, in tag_access_model.objects
                                                  .filter(tag=res.tag, modification=True).values_list('user_id'))
                user_access['access_child'] = list(u_id for u_id, in tag_access_model.objects
                                                   .filter(tag=res.tag, child_creation=True).values_list('user_id'))
        else:
            tags_model = self.model_map[self.kwargs['type']][0]
            context['parents'] = json.dumps(list(tag.pk for tag in tags_model.objects.order_by('tag')))
        context['access'] = json.dumps(user_access)
        return context


class RemoveTagView(LoggedCallMixin, Bview.JsonDetailPostView):
    model_map = {'safe': SafeTag, 'unsafe': UnsafeTag}
    unparallel = [UnsafeTag, SafeTag]

    def get_queryset(self):
        return self.model_map[self.kwargs['type']].objects.all()

    def get_context_data(self, **kwargs):
        if not TagAccess(self.request.user, self.object).delete():
            raise BridgeException(_("You don't have an access to remove this tag"))
        self.object.delete()
        return {}


class MarkTagsView(LoggedCallMixin, Bview.JsonView):
    def get_context_data(self, **kwargs):
        res = TagsInfo(
            self.kwargs['type'],
            json.loads(self.request.POST['selected_tags']),
            self.request.POST.get('deleted')
        )
        return {
            'available': json.dumps(res.available, ensure_ascii=False),
            'selected': json.dumps(res.selected, ensure_ascii=False),
            'tree': get_template('marks/MarkTagsTree.html').render({
                'tags': res.table, 'tags_type': self.kwargs['type'], 'can_edit': True, 'user': self.request.user
            }, self.request)
        }


class ChangeAssociationView(LoggedCallMixin, Bview.JsonDetailPostView):
    model_map = {'safe': MarkSafeReport, 'unsafe': MarkUnsafeReport, 'unknown': MarkUnknownReport}
    unparallel = [MarkSafeReport, MarkUnsafeReport, MarkUnknownReport]

    def get_queryset(self):
        return self.model_map[self.kwargs['type']].objects.all()

    def get_object(self, queryset=None):
        if queryset is None:
            queryset = self.get_queryset()
        try:
            obj = queryset.get(report_id=self.kwargs['rid'], mark_id=self.kwargs['mid'])
        except queryset.model.DoesNotExist:
            raise Http404(_("The accosiation was not found"))
        return obj

    def get_context_data(self, **kwargs):
        recalc = (self.kwargs['act'] == 'unconfirm' or self.object.type == ASSOCIATION_TYPE[2][0])
        self.object.author = self.request.user
        self.object.type = ASSOCIATION_TYPE[1][0] if self.kwargs['act'] == 'confirm' else ASSOCIATION_TYPE[2][0]
        self.object.save()
        mutils.UpdateAssociationCache(self.object, recalc)
        return {}


class LikeAssociation(LoggedCallMixin, Bview.JsonDetailPostView):
    model_map = {
        'safe': (MarkSafeReport, SafeAssociationLike),
        'unsafe': (MarkUnsafeReport, UnsafeAssociationLike),
        'unknown': (MarkUnknownReport, UnknownAssociationLike)
    }
    unparallel = [MarkSafeReport, MarkUnsafeReport, MarkUnknownReport]

    def get_queryset(self):
        return self.model_map[self.kwargs['type']][0].objects.all()

    def get_object(self, queryset=None):
        if queryset is None:
            queryset = self.get_queryset()
        try:
            obj = queryset.get(report_id=self.kwargs['rid'], mark_id=self.kwargs['mid'])
        except queryset.model.DoesNotExist:
            raise Http404(_("The accosiation was not found"))
        return obj

    def get_context_data(self, **kwargs):
        self.model_map[self.kwargs['type']][1].objects\
            .filter(association=self.object, author=self.request.user).delete()
        self.model_map[self.kwargs['type']][1].objects\
            .create(association=self.object, author=self.request.user, dislike=(self.kwargs['act'] == 'dislike'))
        return {}


class DeleteMarksView(LoggedCallMixin, Bview.JsonView):
    unparallel = [MarkSafe, MarkUnsafe, MarkUnknown]

    def get_context_data(self, **kwargs):
        return {'report_id': mutils.delete_marks(self.request.user, self.request.POST['type'],
                                                 json.loads(self.request.POST['ids']),
                                                 report_id=self.request.POST.get('report_id'))}


class GetFuncDescription(LoggedCallMixin, Bview.JsonDetailPostView):
    model = MarkUnsafeCompare

    def get_context_data(self, **kwargs):
        return {
            'compare_desc': self.object.description,
            'convert_desc': self.object.convert.description,
            'convert_name': self.object.convert.name
        }


class CheckUnknownMarkView(LoggedCallMixin, Bview.JsonDetailPostView):
    model = ReportUnknown

    def get_context_data(self, **kwargs):
        res = mutils.UnknownUtils.CheckFunction(
            ArchiveFileContent(self.object, 'problem_description', PROBLEM_DESC_FILE).content.decode('utf8'),
            self.request.POST['function'], self.request.POST['pattern'], self.request.POST['is_regex']
        )
        return {'result': res.match, 'problem': res.problem, 'matched': int(res.problem is not None)}
