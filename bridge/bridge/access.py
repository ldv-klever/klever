from rest_framework.permissions import IsAuthenticated

from bridge.utils import USER_ROLES

from jobs.models import Job, JobHistory
from jobs.utils import JobAccess
from marks.utils import MarkAccess
from reports.models import ReportComponent


class WriteJobPermission(IsAuthenticated):
    def has_permission(self, request, view):
        return super().has_permission(request, view) and JobAccess(request.user).can_create()

    def has_object_permission(self, request, view, obj):
        return super().has_object_permission(request, view, obj) and JobAccess(request.user, obj).can_edit()


class ViewJobPermission(IsAuthenticated):
    def has_object_permission(self, request, view, obj):
        if isinstance(obj, Job):
            job = obj
        elif isinstance(obj, JobHistory):
            job = obj.job
        elif isinstance(obj, ReportComponent):
            job = obj.root.job
        else:
            return False
        return JobAccess(request.user, job).can_view()


class DestroyJobPermission(IsAuthenticated):
    def has_object_permission(self, request, view, obj):
        return JobAccess(request.user, obj).can_delete()


class ServicePermission(IsAuthenticated):
    def has_permission(self, request, view):
        # Authenticated and (manager or service) user
        return super().has_permission(request, view) and request.user.role in {USER_ROLES[2][0], USER_ROLES[4][0]}


class ManagerPermission(IsAuthenticated):
    def has_permission(self, request, view):
        # Authenticated and (manager or service) user
        return super().has_permission(request, view) and request.user.role == USER_ROLES[2][0]
