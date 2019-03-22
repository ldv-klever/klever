import json

from django.utils.translation import ugettext_lazy as _

from rest_framework import status, exceptions
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.generics import get_object_or_404, RetrieveAPIView, GenericAPIView, CreateAPIView
from rest_framework.mixins import CreateModelMixin, RetrieveModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from bridge.vars import USER_ROLES
from bridge.access import ManagerPermission
from tools.profiling import LoggedCallMixin

from users.models import User
from reports.models import ReportSafe, ReportUnsafe, ReportUnknown
from marks.models import MarkSafe, MarkUnsafe, MarkUnknown, SafeTag, UnsafeTag, SafeTagAccess, UnsafeTagAccess
from marks.utils import MarkAccess
from marks.tags import TagAccess, ChangeTagsAccess, UploadTags
from marks.serializers import (
    SafeMarkSerializer, UnsafeMarkSerializer, UnknownMarkSerializer, SafeTagSerializer, UnsafeTagSerializer
)
from marks.SafeUtils import perform_safe_mark_create, perform_safe_mark_update
from marks.UnsafeUtils import perform_unsafe_mark_create, perform_unsafe_mark_update
from marks.UnknownUtils import perform_unknown_mark_create, perform_unknown_mark_update

from caches.utils import UpdateSafeMarksTags, UpdateUnsafeMarksTags


class MarkSafeViewSet(LoggedCallMixin, ModelViewSet):
    parser_classes = (JSONParser,)
    permission_classes = (IsAuthenticated,)
    queryset = MarkSafe.objects.all()
    serializer_class = SafeMarkSerializer

    def get_unparallel(self, request):
        return [MarkSafe] if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} else []

    def create(self, request, *args, **kwargs):
        report = get_object_or_404(ReportSafe, pk=request.data.get('report_id', 0))
        if not MarkAccess(self.request.user, report=report).can_create():
            raise exceptions.PermissionDenied(_("You don't have an access to create new marks"))

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cache_id = perform_safe_mark_create(self.request.user, report, serializer)
        return Response({'cache_id': cache_id}, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        # Partial update is not allowed
        instance = self.get_object()
        if not MarkAccess(self.request.user, mark=instance).can_edit():
            raise exceptions.PermissionDenied(_("You don't have an access to edit this mark"))

        serializer = self.get_serializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        cache_id = perform_safe_mark_update(self.request.user, serializer)

        if getattr(instance, '_prefetched_objects_cache', None):
            instance._prefetched_objects_cache = {}
        return Response({'cache_id': cache_id})


class MarkUnsafeViewSet(LoggedCallMixin, ModelViewSet):
    parser_classes = (JSONParser,)
    permission_classes = (IsAuthenticated,)
    queryset = MarkUnsafe.objects.all()
    serializer_class = UnsafeMarkSerializer

    def get_unparallel(self, request):
        return [MarkUnsafe] if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} else []

    def create(self, request, *args, **kwargs):
        report = get_object_or_404(ReportUnsafe, pk=request.data.get('report_id', 0))
        if not MarkAccess(self.request.user, report=report).can_create():
            raise exceptions.PermissionDenied(_("You don't have an access to create new marks"))

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cache_id = perform_unsafe_mark_create(self.request.user, report, serializer)
        return Response({'cache_id': cache_id}, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        # Partial update is not allowed
        instance = self.get_object()
        if not MarkAccess(self.request.user, mark=instance).can_edit():
            raise exceptions.PermissionDenied(_("You don't have an access to edit this mark"))

        serializer = self.get_serializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        cache_id = perform_unsafe_mark_update(self.request.user, serializer)

        if getattr(instance, '_prefetched_objects_cache', None):
            instance._prefetched_objects_cache = {}
        return Response({'cache_id': cache_id})


class MarkUnknownViewSet(LoggedCallMixin, ModelViewSet):
    parser_classes = (JSONParser,)
    permission_classes = (IsAuthenticated,)
    queryset = MarkUnknown.objects.all()
    serializer_class = UnknownMarkSerializer

    def get_unparallel(self, request):
        return [MarkUnknown] if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} else []

    def create(self, request, *args, **kwargs):
        report = get_object_or_404(ReportUnknown, pk=request.data.get('report_id', 0))
        if not MarkAccess(self.request.user, report=report).can_create():
            raise exceptions.PermissionDenied(_("You don't have an access to create new marks"))

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cache_id = perform_unknown_mark_create(self.request.user, report, serializer)
        return Response({'cache_id': cache_id}, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        # Partial update is not allowed
        instance = self.get_object()
        if not MarkAccess(self.request.user, mark=instance).can_edit():
            raise exceptions.PermissionDenied(_("You don't have an access to edit this mark"))

        serializer = self.get_serializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        cache_id = perform_unknown_mark_update(self.request.user, serializer)

        if getattr(instance, '_prefetched_objects_cache', None):
            instance._prefetched_objects_cache = {}
        return Response({'cache_id': cache_id})


class SafeTagViewSet(LoggedCallMixin, ModelViewSet):
    parser_classes = (JSONParser,)
    permission_classes = (IsAuthenticated,)
    queryset = SafeTag.objects.all()
    serializer_class = SafeTagSerializer

    def get_unparallel(self, request):
        return [SafeTag] if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} else []

    def perform_create(self, serializer):
        parent = serializer.validated_data.get('parent')
        if not TagAccess(self.request.user, parent).create:
            raise exceptions.PermissionDenied(_("You don't have an access to create this tag"))
        serializer.save(author=self.request.user)

    def perform_update(self, serializer):
        if not TagAccess(self.request.user, serializer.instance).edit:
            raise exceptions.PermissionDenied(_("You don't have an access to edit this tag"))
        serializer.save(author=self.request.user)
        UpdateSafeMarksTags()


class UnsafeTagViewSet(LoggedCallMixin, ModelViewSet):
    parser_classes = (JSONParser,)
    permission_classes = (IsAuthenticated,)
    queryset = UnsafeTag.objects.all()
    serializer_class = UnsafeTagSerializer

    def get_unparallel(self, request):
        return [UnsafeTag] if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} else []

    def perform_create(self, serializer):
        parent = serializer.validated_data.get('parent')
        if not TagAccess(self.request.user, parent).create:
            raise exceptions.PermissionDenied(_("You don't have an access to create this tag"))
        serializer.save(author=self.request.user)

    def perform_update(self, serializer):
        if not TagAccess(self.request.user, serializer.instance).edit:
            raise exceptions.PermissionDenied(_("You don't have an access to edit this tag"))
        serializer.save(author=self.request.user)
        UpdateUnsafeMarksTags()


class TagAccessAPIView(LoggedCallMixin, APIView):
    parser_classes = (JSONParser,)
    permission_classes = (ManagerPermission,)

    def post(self, request, tag_type, tag_id):
        ChangeTagsAccess(tag_type, tag_id).save(request.data)
        return Response({})

    def get(self, request, tag_type, tag_id):
        assert request.user.role == USER_ROLES[2][0]
        return Response(ChangeTagsAccess(tag_type, tag_id).data)


class UploadTagsAPIView(LoggedCallMixin, APIView):
    parser_classes = (MultiPartParser,)
    permission_classes = (ManagerPermission,)

    def post(self, request, tag_type):
        if 'file' not in request.data:
            raise exceptions.APIException(_('The file with tags was not provided'))
        UploadTags(request.user, tag_type, request.data['file'])
        return Response({})
