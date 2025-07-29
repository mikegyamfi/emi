from random import sample

from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404

from rest_framework import viewsets, status, generics, filters
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from business.models import Business
from business.serializers import BusinessBriefSerializer
from .models import GenericProduct, GenericService, VendorProduct, VendorService
from .admin_serializers import (
    _AdminToggleMixin, SellerOverviewSerializer
)
from .serializers import (
    ProductSerializer, ServiceSerializer,
    ProductMiniSerializer, ServiceMiniSerializer,
)
from .admin_filters import (
    AdminProductFilter, AdminServiceFilter, AdminBusinessFilter
)
from core.response import ok  # the helper you already use


# ──────────────────────────────────────────────────────────
# 1.  Product   (staff)
# ──────────────────────────────────────────────────────────
class AdminProductViewSet(viewsets.ReadOnlyModelViewSet):
    """
    • list / retrieve with rich ProductSerializer
    • PATCH /<id>/activate|deactivate  – flips `is_active`
      and e-mails the seller.
    """
    queryset = (
        VendorProduct.objects
        .select_related("seller", "business", "category")
        .prefetch_related("images", "tags")
    )
    serializer_class = ProductSerializer
    permission_classes = (IsAdminUser,)
    filter_backends = (DjangoFilterBackend, filters.SearchFilter)
    filterset_class = AdminProductFilter
    search_fields = ("name", "description")

    # -------------------- actions -------------------------------
    def _mail_toggle(self, product):
        """
        Send a very small info mail to the seller when staff
        activates / deactivates a product.
        """
        subject = (
            f"Your product “{product.name}” is now "
            f"{'ACTIVE' if product.is_active else 'INACTIVE'}"
        )
        body = (
            f"Hello {product.seller.get_full_name() or product.seller.username},\n\n"
            f"The product «{product.name}» has just been "
            f"{'activated' if product.is_active else 'deactivated'} "
            f"by the EMI marketplace administrators.\n\n"
            "Regards,\nEMI Team"
        )
        send_mail(subject, body,
                  settings.DEFAULT_FROM_EMAIL,
                  [product.seller.email],
                  fail_silently=True)

    def _toggle(self, request, pk, activate: bool):
        prod = get_object_or_404(VendorProduct, pk=pk)
        was = prod.is_active
        prod.is_active = activate
        prod.save(update_fields=("is_active",))

        if was != activate:
            self._mail_toggle(prod)

        ser = _AdminToggleMixin(prod, context={"request": request})
        return ok("Status updated", ser.data, status.HTTP_200_OK)

    @action(detail=True, methods=["patch"])
    def activate(self, request, pk=None):
        return self._toggle(request, pk, True)

    @action(detail=True, methods=["patch"])
    def deactivate(self, request, pk=None):
        return self._toggle(request, pk, False)


# ──────────────────────────────────────────────────────────
# 2.  Service  (staff)
# ──────────────────────────────────────────────────────────
class AdminServiceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = (
        VendorService.objects
        .select_related("provider", "business", "category")
        .prefetch_related("tags", "attributes")
    )
    serializer_class = ServiceSerializer
    permission_classes = (IsAdminUser,)
    filter_backends = (DjangoFilterBackend, filters.SearchFilter)
    filterset_class = AdminServiceFilter
    search_fields = ("title", "description")

    # e-mail helper (same idea as for Product) -------------------
    def _mail_toggle(self, service):
        subj = (
            f"Your service “{service.title}” is now "
            f"{'ACTIVE' if service.is_active else 'INACTIVE'}"
        )
        body = (
            f"Hello {service.provider.get_full_name() or service.provider.username},\n\n"
            f"The service «{service.title}» has just been "
            f"{'activated' if service.is_active else 'deactivated'} "
            f"by the EMI marketplace administrators.\n\n"
            "Regards,\nEMI Team"
        )
        send_mail(subj, body,
                  settings.DEFAULT_FROM_EMAIL,
                  [service.provider.email],
                  fail_silently=True)

    def _toggle(self, request, pk, activate: bool):
        srv = get_object_or_404(VendorService, pk=pk)
        was = srv.is_active
        srv.is_active = activate
        srv.save(update_fields=("is_active",))

        if was != activate:
            self._mail_toggle(srv)

        ser = _AdminToggleMixin(srv, context={"request": request})
        return ok("Status updated", ser.data)

    @action(detail=True, methods=["patch"])
    def activate(self, request, pk=None):
        return self._toggle(request, pk, True)

    @action(detail=True, methods=["patch"])
    def deactivate(self, request, pk=None):
        return self._toggle(request, pk, False)


# ──────────────────────────────────────────────────────────
# 3.  Business read-only list (owner filter)
# ──────────────────────────────────────────────────────────
class AdminBusinessViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ?owner=<user-pk>   to limit to one seller
    """
    queryset = (
        Business.objects
        .select_related("owner")
        .prefetch_related(
            Prefetch("products", queryset=VendorProduct.objects.only("id")),
            Prefetch("services", queryset=VendorService.objects.only("id")),
        )
    )
    serializer_class = BusinessBriefSerializer
    permission_classes = (IsAdminUser,)
    filter_backends = (DjangoFilterBackend,)
    filterset_class = AdminBusinessFilter


# ──────────────────────────────────────────────────────────
# 4.  Seller overview  (single GET)
# ──────────────────────────────────────────────────────────
class AdminSellerOverview(generics.RetrieveAPIView):
    """
    /admin/sellers/<seller-pk>/overview/

    Returns everything staff typically wants in ONE call:
      • vendor profile
      • all businesses with their products & services
      • standalone products / services
    """
    permission_classes = (IsAdminUser,)
    serializer_class = SellerOverviewSerializer
    lookup_url_kwarg = "seller_pk"

    def get_object(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        seller = get_object_or_404(
            User.objects.prefetch_related(
                "vendorprofile",
                "products__category", "services__category",
                "business_set__products", "business_set__services",
            ),
            pk=self.kwargs[self.lookup_url_kwarg]
        )
        return seller

    # we override get() only to wrap with the unified ok()
    def get(self, request, *a, **kw):
        seller = self.get_object()
        ser = self.get_serializer(seller, context={"request": request})
        return ok("OK", ser.data)
