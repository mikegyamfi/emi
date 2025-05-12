# market_intel/serializers.py
from rest_framework import serializers
import pandas as pd

from core.utils import date_breakdown  # unchanged helper
from .models import (  # ONLY live models
    Region, District, Town, Market,
    Category, Tag,
    Product, Service, ProductServiceImage,
    PriceListing, PriceHistory
)


# ──────────────────────────────────────────
# 1.  LOCATION  (unchanged)
# ──────────────────────────────────────────
class RegionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Region
        fields = ("id", "name")


class DistrictSerializer(serializers.ModelSerializer):
    region = RegionSerializer(read_only=True)
    region_id = serializers.PrimaryKeyRelatedField(
        source="region", queryset=Region.objects.all(), write_only=True
    )

    class Meta:
        model = District
        fields = ("id", "name", "region", "region_id")


class TownSerializer(serializers.ModelSerializer):
    district = DistrictSerializer(read_only=True)
    district_id = serializers.PrimaryKeyRelatedField(
        source="district", queryset=District.objects.all(), write_only=True
    )

    class Meta:
        model = Town
        fields = ("id", "name", "district", "district_id")


class MarketSerializer(serializers.ModelSerializer):
    town = TownSerializer(read_only=True)
    town_id = serializers.PrimaryKeyRelatedField(
        source="town", queryset=Town.objects.all(), write_only=True
    )

    class Meta:
        model = Market
        fields = ("id", "name", "town", "town_id")


# ──────────────────────────────────────────
# 2.  CATEGORY  /  TAGS
# ──────────────────────────────────────────
class ProductBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ("id", "name")


class ServiceBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = ("id", "name")


class CategorySerializer(serializers.ModelSerializer):
    products_and_services = serializers.SerializerMethodField()
    children = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ("id", "name", "image", "parent", "products_and_services", "children")

    # direct children
    def get_products_and_services(self, obj):
        return {
            "products": ProductBriefSerializer(Product.objects.filter(category=obj), many=True).data,
            "services": ServiceBriefSerializer(Service.objects.filter(category=obj), many=True).data,
        }

    # recursive
    def get_children(self, obj):
        return CategorySerializer(obj.category_set.all().order_by("name"), many=True).data


class CategoryDetailSerializer(CategorySerializer):
    """Adds a flattened `all_products` key (products + services in this node AND every descendant)."""
    all_products = serializers.SerializerMethodField()

    class Meta(CategorySerializer.Meta):
        fields = CategorySerializer.Meta.fields + ("all_products",)

    def get_all_products(self, obj):
        leaf_ids = []

        def crawl(node):
            leaf_ids.append(node.id)
            for ch in node.category_set.all():
                crawl(ch)

        crawl(obj)

        prods = Product.objects.filter(category_id__in=leaf_ids)
        servs = Service.objects.filter(category_id__in=leaf_ids)
        return {
            "products": ProductBriefSerializer(prods, many=True).data,
            "services": ServiceBriefSerializer(servs, many=True).data,
        }


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ("id", "name")


# ──────────────────────────────────────────
# 3.  COMMON  MINI  SERIALISERS
# ──────────────────────────────────────────
class TownMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Town
        fields = ("id", "name")


class MarketMiniSerializer(serializers.ModelSerializer):
    town = TownMiniSerializer(read_only=True)

    class Meta:
        model = Market
        fields = ("id", "name", "town")


class StemMini(serializers.ModelSerializer):
    """Tiny helper for Product & Service one-liners."""
    category = serializers.CharField(source="category.name")
    object_type = serializers.SerializerMethodField()

    class Meta:
        fields = ("id", "name", "category", "object_type")

    def get_object_type(self, obj):
        return "Product" if isinstance(obj, Product) else "Service"


class ProductMiniSerializer(StemMini):
    class Meta(StemMini.Meta):
        model = Product


class ServiceMiniSerializer(StemMini):
    class Meta(StemMini.Meta):
        model = Service


# ──────────────────────────────────────────
# 4.  PRICE-LISTING  OVERVIEW
# ──────────────────────────────────────────
class ListingOverviewSerializer(serializers.ModelSerializer):
    kind = serializers.CharField(source="kind", read_only=True)
    product = ProductMiniSerializer(read_only=True)
    service = ServiceMiniSerializer(read_only=True)
    town = TownMiniSerializer(read_only=True)
    market = MarketMiniSerializer(read_only=True)

    class Meta:
        model = PriceListing
        fields = (
            "id", "kind", "product", "service",
            "town", "market",
            "price", "currency",
            "average_price", "lowest_price", "highest_price",
            "status", "updated_at"
        )


# ──────────────────────────────────────────
# 5.  PRODUCT  &  SERVICE  DETAIL
# ──────────────────────────────────────────
class ImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductServiceImage
        fields = ("id", "image", "feature_image", "product", "service")
        read_only_fields = ("id",)


def _listing_qs_for_stem(stem):
    """
    Handy helper: returns active listings for a given Product *or* Service
    including prefetch of last 90 history rows (for graphs).
    """
    return (
        stem.listings
        .filter(status=True)
        .select_related("town", "market", "market__town")
        .prefetch_related(
            "history",
        )
    )


def _listing_qs_for(obj):
    return (
        obj.listings
        .filter(status=True)
        .select_related("town", "market")
        .prefetch_related("history")
    )


class BaseStemSerializer(serializers.ModelSerializer):
    listings = serializers.SerializerMethodField()
    price_summary = serializers.SerializerMethodField()
    location_curves = serializers.SerializerMethodField()
    object_type = serializers.SerializerMethodField()

    class Meta:
        abstract = True  # not a real DRF flag, just to signal intent

    def get_listings(self, obj):
        return ListingOverviewSerializer(
            _listing_qs_for(obj), many=True, context=self.context
        ).data

    def get_price_summary(self, obj):
        rows = [(l.id, l.price, l.currency) for l in obj.listings.all()]
        if not rows:
            return None
        lo = min(rows, key=lambda x: x[1])
        hi = max(rows, key=lambda x: x[1])
        return {
            "cheapest": {"listing_id": lo[0], "price": float(lo[1]), "currency": lo[2]},
            "priciest": {"listing_id": hi[0], "price": float(hi[1]), "currency": hi[2]},
            "count": len(rows),
        }

    def get_location_curves(self, obj):
        data = {}
        for l in _listing_qs_for(obj):
            pts = l.history.order_by("-recorded_at")[:90].values("price", "recorded_at")
            if pts:
                data[str(l.id)] = [
                    {"price": float(p["price"]), "at": p["recorded_at"]} for p in pts
                ]
        return data or None

    def get_object_type(self, obj):
        # overridden in subclasses to "Product" or "Service"
        raise NotImplementedError


class ProductSerializer(BaseStemSerializer):
    category = CategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), source="category", write_only=True
    )
    tags = TagSerializer(many=True, read_only=True)
    tag_ids = serializers.PrimaryKeyRelatedField(
        many=True, source="tags", queryset=Tag.objects.all(), write_only=True
    )
    images = ImageSerializer(many=True, write_only=True, required=False)

    class Meta:
        model = Product
        fields = (
            "id", "name", "description", "sku", "object_type",
            "category", "category_id",
            "tags", "tag_ids", "images",
            "listings", "price_summary", "location_curves",
        )

    def get_object_type(self, _):
        return "Product"


class ServiceSerializer(BaseStemSerializer):
    category = CategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), source="category", write_only=True
    )
    tags = TagSerializer(many=True, read_only=True)
    tag_ids = serializers.PrimaryKeyRelatedField(
        many=True, source="tags", queryset=Tag.objects.all(), write_only=True
    )
    images = ImageSerializer(many=True, write_only=True, required=False)

    class Meta:
        model = Service
        fields = (
            "id", "name", "description", "sku", "object_type",
            "category", "category_id",
            "tags", "tag_ids", "images",
            "listings", "price_summary", "location_curves",
        )

    def get_object_type(self, _):
        return "Service"


# ──────────────────────────────────────────
# 6.  LISTING  CRUD  &  ANALYTICS
# ──────────────────────────────────────────
class ListingSerializer(serializers.ModelSerializer):
    product = ProductMiniSerializer(read_only=True)
    service = ServiceMiniSerializer(read_only=True)
    town = TownMiniSerializer(read_only=True)
    market = MarketMiniSerializer(read_only=True)

    # write-only PKs
    product_id = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all(),
                                                    write_only=True, allow_null=True, source="product")
    service_id = serializers.PrimaryKeyRelatedField(queryset=Service.objects.all(),
                                                    write_only=True, allow_null=True, source="service")
    town_id = serializers.PrimaryKeyRelatedField(queryset=Town.objects.all(),
                                                 write_only=True, allow_null=True, source="town")
    market_id = serializers.PrimaryKeyRelatedField(queryset=Market.objects.all(),
                                                   write_only=True, allow_null=True, source="market")

    kind = serializers.CharField(read_only=True)

    class Meta:
        model = PriceListing
        fields = (
            "id", "kind",
            "product", "service",
            "town", "market",
            "price", "currency", "note", "status",
            # write faces
            "product_id", "service_id",
            "town_id", "market_id",
        )

    # --- business rules -----------------------
    def validate(self, attrs):
        prod = attrs.get("product") or getattr(self.instance, "product", None)
        serv = attrs.get("service") or getattr(self.instance, "service", None)
        if bool(prod) == bool(serv):
            raise serializers.ValidationError("Exactly one of product_id OR service_id is required.")

        town = attrs.get("town") or getattr(self.instance, "town", None)
        market = attrs.get("market") or getattr(self.instance, "market", None)
        if not (town or market):
            raise serializers.ValidationError("Either town_id or market_id must be supplied.")
        return attrs


class PricePointSerializer(serializers.ModelSerializer):
    date_info = serializers.SerializerMethodField()

    class Meta:
        model = PriceHistory
        fields = ("price", "currency", "recorded_at", "date_info")

    def get_date_info(self, obj):
        return date_breakdown(obj.recorded_at)


class ListingAnalyticsSerializer(ListingSerializer):
    """
    Heavy detail view – attaches price history and statistical curves.
    Helper methods (`_history_df`, etc.) are unchanged from earlier patch.
    """
    price_history = serializers.SerializerMethodField()
    quarterly_curve = serializers.SerializerMethodField()
    monthly_curve = serializers.SerializerMethodField()
    top_quarter_overall = serializers.SerializerMethodField()
    top_quarter_recent = serializers.SerializerMethodField()
    high_jump_months = serializers.SerializerMethodField()
    high_drop_months = serializers.SerializerMethodField()
    volatile_months = serializers.SerializerMethodField()
    stable_quarters = serializers.SerializerMethodField()

    class Meta(ListingSerializer.Meta):
        fields = ListingSerializer.Meta.fields + (
            "price_history", "quarterly_curve", "monthly_curve",
            "top_quarter_overall", "top_quarter_recent",
            "high_jump_months", "high_drop_months",
            "volatile_months", "stable_quarters",
        )

    # ----------------- helpers -----------------
    def _history_df(self, obj):
        df = pd.DataFrame(
            obj.history.order_by("recorded_at").values("price", "recorded_at")
        )
        if df.empty:
            return df
        ts = pd.to_datetime(df["recorded_at"])
        df["year"] = ts.dt.year
        df["month"] = ts.dt.month_name().str[:3]  # “Jan”, “Feb”, …
        df["quarter"] = ts.dt.to_period("Q").astype(str)  # “2025Q1”
        return df

    # ---------- history raw ----------
    def get_price_history(self, obj):
        return PricePointSerializer(obj.history.order_by("-recorded_at")[:90], many=True).data

    # ---------- aggregated curves ----
    def get_quarterly_curve(self, obj):
        df = self._history_df(obj)
        if df.empty: return []
        tbl = (df.groupby("quarter")["price"]
               .mean()
               .reset_index()
               .sort_values("quarter"))
        return [{"label": r.quarter, "avg_price": float(round(r.price, 2))}
                for r in tbl.itertuples()]

    def get_monthly_curve(self, obj):
        df = self._history_df(obj)
        if df.empty: return []
        tbl = (df.groupby("month")["price"]
               .mean()
               .reindex([
            "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
        ]).dropna())
        return [{"label": m, "avg_price": float(round(v, 2))} for m, v in tbl.items()]

    # ---------- best / recent quarters --------------
    def get_top_quarter_overall(self, obj):
        df = self._history_df(obj)
        if df.empty: return None
        best = (df.groupby("quarter")["price"].mean()
                .idxmin())  # lowest average price
        return best

    def get_top_quarter_recent(self, obj):
        df = self._history_df(obj)
        if df.empty: return None
        recent = df[df["year"] == df["year"].max()]
        if recent.empty: return None
        best = (recent.groupby("quarter")["price"].mean().idxmin())
        return best

    # ---------- jumps / drops / volatility ----------
    def _month_step_df(self, obj):
        df = self._history_df(obj)
        if df.empty: return pd.DataFrame()
        m = (df.groupby(["year", "month"])["price"].mean()
             .reset_index()
             .sort_values(["year", "month"]))
        m["prev"] = m["price"].shift(1)
        m["delta_pct"] = ((m["price"] - m["prev"]) / m["prev"]) * 100
        return m.dropna()

    def get_high_jump_months(self, obj, top_n=5):
        df = self._month_step_df(obj)
        if df.empty: return []
        best = df.nlargest(top_n, "delta_pct")
        return [{"label": r.month, "delta_pct": float(round(r.delta_pct, 1))} for r in best.itertuples()]

    def get_high_drop_months(self, obj, top_n=5):
        df = self._month_step_df(obj)
        if df.empty: return []
        worst = df.nsmallest(top_n, "delta_pct")
        return [{"label": r.month, "delta_pct": float(round(r.delta_pct, 1))} for r in worst.itertuples()]

    def get_volatile_months(self, obj, top_n=5):
        df = self._history_df(obj)
        if df.empty: return []
        vol = (df.groupby("month")["price"]
               .std()
               .nlargest(top_n))
        return [{"label": m, "std": float(round(v, 2))} for m, v in vol.items()]

    def get_stable_quarters(self, obj, top_n=3):
        df = self._history_df(obj)
        if df.empty: return []
        cv = (df.groupby("quarter")["price"]
              .agg(["mean", "std"])
              .assign(cv=lambda d: d["std"] / d["mean"])
              .nsmallest(top_n, "cv"))
        return [{"label": idx, "cv": float(round(row.cv, 3))} for idx, row in cv.iterrows()]


class ListingWithHistorySerializer(ListingSerializer):
    """
    Light-weight listing used by list-style endpoints:
    • all base fields from ListingSerializer
    • plus the last 90 price points (no heavy analytics)
    """
    price_history = serializers.SerializerMethodField()

    class Meta(ListingSerializer.Meta):
        fields = ListingSerializer.Meta.fields + ("price_history",)

    # ---- helpers --------------------------------------------------
    def get_price_history(self, obj):
        qs = (
            obj.history
            .order_by("-recorded_at")
            .values("price", "currency", "recorded_at")[:90]
        )
        return [
            {
                "price": row["price"],
                "currency": row["currency"],
                **date_breakdown(row["recorded_at"]),
            }
            for row in qs
        ]
