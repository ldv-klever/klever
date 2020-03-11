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

from rest_framework.permissions import IsAuthenticated

from bridge.utils import USER_ROLES

from jobs.models import Job, JobHistory
from jobs.utils import JobAccess
from reports.models import ReportComponent


class WriteJobPermission(IsAuthenticated):
    def has_permission(self, request, view):
        return super().has_permission(request, view) and JobAccess(request.user).can_create

    def has_object_permission(self, request, view, obj):
        return super().has_object_permission(request, view, obj) and JobAccess(request.user, obj).can_edit


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
        return JobAccess(request.user, job).can_view


class DestroyJobPermission(IsAuthenticated):
    def has_object_permission(self, request, view, obj):
        return JobAccess(request.user, obj).can_delete


class ServicePermission(IsAuthenticated):
    def has_permission(self, request, view):
        # Authenticated and (manager or service) user
        return super().has_permission(request, view) and request.user.role in {USER_ROLES[2][0], USER_ROLES[4][0]}


class ManagerPermission(IsAuthenticated):
    def has_permission(self, request, view):
        # Authenticated and (manager or service) user
        return super().has_permission(request, view) and request.user.role == USER_ROLES[2][0]


class DataViewPermission(IsAuthenticated):
    def has_object_permission(self, request, view, obj):
        return super().has_object_permission(request, view, obj) and request.user == obj.author
