# business/views_documents.py
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, parsers
from rest_framework.exceptions import NotFound

from account.models import VendorProfile
from account.permissions import IsVendor
from business.models import Business
from core.response import fail, ok
from document_manager.models import DocumentType
from document_manager.serializers import (
    BusinessDocumentSerializer,
    DocumentTypeSerializer,
    VendorDocumentListSerializer,
    VendorDocumentUploadSerializer
)


@extend_schema(tags=["Business Documents"])
class BusinessDocumentView(generics.ListCreateAPIView):
    """
    GET  /api/v1/businesses/<pk>/documents/   — list all docs for your business
    POST /api/v1/businesses/<pk>/documents/   — upload a new document
    """
    permission_classes = (permissions.IsAuthenticated, IsVendor)
    parser_classes = (parsers.MultiPartParser, parsers.FormParser)
    serializer_class = BusinessDocumentSerializer

    def get_business(self) -> Business:
        try:
            return Business.objects.get(
                pk=self.kwargs["pk"],
                vendor=self.request.user.vendorprofile
            )
        except Business.DoesNotExist:
            raise NotFound({"detail": "Business not found."})

    def get_queryset(self):
        # only documents attached to this business
        return self.get_business().documents.all().order_by("created_at")

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["business"] = self.get_business()
        return ctx


# ───────────────────────────────────────────────────────────
# 1.  Public list of document types
# ───────────────────────────────────────────────────────────
@extend_schema(tags=["Document Types"])
class DocumentTypeListView(generics.ListAPIView):
    """
    GET /api/v1/document-types/
    """
    queryset = DocumentType.objects.all().order_by("name")
    serializer_class = DocumentTypeSerializer
    permission_classes = ()  # AllowAny


# ───────────────────────────────────────────────────────────
# 2.  List documents for a single business
# ───────────────────────────────────────────────────────────
@extend_schema(tags=["Business Documents"])
class BusinessDocumentListView(generics.ListAPIView):
    """
    GET /api/v1/businesses/<business_id>/documents/
    Only the vendor who owns the business (or admins) may call.
    """
    serializer_class = BusinessDocumentSerializer

    def get_permissions(self):
        if self.request.user.is_staff:
            return (permissions.IsAdminUser(),)
        return permissions.IsAuthenticated(), IsVendor(),

    def get_queryset(self):
        biz_id = self.kwargs["pk"]
        user = self.request.user

        try:
            biz = Business.objects.select_related("vendor").get(pk=biz_id)
        except Business.DoesNotExist:
            raise fail("Business not found.", status=404)

        if not (user.is_staff or biz.vendor == user.vendorprofile):
            raise fail("Not allowed.", status=403)

        return biz.documents.all().order_by("created_at")


@extend_schema(tags=["Vendor Documents"])
class VendorDocumentListCreateView(generics.GenericAPIView):
    """
    GET   /api/v1/vendor/documents/            – list all Ghana-Card docs
    POST  /api/v1/vendor/documents/            – upload front/back image
    """
    permission_classes = (permissions.IsAuthenticated, IsVendor)
    parser_classes = (parsers.MultiPartParser, parsers.FormParser)

    def get_vendor(self) -> VendorProfile:
        return self.request.user.vendorprofile

    # ---------- GET ------------------------------------------------ #
    def get(self, request):
        qs = self.get_vendor().documents.all().order_by("created_at")
        data = VendorDocumentListSerializer(qs, many=True).data
        return ok("Documents fetched.", data=data)

    # ---------- POST (upload) ------------------------------------- #
    def post(self, request):
        ser = VendorDocumentUploadSerializer(
            data=request.data,
            context={"vendor": self.get_vendor()},
        )
        if not ser.is_valid():
            return fail("Validation error.", ser.errors)

        with transaction.atomic():
            doc = ser.save()

        return ok("Document uploaded.", data=VendorDocumentListSerializer(doc).data, status=201)
