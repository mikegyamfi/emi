from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets, filters
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.response import Response

from account.permissions import IsVendor  # earlier defined
from account.views import SafeAPIView
from core.lookup_views import AutocompleteMixin
from core.response import fail, ok
from .models import Business, BusinessStatus, BusinessCategory
from .serializers import (
    BusinessListSerializer, BusinessCreateSerializer,
    BusinessAdminActionSerializer, AdminCreateBusinessSerializer, BusinessDetailSerializer, VendorMiniSerializer,
    BusinessActiveSerializer, VerifyBusinessPhoneOTPSerializer,
    ResendBusinessPhoneOTPSerializer, VerifyBusinessEmailOTPSerializer, ResendBusinessEmailOTPSerializer,
    BusinessCategorySerializer
)
from .tasks import (
    send_business_submitted,
    send_business_approved,
    send_business_rejected,
)


@extend_schema(tags=["Business Vendors"])
class VendorBusinessViewSet(viewsets.ModelViewSet):
    """
    /api/v1/my/businesses/
    """
    permission_classes = (IsAuthenticated, IsVendor)

    def get_queryset(self):
        qs = (
            Business.objects
            .filter(vendor=self.request.user.vendorprofile)
            .select_related("vendor__user", "business_category", "region", "district", "town")
        )
        if active := self.request.query_params.get("active"):
            if active.lower() in ("true", "false"):
                qs = qs.filter(business_active=(active.lower() == "true"))
        return qs

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return BusinessCreateSerializer
        if self.action == "retrieve":
            return BusinessDetailSerializer
        return BusinessListSerializer

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        ser = BusinessListSerializer(qs, many=True, context={"request": request})
        vendor_data = VendorMiniSerializer(
            request.user.vendorprofile,
            context={"request": request}
        ).data
        return ok(data={
            "vendor": vendor_data,
            "businesses": ser.data,
        })

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        try:
            serializer.is_valid(raise_exception=True)
            with transaction.atomic():
                biz = serializer.save()
        except DRFValidationError as exc:
            return fail("Validation error", exc.detail, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            print(exc)
            # logger.exception("Error creating business", exc_info=exc)
            return fail("Internal server error", status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        detail = BusinessDetailSerializer(biz, context={"request": request}).data
        return ok("Business created successfully", detail, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(
            instance, data=request.data, partial=partial,
            context={"request": request}
        )
        try:
            serializer.is_valid(raise_exception=True)
            with transaction.atomic():
                biz = serializer.save()
        except DRFValidationError as exc:
            return fail("Validation error", exc.detail, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            print(exc)
            # logger.exception("Error updating business", exc_info=exc)
            return fail("Internal server error", status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        detail = BusinessDetailSerializer(biz, context={"request": request}).data
        return ok("Business updated successfully", detail)

    def destroy(self, request, *args, **kwargs):
        biz = self.get_object()
        if biz.status != BusinessStatus.PENDING:
            return fail("Cannot delete a reviewed business.", status=status.HTTP_400_BAD_REQUEST)
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["patch"])
    def change_business_status(self, request, pk=None):
        biz = self.get_object()
        serializer = BusinessActiveSerializer(data=request.data, context={"business": biz})
        try:
            serializer.is_valid(raise_exception=True)
        except DRFValidationError as exc:
            return fail("Validation failed", exc.detail, status=status.HTTP_400_BAD_REQUEST)

        biz.business_active = serializer.validated_data["active"]
        biz.save(update_fields=["business_active"])
        state = "activated" if biz.business_active else "deactivated"
        return ok(f"Business successfully {state}.")


# -------- 4-B. admin txt ----------------------- #
@extend_schema(tags=["Business Admins"])
class AdminBusinessViewSet(viewsets.ModelViewSet):
    """
    /admin/businesses/            GET  – list   (BusinessListSerializer)
    /admin/businesses/            POST – create (AdminCreateBusinessSerializer)
    /admin/businesses/<id>/       GET  – detail (BusinessDetailSerializer)
    /admin/businesses/<id>/approve/   POST
    /admin/businesses/<id>/reject/    POST
    /admin/businesses/bulk/           POST {'ids':[], 'action':'approve'/'reject'}
    """
    permission_classes = (IsAdminUser,)
    queryset = Business.objects.select_related("vendor__user").order_by("-submitted_at")

    # ---------- choose serializer by action ---------------------- #
    def get_serializer_class(self):
        if self.action == "create":
            return AdminCreateBusinessSerializer
        if self.action == "retrieve":
            return BusinessDetailSerializer
        return BusinessListSerializer

    # ---------- override create to trigger e-mail ---------------- #
    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        biz = ser.save()

        send_business_submitted.delay(biz.vendor.user.email, biz.business_name)
        headers = self.get_success_headers({"id": biz.id})
        return Response(
            {"detail": "Business created for vendor.", "id": biz.id},
            status=status.HTTP_201_CREATED,
            headers=headers,
        )

    # ---------- list filters ------------------------------------ #
    def get_queryset(self):
        qs = super().get_queryset()
        if status_param := self.request.query_params.get("status"):
            qs = qs.filter(status=status_param)
        if vendor_id := self.request.query_params.get("vendor"):
            qs = qs.filter(vendor__user_id=vendor_id)
        return qs

    # ---------- single approve / reject ------------------------- #
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._review(request, pk, BusinessStatus.APPROVED)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self._review(request, pk, BusinessStatus.REJECTED)

    @action(detail=True, methods=["post"])
    def pending(self, request, pk=None):
        return self._review(request, pk, BusinessStatus.PENDING)

    def _review(self, request, pk, status_value):
        biz = self.get_object()
        if biz.status != BusinessStatus.PENDING:
            return Response({"detail": "Already reviewed."}, status=400)

        ser = BusinessAdminActionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        note = ser.validated_data.get("note", "")

        print("note")

        with transaction.atomic():
            biz.status = status_value
            biz.admin_note = note
            biz.reviewed_at = timezone.now()
            biz.reviewer = request.user
            biz.save(update_fields=["status", "admin_note", "reviewed_at", "reviewer"])

        task = send_business_approved if status_value == BusinessStatus.APPROVED else send_business_rejected
        # task.delay(biz.vendor.user.email, biz.business_name, note)
        return Response({"detail": f"{status_value.title()}."})

    # ---------- bulk approve / reject --------------------------- #
    @action(detail=False, methods=["post"])
    def bulk(self, request):
        ids = request.data.get("ids", [])
        action = request.data.get("action")  # 'approve' / 'reject'
        note = request.data.get("note", "")

        if action not in ("approve", "reject"):
            return Response({"detail": "Invalid action."}, status=400)

        qs = self.get_queryset().filter(id__in=ids, status=BusinessStatus.PENDING)
        updated = 0
        for biz in qs:
            biz.status = BusinessStatus.APPROVED if action == "approve" else BusinessStatus.REJECTED
            biz.admin_note = note
            biz.reviewed_at = timezone.now()
            biz.reviewer = request.user
            biz.save()
            task = send_business_approved if action == "approve" else send_business_rejected
            # task.delay(biz.vendor.user.email, biz.business_name, note)
            updated += 1

        return Response({"detail": f"{updated} businesses {action}d."})


@extend_schema(tags=["Business Verifications"])
class ResendBusinessEmailOTPView(SafeAPIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        ser = ResendBusinessEmailOTPSerializer(data=request.data,
                                               context={"request": request})
        if not ser.is_valid():
            return fail("Validation error", ser.errors)
        ser.save()
        return ok("Verification e-mail sent.")


@extend_schema(tags=["Business Verifications"])
class VerifyBusinessEmailOTPView(SafeAPIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        ser = VerifyBusinessEmailOTPSerializer(data=request.data,
                                               context={"request": request})
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response({"detail": "Business e-mail verified."})


@extend_schema(tags=["Business Verifications"])
class ResendBusinessPhoneOTPView(SafeAPIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        ser = ResendBusinessPhoneOTPSerializer(data=request.data,
                                               context={"request": request})
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response({"detail": "Verification SMS sent."})


@extend_schema(tags=["Business Verifications"])
class VerifyBusinessPhoneOTPView(SafeAPIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        ser = VerifyBusinessPhoneOTPSerializer(data=request.data,
                                               context={"request": request})
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response({"detail": "Business phone verified."})


@extend_schema(tags=["Business Categories"])
class BusinessCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    **Endpoints created by the router**

    | Method | URL pattern                        | Purpose                    |
    |--------|------------------------------------|----------------------------|
    | GET    | /api/v1/business-categories/       | List **all** categories    |
    | GET    | /api/v1/business-categories/{pk}/  | Retrieve single category   |

    * Read-only – no create / update / delete.
    * Open to everyone.
    * Searchable by name or description with `?search=term`.
    """
    queryset = BusinessCategory.objects.all().order_by("name")
    serializer_class = BusinessCategorySerializer
    permission_classes = (AllowAny,)
    filter_backends = (filters.SearchFilter,)
    search_fields = ("name", "description")


@extend_schema(tags=["Business Categories Search"])
class BusinessCategorySearchView(AutocompleteMixin):
    base_qs = BusinessCategory.objects.all()
    serializer_class = BusinessCategorySerializer
    search_fields = ("name", "description")
