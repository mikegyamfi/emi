# account/backends.py
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

User = get_user_model()


class PhoneOrEmailBackend(ModelBackend):
    """
    Auth with phone (primary) or e-mail (secondary).
    Add to AUTHENTICATION_BACKENDS after the default one.
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        user = User.objects.filter(phone_number=username).first()
        if user is None and "@" in username:
            user = User.objects.filter(email__iexact=username).first()

        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user


