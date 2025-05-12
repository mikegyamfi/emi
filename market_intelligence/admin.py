# market_intelligence/admin.py
from django.contrib import admin
from django.utils.html import format_html

from . import models


# ────────────────────────────────────────────────────────────
# 1.  LOCATION HIERARCHY
# ────────────────────────────────────────────────────────────
@admin.register(models.Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ("name", "district_count")
    search_fields = ("name",)

    def district_count(self, obj):
        return obj.district_set.count()

    district_count.short_description = "Districts"


@admin.register(models.District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = ("name", "region", "town_count")
    list_filter = ("region",)
    search_fields = ("name", "region__name")

    def town_count(self, obj):
        return obj.town_set.count()

    town_count.short_description = "Towns"


@admin.register(models.Town)
class TownAdmin(admin.ModelAdmin):
    list_display = ("name", "district", "region")
    list_filter = ("district__region", "district")
    search_fields = ("name", "district__name", "district__region__name")

    def region(self, obj):
        return obj.district.region

    region.short_description = "Region"


@admin.register(models.Market)
class MarketAdmin(admin.ModelAdmin):
    list_display = ("name", "town", "district", "region")
    list_filter = ("town__district__region", "town__district")
    search_fields = ("name", "town__name",
                     "town__district__name", "town__district__region__name")

    def district(self, obj):
        return obj.town.district

    district.short_description = "District"

    def region(self, obj):
        return obj.town.district.region

    region.short_description = "Region"


# ────────────────────────────────────────────────────────────
# 2.  TAXONOMY
# ────────────────────────────────────────────────────────────
@admin.register(models.Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent")
    list_filter = ("parent",)
    search_fields = ("name",)


@admin.register(models.Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


# ────────────────────────────────────────────────────────────
# 3.  PRODUCT  &  SERVICE
# ────────────────────────────────────────────────────────────
class ProductImageInline(admin.TabularInline):
    model = models.ProductServiceImage
    fk_name = "product"  # tell Django which FK to use
    extra = 1
    fields = ("image", "feature_image", "status")


@admin.register(models.Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "category", "tag_list")
    list_filter = ("category",)
    search_fields = ("name", "sku", "description")
    inlines = (ProductImageInline,)

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("tags")

    def tag_list(self, obj):
        return ", ".join(obj.tags.values_list("name", flat=True))

    tag_list.short_description = "Tags"


class ServiceImageInline(admin.TabularInline):
    model = models.ProductServiceImage
    fk_name = "service"
    extra = 1
    fields = ("image", "feature_image", "status")


@admin.register(models.Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "category", "tag_list")
    list_filter = ("category",)
    search_fields = ("name", "sku", "description")
    inlines = (ServiceImageInline,)

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("tags")

    def tag_list(self, obj):
        return ", ".join(obj.tags.values_list("name", flat=True))

    tag_list.short_description = "Tags"


# ────────────────────────────────────────────────────────────
# 4.  PRICE-LISTING  (current price + aggregates)
# ────────────────────────────────────────────────────────────
class PriceHistoryInline(admin.TabularInline):
    """Read-only log of snapshots for one listing."""
    model = models.PriceHistory
    extra = 0
    fields = ("price", "currency", "recorded_at")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, *args, **kwargs):
        return False


@admin.register(models.PriceListing)
class PriceListingAdmin(admin.ModelAdmin):
    list_display = (
        "stem", "kind", "price", "average_price",
        "lowest_price", "highest_price",
        "market", "town", "status", "updated_at",
    )
    list_filter = (
        "status",
        "market__town__district__region",
        "product__category", "service__category",
    )
    search_fields = (
        "product__name", "service__name",
        "market__name", "town__name",
    )
    autocomplete_fields = ("product", "service", "town", "market")
    inlines = (PriceHistoryInline,)

    def stem(self, obj):
        return obj.product or obj.service

    stem.short_description = "Product / Service"

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                "product", "service",
                "market", "market__town",
                "town",
            )
        )


# ────────────────────────────────────────────────────────────
# 5.  PRICE HISTORY (stand-alone view, read-only)
# ────────────────────────────────────────────────────────────
@admin.register(models.PriceHistory)
class PriceHistoryAdmin(admin.ModelAdmin):
    list_display = ("listing", "price", "currency", "recorded_at")
    list_filter = ("currency", "listing__market__town__district__region")
    search_fields = ("listing__product__name",
                     "listing__service__name",
                     "listing__market__name")
    readonly_fields = ("listing", "price", "currency", "recorded_at")
    date_hierarchy = "recorded_at"

    def has_add_permission(self, *args, **kwargs):
        return False

    def has_change_permission(self, *args, **kwargs):
        return False
