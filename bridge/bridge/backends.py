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

from django.contrib.auth import backends
from django.db.models import Q

from bridge.vars import JOB_ROLES, USER_ROLES
from jobs.models import Job, UserRole


def has_bridge_access(user):
    if not user or not user.is_active:
        return False
    if user.role != USER_ROLES[0][0]:
        return True

    # Job global role is always less than UserRole
    if Job.objects.filter(~Q(global_role=JOB_ROLES[0][0])).exists():
        return True

    # UserRole can't be JOB_ROLES[0][0] as it is the lowest job global role value
    if UserRole.objects.filter(user=user).exists():
        return True
    return False


class BridgeModelBackend(backends.ModelBackend):
    def user_can_authenticate(self, user):
        return True

    def get_user(self, user_id):
        user = super(BridgeModelBackend, self).get_user(user_id)
        if has_bridge_access(user):
            return user
        return None
