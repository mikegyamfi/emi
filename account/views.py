# accounts/views.py
import logging

from django.db import transaction
from django.db.models import Prefetch, Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status, generics, serializers
from rest_framework.exceptions import ValidationError, AuthenticationFailed
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView, TokenBlacklistView

from core.models import OTP, OTPPurpose, OTPChannel
from core.otp_service import generate_otp
from core.response import fail, ok
from core.utils import flatten_error, dispatch_sms_otp
from .models import CustomUser, Role
from .serializers import (
    SignUpSerializer,
    VerifyEmailSerializer,
    ResendActivationSerializer, TokenPairSerializer, PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer, ChangePasswordSerializer, UserPublicSerializer, UserSelfUpdateSerializer,
    VerifyPhoneSerializer, ResendPhoneActivationSerializer,
)

logger = logging.getLogger(__name__)


class SafeAPIView(APIView):
    """
    Base class: wraps handler methods so **any** unforeseen error
    becomes a clean JSON 500 response (logger keeps the traceback).
    """

    def handle_exception(self, exc):
        if isinstance(exc, ValidationError):
            # Let DRF convert it → 400
            return super().handle_exception(exc)

        logger.exception("Unhandled error in %s", self.__class__.__name__, exc_info=exc)
        return Response(
            {"detail": "Internal server error."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class SignUpView(APIView):
    """
    POST /signup/

    • 201 → brand-new user created
    • 202 → exists but not verified → re-sent OTP
    • 409 → already verified
    • 400 → invalid payload
    """
    permission_classes = (AllowAny,)

    def post(self, request, *args, **kwargs):
        email = (request.data.get("email") or "").lower().strip()
        phone = (request.data.get("phone_number") or "").strip()

        # 1) Existing account?
        if email or phone:
            dup_q = Q()
            if email:
                dup_q |= Q(email__iexact=email)
            if phone:
                dup_q |= Q(phone_number=phone)
            user = CustomUser.objects.filter(dup_q).first()
            if user:
                # already fully verified?
                if user.email_verified or user.phone_verified:
                    return fail(
                        "Account already exists.",
                        error_message="That phone or email is already in use.",
                        status=status.HTTP_409_CONFLICT
                    )
                # unverified → expire old OTP & reissue
                OTP.objects.filter(
                    user=user,
                    purpose__in=(OTPPurpose.USER_EMAIL, OTPPurpose.USER_PHONE),
                    verified=False
                ).update(expires_at=timezone.now() - timezone.timedelta(seconds=1))

                otp = generate_otp(
                    user=user,
                    purpose=OTPPurpose.USER_PHONE,
                    channel=OTPChannel.SMS,
                    digits=6,
                    target=user.phone_number,
                )
                dispatch_sms_otp(otp.id, OTPPurpose.USER_PHONE)

                return ok(
                    "Account exists but is not verified. We’ve sent you a new code.",
                    status=status.HTTP_202_ACCEPTED
                )

        # 2) Brand-new sign-up
        serializer = SignUpSerializer(data=request.data)
        if not serializer.is_valid():
            # pick the first field error message for `error_message`
            field_errors = serializer.errors
            first_field, messages = next(iter(field_errors.items()))
            first_message = messages[0] if isinstance(messages, (list, tuple)) and messages else str(messages)
            return fail(
                "Registration failed.",
                error_message=first_message,
                field_errors=field_errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        # 3) Create user + OTP
        with transaction.atomic():
            user = serializer.save()

        return ok(
            "Account created. Check your inbox/phone for the verification code.",
            status=status.HTTP_201_CREATED
        )



@extend_schema(tags=["User Verification"])
class VerifyEmailView(SafeAPIView, GenericAPIView):
    """
    POST /auth/verify-email/
    { "email": "...", "code": "123456" }

    200 → {code:1,message:"E-mail verified successfully."}
    400 → {code:0,message: ...} if input invalid or code wrong
    500 → {code:0,message:"Internal server error."}
    """
    permission_classes = (AllowAny,)
    serializer_class = VerifyEmailSerializer

    def post(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        try:
            ser.is_valid(raise_exception=True)
            ser.save()
        except ValidationError as exc:
            msg = flatten_error(exc.detail)
            return fail(msg, status=status.HTTP_400_BAD_REQUEST)
        return ok("E-mail verified successfully.")


@extend_schema(tags=["User Verification"])
class ResendActivationView(SafeAPIView, GenericAPIView):
    """
    POST /auth/resend-activation/
    { "email": "..." }

    200 → {code:1,message:"If that account exists and is not verified, an e-mail was sent."}
    400 → invalid email format
    500 → internal error
    """
    permission_classes = (AllowAny,)
    serializer_class = ResendActivationSerializer

    def post(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        try:
            ser.is_valid(raise_exception=True)
            ser.save()
        except ValidationError as exc:
            # we want to tell the caller if their input was malformed
            msg = flatten_error(exc.detail)
            return fail(msg, status=status.HTTP_400_BAD_REQUEST)
        return ok("If that account exists and is not verified, an e-mail was sent.")


@extend_schema(tags=["User Verification"])
class VerifyPhoneView(SafeAPIView, GenericAPIView):
    """
    POST /auth/verify-phone/
    { "phone": "0241234567", "code": "123456" }

    200 → {code:1,message:"Phone verified successfully."}
    400 → {code:0,message:...} on bad format or wrong code
    """
    permission_classes = (AllowAny,)
    serializer_class = VerifyPhoneSerializer

    def post(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        try:
            ser.is_valid(raise_exception=True)
            ser.save()
        except ValidationError as exc:
            msg = flatten_error(exc.detail)
            return fail(msg, status=status.HTTP_400_BAD_REQUEST)
        return ok("Phone verified successfully.")


@extend_schema(tags=["User Verification"])
class ResendPhoneActivationView(SafeAPIView, GenericAPIView):
    """
    POST /auth/resend-phone-activation/
    { "phone_number": "0241234567" }

    200 → {code:1,message:"If that account exists and is not verified, an SMS was sent."}
    400 → invalid phone format
    """
    permission_classes = (AllowAny,)
    serializer_class = ResendPhoneActivationSerializer

    def post(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        try:
            ser.is_valid(raise_exception=True)
            ser.save()
        except ValidationError as exc:
            msg = flatten_error(exc.detail)
            return fail(msg, status=status.HTTP_400_BAD_REQUEST)
        return ok("If that account exists and is not verified, an SMS was sent.")


@extend_schema(tags=["Authentication"])
class LoginView(APIView):
    """
    POST /api/v1/auth/login/
    Body: { "identifier": "<phone OR email>", "password": "<password>" }
    """
    permission_classes = ()  # AllowAny
    authentication_classes = ()  # no JWT needed to login

    def post(self, request, *args, **kwargs):
        serializer = TokenPairSerializer(data=request.data,
                                         context={"request": request})
        try:
            serializer.is_valid(raise_exception=True)
        except AuthenticationFailed as auth_exc:
            # core.response.fail will produce {"code":0,"message":...}
            return fail(str(auth_exc), status=status.HTTP_401_UNAUTHORIZED)
        except serializers.ValidationError as val_err:
            # fallback for any other validation error
            return fail(val_err.detail or "Invalid credentials",
                        status=status.HTTP_400_BAD_REQUEST)

        # success!
        return ok("Login successful", serializer.validated_data)


@extend_schema(tags=["Authentication"])
class RefreshView(TokenRefreshView):
    pass


@extend_schema(tags=["Authentication"])
class VerifyView(TokenVerifyView):
    pass


@extend_schema(tags=["Authentication"])
class LogoutView(TokenBlacklistView):
    """
    POST /logout/
    body: { "refresh": "<token>" }
    Blacklists the supplied refresh token.
    """
    pass


@extend_schema(tags=["Authentication"])
class PasswordResetRequestView(SafeAPIView, GenericAPIView):
    """
    POST /auth/password-reset/request/
    body: { "phone_number": "0241234567" }

    Always returns 200 with a generic message. If
    input is invalid (bad format), returns 400.
    Unexpected errors become 500.
    """
    permission_classes = (AllowAny,)
    serializer_class = PasswordResetRequestSerializer

    def post(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        try:
            ser.is_valid(raise_exception=True)
            ser.save()
        except ValidationError as exc:
            return fail(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        return ok("If that account exists, a code was sent.")


@extend_schema(tags=["Authentication"])
class PasswordResetConfirmView(SafeAPIView, GenericAPIView):
    """
    POST /auth/password-reset/confirm/
    body:
      {
        "phone_number": "0241234567",
        "code": "123456",
        "new_password": "…",
        "new_password_repeat": "…"
      }

    200 on success, 400 if input or code is invalid,
    500 on unexpected errors.
    """
    permission_classes = (AllowAny,)
    serializer_class = PasswordResetConfirmSerializer

    def post(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        try:
            ser.is_valid(raise_exception=True)
            ser.save()
        except ValidationError as exc:
            return fail(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        return ok("Password updated.")


# ---------------- 3‑A. /users/me/ ---------------------- #
@extend_schema(tags=["Users"])
class MeView(generics.RetrieveUpdateAPIView):
    """
    GET  – current user profile
    PATCH– update first_name / last_name / phone / image
    """
    serializer_class = UserSelfUpdateSerializer
    permission_classes = (IsAuthenticated,)

    def get_object(self):
        return self.request.user

    def get_serializer_class(self):
        if self.request.method == "GET":
            return UserPublicSerializer
        return super().get_serializer_class()


# ---------------- 3‑B. /users/ (admin list) ------------ #
@extend_schema(tags=["Users"])
class UserListView(generics.ListAPIView):
    """
    GET /api/v1/users/?role=vendor          → only vendor users
    GET /api/v1/users/?role=vendor,buyer    → vendor OR buyer
    (no query param)                        → all users
    """
    serializer_class = UserPublicSerializer
    permission_classes = (IsAdminUser,)

    # eager-load roles for speed
    queryset = (
        CustomUser.objects
        .all()
        .prefetch_related(Prefetch("role", queryset=Role.objects.only("slug", "name")))
        .order_by("-date_joined")
    )

    def get_queryset(self):
        qs = super().get_queryset()
        role = self.request.query_params.get("role")

        if role:
            slugs = [r.strip().lower() for r in role.split(",") if r.strip()]
            qs = qs.filter(role__slug__in=slugs).distinct()

        return qs


# ---------------- 3‑C. /users/<id>/ (admin retrieve) --- #
@extend_schema(tags=["Users"])
class UserDetailView(generics.RetrieveAPIView):
    queryset = CustomUser.objects.all()
    serializer_class = UserPublicSerializer
    permission_classes = (IsAdminUser,)


# ---------------- 3‑D. /users/change-password/ --------- #
@extend_schema(tags=["Authentication"])
class ChangePasswordView(SafeAPIView, generics.GenericAPIView):
    """
    POST /users/change-password/
    {
      "current_password": "...",
      "new_password": "...",
      "new_password2": "..."
    }

    Returns 200 + {"message": ...} on success, or
    400 + {"error": "..."} on validation failure.
    """
    serializer_class = ChangePasswordSerializer
    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        try:
            serializer.is_valid(raise_exception=True)
            serializer.save()
        except ValidationError as exc:
            # collapse lists/dicts into a user-friendly string
            message = flatten_error(exc.detail)
            return fail(message, status=status.HTTP_400_BAD_REQUEST)

        return ok("Password updated. Please sign in again.")
