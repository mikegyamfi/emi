from typing import Iterable, Tuple

from django.db.models import Min, Max, Avg, Prefetch, Q
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import generics, pagination, viewsets, filters
from rest_framework.permissions import AllowAny

from core.lookup_views import AutocompleteMixin
from core.response import ok
from market_intelligence.models import PriceListing, PriceHistory, Product, Category, Tag, Market, \
    Town, Region, District, Service
from market_intelligence.serializers import ListingWithHistorySerializer, ProductSerializer, CategorySerializer, \
    TagSerializer, ListingSerializer, CategoryDetailSerializer, TownSerializer, MarketSerializer, RegionSerializer, \
    DistrictSerializer, ListingAnalyticsSerializer, ServiceSerializer


class DefaultPagination(pagination.PageNumberPagination):
    page_size = 30
    page_size_query_param = "page_size"
    max_page_size = 200


class Everyone(AllowAny):
    ...


# ----------------- simple readonly viewsets -----------------
@extend_schema(tags=["Market Intelligence Regions"])
class RegionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Region.objects.all().order_by("name")
    serializer_class = RegionSerializer
    permission_classes = (Everyone,)


@extend_schema(tags=["Market Intelligence Districts"])
class DistrictViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = District.objects.select_related("region").order_by("name")
    serializer_class = DistrictSerializer
    permission_classes = (Everyone,)
    filter_backends = (DjangoFilterBackend,)
    filterset_fields = ("region",)


@extend_schema(tags=["Market Intelligence Towns"])
class TownViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Town.objects.select_related("district", "district__region").order_by("name")
    serializer_class = TownSerializer
    permission_classes = (Everyone,)
    filter_backends = (DjangoFilterBackend,)
    filterset_fields = ("district",)


@extend_schema(tags=["Market Intelligence Markets"])
class MarketViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Market.objects.select_related("town", "town__district").order_by("name")
    serializer_class = MarketSerializer
    permission_classes = (Everyone,)
    filter_backends = (DjangoFilterBackend,)
    filterset_fields = ("town",)


# ───────────────── Category ─────────────────────────────
@extend_schema(tags=["Market Intelligence Categories"])
class CategoryViewSet(viewsets.ModelViewSet):
    """
    * list   → full tree; each node has `products` + `children`
    * detail → same, PLUS `all_products` (flattened)
    """
    queryset = Category.objects.all().order_by("name")
    serializer_class = CategorySerializer
    permission_classes = (Everyone,)  # swap for role guard later
    filter_backends = (filters.SearchFilter,)
    search_fields = ("name",)

    # choose richer serializer for /<id>/ -----------------------------
    def get_serializer_class(self):
        if self.action == "retrieve":
            return CategoryDetailSerializer
        return CategorySerializer


# ───────────────── Tag ─────────────────────────────────
@extend_schema(tags=["Market Intelligence Tags"])
class TagViewSet(viewsets.ModelViewSet):
    queryset = Tag.objects.all().order_by("name")
    serializer_class = TagSerializer
    permission_classes = (Everyone,)
    filter_backends = (filters.SearchFilter,)
    search_fields = ("name",)


_LISTING_PREFETCH = (
    "listings__town",
    "listings__market",
    "listings__history",
)

_LOCATION_Q = dict(
    region="listings__town__district__region_id",
    district="listings__town__district_id",
    town="listings__town_id",
    market="listings__market_id",
)


class _BaseStemViewSet(viewsets.ModelViewSet):
    """Shared location/filter logic for both stems."""
    permission_classes = (Everyone,)
    filter_backends = (DjangoFilterBackend, filters.SearchFilter)
    filterset_fields = ("category",)
    search_fields = ("name", "description", "sku")

    def _apply_location_filters(self, qs):
        params = self.request.query_params
        flt = Q()
        for key, path in _LOCATION_Q.items():
            if val := params.get(key):
                flt &= Q(**{path: val})
        return qs.filter(flt) if flt else qs


# ───────────────── Product / Service ───────────────────
@extend_schema(tags=["Market Intelligence Products"])
class ProductViewSet(_BaseStemViewSet):
    """
    Filters
    -------
    • ?category=<pk>
    • ?region=<pk>
    • ?district=<pk>
    • ?town=<pk>
    • ?market=<pk>
    """
    serializer_class = ProductSerializer
    permission_classes = (Everyone,)
    filter_backends = (DjangoFilterBackend, filters.SearchFilter)
    filterset_fields = ("category",)
    search_fields = ("name", "description", "sku")

    # ------------------------------------------------------------
    def get_queryset(self):
        qs = (
            Product.objects
            .select_related("category")
            .prefetch_related(  # new relations
                "tags",
                "images",
                "listings__town",
                "listings__market",
                "listings__history",
            )
            .order_by("-id")
            .order_by("-id")
        )

        # --- location drill-down -------------------------------
        params = self.request.query_params
        region = params.get("region")
        district = params.get("district")
        town = params.get("town")
        market = params.get("market")

        if any([region, district, town, market]):
            # Build a single Q() to match listings down the chain
            listing_filter = Q()

            if market:
                listing_filter &= Q(productandservicelisting__market_id=market)
            if town:
                listing_filter &= Q(productandservicelisting__town_id=town)
            if district:
                listing_filter &= Q(
                    productandservicelisting__town__district_id=district
                )
            if region:
                listing_filter &= Q(
                    productandservicelisting__town__district__region_id=region
                )

            qs = qs.filter(listing_filter)

        return qs


@extend_schema(tags=["Market Intelligence Services"])
class ServiceViewSet(_BaseStemViewSet):
    """
    Same filter set as Product but operates on the Service table.
    """
    serializer_class = ServiceSerializer
    permission_classes = (Everyone,)
    filter_backends = (DjangoFilterBackend, filters.SearchFilter)
    filterset_fields = ("category",)
    search_fields = ("name", "description", "sku")

    def get_queryset(self):
        qs = (
            Service.objects
            .select_related("category")
            .prefetch_related(
                "tags",
                "images",
                "listings__town",
                "listings__market",
                "listings__history",
            )
            .order_by("-id")
        )

        params = self.request.query_params
        region = params.get("region")
        district = params.get("district")
        town = params.get("town")
        market = params.get("market")

        if any([region, district, town, market]):
            q = Q()
            if market:
                q &= Q(productandservicelisting__market_id=market)
            if town:
                q &= Q(productandservicelisting__town_id=town)
            if district:
                q &= Q(productandservicelisting__town__district_id=district)
            if region:
                q &= Q(productandservicelisting__town__district__region_id=region)
            qs = qs.filter(q)

        return qs


# ───────────────── Listing ──────────────────────────────
@extend_schema(tags=["Market Intelligence Listings"])
class ListingViewSet(viewsets.ModelViewSet):
    """
    create / update → ListingSerializer (validates XOR rule)
    retrieve        → ListingAnalyticsSerializer (heavy analytics)
    list            → ListingSerializer (light)
    """
    queryset = PriceListing.objects.select_related(
        "product", "service",
        "town", "market", "market__town"
    ).prefetch_related("history")
    permission_classes = (Everyone,)
    filter_backends = (DjangoFilterBackend,)
    filterset_fields = (
        "town", "market", "product", "service", "status"
    )

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ListingAnalyticsSerializer
        return ListingSerializer


# Create your views here.
# ──────────────────────────────────────────────────────────
# 1.  Region / District / Town product explorer
#     GET /api/v1/explorer/?region=<id>&category=<id>
# ──────────────────────────────────────────────────────────
@extend_schema(tags=["Market Intelligence Explorer"])
class ExplorerView(generics.ListAPIView):
    """
    ?region | ?district | ?town  (highest supplied wins)
    Optional ?category
    Groups results by Category, for both Products **and** Services.
    """
    serializer_class = ProductSerializer
    pagination_class = DefaultPagination
    permission_classes = (Everyone,)

    def _base_qs(self, model):
        qs = model.objects.select_related("category")
        p = self.request.query_params
        if town := p.get("town"):
            qs = qs.filter(listings__town_id=town)
        elif district := p.get("district"):
            qs = qs.filter(listings__town__district_id=district)
        elif region := p.get("region"):
            qs = qs.filter(listings__town__district__region_id=region)
        if cat := p.get("category"):
            qs = qs.filter(category_id=cat)
        return qs.distinct()

    def get_queryset(self):  # never used – needed for DRF
        return Product.objects.none()

    def list(self, request, *args, **kwargs):
        prods = self._base_qs(Product)
        servs = self._base_qs(Service)
        cat_ids = set(prods.values_list("category_id", flat=True)) | set(servs.values_list("category_id", flat=True))

        out = []
        for cat in Category.objects.filter(id__in=cat_ids).order_by("name"):
            out.append({
                "category": CategorySerializer(cat).data,
                "products": ProductSerializer(prods.filter(category=cat),
                                              many=True).data,
                "services": ServiceSerializer(servs.filter(category=cat),
                                              many=True).data,
            })
        return ok("OK", out)


# ──────────────────────────────────────────────────────────
# 2.  Market-level product list with history
#     /markets/<id>/products/
# ──────────────────────────────────────────────────────────
@extend_schema(tags=["Market Intelligence Products"])
class MarketProductView(generics.ListAPIView):
    serializer_class = ListingWithHistorySerializer
    permission_classes = (AllowAny,)
    pagination_class = DefaultPagination

    def get_queryset(self):
        market_id = self.kwargs["pk"]
        cat_id = self.request.query_params.get("category")

        listing_qs = (
            PriceListing.objects
            .filter(market_id=market_id, status=True)
            .select_related("product", "service",  # grab whichever exists
                            "market")
        )

        if cat_id:
            listing_qs = listing_qs.filter(
                Q(product__category_id=cat_id) | Q(service__category_id=cat_id)
            )

        # prefetch latest 90 price pts per listing
        price_qs = PriceHistory.objects.order_by("-recorded_at")
        return listing_qs.prefetch_related(
            Prefetch("history", queryset=price_qs)
        )[:90]


# ──────────────────────────────────────────────────────────
# 3.  Compare up to three markets for one product
#     /products/<id>/compare/?markets=2,7,12
# ──────────────────────────────────────────────────────────
@extend_schema(tags=["Market Intelligence Products"])
class ProductComparisonView(generics.GenericAPIView):
    serializer_class = ListingWithHistorySerializer
    permission_classes = (AllowAny,)

    def get(self, request, pk):
        market_ids = request.GET.get("markets", "")
        ids = [int(i) for i in market_ids.split(",") if i.isdigit()][:3]

        listings = (
            PriceListing.objects
            .filter(
                Q(product_id=pk) | Q(service_id=pk),  # ← stem-agnostic match
                market_id__in=ids,
                status=True
            )
            .select_related("market", "market__town",
                            "product", "service")
            .prefetch_related(
                Prefetch("history",
                         queryset=PriceHistory.objects.order_by("-recorded_at"))
            )
        )

        ser = self.get_serializer(listings, many=True)

        # stats
        summary = (
            listings[:90].values("market__name")
            .annotate(
                latest=Min("history__recorded_at"),
                min=Min("history__price"),
                max=Max("history__price"),
                avg=Avg("history__price"),
            )
        )

        return ok("Comparison", {
            "listings": ser.data,
            "stats": list(summary),
        })


@extend_schema(tags=["Market Intelligence Services"])
class ServiceComparisonView(ProductComparisonView):
    """
    Same implementation as ProductComparisonView; only the
    URL/semantic label changes.
    """

    def get(self, request, pk):
        return super().get(request, pk)


_LOCATION_SEARCH_Q = {
    "region": "listings__town__district__region_id",
    "district": "listings__town__district_id",
    "town": "listings__town_id",
    "market": "listings__market_id",
}


def _apply_location(qs, params) -> Iterable:
    """Apply ?region / ?district / ?town / ?market cascade."""
    flt = Q()
    for key, path in _LOCATION_SEARCH_Q.items():
        if val := params.get(key):
            flt &= Q(**{path: val})
    return qs.filter(flt) if flt else qs


def _apply_many_id_filter(qs, params, param_key: str, field: str) -> Iterable:
    """
    ?tags=1,4,10  →  qs.filter(tags__id__in=[1,4,10])
    """
    if raw := params.get(param_key):
        try:
            ids = [int(i) for i in raw.split(",") if i.isdigit()]
            if ids:
                qs = qs.filter(**{f"{field}__id__in": ids})
        except ValueError:
            pass
    return qs


def _prefetch_history(qs):
    """Reuse in Product *and* Service queries – grabs last 90 points."""
    price_qs = PriceHistory.objects.order_by("-recorded_at")[:90]
    return qs.prefetch_related(
        Prefetch("listings__history", queryset=price_qs)
    )


@extend_schema(tags=["Market Intelligence Search"])
class GlobalSearchView(generics.GenericAPIView):
    """
    GET /search/?q=rice&category=3&tags=1,2&region=7&type=product …

    **Query params**

    | param        | notes                                             |
    |--------------|---------------------------------------------------|
    | `q`          | free-text, `icontains` on name / description      |
    | `type`       | `product`, `service`, *anything/omitted → both*   |
    | `category`   | id                                               |
    | `tags`       | comma-separated tag ids                          |
    | location     | `region`, `district`, `town`, `market` (cascades)|
    | `limit`      | max rows per stem (default = 30)                 |

    **JSON response**

    ```json
    {
      "products": [ …ProductSerializer… ],
      "services": [ …ServiceSerializer… ]
    }
    ```
    """
    permission_classes = (AllowAny,)
    pagination_class = None  # one JSON blob

    # --------------------------------------------------------------
    def _base_qs(self, model, text_fields: Tuple[str, ...], params):
        qs = (
            model.objects
            .select_related("category")
            .prefetch_related("tags", "images", "listings__town",
                              "listings__market")
        )
        # full-text -------------------------------------------------
        if q := params.get("q", "").strip():
            txt = Q()
            for f in text_fields:
                txt |= Q(**{f"{f}__icontains": q})
            qs = qs.filter(txt)

        # category / tags ------------------------------------------
        if cat := params.get("category"):
            qs = qs.filter(category_id=cat)

        qs = _apply_many_id_filter(qs, params, "tags", "tags")

        # location cascade -----------------------------------------
        qs = _apply_location(qs, params)

        return _prefetch_history(qs).distinct()

    # --------------------------------------------------------------
    def get(self, request, *args, **kwargs):
        params = request.query_params
        stem_type = params.get("type", "").lower()
        limit = int(params.get("limit", 30))

        data = {"products": [], "services": []}

        # ---- PRODUCTS -------------------------------------------
        if stem_type in ("", "product", "products"):
            prod_qs = self._base_qs(
                Product,
                ("name", "description"),
                params
            )[:limit]
            data["products"] = ProductSerializer(
                prod_qs, many=True, context=self.get_serializer_context()
            ).data

        # ---- SERVICES -------------------------------------------
        if stem_type in ("", "service", "services"):
            srv_qs = self._base_qs(
                Service,
                ("name", "description"),  # NB: Service.name is “name” field
                params
            )[:limit]
            data["services"] = ServiceSerializer(
                srv_qs, many=True, context=self.get_serializer_context()
            ).data

        return ok("search results", data)


# ------------------------------------------------------------------
# 2️⃣  AUTOCOMPLETE VIEW
# ------------------------------------------------------------------
@extend_schema(tags=["Market Intelligence Search"])
class AutoCompleteView(generics.ListAPIView):
    """
    GET /search/autocomplete/?q=ba&limit=10

    Returns quick *name* suggestions for type-ahead UIs:

    ```json
    {
      "products": ["Basmati Rice", "Bar Soap", …],
      "services": ["Bakery Delivery", …]
    }
    ```
    """
    permission_classes = (AllowAny,)
    pagination_class = None  # single JSON dict

    def list(self, request, *args, **kwargs):
        q = request.query_params.get("q", "").strip()
        limit = int(request.query_params.get("limit", 10))

        def sugg(model, field):
            if not q:
                return []
            return list(
                model.objects
                .filter(**{f"{field}__icontains": q})
                .values_list(field, flat=True)
                .order_by(field)[:limit]
            )

        return ok("OK", {
            "products": sugg(Product, "name"),
            "services": sugg(Service, "name"),
        })


# ────────────────────────────────────────────────
#  Region / District / Town
# ────────────────────────────────────────────────
@extend_schema(tags=["Market Intelligence Search"])
class RegionSearchView(AutocompleteMixin):
    base_qs = Region.objects.all()
    serializer_class = RegionSerializer
    search_fields = ("name",)


@extend_schema(tags=["Market Intelligence Search"])
class DistrictSearchView(AutocompleteMixin):
    base_qs = (District.objects
               .select_related("region"))
    serializer_class = DistrictSerializer
    search_fields = ("name", "region__name")


@extend_schema(tags=["Market Intelligence Search"])
class TownSearchView(AutocompleteMixin):
    base_qs = (Town.objects
               .select_related("district", "district__region"))
    serializer_class = TownSerializer
    search_fields = ("name",
                     "district__name",
                     "district__region__name")
