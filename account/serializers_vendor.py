# -----------------------------------------------------------
# 3.  Vendor profile (only when user has vendor role)
# -----------------------------------------------------------
from django.core.exceptions import ValidationError
from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import serializers, mixins, viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response

from account.models import VendorProfile, Role, CustomUser, VendorAdministratorProfile, VendorManagerProfile
from account.permissions import IsVendorAdminOrManager
from document_manager.models import DocumentType, Document
from market_intelligence.models import Region, District, Town
from market_intelligence.serializers import RegionSerializer, DistrictSerializer, TownSerializer


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


class VendorAdministratorSerializer(serializers.ModelSerializer):
    from account.serializers import UserPublicSerializer
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=CustomUser.objects.all(),
        source="user",
        write_only=True
    )
    user = UserPublicSerializer(read_only=True)

    class Meta:
        model = VendorAdministratorProfile
        fields = ("id", "user_id", "user")

    def create(self, validated_data):
        user = validated_data["user"]

        # 1) assign the 'vendor_admin' role
        role, _ = Role.objects.get_or_create(
            slug="vendor_admin",
            defaults={"name": "Vendor Administrator"}
        )
        user.role.add(role)

        # 2) prevent duplicates
        profile, created = VendorAdministratorProfile.objects.get_or_create(user=user)
        if not created:
            raise serializers.ValidationError(
                {"user_id": "This user is already a Vendor Administrator."}
            )
        return profile


class VendorManagerSerializer(serializers.ModelSerializer):
    from account.serializers import UserPublicSerializer
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=CustomUser.objects.all(),
        source="user",
        write_only=True,
    )
    user = UserPublicSerializer(read_only=True)

    # READ‑ONLY nested objects
    regions = RegionSerializer(many=True, read_only=True)
    districts = DistrictSerializer(many=True, read_only=True)
    towns = TownSerializer(many=True, read_only=True)

    # WRITE‑ONLY ID fields (map back to the same M2M relations)
    region_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Region.objects.all(),
        write_only=True,
        source="regions",
    )
    district_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=District.objects.all(),
        write_only=True,
        source="districts",
    )
    town_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Town.objects.all(),
        write_only=True,
        source="towns",
    )

    class Meta:
        model = VendorManagerProfile
        fields = (
            "id", "user_id", "user",
            # for reads
            "regions", "districts", "towns",
            # for writes
            "region_ids", "district_ids", "town_ids",
        )

    def create(self, validated_data):
        user = validated_data["user"]
        regs = validated_data.pop("regions", [])
        dists = validated_data.pop("districts", [])
        towns = validated_data.pop("towns", [])

        with transaction.atomic():
            # 1) assign role
            role, _ = Role.objects.get_or_create(
                slug="vendor_manager",
                defaults={"name": "Vendor Manager"}
            )
            user.role.add(role)

            # 2) prevent duplicates
            if VendorManagerProfile.objects.filter(user=user).exists():
                raise serializers.ValidationError({
                    "user_id": "This user is already a Vendor Manager."
                })

            # 3) raw insert (bypass clean) so we can attach M2Ms next
            profile = VendorManagerProfile(user=user)
            profile.save_base(raw=True)

            # 4) attach jurisdictions
            profile.regions.set(regs)
            profile.districts.set(dists)
            profile.towns.set(towns)

            # 5) final save (runs clean now that M2Ms exist)
            try:
                profile.save()
            except ValidationError as e:
                raise serializers.ValidationError(e.message_dict or e.messages)

            return profile

    def update(self, instance, validated_data):
        regs = validated_data.pop("regions", None)
        dists = validated_data.pop("districts", None)
        towns = validated_data.pop("towns", None)

        profile = super().update(instance, validated_data)

        if regs is not None:
            profile.regions.set(regs)
        if dists is not None:
            profile.districts.set(dists)
        if towns is not None:
            profile.towns.set(towns)

        try:
            profile.save()
        except ValidationError as e:
            raise serializers.ValidationError(e.message_dict or e.messages)

        return profile


class VendorProfileAdminSerializer(serializers.ModelSerializer):
    from account.serializers import UserPublicSerializer
    user = UserPublicSerializer(read_only=True)
    region = RegionSerializer(read_only=True)
    district = DistrictSerializer(read_only=True)
    town = TownSerializer(read_only=True)

    is_verified = serializers.BooleanField(read_only=True)

    class Meta:
        model = VendorProfile
        fields = (
            "user", "display_name", "bio",
            "date_of_birth",
            "region", "district", "town",
            "ghana_card_verified", "vendor_profile_verified",
            "is_verified",
        )


class VendorProfileAdminViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet
):
    """
    GET   /api/v1/vendor-mgmt/vendors/          → list + counts
    GET   /api/v1/vendor-mgmt/vendors/{pk}/     → retrieve one
    POST  /api/v1/vendor-mgmt/vendors/{pk}/verify/ → verify vendor
    """
    serializer_class = VendorProfileAdminSerializer
    permission_classes = [IsVendorAdminOrManager]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = {
        "region__id": ["exact"],
        "district__id": ["exact"],
        "town__id": ["exact"],
        "ghana_card_verified": ["exact"],
        "vendor_profile_verified": ["exact"],
    }
    search_fields = ["display_name", "user__first_name", "user__last_name", "user__phone_number"]

    def get_queryset(self):
        qs = VendorProfile.objects.select_related("user", "region", "district", "town")
        user = self.request.user

        # Vendor Administrators see all
        if hasattr(user, "vendor_admin_profile"):
            return qs

        # Vendor Managers see only vendors in their jurisdictions
        mgr = user.vendor_manager_profile
        if mgr.regions.exists():
            return qs.filter(region__in=mgr.regions.all())
        if mgr.districts.exists():
            return qs.filter(district__in=mgr.districts.all())
        if mgr.towns.exists():
            return qs.filter(town__in=mgr.towns.all())

        return qs.none()

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())

        total = qs.count()
        verified = qs.filter(ghana_card_verified=True, vendor_profile_verified=True).count()
        unverified = total - verified

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response({
                "counts": {
                    "total": total,
                    "verified": verified,
                    "unverified": unverified,
                },
                "vendors": serializer.data,
            })

        serializer = self.get_serializer(qs, many=True)
        return Response({
            "counts": {
                "total": total,
                "verified": verified,
                "unverified": unverified,
            },
            "vendors": serializer.data,
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        """
        POST /api/v1/vendor-mgmt/vendors/{pk}/verify/
        Atomically sets both verification flags to True.
        """
        profile = self.get_object()
        with transaction.atomic():
            profile.ghana_card_verified = True
            profile.vendor_profile_verified = True
            profile.save(update_fields=["ghana_card_verified", "vendor_profile_verified"])

        serializer = self.get_serializer(profile)
        return Response(serializer.data, status=status.HTTP_200_OK)
