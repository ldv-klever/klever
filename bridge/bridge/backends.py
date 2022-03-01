from django.contrib.auth import backends


class BridgeModelBackend(backends.ModelBackend):
    def user_can_authenticate(self, user):
        return True

    def get_user(self, user_id):
        user = super(BridgeModelBackend, self).get_user(user_id)
        if user and not user.is_active:
            return None
        return user
