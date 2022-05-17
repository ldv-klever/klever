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
import os
import zipfile

from django.core.files import File
from django.db.models import F
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from rest_framework import status, exceptions
from rest_framework.generics import get_object_or_404, DestroyAPIView, RetrieveAPIView
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from bridge.vars import USER_ROLES
from bridge.utils import BridgeAPIPagination, extract_archive, logger
from bridge.access import ManagerPermission, ServicePermission
from bridge.CustomViews import StreamingResponseAPIView, TemplateAPIRetrieveView
from tools.profiling import LoggedCallMixin

from reports.models import ReportSafe, ReportUnsafe, ReportUnknown
from marks.models import (
    MarkSafe, MarkUnsafe, MarkUnknown, Tag, MarkSafeReport, MarkUnsafeReport,
    MarkUnknownReport, SafeAssociationLike, UnsafeAssociationLike, UnknownAssociationLike,
    MarkSafeHistory, MarkUnsafeHistory, MarkUnknownHistory
)

from marks.Download import AllMarksGenerator, MarksUploader, UploadAllMarks
from marks.markversion import MarkVersionFormData
from marks.serializers import (
    SafeMarkSerializer, UnsafeMarkSerializer, UnknownMarkSerializer, TagSerializer, UpdatedPresetUnsafeMarkSerializer
)
from marks.tags import TagAccessInfo, ChangeTagsAccess, UploadTagsTree
from marks.utils import MarkAccess

from marks.SafeUtils import (
    perform_safe_mark_create, perform_safe_mark_update, RemoveSafeMark, ConfirmSafeMark, UnconfirmSafeMark
)
from marks.UnsafeUtils import (
    perform_unsafe_mark_create, perform_unsafe_mark_update, RemoveUnsafeMark, ConfirmUnsafeMark, UnconfirmUnsafeMark
)
from marks.UnknownUtils import (
    perform_unknown_mark_create, perform_unknown_mark_update, CheckUnknownFunction,
    RemoveUnknownMark, ConfirmUnknownMark, UnconfirmUnknownMark
)

from caches.utils import UpdateMarksTags, RecalculateSafeCache, RecalculateUnsafeCache, RecalculateUnknownCache


class MarkSafeViewSet(LoggedCallMixin, ModelViewSet):
    parser_classes = (JSONParser, FormParser)
    permission_classes = (IsAuthenticated,)
    queryset = MarkSafe.objects.all()
    serializer_class = SafeMarkSerializer
    pagination_class = BridgeAPIPagination

    def get_unparallel(self, request):
        return [MarkSafe] if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} else []

    def create(self, request, *args, **kwargs):
        report = get_object_or_404(ReportSafe, pk=request.data.get('report_id', 0))
        if not MarkAccess(request.user, report=report).can_create:
            raise exceptions.PermissionDenied(_("You don't have an access to create new marks"))

        serializer = self.get_serializer(
            data=request.data, fields=('is_modifiable', 'verdict', 'mark_version')
        )
        serializer.is_valid(raise_exception=True)
        mark, cache_id = perform_safe_mark_create(self.request.user, report, serializer)
        changes_url = '{}?mark_id={}'.format(reverse('marks:safe-ass-changes', args=[cache_id]), mark.id)
        return Response({'url': changes_url}, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        # Partial update is not allowed
        instance = self.get_object()
        if not MarkAccess(request.user, mark=instance).can_edit:
            raise exceptions.PermissionDenied(_("You don't have an access to edit this mark"))

        serializer = self.get_serializer(
            instance, data=request.data, fields=('is_modifiable', 'verdict', 'mark_version')
        )
        serializer.is_valid(raise_exception=True)
        cache_id = perform_safe_mark_update(self.request.user, serializer)

        if getattr(instance, '_prefetched_objects_cache', None):
            instance._prefetched_objects_cache = {}
        changes_url = '{}?mark_id={}'.format(reverse('marks:safe-ass-changes', args=[cache_id]), instance.id)
        return Response({'url': changes_url})

    def perform_destroy(self, instance):
        if not MarkAccess(self.request.user, mark=instance).can_delete:
            raise exceptions.PermissionDenied(_("You don't have an access to remove this mark"))
        reports_ids = RemoveSafeMark(instance).destroy()
        RecalculateSafeCache(reports_ids)


class MarkUnsafeViewSet(LoggedCallMixin, ModelViewSet):
    parser_classes = (JSONParser,)
    permission_classes = (IsAuthenticated,)
    queryset = MarkUnsafe.objects.all()
    serializer_class = UnsafeMarkSerializer
    pagination_class = BridgeAPIPagination

    def get_unparallel(self, request):
        return [MarkUnsafe] if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} else []

    def create(self, request, *args, **kwargs):
        report = get_object_or_404(ReportUnsafe, pk=request.data.get('report_id', 0))
        if not MarkAccess(request.user, report=report).can_create:
            raise exceptions.PermissionDenied(_("You don't have an access to create new marks"))

        serializer = self.get_serializer(
            data=request.data, fields=('is_modifiable', 'verdict', 'mark_version', 'function', 'regexp')
        )
        serializer.is_valid(raise_exception=True)
        mark, cache_id = perform_unsafe_mark_create(self.request.user, report, serializer)
        changes_url = '{}?mark_id={}'.format(reverse('marks:unsafe-ass-changes', args=[cache_id]), mark.id)
        return Response({'url': changes_url}, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        # Partial update is not allowed
        instance = self.get_object()
        if not MarkAccess(request.user, mark=instance).can_edit:
            raise exceptions.PermissionDenied(_("You don't have an access to edit this mark"))

        serializer = self.get_serializer(
            instance, data=request.data, fields=('is_modifiable', 'verdict', 'mark_version', 'error_trace', 'regexp')
        )
        try:
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            logger.error(e)
            raise
        cache_id = perform_unsafe_mark_update(self.request.user, serializer)

        if getattr(instance, '_prefetched_objects_cache', None):
            instance._prefetched_objects_cache = {}
        changes_url = '{}?mark_id={}'.format(reverse('marks:unsafe-ass-changes', args=[cache_id]), instance.id)
        return Response({'url': changes_url})

    def perform_destroy(self, instance):
        if not MarkAccess(self.request.user, mark=instance).can_delete:
            raise exceptions.PermissionDenied(_("You don't have an access to remove this mark"))
        reports_ids = RemoveUnsafeMark(instance).destroy()
        RecalculateUnsafeCache(reports_ids)


class MarkUnknownViewSet(LoggedCallMixin, ModelViewSet):
    parser_classes = (JSONParser,)
    permission_classes = (IsAuthenticated,)
    queryset = MarkUnknown.objects.all()
    serializer_class = UnknownMarkSerializer
    pagination_class = BridgeAPIPagination

    def get_unparallel(self, request):
        return [MarkUnknown] if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} else []

    def create(self, request, *args, **kwargs):
        report = get_object_or_404(ReportUnknown, pk=request.data.get('report_id', 0))
        if not MarkAccess(request.user, report=report).can_create:
            raise exceptions.PermissionDenied(_("You don't have an access to create new marks"))

        serializer = self.get_serializer(data=request.data, fields=(
            'is_modifiable', 'mark_version', 'function', 'is_regexp', 'problem_pattern', 'link'
        ))
        serializer.is_valid(raise_exception=True)
        mark, cache_id = perform_unknown_mark_create(self.request.user, report, serializer)
        changes_url = '{}?mark_id={}'.format(reverse('marks:unknown-ass-changes', args=[cache_id]), mark.id)
        return Response({'url': changes_url}, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        # Partial update is not allowed
        instance = self.get_object()
        if not MarkAccess(request.user, mark=instance).can_edit:
            raise exceptions.PermissionDenied(_("You don't have an access to edit this mark"))

        serializer = self.get_serializer(instance, data=request.data, fields=(
            'is_modifiable', 'mark_version', 'function', 'is_regexp', 'problem_pattern', 'link'
        ))
        serializer.is_valid(raise_exception=True)
        cache_id = perform_unknown_mark_update(self.request.user, serializer)

        if getattr(instance, '_prefetched_objects_cache', None):
            instance._prefetched_objects_cache = {}
        changes_url = '{}?mark_id={}'.format(reverse('marks:unknown-ass-changes', args=[cache_id]), instance.id)
        return Response({'url': changes_url})

    def perform_destroy(self, instance):
        if not MarkAccess(self.request.user, mark=instance).can_delete:
            raise exceptions.PermissionDenied(_("You don't have an access to remove this mark"))
        reports_ids = RemoveUnknownMark(instance).destroy()
        RecalculateUnknownCache(reports_ids)


class TagViewSet(LoggedCallMixin, ModelViewSet):
    parser_classes = (JSONParser,)
    permission_classes = (IsAuthenticated,)
    queryset = Tag.objects.all()
    serializer_class = TagSerializer

    def get_serializer(self, *args, **kwargs):
        fields = None
        if self.request.method == 'GET':
            fields = self.request.query_params.getlist('fields')
        elif self.request.method in {'POST', 'PUT', 'PATCH'}:
            fields = {'parent', 'shortname', 'description'}
        return super().get_serializer(*args, fields=fields, **kwargs)

    def get_unparallel(self, request):
        return [Tag] if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} else []

    def perform_create(self, serializer):
        parent = serializer.validated_data.get('parent')
        if not TagAccessInfo(self.request.user, parent).create:
            raise exceptions.PermissionDenied(_("You don't have an access to create this tag"))
        serializer.save(author=self.request.user)

    def perform_update(self, serializer):
        if not TagAccessInfo(self.request.user, serializer.instance).edit:
            raise exceptions.PermissionDenied(_("You don't have an access to edit this tag"))
        serializer.save(author=self.request.user)
        UpdateMarksTags()

    def perform_destroy(self, instance):
        if not TagAccessInfo(self.request.user, instance).delete:
            raise exceptions.PermissionDenied(_("You don't have an access to delete this tag"))
        super().perform_destroy(instance)
        UpdateMarksTags()


class TagAccessView(LoggedCallMixin, APIView):
    parser_classes = (JSONParser,)
    permission_classes = (ManagerPermission,)

    def post(self, request, tag_id):
        ChangeTagsAccess(tag_id).save(request.data)
        return Response({})

    def get(self, request, tag_id):
        assert request.user.role == USER_ROLES[2][0]
        return Response(ChangeTagsAccess(tag_id).data)


class UploadTagsView(LoggedCallMixin, APIView):
    parser_classes = (MultiPartParser,)
    permission_classes = (ManagerPermission,)

    def post(self, request):
        if 'file' not in request.data:
            raise exceptions.APIException(_('The file with tags was not provided'))
        tags_tree = json.loads(request.data['file'].read().decode('utf8'))
        UploadTagsTree(request.user, tags_tree)
        return Response({})


class RemoveVersionsBase(LoggedCallMixin, DestroyAPIView):
    permission_classes = (IsAuthenticated,)

    def destroy(self, request, *args, **kwargs):
        mark = self.get_object()
        access = MarkAccess(request.user, mark=mark)
        if not access.can_edit:
            raise exceptions.ValidationError(_("You don't have an access to edit this mark"))

        checked_versions = mark.versions.filter(version__in=json.loads(request.data['versions']))
        if len(checked_versions) == 0:
            raise exceptions.ValidationError(_('There is nothing to delete'))
        if not access.can_remove_versions(checked_versions):
            raise exceptions.ValidationError(_("You don't have an access to remove one of the selected version"))
        checked_versions.delete()

        return Response({'message': _('Selected versions were successfully deleted')})


class SafeRmVersionsView(RemoveVersionsBase):
    queryset = MarkSafe.objects


class UnsafeRmVersionsView(RemoveVersionsBase):
    queryset = MarkUnsafe.objects


class UnknownRmVersionsView(RemoveVersionsBase):
    queryset = MarkUnknown.objects


class CheckUnknownFuncView(LoggedCallMixin, APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, report_id):
        res = CheckUnknownFunction(
            get_object_or_404(ReportUnknown, pk=report_id),
            request.data['function'],
            request.data['pattern'],
            request.data['is_regex']
        )
        return Response(data={
            'result': res.match, 'problem': res.problem, 'matched': int(res.problem is not None)
        })


class RemoveSafeMarksView(LoggedCallMixin, APIView):
    unparallel = [MarkSafe]
    permission_classes = (ManagerPermission,)

    def delete(self, request):
        reports_ids = set()
        for mark in MarkSafe.objects.filter(id__in=json.loads(self.request.POST['ids'])):
            reports_ids |= RemoveSafeMark(mark).destroy()
        RecalculateSafeCache(reports_ids)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RemoveUnsafeMarksView(LoggedCallMixin, APIView):
    unparallel = [MarkUnsafe]
    permission_classes = (ManagerPermission,)

    def delete(self, request):
        reports_ids = set()
        for mark in MarkUnsafe.objects.filter(id__in=json.loads(self.request.POST['ids'])):
            reports_ids |= RemoveUnsafeMark(mark).destroy()
        RecalculateUnsafeCache(reports_ids)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RemoveUnknownMarksView(LoggedCallMixin, APIView):
    unparallel = [MarkUnknown]
    permission_classes = (ManagerPermission,)

    def delete(self, request):
        reports_ids = set()
        for mark in MarkUnknown.objects.filter(id__in=json.loads(self.request.POST['ids'])):
            reports_ids |= RemoveUnknownMark(mark).destroy()
        RecalculateUnknownCache(reports_ids)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ConfirmSafeMarkView(LoggedCallMixin, APIView):
    def post(self, request, pk):
        ConfirmSafeMark(request.user, get_object_or_404(MarkSafeReport, pk=pk))
        return Response({})

    def delete(self, request, pk):
        UnconfirmSafeMark(request.user, get_object_or_404(MarkSafeReport, pk=pk))
        return Response({})


class ConfirmUnsafeMarkView(LoggedCallMixin, APIView):
    def post(self, request, pk):
        ConfirmUnsafeMark(request.user, get_object_or_404(MarkUnsafeReport, pk=pk))
        return Response({})

    def delete(self, request, pk):
        UnconfirmUnsafeMark(request.user, get_object_or_404(MarkUnsafeReport, pk=pk))
        return Response({})


class ConfirmUnknownMarkView(LoggedCallMixin, APIView):
    def post(self, request, pk):
        ConfirmUnknownMark(request.user, get_object_or_404(MarkUnknownReport, pk=pk))
        return Response({})

    def delete(self, request, pk):
        UnconfirmUnknownMark(request.user, get_object_or_404(MarkUnknownReport, pk=pk))
        return Response({})


class LikeMarkBase(LoggedCallMixin, APIView):
    association_model = None
    like_model = None

    def process_like(self, pk, user, dislike):
        assert self.association_model is not None and self.like_model is not None, 'Wrong usage'
        association = get_object_or_404(self.association_model, pk=pk)
        self.like_model.objects.filter(association=association, author=user).delete()
        self.like_model.objects.create(association=association, author=user, dislike=dislike)

    def post(self, request, pk):
        self.process_like(pk, request.user, False)
        return Response({})

    def delete(self, request, pk):
        self.process_like(pk, request.user, True)
        return Response({})


class LikeSafeMark(LikeMarkBase):
    association_model = MarkSafeReport
    like_model = SafeAssociationLike


class LikeUnsafeMark(LikeMarkBase):
    association_model = MarkUnsafeReport
    like_model = UnsafeAssociationLike


class LikeUnknownMark(LikeMarkBase):
    association_model = MarkUnknownReport
    like_model = UnknownAssociationLike


class DownloadAllMarksView(LoggedCallMixin, StreamingResponseAPIView):
    unparallel = ['MarkSafe', 'MarkUnsafe', 'MarkUnknown']
    permission_classes = (IsAuthenticated,)

    def get_generator(self):
        return AllMarksGenerator()


class UploadMarksView(LoggedCallMixin, APIView):
    unparallel = [MarkSafe, MarkUnsafe, MarkUnknown]

    def post(self, request):
        if not MarkAccess(request.user).can_upload:
            raise exceptions.PermissionDenied(_("You don't have an access to create new marks"))

        marks_links = []
        failed_mark_uploads = 0
        marks_uploader = MarksUploader(request.user)
        for f in self.request.FILES.getlist('file'):
            with zipfile.ZipFile(f, 'r') as zfp:
                if all(file_name.endswith('.zip') for file_name in zfp.namelist()):
                    marks_dir = extract_archive(f)
                    for arch_name in os.listdir(marks_dir.name):
                        with open(os.path.join(marks_dir.name, arch_name), mode='rb') as fp:
                            try:
                                marks_links.append(marks_uploader.upload_mark(File(fp, name=arch_name))[1])
                            except Exception as e:
                                logger.exception(e)
                                logger.error('Uploading of mark "{}" has failed.'.format(arch_name))
                                failed_mark_uploads += 1
                else:
                    marks_links.append(marks_uploader.upload_mark(f)[1])

        if len(marks_links) == 1:
            return Response({'url': marks_links[0]})

        if failed_mark_uploads:
            return Response({'message': _('Number of created marks: %(number)s.'
                                          ' Number of marks which uploading failed: %(failed_number)s.'
                                          ' See logs for details.')
                                        % {'number': len(marks_links), 'failed_number': failed_mark_uploads}})
        else:
            return Response({'message': _('Number of created marks: %(number)s') % {'number': len(marks_links)}})


class UploadAllMarksView(LoggedCallMixin, APIView):
    unparallel = [MarkSafe, MarkUnsafe, MarkUnknown]
    permission_classes = (ServicePermission,)

    def post(self, request):
        marks_dir = extract_archive(self.request.FILES['file'])
        res = UploadAllMarks(request.user, marks_dir.name, bool(int(request.POST.get('delete', 0))))
        return Response(res.numbers)


class InlineEditForm(LoggedCallMixin, TemplateAPIRetrieveView):
    permission_classes = (IsAuthenticated,)
    template_name = 'marks/InlineMarkForm.html'
    lookup_field = 'mark_id'
    mtype = None

    def get_queryset(self):
        if self.mtype == 'safe':
            model = MarkSafeHistory
        elif self.mtype == 'unsafe':
            model = MarkUnsafeHistory
        elif self.mtype == 'unknown':
            model = MarkUnknownHistory
        else:
            raise RuntimeError('Wrong view usage')
        return model.objects.select_related('mark').filter(version=F('mark__version'))

    def get_context_data(self, instance, **kwargs):
        context = super().get_context_data(instance, **kwargs)
        context.update({
            'action': 'edit',
            'attrs': instance.attrs.all(),
            'data': MarkVersionFormData(self.mtype, mark_version=instance),
            'save_url': reverse('marks:api-{mtype}-detail'.format(mtype=self.mtype), args=[instance.mark_id]),
            'save_method': 'PUT'
        })
        return context


class InlineCreateForm(LoggedCallMixin, TemplateAPIRetrieveView):
    permission_classes = (IsAuthenticated,)
    template_name = 'marks/InlineMarkForm.html'
    lookup_url_kwarg = 'r_id'
    mtype = None

    def get_queryset(self):
        if self.mtype == 'safe':
            model = ReportSafe
        elif self.mtype == 'unsafe':
            model = ReportUnsafe
        elif self.mtype == 'unknown':
            model = ReportUnknown
        else:
            raise RuntimeError('Wrong view usage')
        return model.objects.all()

    def get_context_data(self, instance, **kwargs):
        context = super().get_context_data(instance, **kwargs)
        context.update({
            'action': 'create',
            'attrs': instance.attrs.all(),
            'data': MarkVersionFormData(self.mtype),
            'save_url': reverse('marks:api-{mtype}-list'.format(mtype=self.mtype)),
            'save_method': 'POST'
        })
        return context


class GetUpdatedPresetView(LoggedCallMixin, RetrieveAPIView):
    permission_classes = (IsAuthenticated,)
    queryset = MarkUnsafe.objects.all()
    serializer_class = UpdatedPresetUnsafeMarkSerializer
    lookup_url_kwarg = "identifier"
    lookup_field = "identifier"
