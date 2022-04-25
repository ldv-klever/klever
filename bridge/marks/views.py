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
from urllib.parse import unquote

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import F
from django.template.defaulttags import register
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.generic import DetailView
from django.views.generic.base import TemplateView
from django.views.generic.detail import SingleObjectMixin

from bridge.vars import VIEW_TYPES, PROBLEM_DESC_FILE, COMPARE_FUNCTIONS, CONVERT_FUNCTIONS
from bridge.utils import BridgeException, ArchiveFileContent
from bridge.CustomViews import DataViewMixin, StreamingResponseView
from tools.profiling import LoggedCallMixin

from reports.models import ReportSafe, ReportUnsafe, ReportUnknown
from marks.models import MarkSafe, MarkUnsafe, MarkUnknown, MarkSafeHistory, MarkUnsafeHistory, MarkUnknownHistory

from marks.Download import (
    SafeMarkGenerator, UnsafeMarkGenerator, UnknownMarkGenerator, SeveralMarksGenerator,
    SafePresetFile, UnsafePresetFile, UnknownPresetFile
)
from marks.markversion import MarkVersionFormData
from marks.serializers import SMVlistSerializerRO, UMVlistSerializerRO, FMVlistSerializerRO
from marks.tables import (
    SafeMarksTable, UnsafeMarksTable, UnknownMarksTable,
    SafeAssociationsTable, UnsafeAssociationsTable, UnknownAssociationsTable,
    SafeAssChanges, UnsafeAssChanges, UnknownAssChanges
)
from marks.tags import AllTagsTree, DownloadTags, MarkTagsTree, SelectedTagsTree
from marks.utils import MarkAccess, CompareMarkVersions
from reports.verdicts import safe_color, unsafe_color, bug_status_color


@register.filter
def value_type(value):
    return str(type(value))


class SafeMarksListView(LoginRequiredMixin, LoggedCallMixin, DataViewMixin, TemplateView):
    template_name = 'marks/MarkList.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tabledata'] = SafeMarksTable(self.request.user, self.get_view(VIEW_TYPES[8]), self.request.GET)
        return context


class UnsafeMarksListView(LoginRequiredMixin, LoggedCallMixin, DataViewMixin, TemplateView):
    template_name = 'marks/MarkList.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tabledata'] = UnsafeMarksTable(self.request.user, self.get_view(VIEW_TYPES[7]), self.request.GET)
        return context


class UnknownMarksListView(LoginRequiredMixin, LoggedCallMixin, DataViewMixin, TemplateView):
    template_name = 'marks/MarkList.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tabledata'] = UnknownMarksTable(self.request.user, self.get_view(VIEW_TYPES[9]), self.request.GET)
        return context


class SafeMarkPage(LoginRequiredMixin, LoggedCallMixin, DataViewMixin, DetailView):
    template_name = 'marks/SafeMark.html'
    model = MarkSafe

    def get_context_data(self, **kwargs):
        mark_version = MarkSafeHistory.objects.select_related('mark', 'author') \
            .get(mark=self.object, version=F('mark__version'))
        return {
            'mark': self.object, 'mark_version': mark_version,
            'verdict': {
                'id': mark_version.verdict,
                'text': mark_version.get_verdict_display(),
                'color': safe_color(mark_version.verdict, inverted=True)
            },
            'access': MarkAccess(self.request.user, mark=self.object),
            'versions': SMVlistSerializerRO(mark=self.object).data,
            'tags': MarkTagsTree(mark_version),
            'reports': SafeAssociationsTable(
                self.request.user, self.object, self.get_view(VIEW_TYPES[14]), self.request.GET
            )
        }


class UnsafeMarkPage(LoginRequiredMixin, LoggedCallMixin, DataViewMixin, DetailView):
    template_name = 'marks/UnsafeMark.html'
    model = MarkUnsafe

    def get_context_data(self, **kwargs):
        mark_version = MarkUnsafeHistory.objects.select_related('mark', 'author')\
            .get(mark=self.object, version=F('mark__version'))

        error_trace = None
        if self.object.error_trace:
            with self.object.error_trace.file.file as fp:
                error_trace = fp.read().decode('utf-8')

        context = {
            'mark': self.object, 'mark_version': mark_version,
            'verdict': {
                'id': self.object.verdict,
                'text': self.object.get_verdict_display(),
                'color': unsafe_color(self.object.verdict, inverted=True)
            },
            'access': MarkAccess(self.request.user, mark=self.object),
            'versions': UMVlistSerializerRO(mark=self.object).data,
            'tags': MarkTagsTree(mark_version),
            'reports': UnsafeAssociationsTable(
                self.request.user, self.object, self.get_view(VIEW_TYPES[13]), self.request.GET
            ),
            'error_trace': error_trace,
            'compare_func': {
                'name': self.object.function,
                'desc': COMPARE_FUNCTIONS[self.object.function]['desc']
            },
            'convert_func': {
                'name': COMPARE_FUNCTIONS[self.object.function]['convert'],
                'desc': CONVERT_FUNCTIONS[COMPARE_FUNCTIONS[self.object.function]['convert']]
            }
        }
        if self.object.status:
            context['bug_status'] = {
                'id': self.object.status,
                'text': self.object.get_status_display(),
                'color': bug_status_color(self.object.status)
            }
        return context


class UnknownMarkPage(LoginRequiredMixin, LoggedCallMixin, DataViewMixin, DetailView):
    template_name = 'marks/UnknownMark.html'
    model = MarkUnknown

    def get_context_data(self, **kwargs):
        mark_version = MarkUnknownHistory.objects.select_related('mark', 'author')\
            .get(mark=self.object, version=F('mark__version'))
        return {
            'mark': self.object, 'mark_version': mark_version,
            'access': MarkAccess(self.request.user, mark=self.object),
            'versions': FMVlistSerializerRO(mark=self.object).data,
            'reports': UnknownAssociationsTable(
                self.request.user, self.object, self.get_view(VIEW_TYPES[15]), self.request.GET
            )
        }


class MarkCreateViewBase(LoginRequiredMixin, LoggedCallMixin, DetailView):
    mark_type = None
    template_name = 'marks/MarkForm.html'

    def get_queryset(self):
        queryset = super(MarkCreateViewBase, self).get_queryset()
        return queryset.select_related('decision')

    def get_context_data(self, **kwargs):
        access = MarkAccess(self.request.user, report=self.object)
        if not access.can_create:
            raise BridgeException(_("You don't have an access to create new mark"))
        context = super().get_context_data(**kwargs)
        context.update({
            'access': access,
            'cancel_url': reverse('reports:{}'.format(self.mark_type), args=[
                self.object.decision.identifier, self.object.identifier
            ]),
            'save_url': reverse('marks:api-{mtype}-list'.format(mtype=self.mark_type)),
            'save_method': 'POST',
            'data': MarkVersionFormData(self.mark_type),
            'attrs': self.object.attrs.all()
        })
        return context


class SafeMarkCreateView(MarkCreateViewBase):
    mark_type = 'safe'
    model = ReportSafe


class UnsafeMarkCreateView(MarkCreateViewBase):
    mark_type = 'unsafe'
    model = ReportUnsafe


class UnknownMarkCreateView(MarkCreateViewBase):
    mark_type = 'unknown'
    model = ReportUnknown

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add problem description for unknown mark creation
        context['problem_description'] = ArchiveFileContent(
            self.object, 'problem_description', PROBLEM_DESC_FILE
        ).content.decode('utf8')
        return context


class MarkEditViewBase(LoginRequiredMixin, LoggedCallMixin, DetailView):
    mark_type = None
    version_model = None
    versions_serializer_class = None
    template_name = 'marks/MarkForm.html'

    def get_context_data(self, **kwargs):
        access = MarkAccess(self.request.user, mark=self.object)
        if not access.can_edit:
            raise BridgeException(_("You don't have an access to edit this mark"))
        context = super().get_context_data(**kwargs)
        mark_version = self.version_model.objects.select_related('mark')\
            .get(mark=self.object, version=int(self.request.GET.get('version', self.object.version)))
        context.update({
            'access': access,
            'versions': self.versions_serializer_class(mark=self.object).data,
            'cancel_url': reverse('marks:{}'.format(self.mark_type), args=[self.object.id]),
            'save_url': reverse('marks:api-{mtype}-detail'.format(mtype=self.mark_type), args=[self.object.id]),
            'save_method': 'PUT',
            'data': MarkVersionFormData(self.mark_type, mark_version=mark_version),
            'attrs': mark_version.attrs.all()
        })
        return context


class SafeMarkEditView(MarkEditViewBase):
    model = MarkSafe
    mark_type = 'safe'
    version_model = MarkSafeHistory
    versions_serializer_class = SMVlistSerializerRO


class UnsafeMarkEditView(MarkEditViewBase):
    model = MarkUnsafe
    mark_type = 'unsafe'
    version_model = MarkUnsafeHistory
    versions_serializer_class = UMVlistSerializerRO


class UnknownMarkEditView(MarkEditViewBase):
    model = MarkUnknown
    mark_type = 'unknown'
    version_model = MarkUnknownHistory
    versions_serializer_class = FMVlistSerializerRO


class SafeAssChangesView(LoginRequiredMixin, LoggedCallMixin, DataViewMixin, TemplateView):
    template_name = 'marks/SaveMarkResult.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        if self.request.GET.get('mark_id'):
            context['mark_url'] = reverse('marks:safe', args=[self.request.GET['mark_id']])
        context['TableData'] = SafeAssChanges(self.kwargs['cache_id'], self.get_view(VIEW_TYPES[16]))
        return context


class UnsafeAssChangesView(LoginRequiredMixin, LoggedCallMixin, DataViewMixin, TemplateView):
    template_name = 'marks/SaveMarkResult.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        if self.request.GET.get('mark_id'):
            context['mark_url'] = reverse('marks:unsafe', args=[self.request.GET['mark_id']])
        context['TableData'] = UnsafeAssChanges(self.kwargs['cache_id'], self.get_view(VIEW_TYPES[17]))
        return context


class UnknownAssChangesView(LoginRequiredMixin, LoggedCallMixin, DataViewMixin, TemplateView):
    template_name = 'marks/SaveMarkResult.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        if self.request.GET.get('mark_id'):
            context['mark_url'] = reverse('marks:unknown', args=[self.request.GET['mark_id']])
        context['TableData'] = UnknownAssChanges(self.kwargs['cache_id'], self.get_view(VIEW_TYPES[18]))
        return context


class MarkTagsView(LoggedCallMixin, TemplateView):
    template_name = 'marks/MarkTagsForm.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tags'] = SelectedTagsTree(
            self.request.GET.getlist('selected'), self.request.GET.get('deleted'), self.request.GET.get('added')
        )
        return context


class CompareVersionsBase(LoginRequiredMixin, LoggedCallMixin, DetailView):
    template_name = 'marks/markVCmp.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        mark_versions = self.object.versions.filter(version__in=[self.kwargs['v1'], self.kwargs['v2']])\
            .select_related('author')
        if len(mark_versions) != 2:
            raise BridgeException(_('The page is outdated, reload it please'))
        context['data'] = CompareMarkVersions(self.object, *list(mark_versions))
        return context


class SafeCompareVersionsView(CompareVersionsBase):
    model = MarkSafe


class UnsafeCompareVersionsView(CompareVersionsBase):
    model = MarkUnsafe


class UnknownCompareVersionsView(CompareVersionsBase):
    model = MarkUnknown


class TagsTreeView(LoginRequiredMixin, LoggedCallMixin, TemplateView):
    template_name = 'marks/TagsTree.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tree'] = AllTagsTree(self.request.user)
        return context


class DownloadTagsView(LoginRequiredMixin, StreamingResponseView):
    def get_generator(self):
        return DownloadTags()


class DownloadSafeMarkView(LoginRequiredMixin, LoggedCallMixin, SingleObjectMixin, StreamingResponseView):
    model = MarkSafe

    def get_generator(self):
        return SafeMarkGenerator(self.get_object())


class DownloadUnsafeMarkView(LoginRequiredMixin, LoggedCallMixin, SingleObjectMixin, StreamingResponseView):
    model = MarkUnsafe

    def get_generator(self):
        return UnsafeMarkGenerator(self.get_object())


class DownloadUnknownMarkView(LoginRequiredMixin, LoggedCallMixin, SingleObjectMixin, StreamingResponseView):
    model = MarkUnknown

    def get_generator(self):
        return UnknownMarkGenerator(self.get_object())


class PresetSafeMarkView(LoginRequiredMixin, LoggedCallMixin, SingleObjectMixin, StreamingResponseView):
    model = MarkSafe

    def get_generator(self):
        return SafePresetFile(self.get_object())


class PresetUnsafeMarkView(LoginRequiredMixin, LoggedCallMixin, SingleObjectMixin, StreamingResponseView):
    model = MarkUnsafe

    def get_generator(self):
        return UnsafePresetFile(self.get_object())


class PresetUnknownMarkView(LoginRequiredMixin, LoggedCallMixin, SingleObjectMixin, StreamingResponseView):
    model = MarkUnknown

    def get_generator(self):
        return UnknownPresetFile(self.get_object())


class DownloadSeveralMarksView(LoginRequiredMixin, LoggedCallMixin, StreamingResponseView):
    def get_generator(self):
        marks = []
        marks_data = json.loads(unquote(self.request.GET['marks']))
        if marks_data.get('safe'):
            marks.extend(list(MarkSafe.objects.filter(id__in=marks_data['safe'])))
        if marks_data.get('unsafe'):
            marks.extend(list(MarkUnsafe.objects.filter(id__in=marks_data['unsafe'])))
        if marks_data.get('unknown'):
            marks.extend(list(MarkUnknown.objects.filter(id__in=marks_data['unknown'])))
        return SeveralMarksGenerator(marks)
