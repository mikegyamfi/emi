import json
import re, secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import password_validation, authenticate
from django.contrib.auth.models import update_last_login
from django.contrib.auth.password_validation import MinimumLengthValidator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from rest_framework import serializers, exceptions
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import OTPPurpose, OTPChannel, OTP
from core.otp_service import verify_otp, generate_otp
from core.utils import dispatch_sms_otp
from .models import CustomUser, VendorProfile, AgentProfile, Role, AggregatorProfile, UserProfile
from .serializers_vendor import VendorProfileSerializer
from .tasks import send_password_reset_email, send_user_email_otp, send_user_phone_otp

GH_LOCAL_PHONE_RE = r"^0\d{9}$"  # 10 digits, leading 0


# ------------------------------------------------------- #
# 3‑A.  Sign‑up
# ------------------------------------------------------- #

class SignUpSerializer(serializers.ModelSerializer):
    phone_number = serializers.RegexField(
        GH_LOCAL_PHONE_RE,
        error_messages={
            "invalid": "Enter a valid 10-digit Ghanaian mobile number (e.g. 0241234567)."
        }
    )
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True, min_length=8)
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = CustomUser
        fields = ("first_name", "last_name", "phone_number",
                  "email", "password", "confirm_password")

    def validate_phone_number(self, value):
        if CustomUser.objects.filter(phone_number=value.strip()).exists():
            raise serializers.ValidationError("Phone already registered.")
        return value.strip()

    def validate_email(self, value):
        if value and CustomUser.objects.filter(email__iexact=value.strip()).exists():
            raise serializers.ValidationError("E-mail already registered.")
        return value.lower().strip() if value else None

    def validate_password(self, value):
        # Only enforce minimum length; skip common-password & similarity checks
        try:
            password_validation.validate_password(
                password=value,
                user=None,
                password_validators=[MinimumLengthValidator(min_length=8)]
            )
        except DjangoValidationError as e:
            # e.messages is a list of error strings
            raise serializers.ValidationError(e.messages)
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return attrs

    def create(self, validated):
        validated.pop("confirm_password")
        with transaction.atomic():
            user = CustomUser.objects.create_user(**validated)
            buyer_role, _ = Role.objects.get_or_create(
                slug="buyer", defaults={"name": "Buyer"}
            )
            user.role.add(buyer_role)

            # generate OTP on phone only
            otp = generate_otp(
                user=user,
                purpose=OTPPurpose.USER_PHONE,
                channel=OTPChannel.SMS,
                digits=6,
                target=user.phone_number,
            )
            dispatch_sms_otp(otp.id, OTPPurpose.USER_PHONE)
        return user


INVALID_COMBO = "Invalid e-mail / code."
INVALID_PHONE = "Invalid phone number / code."


# --------------------------------------------------------
#  A.  Verify user e-mail
# --------------------------------------------------------
class VerifyEmailSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(max_length=8)

    def validate(self, attrs):
        email = attrs["email"].lower().strip()
        code = re.sub(r"\D", "", attrs["code"])
        try:
            user = CustomUser.objects.get(email__iexact=email)
        except CustomUser.DoesNotExist:
            raise exceptions.ValidationError({"detail": INVALID_COMBO})

        if not verify_otp(
                user=user,
                purpose=OTPPurpose.USER_EMAIL,
                code=code,
        ):
            raise exceptions.ValidationError({"detail": INVALID_COMBO})

        attrs["user"] = user
        return attrs

    def save(self, **kwargs):
        user: CustomUser = self.validated_data["user"]
        user.email_verified = True
        user.active = True
        user.save(update_fields=["email_verified", "active"])
        return user


# --------------------------------------------------------
#  B.  Resend e-mail activation
# --------------------------------------------------------
class ResendActivationSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        try:
            self.instance = CustomUser.objects.get(email__iexact=value.lower().strip())
        except CustomUser.DoesNotExist:
            # generic response
            pass
        return value

    def save(self, **kwargs):
        print("got here")
        if not getattr(self, "instance", None):
            return None  # silent

        user: CustomUser = self.instance
        if user.email_verified:
            raise exceptions.ValidationError("E-mail already verified.")
        print("got to before otp")
        otp = generate_otp(
            user=user,
            purpose=OTPPurpose.USER_EMAIL,
            channel=OTPChannel.EMAIL,
            digits=6,
        )
        # send_user_email_otp.delay(otp.id)
        return otp


# --------------------------------------------------------
#  C.  Verify user phone (SMS)
# --------------------------------------------------------
class VerifyPhoneSerializer(serializers.Serializer):
    phone = serializers.RegexField(
        GH_LOCAL_PHONE_RE,
        error_messages={
            "invalid": "Enter a valid 10-digit Ghanaian mobile number (e.g. 0241234567)."
        }
    )
    code = serializers.CharField(max_length=8)

    def validate(self, attrs):
        phone = re.sub(r"\s+", "", attrs["phone"])
        code = re.sub(r"\D", "", attrs["code"])
        try:
            user = CustomUser.objects.get(phone_number=phone)
        except CustomUser.DoesNotExist:
            raise exceptions.ValidationError({"detail": INVALID_PHONE})

        if not verify_otp(
                user=user,
                purpose=OTPPurpose.USER_PHONE,
                code=code,
        ):
            raise exceptions.ValidationError({"detail": INVALID_PHONE})

        attrs["user"] = user
        return attrs

    def save(self, **kwargs):
        user: CustomUser = self.validated_data["user"]
        user.phone_verified = True
        user.active = True
        user.save(update_fields=["phone_verified"])
        return user


# --------------------------------------------------------
#  D.  Resend phone activation
# --------------------------------------------------------
class ResendPhoneActivationSerializer(serializers.Serializer):
    phone_number = serializers.RegexField(
        GH_LOCAL_PHONE_RE,
        error_messages={
            "invalid": "Enter a valid 10-digit Ghanaian mobile number (e.g. 0241234567)."
        }
    )

    def validate_phone_number(self, value):
        value = value.strip()
        self.instance = CustomUser.objects.filter(phone_number=value).first()
        return value

    def save(self, **kwargs):
        if not getattr(self, "instance", None):
            return None  # silent generic response

        user: CustomUser = self.instance
        if user.phone_verified:
            raise exceptions.ValidationError("Phone already verified.")

        otp = generate_otp(
            user=user,
            purpose=OTPPurpose.USER_PHONE,
            channel=OTPChannel.SMS,
            digits=6,
            target=user.phone_number,
        )
        print("resend otp generated")
        dispatch_sms_otp(otp.id, OTPPurpose.USER_PHONE)
        return otp


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ("slug", "name")


# -----------------------------------------------------------
# 2.  Generic user-info slice (avatar, phone, etc.)
# -----------------------------------------------------------
class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ("user_image",)


# -----------------------------------------------------------
# 4.  Aggregator profile (extend later as fields grow)
# -----------------------------------------------------------
class AggregatorProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = AggregatorProfile
        fields = ()  # no extra fields yet → empty tuple returns `{}`


# -----------------------------------------------------------
# 5.  Agent profile (extend later)
# -----------------------------------------------------------
class AgentProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentProfile
        fields = ()


INVALID_CREDENTIALS = "Invalid e‑mail or password."


class TokenPairSerializer(serializers.Serializer):
    """
    POST /login/  { "identifier": "<phone OR email>", "password": "..." }
    Returns via core.response.ok:
      {
        "code": 1,
        "message": "Login successful",
        "data": {
          "access": "...",
          "refresh": "...",
          "user": { … }
        }
      }
    On failure returns core.response.fail with appropriate message.
    """
    identifier = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False)

    default_error_messages = {"invalid": "Invalid credentials."}

    def validate(self, attrs):
        ident = attrs["identifier"].strip()
        pwd = attrs["password"]

        if ident.isdigit() and not re.fullmatch(GH_LOCAL_PHONE_RE, ident):
            raise serializers.ValidationError(
                {"identifier": "Enter a valid 10-digit Ghanaian mobile number (e.g. 0241234567)."}
            )

        # Determine if this is phone‐based or email‐based login
        is_phone = bool(re.fullmatch(GH_LOCAL_PHONE_RE, ident))
        user = None

        if is_phone:
            user = CustomUser.objects.filter(phone_number=ident).first()
        else:
            # treat as email if it contains "@"
            if "@" in ident:
                user = CustomUser.objects.filter(email__iexact=ident).first()

        # Early failure: no such user or bad password
        if not user or not user.check_password(pwd):
            raise AuthenticationFailed(self.error_messages["invalid"])

        # Channel‐specific verification
        if is_phone:
            if not user.phone_verified:
                raise AuthenticationFailed("Phone number not verified.")
        else:
            if not user.email_verified:
                raise AuthenticationFailed("E-mail address not verified.")

        # Finally, issue tokens
        refresh = RefreshToken.for_user(user)
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": UserPublicSerializer(user, context=self.context).data,
        }


token_generator = PasswordResetTokenGenerator()


# ────────────────────────────────────────────────────────────────
# 1.  REQUEST  – send a 6-digit code via SMS
# ----------------------------------------------------------------
class PasswordResetRequestSerializer(serializers.Serializer):
    phone_number = serializers.RegexField(
        GH_LOCAL_PHONE_RE,
        error_messages={"invalid": "Enter a valid 10-digit Ghanaian mobile number (e.g. 0241234567)."}
    )

    # ----------------- validation -------------------------------
    def validate_phone_number(self, value):
        self.user = CustomUser.objects.filter(phone_number=value).first()
        return value

    # ----------------- side-effect ------------------------------
    def save(self, **kwargs):
        """
        * Always returns 200 to caller – even if phone is unknown.
        * Generates **one** 6-digit code; if a previous un-used code for
          the same user exists it’s silently expired.
        """
        if not getattr(self, "user", None):
            return  # silent: we don’t reveal if the phone exists

        # expire any older, unused reset codes
        OTP.objects.filter(
            user=self.user,
            purpose=OTPPurpose.PASSWORD_RESET_CODE,
            channel=OTPChannel.SMS,
            verified=False,
        ).update(expires_at=timezone.now() - timedelta(seconds=1))

        # create fresh code
        otp = generate_otp(
            user=self.user,
            purpose=OTPPurpose.PASSWORD_RESET_CODE,
            channel=OTPChannel.SMS,
            digits=6,
            target=self.user.phone_number,
        )
        dispatch_sms_otp(otp.id, OTPPurpose.PASSWORD_RESET_CODE)


# ------------------- 1‑B. confirm reset ----------------------------- #
class PasswordResetConfirmSerializer(serializers.Serializer):
    phone_number = serializers.RegexField(
        GH_LOCAL_PHONE_RE,
        error_messages={"invalid": "Enter a valid 10-digit Ghanaian mobile number (e.g. 0241234567)."}
    )
    code = serializers.CharField(max_length=8)
    new_password = serializers.CharField(write_only=True, min_length=8)
    new_password_repeat = serializers.CharField(write_only=True, min_length=8)

    # ----------------- validation -------------------------------
    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_repeat"]:
            raise serializers.ValidationError({"new_password_repeat": "Passwords do not match."})

        phone = attrs["phone_number"]
        try:
            self.user = CustomUser.objects.get(phone_number=phone)
        except CustomUser.DoesNotExist:
            raise serializers.ValidationError("Invalid phone / code.")

        # verify OTP (strips any accidental spaces/dashes)
        ok = verify_otp(
            user=self.user,
            purpose=OTPPurpose.PASSWORD_RESET_CODE,
            code=re.sub(r"\D", "", attrs["code"]),
        )
        if not ok:
            raise serializers.ValidationError("Invalid phone / code.")

        password_validation.validate_password(attrs["new_password"], self.user)
        return attrs

    # ----------------- write ------------------------------------
    def save(self, **kwargs):
        from rest_framework_simplejwt.token_blacklist.models import (  # local import to avoid circulars
            OutstandingToken, BlacklistedToken)

        self.user.set_password(self.validated_data["new_password"])
        self.user.save(update_fields=["password"])

        # invalidate every outstanding refresh token
        for t in OutstandingToken.objects.filter(user=self.user):
            BlacklistedToken.objects.get_or_create(token=t)

        return self.user


# -------- 1‑A. public read ---------------------------- #
class UserPublicSerializer(serializers.ModelSerializer):
    user_profile = UserProfileSerializer(source="userprofile", read_only=True)
    vendor_profile = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = (
            "id", "email", "first_name", "last_name", "phone_number",
            "email_verified", "phone_verified", "active",
            "roles",  # list of slugs
            "user_profile",
            "vendor_profile",
        )

    roles = serializers.SerializerMethodField()

    def get_roles(self, obj):
        return list(obj.role.values_list("slug", flat=True))

    def get_vendor_profile(self, obj):
        if obj.role.filter(slug="vendor").exists() and hasattr(obj, "vendorprofile"):
            return VendorProfileSerializer(obj.vendorprofile).data
        return None


# -------- 1‑B. self‑update ---------------------------- #
class UserSelfUpdateSerializer(serializers.ModelSerializer):
    # extra, optional fields for related tables
    user_image = serializers.ImageField(write_only=True, required=False, allow_null=True)
    display_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    bio = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = CustomUser
        fields = (
            "first_name", "last_name", "phone_number",
            "user_image",  # UserProfile
            "display_name", "bio"  # VendorProfile
        )
        extra_kwargs = {
            "phone_number": {"required": False, "allow_blank": True},
        }

    # override update to split payload
    def update(self, instance, validated_data):
        # ---- 1. user core fields ----
        for field in ("first_name", "last_name", "phone_number"):
            if field in validated_data:
                setattr(instance, field, validated_data.pop(field))
        instance.save(update_fields=["first_name", "last_name", "phone_number"])

        # ---- 2. user profile (avatar) ----
        if "user_image" in validated_data:
            img = validated_data.pop("user_image")
            profile, _ = instance.userprofile.__class__.objects.get_or_create(user=instance)
            profile.user_image = img
            profile.save(update_fields=["user_image"])

        # ---- 3. vendor profile ----
        vendor_fields = {k: validated_data.pop(k) for k in ("display_name", "bio") if k in validated_data}
        if vendor_fields:
            # ensure role exists
            vendor_role, _ = Role.objects.get_or_create(slug="vendor", defaults={"name": "Vendor"})
            instance.role.add(vendor_role)

            vp, _ = instance.vendorprofile.__class__.objects.get_or_create(user=instance)
            for k, v in vendor_fields.items():
                setattr(vp, k, v)
            vp.save()

        return instance


# -------- 1‑C. change password ------------------------ #
class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    new_password2 = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs):
        user = self.context["request"].user
        if not user.check_password(attrs["current_password"]):
            raise serializers.ValidationError({"current_password": "Wrong password."})

        if attrs["new_password"] != attrs["new_password2"]:
            raise serializers.ValidationError({"new_password2": "Passwords do not match."})

        password_validation.validate_password(attrs["new_password"], user)
        return attrs

    def save(self, **kwargs):
        user = self.context["request"].user
        new_password = self.validated_data["new_password"]
        user.set_password(new_password)
        user.save(update_fields=["password"])

        # revoke existing refresh tokens
        for token in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=token)
        return user


class UserMinimalSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['id', 'email', 'first_name', 'last_name', "email", "phone_number"]
