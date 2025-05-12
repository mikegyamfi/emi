from django.db import transaction
from rest_framework import serializers

from account.models import VendorProfile
from account.serializers import UserPublicSerializer
from core.models import OTPPurpose, OTPChannel
from core.otp_service import verify_otp, generate_otp
from core.utils import dispatch_sms_otp
from core.vendor_utils import vendor_is_verified
from document_manager.serializers import BusinessDocumentSerializer
from market_intelligence.models import Region, District, Town
from market_intelligence.serializers import RegionSerializer, DistrictSerializer, TownSerializer
from .models import Business, BusinessStatus, BusinessCategory
from .tasks import send_business_email_otp, send_business_phone_otp


# ───────── mini vendor block ─────────────────────────── #
class VendorMiniSerializer(serializers.ModelSerializer):
    user = UserPublicSerializer(read_only=True)

    class Meta:
        model = VendorProfile
        fields = ("display_name", "bio", "user")


class BusinessCategorySerializer(serializers.ModelSerializer):
    """
    Generic read-only representation – (id, name, description)
    """

    class Meta:
        model = BusinessCategory
        fields = ("id", "name", "description")


# ────────────────────────────────────────────────────────────
# 2-A.  Vendor → list / detail
# ────────────────────────────────────────────────────────────
class BusinessListSerializer(serializers.ModelSerializer):
    vendor = VendorMiniSerializer(read_only=True)
    business_category = serializers.PrimaryKeyRelatedField(
        read_only=True,
    )
    region = RegionSerializer(read_only=True)
    district = DistrictSerializer(read_only=True)
    town = TownSerializer(read_only=True)
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model = Business
        fields = (
            "id", "business_name", "tin_number",
            "business_category",
            "address", "business_location", "gps_code",
            "region", "district", "town",
            "business_email", "business_email_verified",
            "business_phone", "business_phone_verified",
            "status", "business_active",
            "submitted_at", "reviewed_at",
            "business_description", "logo_url",
            "vendor",
        )
        read_only_fields = (
            "status", "reviewed_at",
            "business_email_verified", "business_phone_verified",
            "submitted_at",
        )

    def get_logo_url(self, obj):
        req = self.context.get("request")
        if obj.business_logo and req:
            return req.build_absolute_uri(obj.business_logo.url)
        return None


class BusinessDetailSerializer(BusinessListSerializer):
    other_businesses = serializers.SerializerMethodField()
    documents = BusinessDocumentSerializer(many=True, read_only=True)

    class Meta(BusinessListSerializer.Meta):
        fields = BusinessListSerializer.Meta.fields + (
            "other_businesses", "documents",
        )

    def get_other_businesses(self, obj):
        qs = obj.vendor.businesses.exclude(pk=obj.pk).order_by("-submitted_at")
        return [
            {"id": b.id, "business_name": b.business_name, "status": b.status}
            for b in qs
        ]


# ────────────────────────────────────────────────────────────
# 2-B.  Create / update
# ────────────────────────────────────────────────────────────
class BusinessCreateSerializer(serializers.ModelSerializer):
    business_category = serializers.PrimaryKeyRelatedField(
        queryset=BusinessCategory.objects.all(),
        required=False, allow_null=True
    )
    region = serializers.PrimaryKeyRelatedField(
        queryset=Region.objects.all(),
        required=False, allow_null=True
    )
    district = serializers.PrimaryKeyRelatedField(
        queryset=District.objects.all(),
        required=False, allow_null=True
    )
    town = serializers.PrimaryKeyRelatedField(
        queryset=Town.objects.all(),
        required=False, allow_null=True
    )
    business_logo = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = Business
        fields = (
            "business_category", "business_name", "tin_number",
            "business_description", "address",
            "business_location", "gps_code", "region", "district", "town",
            "business_email", "business_phone", "business_logo",
        )

    def _ensure_vendor(self):
        user = self.context["request"].user
        try:
            return user.vendorprofile
        except VendorProfile.DoesNotExist:
            raise serializers.ValidationError("You must be a vendor to create a business.")

    def _ensure_verified(self, vendor: VendorProfile):
        if not vendor.is_verified:
            raise serializers.ValidationError("Your vendor profile must be verified before creating a business.")

    def create(self, validated):
        vendor = self._ensure_vendor()
        self._ensure_verified(vendor)

        # default contact if omitted
        validated.setdefault("business_email", vendor.user.email)
        validated.setdefault("business_phone", vendor.user.phone_number or "")

        # attach vendor FK
        validated["vendor"] = vendor

        with transaction.atomic():
            biz = super().create(validated)

            # send OTPs for both channels
            if biz.business_email:
                otp = generate_otp(
                    user=biz.vendor.user,
                    purpose=OTPPurpose.BUSINESS_EMAIL,
                    channel=OTPChannel.EMAIL,
                    digits=6,
                    target=biz.business_email,
                )
                # send_business_email_otp.delay(otp.id)

            if biz.business_phone:
                otp = generate_otp(
                    user=biz.vendor.user,
                    purpose=OTPPurpose.BUSINESS_PHONE,
                    channel=OTPChannel.SMS,
                    digits=6,
                    target=biz.business_phone,
                )
                dispatch_sms_otp(otp.id, OTPPurpose.USER_PHONE)

        return biz

    def update(self, instance, validated):
        if instance.status != BusinessStatus.PENDING:
            raise serializers.ValidationError("Cannot modify a reviewed business.")

        reset, resend_email, resend_phone = False, False, False

        if "business_email" in validated and validated["business_email"] != instance.business_email:
            validated["business_email_verified"] = False
            reset = resend_email = True

        if "business_phone" in validated and validated["business_phone"] != instance.business_phone:
            validated["business_phone_verified"] = False
            reset = resend_phone = True

        if reset:
            validated["status"] = BusinessStatus.PENDING
            validated["business_active"] = False

        with transaction.atomic():
            biz = super().update(instance, validated)

            # re-issue OTPs only if channel changed
            if resend_email:
                otp = generate_otp(
                    user=biz.vendor.user,
                    purpose=OTPPurpose.BUSINESS_EMAIL,
                    channel=OTPChannel.EMAIL,
                    digits=6,
                    target=biz.business_email,
                )
                # send_business_email_otp.delay(otp.id)

            if resend_phone:
                otp = generate_otp(
                    user=biz.vendor.user,
                    purpose=OTPPurpose.BUSINESS_PHONE,
                    channel=OTPChannel.SMS,
                    digits=6,
                    target=biz.business_phone,
                )
                dispatch_sms_otp(otp.id, OTPPurpose.USER_PHONE)

        return biz


class BusinessActiveSerializer(serializers.Serializer):
    active = serializers.BooleanField()

    def validate_active(self, value):
        biz: Business = self.context["business"]
        if value and not biz.prerequisites_met:
            raise serializers.ValidationError(
                "Cannot activate: email & phone must be verified and status must be APPROVED."
            )
        return value


# ────────────────────────────────────────────────────────────
# 2-C.  Admin bulk / approve serializer (unchanged)
# ────────────────────────────────────────────────────────────
class BusinessAdminActionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=[BusinessStatus.APPROVED, BusinessStatus.REJECTED, BusinessStatus.PENDING]
    )
    note = serializers.CharField(required=False, allow_blank=True)


# ────────────────────────────────────────────────────────────
# 2-D.  Admin create (field list trimmed)
# ────────────────────────────────────────────────────────────
class AdminCreateBusinessSerializer(BusinessCreateSerializer):
    vendor_id = serializers.IntegerField(write_only=True)

    class Meta(BusinessCreateSerializer.Meta):
        fields = ("vendor_id",) + BusinessCreateSerializer.Meta.fields

    def validate_vendor_id(self, pk):
        try:
            return VendorProfile.objects.get(pk=pk)
        except VendorProfile.DoesNotExist:
            raise serializers.ValidationError("Vendor not found.")

    def create(self, validated):
        validated["vendor"] = validated.pop("vendor_id")
        return super().create(validated)


# ────────────────────────────────────────────────────────────
# 2-E.  Business e-mail / phone OTP flows
# ────────────────────────────────────────────────────────────
class _BaseBizOtpSerializer(serializers.Serializer):
    business_id = serializers.IntegerField()

    def _get_business(self, business_id):
        """Return vendor-owned Business or raise ValidationError."""
        vendor = self.context["request"].user.vendorprofile
        try:
            return Business.objects.get(id=business_id, vendor=vendor)
        except Business.DoesNotExist:
            raise serializers.ValidationError({"business_id": "Business not found."})


# ---------- resend (initial + later) ---------------------- #
class ResendBusinessEmailOTPSerializer(_BaseBizOtpSerializer):
    def validate(self, attrs):
        biz = self._get_business(attrs["business_id"])
        if biz.business_email_verified:
            raise serializers.ValidationError("E-mail already verified.")
        attrs["business"] = biz
        return attrs

    def save(self):
        biz = self.validated_data["business"]
        with transaction.atomic():
            otp = generate_otp(
                user=biz.vendor.user,
                purpose=OTPPurpose.BUSINESS_EMAIL,
                channel=OTPChannel.EMAIL,
                target=biz.business_email,
            )
        # transaction.on_commit(send_business_email_otp.delay(otp.id))
        return otp


class ResendBusinessPhoneOTPSerializer(_BaseBizOtpSerializer):
    def validate(self, attrs):
        biz = self._get_business(attrs["business_id"])  # ← pass pk
        if biz.business_phone_verified:
            raise serializers.ValidationError("Phone already verified.")
        attrs["business"] = biz
        return attrs

    def save(self):
        biz = self.validated_data["business"]
        with transaction.atomic():
            otp = generate_otp(
                user=biz.vendor.user,
                purpose=OTPPurpose.BUSINESS_PHONE,
                channel=OTPChannel.SMS,
                target=biz.business_phone,
            )
        transaction.on_commit(dispatch_sms_otp(otp.id, OTPPurpose.USER_PHONE))
        return otp


class _VerifyMixin(_BaseBizOtpSerializer):
    # code is mandatory for verify endpoints
    code = serializers.CharField(max_length=8, required=True)

    def _require_code(self, attrs):
        code = attrs.get("code", "").strip()
        if not code:
            raise serializers.ValidationError({"code": "This field is required."})
        return code


class VerifyBusinessEmailOTPSerializer(_VerifyMixin):
    def validate(self, attrs):
        biz = self._get_business(attrs["business_id"])
        if biz.business_email_verified:
            raise serializers.ValidationError("E-mail already verified.")

        code = self._require_code(attrs)
        if not verify_otp(
                user=biz.vendor.user,
                purpose=OTPPurpose.BUSINESS_EMAIL,
                code=code,
        ):
            raise serializers.ValidationError({"code": "Invalid or expired code."})

        attrs["business"] = biz
        return attrs

    def save(self):
        biz: Business = self.validated_data["business"]
        with transaction.atomic():
            biz.business_email_verified = True
            biz.save(update_fields=["business_email_verified"])
        return biz


class VerifyBusinessPhoneOTPSerializer(_VerifyMixin):
    def validate(self, attrs):
        biz = self._get_business(attrs["business_id"])
        if biz.business_phone_verified:
            raise serializers.ValidationError("Business Phone already verified.")
        code = self._require_code(attrs)

        if not verify_otp(
                user=biz.vendor.user,
                purpose=OTPPurpose.BUSINESS_PHONE,
                code=code,
        ):
            raise serializers.ValidationError({"code": "Invalid or expired code."})

        attrs["business"] = biz
        return attrs

    def save(self):
        biz = self.validated_data["business"]
        biz.business_phone_verified = True
        biz.save(update_fields=["business_phone_verified"])
        return biz


class BusinessBriefSerializer(serializers.ModelSerializer):
    business_category = BusinessCategorySerializer(read_only=True)

    class Meta:
        model = Business
        fields = (
            "id", "business_category", "business_name", "gps_code", "region", "address", "status",
            "submitted_at", "reviewed_at", "business_active",
            "business_description",
            "business_email", "business_phone", "business_logo",
        )
