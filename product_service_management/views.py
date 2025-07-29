# product_service/views.py
# ===============================================================
from decimal import Decimal, InvalidOperation
from random import sample

import django_filters as df
from django.db.models import Q, Count
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets, generics, filters, pagination, serializers, permissions
from rest_framework.decorators import action
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from account.models import CustomUser, VendorProfile
from account.serializers_vendor import VendorProfileSerializer
from business.serializers import BusinessBriefSerializer
from core.lookup_views import AutocompleteMixin
from core.response import ok, fail  # your helper
from account.permissions import IsVendor  # «seller» guard
from business.models import Business  # for ?business filter
from core.utils import flatten_error

from .models import (
    Category, Tag, Attributes,
    ProductImage, ProductServiceStatus, ProductCondition, SKU, ServiceImage, ServicePricingChoices, GenericProduct,
    VendorProduct, GenericService, VendorService, VendorServiceImage, VendorProductImage
)
from .serializers import (
    CategoryTreeSerializer,
    TagSerializer, AttributeSerializer, SKUMiniSerializer, CategoryDetailSerializer,CategoryMiniSerializer, SKUSerializer, ConditionMiniSerializer, StatusMiniSerializer,
    ServicePricingChoiceSerializer, VendorProductSerializer, VendorServiceSerializer, VendorServiceDetailSerializer,
    VendorProductDetailSerializer, VendorServiceMiniSerializer, VendorProductImageSerializer,
    VendorServiceImageSerializer,
)


# ────────────────────────────────────────────────────────────
# 0.  Common bits
# ────────────────────────────────────────────────────────────
class Everyone(AllowAny):
    ...


class DefaultPagination(pagination.PageNumberPagination):
    page_size = 24
    page_size_query_param = "page_size"
    max_page_size = 120


class GenericProductFilter(df.FilterSet):
    is_active = df.BooleanFilter()
    category = df.NumberFilter(field_name="category_id")

    class Meta:
        model = GenericProduct
        fields = []


class VendorProductFilter(df.FilterSet):
    is_active = df.BooleanFilter()
    featured = df.BooleanFilter()
    product = df.CharFilter(field_name="product__product_id")
    tags = df.ModelMultipleChoiceFilter(
        field_name="tags__id", to_field_name="id", queryset=Tag.objects.all(), conjoined=False
    )
    attributes = df.ModelMultipleChoiceFilter(
        field_name="attributes__id", to_field_name="id", queryset=Attributes.objects.all(), conjoined=False
    )
    business = df.NumberFilter(field_name="business_id")
    seller = df.NumberFilter(field_name="seller_id")

    class Meta:
        model = VendorProduct
        fields = []


class GenericServiceFilter(df.FilterSet):
    is_active = df.BooleanFilter()
    category = df.NumberFilter(field_name="category_id")

    class Meta:
        model = GenericService
        fields = []


class VendorServiceFilter(df.FilterSet):
    """
    Service listing filters (on VendorService):
    • service__category – id
    • is_active / featured – bool
    • pricing_type – id
    • regions / districts / towns– id (M2M)
    • business / provider – id
    """
    is_active = df.BooleanFilter()
    featured = df.BooleanFilter()
    service_category = df.NumberFilter(field_name="service__category_id")
    pricing_type = df.NumberFilter(field_name="pricing_type__id")
    regions = df.NumberFilter(field_name="regions__id")
    districts = df.NumberFilter(field_name="districts__id")
    towns = df.NumberFilter(field_name="towns__id")
    business = df.NumberFilter(field_name="business_id")
    provider = df.NumberFilter(field_name="provider_id")

    class Meta:
        model = VendorService
        fields = []


class PublicVendorProductFilter(df.FilterSet):
    """
    Filters for public vendor listings.
    """
    is_active = df.BooleanFilter()
    featured = df.BooleanFilter()
    # filter by the underlying catalogue category
    product_category = df.NumberFilter(field_name="product__category_id")
    # common public facets
    seller = df.NumberFilter(field_name="seller_id")
    business = df.NumberFilter(field_name="business_id")
    tag = df.NumberFilter(field_name="tags__id")
    attribute = df.NumberFilter(field_name="attributes__id")

    class Meta:
        model = VendorProduct
        fields = []


# ────────────────────────────────────────────────────────────
# 1.  PUBLIC READ-ONLY ENDPOINTS
# ────────────────────────────────────────────────────────────
@extend_schema(tags=["Public Products"])
class PublicProductViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Public listing of **VendorProduct** (each vendor's offer for a GenericProduct).
    Users see real, purchasable listings with vendor price/quantity,
    not the raw catalogue.
    """
    queryset = (
        VendorProduct.objects
        .filter(is_active=True)
        .select_related("product", "seller", "business")
        .prefetch_related("images", "tags", "attributes")
        .order_by("-created_at")
    )
    serializer_class = VendorProductSerializer
    permission_classes = (Everyone,)
    pagination_class = DefaultPagination

    filter_backends = (DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter)
    filterset_class = PublicVendorProductFilter
    # search on the underlying product text + seller/business names
    search_fields = (
        "product__name",
        "product__slug",
        "product__description",
        "seller__vendorprofile__display_name",
        "business__business_name",
    )
    ordering_fields = ("price", "created_at", "featured")
    ordering = ("-created_at",)

    lookup_field = "listing_id"


class PublicVendorServiceFilter(df.FilterSet):
    """
    Filters for public vendor service listings.
    """
    # basics
    is_active = df.BooleanFilter()
    featured = df.BooleanFilter()
    is_remote = df.BooleanFilter()

    # pricing
    pricing_type = df.NumberFilter(field_name="pricing_type_id")
    min_price = df.NumberFilter(field_name="price", lookup_expr="gte")
    max_price = df.NumberFilter(field_name="price", lookup_expr="lte")

    # underlying catalogue category (GenericService.category)
    service_category = df.NumberFilter(field_name="service__category_id")

    # ownership
    provider = df.NumberFilter(field_name="provider_id")
    business = df.NumberFilter(field_name="business_id")

    # coverage (M2M)
    region = df.NumberFilter(field_name="regions__id")
    district = df.NumberFilter(field_name="districts__id")
    town = df.NumberFilter(field_name="towns__id")

    # facets
    tag = df.NumberFilter(field_name="tags__id")
    attribute = df.NumberFilter(field_name="attributes__id")

    class Meta:
        model = VendorService
        fields = []  # declared explicitly above


@extend_schema(tags=["Public Services"])
class PublicServiceViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Public listing of **VendorService** (each provider's offer for a GenericService).
    Users see real, bookable service listings with provider pricing and coverage,
    not the raw service catalogue.
    """
    queryset = (
        VendorService.objects
        .filter(is_active=True)
        .select_related(
            "service", "service__category",
            "provider", "business", "pricing_type",
        )
        .prefetch_related(
            "regions", "districts", "towns",
            "tags", "attributes", "images",
        )
        .order_by("-created_at")
    )

    serializer_class = VendorServiceSerializer  # default for list
    permission_classes = (Everyone,)
    pagination_class = DefaultPagination

    filter_backends = (DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter)
    filterset_class = PublicVendorServiceFilter
    # search across vendor overlay + underlying generic content + owner names
    search_fields = (
        "name", "description",  # VendorService overlay fields
        "service__title", "service__description",  # GenericService copy
        "provider__vendorprofile__display_name",
        "business__business_name",
    )
    ordering_fields = ("price", "created_at", "featured")
    ordering = ("-created_at",)
    lookup_field = "vendor_service_id"  # UUID

    def get_serializer_class(self):
        return (
            VendorServiceDetailSerializer
            if self.action == "retrieve"
            else VendorServiceSerializer
        )


# @extend_schema(tags=["Product Public Category Trees"])
# class PublicCategoryTree(generics.GenericAPIView):
#     """
#     GET /categories/tree/
#     {
#       "code": 1,
#       "message": "OK",
#       "data": {
#         "categories"        : …  # full active tree
#         "product_categories": …  # roots that *contain or descend-to* products
#         "service_categories": …  # same for services
#       }
#     }
#     """
#     permission_classes = (Everyone,)
#
#     # -------------------------------------------------------------
#     # helpers
#     # -------------------------------------------------------------
#     def _active_roots(self, cats_qs):
#         """
#         Given **any** Category queryset, return the distinct set of
#         *active* root categories that lie on the path to those nodes.
#         """
#         # (1) fetch only the columns we need – id & parent_id
#         lookup = dict(
#             Category.objects
#             .filter(is_active=True)
#             .values_list("id", "parent_id")
#         )
#
#         root_ids = set()
#         for cat_id in cats_qs.values_list("id", flat=True).distinct():
#             cur = cat_id
#             # climb up until we hit the top (parent_id == None)
#             while cur and cur in lookup:
#                 parent = lookup[cur]
#                 if parent is None:  # ← root reached
#                     root_ids.add(cur)
#                     break
#                 cur = parent
#         return (
#             Category.objects
#             .filter(id__in=root_ids, is_active=True)
#             .order_by("name")
#         )
#
#     # -------------------------------------------------------------
#     # GET
#     # -------------------------------------------------------------
#     def get(self, request, *args, **kwargs):
#
#         # --- 1) full tree (unchanged) ----------------------------
#         all_roots = (
#             Category.objects
#             .filter(is_active=True, parent__isnull=True)
#             .order_by("name")
#         )
#
#         # --- 2) product / service roots --------------------------
#         product_nodes = Category.objects.filter(products__isnull=False)
#         service_nodes = Category.objects.filter(services__isnull=False)
#
#         product_roots = self._active_roots(product_nodes)
#         service_roots = self._active_roots(service_nodes)
#
#         ctx = {"request": request}
#         serializer = CategoryTreeSerializer
#
#         payload = {
#             "categories": serializer(all_roots, many=True, context=ctx).data,
#             "product_categories": serializer(product_roots, many=True, context=ctx).data,
#             "service_categories": serializer(service_roots, many=True, context=ctx).data,
#         }
#         return ok("OK", payload)
#
#
# @extend_schema(tags=["Product Public Category Details"])
# class PublicCategoryDetail(generics.RetrieveAPIView):
#     """
#     GET /categories/<pk>/
#
#     Returns the subtree starting at `<pk>` *plus* meta flags that help
#     the front-end decide what UI controls to show.
#
#     Response
#     --------
#     {
#       "code": 1,
#       "message": "OK",
#       "data": CategoryDetailSerializer
#     }
#     """
#     lookup_field = "pk"
#     queryset = Category.objects.filter(is_active=True)
#     serializer_class = CategoryDetailSerializer
#
#     def retrieve(self, request, *args, **kwargs):
#         obj = self.get_object()
#         ser = self.get_serializer(obj, context={"request": request})
#         return ok("OK", ser.data)


# quick “random N” helpers  ----------------------------------
class _RandomMixin:
    """
    Helper that returns up-to-N random *active* rows for any model that
    has an `is_active` BooleanField — no assumption about the PK name.
    """

    def _rand_queryset(self, model, n: int):
        pk_name = model._meta.pk.name
        ids = list(
            model.objects.filter(is_active=True)
            .values_list(pk_name, flat=True)
        )
        chosen = ids if len(ids) <= n else sample(ids, n)
        return model.objects.filter(**{f"{pk_name}__in": chosen})


# -----------------------------------------------------------
# Random product/service endpoints
# -----------------------------------------------------------
@extend_schema(tags=["Random Products"])
class RandomProducts(_RandomMixin, generics.ListAPIView):
    """
    /products/random/?n=12   (default **8**)
    Returns random **vendor product listings** (VendorProduct).
    """
    serializer_class = VendorProductSerializer
    permission_classes = (Everyone,)

    def get_queryset(self):
        n = int(self.request.query_params.get("n", 8))
        return (
            self._rand_queryset(VendorProduct, n)
            .select_related("product", "seller", "business")
            .prefetch_related("images")
        )


@extend_schema(tags=["Product Glocal Search"])
class GlobalSearch(generics.ListAPIView):
    """
    /search/?q=rice&category=3&is_active=true …

    Searches vendor **listings**:
        • VendorProduct.product.name / .product.description
        • VendorService.service.title / VendorService.description
        • Business.business_name
        • Seller (VendorProfile.display_name)

    Response
    --------
    {
      "products": [... VendorProductSerializer ...],
      "services": [... VendorServiceSerializer ...]
    }
    """
    permission_classes = (Everyone,)
    pagination_class = None  # single JSON blob

    def get(self, request):
        q = request.query_params.get("q", "").strip()
        cat = request.query_params.get("category")

        vp = VendorProduct.objects.filter(is_active=True)
        vs = VendorService.objects.filter(is_active=True)

        if q:
            vp = vp.filter(
                Q(name__icontains=q) |
                Q(description__icontains=q) |
                Q(seller__vendorprofile__display_name__icontains=q) |
                Q(business__business_name__icontains=q)
            )
            vs = vs.filter(
                Q(title__icontains=q) |
                Q(description__icontains=q) |
                Q(provider__vendorprofile__display_name__icontains=q) |
                Q(business__business_name__icontains=q)
            )

        if cat:
            try:
                cat_id = int(cat)
                vp = vp.filter(product__category_id=cat_id)
                vs = vs.filter(service__category_id=cat_id)
            except ValueError:
                pass

        ctx = self.get_serializer_context()
        return ok("search results", {
            "products": VendorProductSerializer(
                vp.select_related("product", "seller", "business")
                  .prefetch_related("images")[:30],
                many=True, context=ctx
            ).data,
            "services": VendorServiceSerializer(
                vs.select_related("service", "provider", "business")
                  .prefetch_related("images")[:30],
                many=True, context=ctx
            ).data,
        })


# ────────────────────────────────────────────────────────────
# 2.  SELLER / BUSINESS MANAGEMENT
# ────────────────────────────────────────────────────────────
class _OwnerOnly:
    """
    Mix-in ensuring the object belongs to request.user
    (works for both Product & Service).
    """

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(seller=self.request.user)  # product
        # for ServiceViewSet we override to provider


@extend_schema(tags=["Seller Products"])
class SellerProductViewSet(viewsets.ModelViewSet):
    """
    /my_products_management/ … full vendor CRUD on **VendorProduct**.
    Supports multiple image uploads via `new_images`.
    """
    permission_classes = (IsVendor,)
    parser_classes = (MultiPartParser, FormParser)
    pagination_class = DefaultPagination
    queryset = (
        VendorProduct.objects
        .select_related("product", "business")
        .prefetch_related("images", "tags", "attributes")
    )
    filter_backends = (DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter)
    filterset_class = VendorProductFilter
    search_fields = ("product__name", "product__slug", "product__description")
    ordering_fields = ("price", "created_at")
    ordering = ("-created_at",)
    lookup_field = "listing_id"

    def get_serializer_class(self):
        if self.action == "retrieve":
            return VendorProductDetailSerializer
        return VendorProductSerializer

    def get_queryset(self):
        return super().get_queryset().filter(seller=self.request.user)

    def perform_create(self, serializer):
        serializer.save(seller=self.request.user)

    def perform_update(self, serializer):
        serializer.save()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        try:
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
        except serializers.ValidationError as exc:
            return fail("Validation error", error_message=flatten_error(exc.detail))
        return ok("Product created successfully", serializer.data)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(
            instance, data=request.data, partial=partial, context={"request": request}
        )
        try:
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
        except serializers.ValidationError as exc:
            return fail("Validation error", error_message=flatten_error(exc.detail))
        return ok("Product updated successfully", serializer.data)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, partial=True, **kwargs)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        vp = self.get_object()
        vp.is_active = True
        vp.save(update_fields=["is_active"])
        data = VendorProductSerializer(vp, context={"request": request}).data
        return ok("Product activated", data)

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        vp = self.get_object()
        vp.is_active = False
        vp.save(update_fields=["is_active"])
        data = VendorProductSerializer(vp, context={"request": request}).data
        return ok("Product deactivated", data)

    @action(detail=False, url_path=r'by-business/(?P<business_pk>\d+)', methods=["get"])
    def by_business(self, request, business_pk=None):
        vendor = VendorProfile.objects.get(user=request.user)
        biz = get_object_or_404(Business.objects.filter(vendor=vendor, pk=business_pk)
        )
        qs = self.filter_queryset(self.get_queryset().filter(business=biz))
        page = self.paginate_queryset(qs)
        serializer = self.get_serializer(page or qs, many=True, context={"request": request})
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return ok("OK", serializer.data)


@extend_schema(tags=["Product Seller Services"])
class SellerServiceViewSet(viewsets.ModelViewSet):
    """
    Vendor CRUD on **VendorService** listings.

    Filters & search use `VendorServiceFilter`  +  ?search=<text>
    """
    permission_classes = (IsVendor,)
    pagination_class = DefaultPagination
    filter_backends = (DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter)
    filterset_class = VendorServiceFilter
    search_fields = ("service__title", "description")
    ordering_fields = ("price", "created_at")
    ordering = ("-created_at",)
    lookup_field = "vendor_service_id"

    serializer_class = VendorServiceSerializer

    queryset = (
        VendorService.objects
        .select_related("service", "business")
        .prefetch_related("images", "tags", "attributes", "regions", "districts", "towns")
    )

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return VendorServiceDetailSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        return super().get_queryset().filter(provider=self.request.user)

    # override list
    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        ser = self.get_serializer(page or qs, many=True)
        data = ser.data
        if page is not None:
            return self.get_paginated_response(data)
        return ok(data=data)

    # override retrieve
    def retrieve(self, request, *args, **kwargs):
        inst = self.get_object()
        ser = self.get_serializer(inst)
        return ok(data=ser.data)

    # override create
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        try:
            serializer.is_valid(raise_exception=True)
            # provider is set in serializer.create() from request.user
            self.perform_create(serializer)
        except serializers.ValidationError as exc:
            return fail("Validation error", error_message=flatten_error(exc.detail))
        return ok("Service created successfully", serializer.data)

    # override update (PUT/PATCH)
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        inst = self.get_object()
        ser = self.get_serializer(inst, data=request.data, partial=partial)
        ser.is_valid(raise_exception=True)
        self.perform_update(ser)
        return ok("Service updated successfully.", ser.data)

    # override destroy
    def destroy(self, request, *args, **kwargs):
        inst = self.get_object()
        self.perform_destroy(inst)
        return ok("Service deleted successfully.")

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        srv = self.get_object()
        srv.is_active = True
        srv.save(update_fields=["is_active"])
        return ok("Service activated", VendorServiceMiniSerializer(srv, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        srv = self.get_object()
        srv.is_active = False
        srv.save(update_fields=["is_active"])
        return ok("Service deactivated", VendorServiceMiniSerializer(srv, context={"request": request}).data)

    @action(detail=False, url_path=r'by-business/(?P<business_pk>\d+)', methods=["get"])
    def by_business(self, request, business_pk=None):
        vendor = VendorProfile.objects.get(user=request.user)
        biz = get_object_or_404(
            Business.objects.filter(vendor=vendor),
            pk=business_pk
        )
        qs = self.filter_queryset(self.get_queryset().filter(business=biz))
        page = self.paginate_queryset(qs)
        ser = self.get_serializer(page or qs, many=True)
        data = ser.data
        if page is not None:
            return self.get_paginated_response(data)
        return ok(data=data)


# ────────────────────────────────────────────────────────────
# 3.  LIGHT-WEIGHT LOOK-UPS  (Tags, Attributes, SKU)
# ────────────────────────────────────────────────────────────
@extend_schema(tags=["Product Tags"])
class TagViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Tag.objects.all().order_by("name")
    serializer_class = TagSerializer
    permission_classes = (Everyone,)
    filter_backends = (filters.SearchFilter,)
    search_fields = ("name",)


@extend_schema(tags=["Product Attributes"])
class AttributeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Attributes.objects.all().order_by("name")
    serializer_class = AttributeSerializer
    permission_classes = (Everyone,)


# 1) Public read-only -------------------------------------------------
@extend_schema(tags=["Product SKUs"])
class SKUViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /sku/?search=box
    GET /sku/{pk}/

    • search = icontains on *name* or *description*
    """
    queryset = SKU.objects.all().order_by("name")
    serializer_class = SKUMiniSerializer
    permission_classes = (Everyone,)
    filter_backends = (filters.SearchFilter,)
    search_fields = ("name", "description")

    def get_queryset(self):
        raw = self.request.query_params.get("category")
        if not raw:
            return SKU.objects.all().order_by("id")

        try:
            cat_ids = [int(pk) for pk in raw.split(",") if pk.strip().isdigit()]
        except ValueError:
            cat_ids = []

        if not cat_ids:
            return SKU.objects.none()

        return (
            SKU.objects
            .filter(category__id__in=cat_ids)
            .distinct()
            .order_by("id")
        )



@extend_schema(tags=["Product SKU Search"])
class SKUSearchView(generics.ListAPIView):
    """
    /sku/search/?q=gra&limit=15   (default limit = 10)

    Tiny payload (SKUMiniSerializer).
    """
    serializer_class = SKUMiniSerializer
    permission_classes = (Everyone,)
    pagination_class = None
    filter_backends = (filters.SearchFilter,)
    search_fields = ("name", "description")

    def get_queryset(self):
        q = self.request.query_params.get("q", "")
        limit = int(self.request.query_params.get("limit", 10))
        base = SKU.objects.all()
        if q:
            base = base.filter(Q(name__icontains=q) | Q(description__icontains=q))
        return base.order_by("name")[:limit]


# 3) All SKUs linked to a Category -----------------------------------
@extend_schema(tags=["Category SKUs"])
class CategorySKUList(generics.ListAPIView):
    """
    /sku/by-category/<pk>/
    """
    serializer_class = SKUMiniSerializer
    permission_classes = (Everyone,)
    pagination_class = None

    def get_queryset(self):
        cat_id = self.kwargs["pk"]
        return Category.objects.get(pk=cat_id).available_sku.all().order_by("name")


@extend_schema(tags=["Vendor SKUs"])
class VendorSKUViewSet(viewsets.ModelViewSet):
    """
    /my/sku/ → list + create
    /my/sku/{pk}/ → retrieve / update / delete (own SKUs only)

    • list = GLOBAL SKUs (creator=NULL) **plus** user's own
    • create= new SKU with creator = request.user
    """
    serializer_class = SKUSerializer
    permission_classes = (permissions.IsAuthenticated, IsVendor)
    filter_backends = (filters.SearchFilter,)
    search_fields = ("name", "description")

    def get_queryset(self):
        usr = self.request.user
        return SKU.objects.filter(Q(creator__isnull=True) | Q(creator=usr)).order_by("name")

    def perform_create(self, serializer):
        serializer.save(creator=self.request.user)


# ────────────────────────────────────────────────────────────
# 4.  Images (Vendor listings)
# ────────────────────────────────────────────────────────────
class IsVendorProductImageOwnerOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj: VendorProductImage):
        if request.method in permissions.SAFE_METHODS:
            return True
        user = request.user
        if not user.is_authenticated:
            return False
        if user.is_staff or user.is_superuser:
            return True
        return obj.vendor_product.seller_id == user.id


@extend_schema(tags=["Product Images"])
class ProductImageViewSet(viewsets.ModelViewSet):
    """
    /product-images/  (for **VendorProductImage**)
    ───────────────────────────────────────────────
    list    GET     ?vendor_product=<listing_id>&is_primary=true
    create  POST    { vendor_product, image, is_primary }
    detail  GET     /{pk}/
    patch   PATCH   /{pk}/ { is_primary }
    delete  DELETE  /{pk}/
    """
    queryset = (
        VendorProductImage.objects
        .select_related("vendor_product", "vendor_product__seller")
        .order_by("-is_primary", "-created")
    )
    serializer_class = VendorProductImageSerializer
    permission_classes = (IsVendorProductImageOwnerOrReadOnly,)
    parser_classes = (MultiPartParser, FormParser)
    filter_backends = (DjangoFilterBackend, filters.OrderingFilter)
    filterset_fields = ("vendor_product", "is_primary")
    ordering_fields = ("created", "is_primary")
    ordering = ("-is_primary", "-created")


class IsVendorServiceImageOwnerOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj: VendorServiceImage):
        if request.method in permissions.SAFE_METHODS:
            return True
        user = request.user
        if not user.is_authenticated:
            return False
        if user.is_staff or user.is_superuser:
            return True
        return obj.vendor_service.provider_id == user.id


@extend_schema(tags=["Product Service Images"])
class ServiceImageViewSet(viewsets.ModelViewSet):
    """
    /service-images/  (for **VendorServiceImage**)
    ─────────────────────────────────────────────────────
    list    GET     ?vendor_service=<vendor_service_id>&is_primary=true
    create  POST    { vendor_service, image, is_primary }
    detail  GET     /{pk}/
    patch   PATCH   /{pk}/ { is_primary }
    delete  DELETE  /{pk}/
    """
    queryset = (
        VendorServiceImage.objects
        .select_related("vendor_service", "vendor_service__provider")
        .order_by("-is_primary", "-created")
    )
    serializer_class = VendorServiceImageSerializer
    permission_classes = (IsVendorServiceImageOwnerOrReadOnly,)
    parser_classes = (MultiPartParser, FormParser)
    filter_backends = (DjangoFilterBackend, filters.OrderingFilter)
    filterset_fields = ("vendor_service", "is_primary")
    ordering_fields = ("created", "is_primary")
    ordering = ("-is_primary", "-created")


# ────────────────────────────────────────────────────────────────
# 1.  Product-only search
#     /search/products/?q=rice&category=4&is_active=true
# ────────────────────────────────────────────────────────────────
@extend_schema(tags=["Product Business Search"])
class ProductSearchView(generics.ListAPIView):
    """
    Query params
    ------------
      q=<str> – free-text (product.name / product.description)
      category=<id> – product.category
      condition=<id> – product condition ID
      is_active=true|false (defaults to *true* if omitted)
      min_price=<decimal>
      max_price=<decimal>
      region=<region_id> – via business OR seller.vendorprofile
      district=<district_id> – via business OR seller.vendorprofile
    """
    serializer_class = VendorProductSerializer
    permission_classes = (Everyone,)
    pagination_class = DefaultPagination
    filter_backends = (filters.SearchFilter,)
    search_fields = ("product__name", "product__description",)

    def get_queryset(self):
        params = self.request.query_params
        q = params.get("q", "").strip()
        cat = params.get("category")
        cond = params.get("condition")
        is_active = params.get("is_active", "true").lower() != "false"
        min_price = params.get("min_price")
        max_price = params.get("max_price")
        region_id = params.get("region")
        district_id = params.get("district")

        qs = (
            VendorProduct.objects
            .select_related("product", "product__category")
            .prefetch_related("images", "tags")
            .order_by("-listing_id")
        )

        if is_active:
            qs = qs.filter(is_active=True)

        if q:
            qs = qs.filter(
                Q(name__icontains=q) |
                Q(description__icontains=q)
            )

        if cat:
            try:
                qs = qs.filter(product__category_id=int(cat))
            except ValueError:
                pass

        if cond:
            try:
                qs = qs.filter(condition_id=int(cond))
            except ValueError:
                pass

        if min_price:
            try:
                qs = qs.filter(price__gte=Decimal(min_price))
            except (InvalidOperation, ValueError):
                pass
        if max_price:
            try:
                qs = qs.filter(price__lte=Decimal(max_price))
            except (InvalidOperation, ValueError):
                pass

        if region_id:
            try:
                rid = int(region_id)
                qs = qs.filter(
                    Q(business__region_id=rid) |
                    Q(business__isnull=True,
                      seller__vendorprofile__region_id=rid)
                )
            except ValueError:
                pass

        if district_id:
            try:
                did = int(district_id)
                qs = qs.filter(
                    Q(business__district_id=did) |
                    Q(business__isnull=True,
                      seller__vendorprofile__district_id=did)
                )
            except ValueError:
                pass

        return qs


@extend_schema(tags=["Product Service Search"])
class ServiceSearchView(generics.ListAPIView):
    """
    Query params
    ------------
      q=<str> – free-text (service.title / listing.description / provider / business)
      category=<id> – service.category
      pricing_type=<id> – service pricing choice ID
      is_active=true|false (defaults to *true* if omitted)
      min_price=<decimal>
      max_price=<decimal>
      region=<region_id>– via VendorService.regions or business/provider profile
      district=<district_id> – via VendorService.districts or business/provider profile
    """
    serializer_class = VendorServiceSerializer
    permission_classes = (Everyone,)
    pagination_class = DefaultPagination
    filter_backends = (filters.SearchFilter,)
    search_fields = ("service__title", "description",)

    def get_queryset(self):
        params = self.request.query_params
        q = params.get("q", "").strip()
        cat = params.get("category")
        pt = params.get("pricing_type")
        is_active = params.get("is_active", "true").lower() != "false"
        min_price = params.get("min_price")
        max_price = params.get("max_price")
        region_id = params.get("region")
        district_id = params.get("district")

        qs = (
            VendorService.objects
            .select_related("service", "service__category")
            .prefetch_related("images", "tags")
            .order_by("-vendor_service_id")
        )

        if is_active:
            qs = qs.filter(is_active=True)

        if q:
            qs = qs.filter(
                Q(service__title__icontains=q) |
                Q(description__icontains=q)
            )

        if cat:
            try:
                qs = qs.filter(service__category_id=int(cat))
            except ValueError:
                pass

        if pt:
            try:
                qs = qs.filter(pricing_type_id=int(pt))
            except ValueError:
                pass

        if min_price:
            try:
                qs = qs.filter(price__gte=Decimal(min_price))
            except (InvalidOperation, ValueError):
                pass
        if max_price:
            try:
                qs = qs.filter(price__lte=Decimal(max_price))
            except (InvalidOperation, ValueError):
                pass

        if region_id:
            try:
                rid = int(region_id)
                qs = qs.filter(
                    Q(regions__id=rid) |
                    Q(business__region_id=rid) |
                    Q(business__isnull=True,
                      provider__vendorprofile__region_id=rid)
                )
            except ValueError:
                pass

        if district_id:
            try:
                did = int(district_id)
                qs = qs.filter(
                    Q(districts__id=did) |
                    Q(business__district_id=did) |
                    Q(business__isnull=True,
                      provider__vendorprofile__district_id=did)
                )
            except ValueError:
                pass

        return qs.distinct()


# ────────────────────────────────────────────────────────────────
# 3.  Business search
#     /search/businesses/?q=agro
# ────────────────────────────────────────────────────────────────
@extend_schema(tags=["Product Business Search"])
class BusinessSearchView(generics.ListAPIView):
    """
    Searches Business.name (icontains) + owner.vendorprofile.display_name.
    """
    serializer_class = BusinessBriefSerializer
    permission_classes = (Everyone,)
    pagination_class = DefaultPagination
    filter_backends = (filters.SearchFilter,)
    search_fields = ("business_name",)

    def get_queryset(self):
        q = self.request.query_params.get("q", "").strip()
        qs = Business.objects.select_related("vendor")
        if q:
            qs = qs.filter(
                Q(business_name__icontains=q) |
                Q(vendor__vendorprofile__display_name__icontains=q)
            )
        return qs.order_by("business_name")



# ────────────────────────────────────────────────────────────────
# 4.  Seller / Vendor search
#     /search/sellers/?q=kwame
# ────────────────────────────────────────────────────────────────
@extend_schema(tags=["Product Seller Search"])
class SellerSearchView(generics.ListAPIView):
    """
    Returns **vendor profiles** (not raw users) matching the search term.
    """
    serializer_class = VendorProfileSerializer
    permission_classes = (Everyone,)
    pagination_class = DefaultPagination
    filter_backends = (filters.SearchFilter,)
    search_fields = ("display_name",)

    def get_queryset(self):
        q = self.request.query_params.get("q", "").strip()
        qs = CustomUser.objects.filter(vendorprofile__isnull=False)
        if q:
            qs = qs.filter(vendorprofile__display_name__icontains=q)
        return qs.select_related("vendorprofile").order_by("vendorprofile__display_name")


# @extend_schema(tags=["Product Categories"])
# class CategorySearchView(AutocompleteMixin):
#     """
#     Uses the light *mini* serializer (id & name only) so the
#     autocomplete payload stays tiny.
#     """
#     base_qs = Category.objects.filter(is_active=True)
#     serializer_class = CategoryMiniSerializer
#     search_fields = ("name", "description")

@extend_schema(tags=["Product Categories"])
class PublicProductCategoryTree(ListAPIView):
    """
    GET /product-categories/tree/
    full active tree of product categories
    """
    permission_classes = (Everyone,)
    queryset = Category.objects.filter(
        type=Category.PRODUCT,
        is_active=True,
        parent__isnull=True
    ).order_by("name")
    serializer_class = CategoryTreeSerializer


@extend_schema(tags=["Product Categories"])
class PublicProductCategoryDetail(RetrieveAPIView):
    """
    GET /product-categories/<pk>/
    subtree + detail flags for products
    """
    permission_classes = (Everyone,)
    lookup_field = "pk"
    queryset = Category.objects.filter(
        type=Category.PRODUCT,
        is_active=True
    )
    serializer_class = CategoryDetailSerializer

    def retrieve(self, request, *args, **kwargs):
        obj = self.get_object()
        data = self.get_serializer(obj, context={"request": request}).data
        return ok("OK", data)


@extend_schema(tags=["Product Categories"])
class ProductCategorySearchView(AutocompleteMixin):
    """
    Autocomplete (id/name) for product categories
    """
    base_qs = Category.objects.filter(type=Category.PRODUCT, is_active=True)
    serializer_class = CategoryMiniSerializer
    search_fields = ("name", "description")


@extend_schema(tags=["Service Categories"])
class PublicServiceCategoryTree(ListAPIView):
    """
    GET /service-categories/tree/
    full active tree of service categories
    """
    permission_classes = (Everyone,)
    queryset = Category.objects.filter(
        type=Category.SERVICE,
        is_active=True,
        parent__isnull=True
    ).order_by("name")
    serializer_class = CategoryTreeSerializer


@extend_schema(tags=["Service Categories"])
class PublicServiceCategoryDetail(RetrieveAPIView):
    """
    GET /service-categories/<pk>/
    subtree + detail flags for services
    """
    permission_classes = (Everyone,)
    lookup_field = "pk"
    queryset = Category.objects.filter(
        type=Category.SERVICE,
        is_active=True
    )
    serializer_class = CategoryDetailSerializer

    def retrieve(self, request, *args, **kwargs):
        obj = self.get_object()
        data = self.get_serializer(obj, context={"request": request}).data
        return ok("OK", data)


@extend_schema(tags=["Service Categories"])
class ServiceCategorySearchView(AutocompleteMixin):
    """
    Autocomplete (id/name) for service categories
    """
    base_qs = Category.objects.filter(type=Category.SERVICE, is_active=True)
    serializer_class = CategoryMiniSerializer
    search_fields = ("name", "description")


@extend_schema(tags=["Product Conditions"])
class ProductConditionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /product-conditions/          – list
    GET /product-conditions/{pk}/     – retrieve

    *Search* → ?search=<term>  (icontains on name / description)
    """
    queryset = ProductCondition.objects.all().order_by("name")
    serializer_class = ConditionMiniSerializer
    permission_classes = (Everyone,)
    filter_backends = (filters.SearchFilter,)
    search_fields = ("name", "description")


@extend_schema(tags=["Product Service Statuses"])
class ProductServiceStatusViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /product-statuses/            – list
    GET /product-statuses/{pk}/       – retrieve

    *Search* → ?search=<term>  (icontains on name / description)
    """
    queryset = ProductServiceStatus.objects.all().order_by("name")
    serializer_class = StatusMiniSerializer
    permission_classes = (Everyone,)
    filter_backends = (filters.SearchFilter,)
    search_fields = ("name", "description")


class ServicePricingChoiceViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET  /pricing-choices/         → list all
    GET  /pricing-choices/{pk}/    → retrieve one
    ?search=<term>                 → icontains on name or description
    """
    queryset = ServicePricingChoices.objects.all().order_by("name")
    serializer_class = ServicePricingChoiceSerializer
    permission_classes = (AllowAny,)
    filter_backends = (filters.SearchFilter,)
    search_fields = ("name", "description")

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(qs, many=True)
        return ok("OK", serializer.data)

    def retrieve(self, request, *args, **kwargs):
        obj = self.get_object()
        serializer = self.get_serializer(obj)
        return ok("OK", serializer.data)


class TopProductsView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = VendorProductSerializer

    def get_queryset(self):
        # assumes an orders app pointing to VendorProduct via related_name="direct_orders"
        return (
            VendorProduct.objects.annotate(order_count=Count("direct_orders"))
            .filter(is_active=True)
            .order_by("-order_count")[:10]
        )

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return ok("Top 10 popular products", serializer.data)


class TopServicesView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = VendorServiceSerializer

    def get_queryset(self):
        # assumes a bookings app pointing to VendorService via related_name="direct_bookings"
        return (
            VendorService.objects.annotate(booking_count=Count("direct_bookings"))
            .filter(is_active=True)
            .order_by("-booking_count")[:10]
        )

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return ok("Top 10 popular services", serializer.data)


# ────────────────────────────────────────────────
# 1.a  PRODUCT CATEGORY TREE & DETAIL & SEARCH
# ────────────────────────────────────────────────

@extend_schema(tags=["Product Categories"])
class PublicProductCategoryTree(ListAPIView):
    """
    GET /product-categories/tree/
    full active tree of product categories
    """
    permission_classes = (Everyone,)
    queryset = Category.objects.filter(
        type=Category.PRODUCT,
        is_active=True,
        parent__isnull=True
    ).order_by("name")
    serializer_class = CategoryTreeSerializer


@extend_schema(tags=["Product Categories"])
class PublicProductCategoryDetail(RetrieveAPIView):
    """
    GET /product-categories/<pk>/
    subtree + detail flags for products
    """
    permission_classes = (Everyone,)
    lookup_field = "pk"
    queryset = Category.objects.filter(
        type=Category.PRODUCT,
        is_active=True
    )
    serializer_class = CategoryDetailSerializer

    def retrieve(self, request, *args, **kwargs):
        obj = self.get_object()
        data = self.get_serializer(obj, context={"request": request}).data
        return ok("OK", data)


@extend_schema(tags=["Product Categories"])
class ProductCategorySearchView(AutocompleteMixin):
    """
    Autocomplete (id/name) for product categories
    """
    base_qs = Category.objects.filter(type=Category.PRODUCT, is_active=True)
    serializer_class = CategoryMiniSerializer
    search_fields = ("name", "description")


# ────────────────────────────────────────────────
# 1.b  SERVICE CATEGORY TREE & DETAIL & SEARCH
# ────────────────────────────────────────────────
#
# @extend_schema(tags=["Service Categories"])
# class PublicServiceCategoryTree(ListAPIView):
#     """
#     GET /service-categories/tree/
#     full active tree of service categories
#     """
#     permission_classes = (Everyone,)
#     queryset = Category.objects.filter(
#         type=Category.SERVICE,
#         is_active=True,
#         parent__isnull=True
#     ).order_by("name")
#     serializer_class = CategoryTreeSerializer
#
#
# @extend_schema(tags=["Service Categories"])
# class PublicServiceCategoryDetail(RetrieveAPIView):
#     """
#     GET /service-categories/<pk>/
#     subtree + detail flags for services
#     """
#     permission_classes = (Everyone,)
#     lookup_field = "pk"
#     queryset = Category.objects.filter(
#         type=Category.SERVICE,
#         is_active=True
#     )
#     serializer_class = CategoryDetailSerializer
#
#     def retrieve(self, request, *args, **kwargs):
#         obj = self.get_object()
#         data = self.get_serializer(obj, context={"request": request}).data
#         return ok("OK", data)
#
#
# @extend_schema(tags=["Service Categories"])
# class ServiceCategorySearchView(AutocompleteMixin):
#     """
#     Autocomplete (id/name) for service categories
#     """
#     base_qs = Category.objects.filter(type=Category.SERVICE, is_active=True)
#     serializer_class = CategoryMiniSerializer
#     search_fields = ("name", "description")
