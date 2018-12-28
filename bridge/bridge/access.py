from rest_framework.permissions import IsAuthenticated

from bridge.utils import USER_ROLES

from jobs.models import Job, JobHistory
from jobs.utils import JobAccess


class WriteJobPermission(IsAuthenticated):
    def has_permission(self, request, view):
        return super().has_permission(request, view) and JobAccess(request.user).can_create()

    def has_object_permission(self, request, view, obj):
        return super().has_object_permission(request, view, obj) and JobAccess(request.user, obj).can_edit()


class ViewJobPermission(IsAuthenticated):
    def has_object_permission(self, request, view, obj):
        if isinstance(obj, JobHistory):
            obj = obj.job
        return JobAccess(request.user, obj).can_view()


class ServicePermission(IsAuthenticated):
    def has_permission(self, request, view):
        # Authenticated and (manager or service) user
        return super().has_permission(request, view) and request.user.role in {USER_ROLES[2][0], USER_ROLES[4][0]}
