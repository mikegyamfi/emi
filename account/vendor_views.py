from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response

from core.response import fail, ok
from core.utils import flatten_error
from .models import CustomUser, VendorProfile, VendorAdministratorProfile, VendorManagerProfile
from .serializers_vendor import (
    BecomeVendorSerializer,
    VendorProfileSerializer, GhanaCardVerifySerializer, VendorAdministratorSerializer, VendorManagerSerializer,
)
from .tasks import send_vendor_welcome_email
from .permissions import IsVendor, IsSelfOrAdmin
from .views import SafeAPIView


# ---------- 4-A. Become vendor ---------------------------- #
@extend_schema(tags=["Vendors"])
class BecomeVendorView(SafeAPIView, APIView):
    """
    POST /vendors/become/?user_id=<id>?
    • Authenticated users can promote themselves.
    • Admins can promote any user by specifying ?user_id=<id>.
    """
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        # determine target
        target = request.user
        user_id = request.query_params.get("user_id")
        if user_id:
            if not request.user.is_staff:
                return fail("Forbidden.", status=status.HTTP_403_FORBIDDEN)
            target = get_object_or_404(CustomUser, pk=user_id)

        serializer = BecomeVendorSerializer(data=request.data, context={"user": target})
        try:
            serializer.is_valid(raise_exception=True)
            with transaction.atomic():
                vp = serializer.save()
        except ValidationError as exc:
            return fail(flatten_error(exc.detail), status=status.HTTP_400_BAD_REQUEST)

        # mail dispatch
        return ok("Vendor role added successfully.", {"vendor_profile": VendorProfileSerializer(vp).data})


@extend_schema(tags=["Vendors"])
class VendorMeView(SafeAPIView, generics.RetrieveUpdateAPIView):
    """
    GET  /vendors/me/    → view your vendor profile
    PATCH /vendors/me/   → update your vendor profile
    """
    permission_classes = (IsAuthenticated, IsVendor)
    serializer_class = VendorProfileSerializer

    def get_object(self):
        return self.request.user.vendorprofile

    def get(self, request, *args, **kwargs):
        vp = self.get_object()
        data = self.get_serializer(vp).data
        return ok("Vendor profile retrieved.", data)

    def patch(self, request, *args, **kwargs):
        vp = self.get_object()
        serializer = self.get_serializer(vp, data=request.data, partial=True)
        try:
            serializer.is_valid(raise_exception=True)
            serializer.save()
        except ValidationError as exc:
            return fail(flatten_error(exc.detail), status=status.HTTP_400_BAD_REQUEST)

        return ok("Vendor profile updated.", serializer.data)


# ---------- 4-C. Admin vendor list / detail --------------- #
@extend_schema(tags=["Vendors"])
class VendorListView(generics.ListAPIView):
    permission_classes = (IsAdminUser,)
    serializer_class = VendorProfileSerializer
    queryset = VendorProfile.objects.select_related("user").order_by("-user__date_joined")


@extend_schema(tags=["Vendors"])
class VendorDetailView(generics.RetrieveAPIView):
    permission_classes = (IsAdminUser | IsSelfOrAdmin,)
    serializer_class = VendorProfileSerializer
    queryset = VendorProfile.objects.select_related("user")


@extend_schema(tags=["Vendors"])
class AdminPromoteVendorView(APIView):
    """
    POST /vendors/<user_id>/promote/
    Body: { "display_name": "...", "bio": "..." }

    • Admin-only
    • Adds vendor role, creates/updates profile, fires welcome e-mail
    """
    permission_classes = (IsAdminUser,)

    def post(self, request, user_id):
        try:
            target = CustomUser.objects.get(pk=user_id)
        except CustomUser.DoesNotExist:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = BecomeVendorSerializer(data=request.data, context={"user": target})
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            vp = serializer.save()

        send_vendor_welcome_email.delay(target.email, vp.display_name or target.email)
        return Response({"detail": f"{target.email} promoted to vendor."},
                        status=status.HTTP_200_OK)


@extend_schema(tags=["Vendors"])
class VerifyVendorGhanaCardView(SafeAPIView):
    """
    POST /api/v1/admin/vendors/<id>/verify-ghana-card/
    Body (optional): { "note": "checked against registry" }
    """
    permission_classes = (IsAdminUser,)

    def post(self, request, vendor_id: int):
        try:
            vendor = VendorProfile.objects.get(pk=vendor_id)
        except VendorProfile.DoesNotExist:
            return fail("Vendor not found.", status=404)

        if vendor.ghana_card_verified:
            return fail("Ghana-card already verified.", status=409)

        ser = GhanaCardVerifySerializer(data=request.data)
        if not ser.is_valid():
            return fail("Validation error.", ser.errors)

        with transaction.atomic():
            vendor.ghana_card_verified = True
            vendor.save(update_fields=["ghana_card_verified"])
            # (Optional) store the note in an audit table or log here
            note = ser.validated_data.get("note", "")

        return ok(f"Ghana-card verified{' – ' + note if note else ''}.")


class VendorAdministratorViewSet(viewsets.ModelViewSet):
    """
    GET  /api/v1/admin/vendor-administrators/       → list all
    POST /api/v1/admin/vendor-administrators/       → assign a user
    DELETE /api/v1/admin/vendor-administrators/{pk}/ → revoke
    """
    queryset = VendorAdministratorProfile.objects.select_related("user").all()
    serializer_class = VendorAdministratorSerializer
    permission_classes = [IsAdminUser]


class VendorManagerViewSet(viewsets.ModelViewSet):
    """
    GET /api/v1/admin/vendor-managers/ → list all (+ count)
       Query params: ?region_id=…&district_id=…&town_id=…
       filters list to only those managers covering the given area.
    POST   /api/v1/admin/vendor-managers/              → assign a user + jurisdictions
    GET    /api/v1/admin/vendor-managers/{pk}/         → retrieve one
    PATCH  /api/v1/admin/vendor-managers/{pk}/         → update jurisdictions
    DELETE /api/v1/admin/vendor-managers/{pk}/         → revoke
    """
    queryset = VendorManagerProfile.objects.select_related("user") \
        .prefetch_related("regions", "districts", "towns")
    serializer_class = VendorManagerSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if region := params.get("region_id"):
            qs = qs.filter(regions__id=region)
        if district := params.get("district_id"):
            qs = qs.filter(districts__id=district)
        if town := params.get("town_id"):
            qs = qs.filter(towns__id=town)
        return qs

    def list(self, request, *args, **kwargs):
        """
        Return { count: n, managers: [ …serialized… ] }
        so you get both the list and how many match.
        """
        qs = self.get_queryset()
        page = self.paginate_queryset(qs)
        if page is not None:
            ser = self.get_serializer(page, many=True)
            return self.get_paginated_response(ser.data)

        ser = self.get_serializer(qs, many=True)
        return Response({"count": qs.count(), "managers": ser.data}, status=status.HTTP_200_OK)








