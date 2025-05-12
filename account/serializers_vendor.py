# -----------------------------------------------------------
# 3.  Vendor profile (only when user has vendor role)
# -----------------------------------------------------------
from rest_framework import serializers

from account.models import VendorProfile, Role
from document_manager.models import DocumentType, Document
from market_intelligence.models import Region, District, Town


class VendorDocumentSerializer(serializers.ModelSerializer):
    document_type = serializers.PrimaryKeyRelatedField(
        queryset=DocumentType.objects.all()
    )
    label = serializers.CharField(required=False, allow_blank=True)
    name = serializers.CharField(source='document_type')

    class Meta:
        model = Document
        fields = ("id", "document_type", "name", "label", "doc", "created_at")
        read_only_fields = ("id", "created_at")

    # bind the uploaded doc to the Business passed in context
    def create(self, validated):
        vendor: VendorProfile = self.context["vendor"]
        validated["content_object"] = vendor  # GenericForeignKey
        return super().create(validated)


class BecomeVendorSerializer(serializers.Serializer):
    display_name = serializers.CharField(max_length=250)
    bio = serializers.CharField(required=False, allow_blank=True)
    ghana_card_id = serializers.CharField(required=False, allow_blank=True)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    region_id = serializers.PrimaryKeyRelatedField(
        queryset=Region.objects.all(),
        source="region",
        write_only=True,
        required=False
    )
    district_id = serializers.PrimaryKeyRelatedField(
        queryset=District.objects.all(),
        source="district",
        write_only=True,
        required=False
    )
    town_id = serializers.PrimaryKeyRelatedField(
        queryset=Town.objects.all(),
        source="town",
        write_only=True,
        required=False
    )

    def validate(self, attrs):
        user = self.context["user"]
        if user.role.filter(slug="vendor").exists():
            raise serializers.ValidationError("User is already a vendor.")
        return attrs

    def save(self, **kwargs):
        user = self.context["user"]

        # 1) Attach the vendor role
        vendor_role, _ = Role.objects.get_or_create(
            slug="vendor",
            defaults={"name": "Vendor"}
        )
        user.role.add(vendor_role)

        # 2) Create or update the VendorProfile
        vp, _ = VendorProfile.objects.get_or_create(user=user)
        vp.display_name = self.validated_data["display_name"]
        vp.bio = self.validated_data.get("bio", vp.bio)

        if "date_of_birth" in self.validated_data:
            vp.date_of_birth = self.validated_data["date_of_birth"]

        # Optional geo-fields
        if region := self.validated_data.get("region"):
            print(region)
            vp.region = region
        if district := self.validated_data.get("district"):
            vp.district = district
        if town := self.validated_data.get("town"):
            vp.town = town
        if ghana_card_id := self.validated_data.get("ghana_card_id"):
            vp.ghana_card_id = ghana_card_id

        vp.save()
        return vp


class VendorProfileSerializer(serializers.ModelSerializer):
    region = serializers.SerializerMethodField()
    district = serializers.SerializerMethodField()
    town = serializers.SerializerMethodField()

    class Meta:
        model = VendorProfile
        fields = (
            "display_name",
            "bio",
            "is_verified",
            "date_of_birth",
            "region",
            "district",
            "town",
        )

    def get_region(self, obj):
        if obj.region:
            return {"id": obj.region.id, "name": obj.region.name}
        return None

    def get_district(self, obj):
        if obj.district:
            return {"id": obj.district.id, "name": obj.district.name}
        return None

    def get_town(self, obj):
        if obj.town:
            return {"id": obj.town.id, "name": obj.town.name}
        return None


class GhanaCardVerifySerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, max_length=300)


