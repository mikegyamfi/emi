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

from .models import (
    Product, Service, Category, Tag, Attributes,
    ProductImage, ProductServiceStatus, ProductCondition, SKU, ServiceImage, ServicePricingChoices
)
from .serializers import (
    ProductSerializer, ServiceSerializer, CategoryTreeSerializer,
    TagSerializer, AttributeSerializer, SKUMiniSerializer, CategoryDetailSerializer, ProductDetailSerializer,
    ProductMiniSerializer, ServiceMiniSerializer, ServiceDetailSerializer, ProductImageSerializer,
    ServiceImageSerializer, CategoryMiniSerializer, SKUSerializer, ConditionMiniSerializer, StatusMiniSerializer,
    ServicePricingChoiceSerializer,
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


# quick reusable filters
class _ProductFilter(df.FilterSet):
    is_active = df.BooleanFilter()
    featured = df.BooleanFilter()
    category = df.NumberFilter(field_name="category_id")
    tags = df.ModelMultipleChoiceFilter(
        field_name="tags__id", to_field_name="id", queryset=Tag.objects.all(),
        conjoined=False)
    attributes = df.ModelMultipleChoiceFilter(
        field_name="attributes__id", to_field_name="id",
        queryset=Attributes.objects.all(), conjoined=False)
    business = df.NumberFilter(field_name="business_id")
    seller = df.NumberFilter(field_name="seller_id")

    class Meta:
        model = Product
        fields = []  # ↑ all declared manually


class _ServiceFilter(_ProductFilter):
    """
    Extends the generic product filter with every lookup that makes sense
    for a Service:

    • category           – id
    • is_active          – bool
    • is_remote          – bool
    • pricing_type       – id
    • regions            – id  (many-to-many)
    • district           – id  (many-to-many)
    • town               – id  (many-to-many)
    • tag                – id  (many-to-many)
    • attribute          – id  (many-to-many)
    """

    pricing_type = df.NumberFilter(field_name="pricing_type__id")
    regions = df.NumberFilter(field_name="regions__id")
    district = df.NumberFilter(field_name="district__id")
    town = df.NumberFilter(field_name="town__id")

    # The product filter already carried `category`, `tag`, `attribute`,
    # `is_active` …

    class Meta(_ProductFilter.Meta):
        model = Service
        # merge parent fields + the four above
        fields = _ProductFilter.Meta.fields + [
            "pricing_type",
            "regions", "district", "town",
        ]


# ────────────────────────────────────────────────────────────
# 1.  PUBLIC READ-ONLY ENDPOINTS
# ────────────────────────────────────────────────────────────
@extend_schema(tags=["Public Products"])
class PublicProductViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Anyone can list / retrieve products
    """
    queryset = (
        Product.objects
        .select_related(
            "category",
            "seller", "seller__vendorprofile",
            "business",
        )
        .prefetch_related(
            "tags", "attributes", "images",
        )
    )
    serializer_class = ProductSerializer  # default for “list”
    permission_classes = (Everyone,)
    pagination_class = DefaultPagination
    filter_backends = (DjangoFilterBackend, filters.SearchFilter)
    filterset_class = _ProductFilter
    search_fields = ("name", "slug", "description")

    # -----------------------------------------------------------
    # automatically switch to the detail serializer
    # -----------------------------------------------------------
    def get_serializer_class(self):
        if self.action == "retrieve":
            return ProductDetailSerializer
        return super().get_serializer_class()


@extend_schema(tags=["Public Services"])
class PublicServiceViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Same idea as above for services.
    """
    queryset = Service.objects.prefetch_related(
        "tags", "attributes", "images", "category")
    serializer_class = ServiceSerializer
    permission_classes = (Everyone,)
    pagination_class = DefaultPagination
    filter_backends = (DjangoFilterBackend, filters.SearchFilter)
    filterset_class = _ServiceFilter
    search_fields = ("title", "description")


@extend_schema(tags=["Product Public Category Trees"])
class PublicCategoryTree(generics.GenericAPIView):
    """
    GET /categories/tree/
    {
      "code": 1,
      "message": "OK",
      "data": {
        "categories"        : …  # full active tree
        "product_categories": …  # roots that *contain or descend-to* products
        "service_categories": …  # same for services
      }
    }
    """
    permission_classes = (Everyone,)

    # -------------------------------------------------------------
    # helpers
    # -------------------------------------------------------------
    def _active_roots(self, cats_qs):
        """
        Given **any** Category queryset, return the distinct set of
        *active* root categories that lie on the path to those nodes.
        """
        # (1) fetch only the columns we need – id & parent_id
        lookup = dict(
            Category.objects
            .filter(is_active=True)
            .values_list("id", "parent_id")
        )

        root_ids = set()
        for cat_id in cats_qs.values_list("id", flat=True).distinct():
            cur = cat_id
            # climb up until we hit the top (parent_id == None)
            while cur and cur in lookup:
                parent = lookup[cur]
                if parent is None:  # ← root reached
                    root_ids.add(cur)
                    break
                cur = parent
        return (
            Category.objects
            .filter(id__in=root_ids, is_active=True)
            .order_by("name")
        )

    # -------------------------------------------------------------
    # GET
    # -------------------------------------------------------------
    def get(self, request, *args, **kwargs):

        # --- 1) full tree (unchanged) ----------------------------
        all_roots = (
            Category.objects
            .filter(is_active=True, parent__isnull=True)
            .order_by("name")
        )

        # --- 2) product / service roots --------------------------
        product_nodes = Category.objects.filter(products__isnull=False)
        service_nodes = Category.objects.filter(services__isnull=False)

        product_roots = self._active_roots(product_nodes)
        service_roots = self._active_roots(service_nodes)

        ctx = {"request": request}
        serializer = CategoryTreeSerializer

        payload = {
            "categories": serializer(all_roots, many=True, context=ctx).data,
            "product_categories": serializer(product_roots, many=True, context=ctx).data,
            "service_categories": serializer(service_roots, many=True, context=ctx).data,
        }
        return ok("OK", payload)


@extend_schema(tags=["Product Public Category Details"])
class PublicCategoryDetail(generics.RetrieveAPIView):
    """
    GET /categories/<pk>/

    Returns the subtree starting at `<pk>` *plus* meta flags that help
    the front-end decide what UI controls to show.

    Response
    --------
    {
      "code": 1,
      "message": "OK",
      "data": CategoryDetailSerializer
    }
    """
    lookup_field = "pk"
    queryset = Category.objects.filter(is_active=True)
    serializer_class = CategoryDetailSerializer

    def retrieve(self, request, *args, **kwargs):
        obj = self.get_object()
        ser = self.get_serializer(obj, context={"request": request})
        return ok("OK", ser.data)


# quick “random N” helpers  ----------------------------------
class _RandomMixin:
    """
    Helper that returns up-to-N random *active* rows for any model that
    has an `is_active` BooleanField — no assumption about the PK name.
    """

    def _rand_queryset(self, model, n: int):
        pk_name = model._meta.pk.name  # ← smart ✔
        ids = list(
            model.objects.filter(is_active=True)
            .values_list(pk_name, flat=True)
        )

        # if we have <= n rows, just return them all
        chosen = ids if len(ids) <= n else sample(ids, n)

        return model.objects.filter(**{f"{pk_name}__in": chosen})


# -----------------------------------------------------------
# Random product/service endpoints
# -----------------------------------------------------------
@extend_schema(tags=["Random Products"])
class RandomProducts(_RandomMixin, generics.ListAPIView):
    """
    /products/random/?n=12   (default **8**)
    """
    serializer_class = ProductSerializer
    permission_classes = (Everyone,)

    def get_queryset(self):
        n = int(self.request.query_params.get("n", 8))
        return self._rand_queryset(Product, n)


@extend_schema(tags=["Random Services"])
class RandomServices(_RandomMixin, generics.ListAPIView):
    """
    /services/random/?n=12   (default **8**)
    """
    serializer_class = ServiceSerializer
    permission_classes = (Everyone,)

    def get_queryset(self):
        n = int(self.request.query_params.get("n", 8))
        return self._rand_queryset(Service, n)


# full-text   products + services + business + seller ----------
@extend_schema(tags=["Product Glocal Search"])
class GlobalSearch(generics.ListAPIView):
    """
    /search/?q=rice&category=3&is_active=true …

    Searches:
        • Product.name / .description
        • Service.name / .description
        • Business.name
        • Seller (VendorProfile.display_name)

    Result schema:
    ```json
    {
      "products":  [... ProductSerializer ...],
      "services":  [... ServiceSerializer ...]
    }
    ```
    """
    permission_classes = (Everyone,)
    pagination_class = None  # single JSON blob

    def get(self, request):
        q = request.query_params.get("q", "").strip()
        cat = request.query_params.get("category")
        base_prod = Product.objects.filter(is_active=True)
        base_srv = Service.objects.filter(is_active=True)

        if q:
            base_prod = base_prod.filter(
                Q(name__icontains=q) | Q(description__icontains=q) |
                Q(seller__vendorprofile__display_name__icontains=q) |
                Q(business__business_name__icontains=q)
            )
            base_srv = base_srv.filter(
                Q(title__icontains=q) | Q(description__icontains=q) |
                Q(provider__vendorprofile__display_name__icontains=q) |
                Q(business__business_name__icontains=q)
            )
        if cat:
            base_prod = base_prod.filter(category_id=cat)
            base_srv = base_srv.filter(category_id=cat)

        return ok("search results", {
            "products": ProductSerializer(base_prod[:30], many=True,
                                          context=self.get_serializer_context()).data,
            "services": ServiceSerializer(base_srv[:30], many=True,
                                          context=self.get_serializer_context()).data,
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
    /my_products_management/ … full vendor CRUD.
    Supports multiple image uploads via `new_images`.
    """
    permission_classes = (IsVendor,)
    parser_classes = (MultiPartParser, FormParser)
    pagination_class = DefaultPagination
    queryset = (
        Product.objects
        .select_related("category", "business")
        .prefetch_related("images", "tags", "attributes")
    )
    filter_backends = (DjangoFilterBackend, filters.SearchFilter)
    filterset_class = _ProductFilter
    search_fields = ("name", "slug", "description")

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ProductDetailSerializer
        return ProductSerializer

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
            return fail("Validation error", exc.detail)
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
            return fail("Validation error", exc.detail)
        return ok("Product updated successfully", serializer.data)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, partial=True, **kwargs)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        prod = self.get_object()
        prod.is_active = True
        prod.save(update_fields=["is_active"])
        data = ProductMiniSerializer(prod, context={"request": request}).data
        return ok("Product activated", data)

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        prod = self.get_object()
        prod.is_active = False
        prod.save(update_fields=["is_active"])
        data = ProductMiniSerializer(prod, context={"request": request}).data
        return ok("Product deactivated", data)

    @action(detail=False, url_path=r'by-business/(?P<business_pk>\d+)', methods=["get"])
    def by_business(self, request, business_pk=None):
        vendor = VendorProfile.objects.get(user=request.user)
        biz = get_object_or_404(
            Business.objects.filter(vendor=vendor),
            pk=business_pk
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
    * default list / create / update / destroy use **ServiceSerializer**
    * retrieve       → **ServiceDetailSerializer**

    Filters & search are identical to the public view:
        `_ServiceFilter`  +  ?search=<text>
    """
    permission_classes = (IsVendor,)
    pagination_class = DefaultPagination
    filter_backends = (DjangoFilterBackend, filters.SearchFilter)
    filterset_class = _ServiceFilter
    search_fields = ("title", "description")

    queryset = (
        Service.objects
        .select_related("category", "business")
        .prefetch_related("images", "tags", "attributes",
                          "regions", "district", "town")
    )

    # choose serializer
    def get_serializer_class(self):
        return ServiceDetailSerializer if self.action == "retrieve" else ServiceSerializer

    # scope to this vendor
    def get_queryset(self):
        return super().get_queryset().filter(provider=self.request.user)

    # override list
    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        ser = self.get_serializer(page or qs, many=True)
        data = ser.data

        if page is not None:
            # keep DRF’s pagination envelope
            return self.get_paginated_response(data)

        return ok(data=data)

    # override retrieve
    def retrieve(self, request, *args, **kwargs):
        inst = self.get_object()
        ser = self.get_serializer(inst)
        return ok(data=ser.data)

    # override create
    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        self.perform_create(ser)
        return ok("Service created successfully.", ser.data)

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

    # custom activate/deactivate already use ok()
    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        srv = self.get_object()
        srv.is_active = True
        srv.save(update_fields=["is_active"])
        return ok("Service activated", ServiceMiniSerializer(srv, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        srv = self.get_object()
        srv.is_active = False
        srv.save(update_fields=["is_active"])
        return ok("Service deactivated", ServiceMiniSerializer(srv, context={"request": request}).data)

    # list by-business
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

        # reverse accessor is “category”
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
    pagination_class = None  # single flat list
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
    /sku/by-category/<cat_id>/
    """
    serializer_class = SKUMiniSerializer
    permission_classes = (Everyone,)
    pagination_class = None
    search_fields = ("name", "description")

    def get_queryset(self):
        cat_id = self.kwargs["pk"]
        return (
            Category.objects
            .get(pk=cat_id)
            .available_sku  # M2M manager
            .all()
            .order_by("name")
        )


@extend_schema(tags=["Vendor SKUs"])
class VendorSKUViewSet(viewsets.ModelViewSet):
    """
    /my/sku/           → list + create
    /my/sku/{pk}/      → retrieve / update / delete (own SKUs only)

    • list  = GLOBAL SKUs (creator=NULL) **plus** user's own
    • create= new SKU with creator = request.user
    """
    serializer_class = SKUSerializer
    permission_classes = (permissions.IsAuthenticated, IsVendor)
    filter_backends = (filters.SearchFilter,)
    search_fields = ("name", "description")

    # ---------- queryset helper -------------------
    def get_queryset(self):
        usr = self.request.user
        return (
            SKU.objects
            .filter(Q(creator__isnull=True) | Q(creator=usr))
            .order_by("name")
        )

    # ---------- create override -------------------
    def perform_create(self, serializer):
        serializer.save(creator=self.request.user)


class IsProductOwnerOrReadOnly(permissions.BasePermission):
    """
    • SAFE methods (GET / HEAD / OPTIONS) → always allowed
    • WRITE methods → allowed if request.user is
        – the seller who owns the related product, or
        – an authenticated staff / super-user
    """

    def has_object_permission(self, request, view, obj: ProductImage):
        if request.method in permissions.SAFE_METHODS:
            return True

        user = request.user
        if not user.is_authenticated:  # must be logged-in
            return False

        if user.is_staff or user.is_superuser:  # admins
            return True

        return obj.product.seller_id == user.id  # owner check


@extend_schema(tags=["Product Images"])
class ProductImageViewSet(viewsets.ModelViewSet):
    """
    /product-images/
    ───────────────────────────────────────────────
    list    GET     ?product=<id>&is_primary=true
    create  POST    { product, image, is_primary }
    detail  GET     /{pk}/
    patch   PATCH   /{pk}/ { is_primary }
    delete  DELETE  /{pk}/
    """
    queryset = (
        ProductImage.objects
        .select_related("product", "product__seller")
        .order_by("-is_primary", "-created")
    )
    serializer_class = ProductImageSerializer
    permission_classes = (IsProductOwnerOrReadOnly,)
    parser_classes = (MultiPartParser, FormParser)  # ← accept files
    filter_backends = (DjangoFilterBackend, filters.OrderingFilter)
    filterset_fields = ("product", "is_primary")
    ordering_fields = ("created", "is_primary")
    ordering = ("-is_primary", "-created")


class IsServiceOwnerOrReadOnly(permissions.BasePermission):
    """
    • SAFE methods → always allowed.
    • WRITE methods → only the service's provider **or** staff.
    """

    def has_object_permission(self, request, view, obj: ServiceImage):
        if request.method in permissions.SAFE_METHODS:
            return True

        user = request.user
        if not user.is_authenticated:
            return False

        if user.is_staff or user.is_superuser:
            return True

        return obj.service.provider_id == user.id


@extend_schema(tags=["Product Service Images"])
class ServiceImageViewSet(viewsets.ModelViewSet):
    """
    /service-images/
    ─────────────────────────────────────────────────────
    list    GET     ?service=<id>&is_primary=true
    create  POST    { service, image, is_primary }
    detail  GET     /{pk}/
    patch   PATCH   /{pk}/ { is_primary }
    delete  DELETE  /{pk}/
    """
    queryset = (
        ServiceImage.objects
        .select_related("service", "service__provider")
        .order_by("-is_primary", "-created")
    )
    serializer_class = ServiceImageSerializer
    permission_classes = (IsServiceOwnerOrReadOnly,)
    parser_classes = (MultiPartParser, FormParser)  # ← enable file upload
    filter_backends = (DjangoFilterBackend, filters.OrderingFilter)
    filterset_fields = ("service", "is_primary")
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
      q=<str>                – free-text (name / description)
      category=<id>
      condition=<id>         – product condition ID
      is_active=true|false   (defaults to *true* if omitted)
      min_price=<decimal>
      max_price=<decimal>
      region=<region_id>
      district=<district_id>
    """
    serializer_class = ProductSerializer
    permission_classes = (Everyone,)
    pagination_class = DefaultPagination
    filter_backends = (filters.SearchFilter,)
    search_fields = ("name", "description",)

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
            Product.objects
            .select_related("category")
            .prefetch_related("images", "tags")
            .order_by("-product_id")
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
                qs = qs.filter(category_id=int(cat))
            except ValueError:
                pass

        # ── CONDITION ─────────────────────────────
        if cond:
            try:
                qs = qs.filter(condition_id=int(cond))
            except ValueError:
                pass

        # ── PRICE RANGE ───────────────────────────
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

        # ── REGION ───────────────────────────────
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

        # ── DISTRICT ────────────────────────────
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
      q=<str>                  – free-text (title / description / provider / business)
      category=<id>
      pricing_type=<id>        – service pricing choice ID
      is_active=true|false     (defaults to *true* if omitted)
      min_price=<decimal>
      max_price=<decimal>
      region=<region_id>
      district=<district_id>
    """
    serializer_class = ServiceSerializer
    permission_classes = (Everyone,)
    pagination_class = DefaultPagination
    filter_backends = (filters.SearchFilter,)
    search_fields = ("title", "description",)

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
            Service.objects
            .select_related("category")
            .prefetch_related("images", "tags")
            .order_by("-service_id")
        )

        if is_active:
            qs = qs.filter(is_active=True)

        if q:
            qs = qs.filter(
                Q(title__icontains=q)
                # Q(description__icontains=q) |
                # Q(provider__vendorprofile__display_name__icontains=q) |
                # Q(business__business_name__icontains=q)
            )

        if cat:
            try:
                qs = qs.filter(category_id=int(cat))
            except ValueError:
                pass

        # ── PRICING TYPE ────────────────────────────
        if pt:
            try:
                qs = qs.filter(pricing_type_id=int(pt))
            except ValueError:
                pass

        # ── PRICE RANGE ────────────────────────────
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

        # ── REGION ────────────────────────────────
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

        # ── DISTRICT ──────────────────────────────
        if district_id:
            try:
                did = int(district_id)
                qs = qs.filter(
                    Q(district__id=did) |
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
        # Only users that actually *have* a vendor profile
        qs = CustomUser.objects.filter(vendorprofile__isnull=False)
        if q:
            qs = qs.filter(vendorprofile__display_name__icontains=q)
        return qs.select_related("vendorprofile").order_by("vendorprofile__display_name")


@extend_schema(tags=["Product Categories"])
class CategorySearchView(AutocompleteMixin):
    """
    Uses the light *mini* serializer (id & name only) so the
    autocomplete payload stays tiny.
    """
    base_qs = Category.objects.filter(is_active=True)
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
