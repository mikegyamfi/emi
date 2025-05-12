from django.contrib import admin

# Register your models here.
# product_service_management/admin.py
from django.contrib import admin
from django.utils.html import format_html, format_html_join

from . import models
from .models import ProductImage, ServiceImage


# ────────────────────────────────────────────────────────────
# 1.  LOW-LEVEL “VOCABULARY” TABLES
# ────────────────────────────────────────────────────────────
@admin.register(models.SKU)
class SKUAdmin(admin.ModelAdmin):
    list_display = ("name", "description")
    search_fields = ("name", "description")
    ordering = ("name",)


@admin.register(models.ProductCondition)
class ProductConditionAdmin(admin.ModelAdmin):
    list_display = ("name", "description")
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(models.ProductServiceStatus)
class ProductServiceStatusAdmin(admin.ModelAdmin):
    list_display = ("name", "description")
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(models.ServicePricingChoices)
class ServicePricingChoiceAdmin(admin.ModelAdmin):
    list_display = ("name", "description")
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(models.Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(models.Attributes)
class AttributeAdmin(admin.ModelAdmin):
    list_display = ("name", "value", "description")
    search_fields = ("name", "value")
    ordering = ("name",)


# ────────────────────────────────────────────────────────────
# 2.  CATEGORY TREE
# ────────────────────────────────────────────────────────────
@admin.register(models.Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = (
        "name", "parent", "is_active",
        "children_count", "product_count", "service_count",
        "preview_icon",
    )
    list_filter = ("is_active", "parent")
    search_fields = ("name", "description")
    readonly_fields = ("preview_icon",)
    ordering = ("parent__name", "name")

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .prefetch_related("children", "products", "services")
        )

    # --- helper columns ------------------------------------
    @admin.display(description="# children")
    def children_count(self, obj):
        return obj.children.count()

    @admin.display(description="# products")
    def product_count(self, obj):
        return obj.products.count()

    @admin.display(description="# services")
    def service_count(self, obj):
        return obj.services.count()

    @admin.display(description="Icon")
    def preview_icon(self, obj):
        if obj.icon:
            return format_html("<img src='{}' style='height:32px' />", obj.icon.url)
        return "—"


# ────────────────────────────────────────────────────────────
# 3.  PRODUCT & IMAGES
# ────────────────────────────────────────────────────────────
class ProductImageInline(admin.TabularInline):
    model = models.ProductImage
    extra = 1
    fields = ("image", "is_primary", "created")
    readonly_fields = ("created",)

    @admin.display(description="Preview")
    def image_tag(self, obj):
        if obj.image:
            return format_html("<img src='{}' style='height:48px' />", obj.image.url)
        return "—"


@admin.register(models.Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name", "seller", "business",
        "category", "price", "quantity",
        "condition", "status", "featured",
        "is_active", "created_at",
    )
    list_filter = (
        "is_active", "featured", "category",
        "condition", "status",
        "created_at",
    )
    search_fields = ("name", "description", "sku__name", "tags__name")
    autocomplete_fields = ("seller", "business", "category", "sku", "tags", "attributes")
    inlines = (ProductImageInline,)
    readonly_fields = ("created_at", "last_updated_at")
    date_hierarchy = "created_at"

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                "seller", "business",
                "category", "condition", "status", "sku"
            )
            .prefetch_related("tags")
        )


# ────────────────────────────────────────────────────────────
# 4.  SERVICE
# ────────────────────────────────────────────────────────────
@admin.register(models.Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = (
        "title", "provider", "business",
        "category", "pricing_type", "price",
        "is_remote", "is_active", "created_at",
        "region_list", "district_list", "town_list",
    )
    list_filter = (
        "is_active", "is_remote", "pricing_type",
        "category", "regions", "district", "town",
        "created_at",
    )
    search_fields = ("title", "description", "tags__name")
    autocomplete_fields = ("provider", "business", "category", "tags",
                           "regions", "district", "town")
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "created_at"

    # -------- helper columns -------------------------------
    @admin.display(description="Regions")
    def region_list(self, obj):
        return ", ".join(obj.regions.values_list("name", flat=True))

    @admin.display(description="Districts")
    def district_list(self, obj):
        return ", ".join(obj.district.values_list("name", flat=True))

    @admin.display(description="Towns")
    def town_list(self, obj):
        return ", ".join(obj.town.values_list("name", flat=True))

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                "provider", "business", "category", "pricing_type"
            )
            .prefetch_related("regions", "district", "town", "tags")
        )


admin.site.register(ProductImage)
admin.site.register(ServiceImage)


