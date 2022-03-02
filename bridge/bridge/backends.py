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
