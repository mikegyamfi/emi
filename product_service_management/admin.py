from django.contrib import admin
from django.utils.html import format_html

from .models import (
    SKU, Category,
    ProductCondition, ProductServiceStatus,
    Tag, Attributes,
    ServicePricingChoices,
    GenericProduct, ProductImage, VendorProduct, VendorProductImage,
    GenericService, ServiceImage, VendorService, VendorServiceImage,
)


# ────────────────────────────────────────────────────────────
# 1.  LOW‑LEVEL VOCABULARY TABLES
# ────────────────────────────────────────────────────────────
@admin.register(SKU)
class SKUAdmin(admin.ModelAdmin):
    list_display   = ("name", "description")
    search_fields  = ("name", "description")
    ordering       = ("name",)


@admin.register(ProductCondition)
class ProductConditionAdmin(admin.ModelAdmin):
    list_display  = ("name", "description")
    search_fields = ("name",)
    ordering      = ("name",)


@admin.register(ProductServiceStatus)
class ProductServiceStatusAdmin(admin.ModelAdmin):
    list_display  = ("name", "description")
    search_fields = ("name",)
    ordering      = ("name",)


@admin.register(ServicePricingChoices)
class ServicePricingChoiceAdmin(admin.ModelAdmin):
    list_display  = ("name", "description")
    search_fields = ("name",)
    ordering      = ("name",)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display  = ("name",)
    search_fields = ("name",)
    ordering      = ("name",)


@admin.register(Attributes)
class AttributeAdmin(admin.ModelAdmin):
    list_display  = ("name", "value", "description")
    search_fields = ("name", "value")
    ordering      = ("name",)


# ────────────────────────────────────────────────────────────
# 2.  CATEGORY TREE
# ────────────────────────────────────────────────────────────
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display   = (
        "name", "parent", "type", "is_active",
        "children_count", "preview_icon"
    )
    list_filter    = ("type", "is_active", "parent")
    search_fields  = ("name", "description")
    readonly_fields= ("preview_icon",)
    ordering       = ("parent__name", "name")

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("children")

    @admin.display(description="# children")
    def children_count(self, obj):
        return obj.children.count()

    @admin.display(description="Icon")
    def preview_icon(self, obj):
        if obj.icon:
            return format_html("<img src='{}' style='height:32px' />", obj.icon.url)
        return "—"


# ────────────────────────────────────────────────────────────
# 3.  GENERIC PRODUCT & IMAGES
# ────────────────────────────────────────────────────────────
class ProductImageInline(admin.TabularInline):
    model           = ProductImage
    extra           = 1
    fields          = ("image", "is_primary", "created", "preview")
    readonly_fields = ("created", "preview")

    @admin.display(description="Preview")
    def preview(self, obj):
        if obj.image:
            return format_html("<img src='{}' style='height:48px' />", obj.image.url)
        return "—"


@admin.register(GenericProduct)
class GenericProductAdmin(admin.ModelAdmin):
    list_display      = (
        "name", "slug", "category",
        "featured", "is_active", "created_at"
    )
    list_filter       = ("is_active", "featured", "category")
    search_fields     = ("name", "description", "sku__name", "tags__name")
    autocomplete_fields = (
        "category", "sku", "tags", "attributes"
    )
    inlines           = (ProductImageInline,)
    readonly_fields   = ("created_at", "last_updated_at")
    date_hierarchy    = "created_at"

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("category", "sku")
            .prefetch_related("tags", "attributes")
        )


# ────────────────────────────────────────────────────────────
# 4.  VENDOR PRODUCT & IMAGES
# ────────────────────────────────────────────────────────────
class VendorProductImageInline(admin.TabularInline):
    model           = VendorProductImage
    extra           = 1
    fields          = ("image", "is_primary", "created", "preview")
    readonly_fields = ("created", "preview")

    @admin.display(description="Preview")
    def preview(self, obj):
        if obj.image:
            return format_html("<img src='{}' style='height:48px' />", obj.image.url)
        return "—"


@admin.register(VendorProduct)
class VendorProductAdmin(admin.ModelAdmin):
    list_display      = (
        "listing_id", "product", "seller", "business",
        "price", "quantity", "condition", "status",
        "featured", "is_active", "created_at"
    )
    list_filter       = (
        "is_active", "featured", "product",
        "seller", "business", "condition", "status", "created_at"
    )
    search_fields     = (
        "product__name",
        "seller__phone_number",
        "seller__email"
    )
    autocomplete_fields = (
        "product", "seller", "business", "condition", "status"
    )
    inlines           = (VendorProductImageInline,)
    readonly_fields   = ("created_at", "last_updated_at")
    date_hierarchy    = "created_at"

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("product", "seller", "business", "condition", "status")
        )


# ────────────────────────────────────────────────────────────
# 5.  GENERIC SERVICE & IMAGES
# ────────────────────────────────────────────────────────────
class ServiceImageInline(admin.TabularInline):
    model           = ServiceImage
    extra           = 1
    fields          = ("image", "is_primary", "created", "preview")
    readonly_fields = ("created", "preview")

    @admin.display(description="Preview")
    def preview(self, obj):
        if obj.image:
            return format_html("<img src='{}' style='height:48px' />", obj.image.url)
        return "—"


@admin.register(GenericService)
class GenericServiceAdmin(admin.ModelAdmin):
    list_display      = (
        "title", "slug", "category",
        "is_active", "created_at"
    )
    list_filter       = ("is_active", "category", "created_at")
    search_fields     = ("title", "description")
    autocomplete_fields = ("category",)
    inlines           = (ServiceImageInline,)
    readonly_fields   = ("created_at", "updated_at")
    date_hierarchy    = "created_at"

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("category")
        )


# ────────────────────────────────────────────────────────────
# 6.  VENDOR SERVICE & IMAGES
# ────────────────────────────────────────────────────────────
class VendorServiceImageInline(admin.TabularInline):
    model           = VendorServiceImage
    extra           = 1
    fields          = ("image", "is_primary", "created", "preview")
    readonly_fields = ("created", "preview")

    @admin.display(description="Preview")
    def preview(self, obj):
        if obj.image:
            return format_html("<img src='{}' style='height:48px' />", obj.image.url)
        return "—"


@admin.register(VendorService)
class VendorServiceAdmin(admin.ModelAdmin):
    list_display      = (
        "listing_id", "service", "provider", "business",
        "pricing_type", "price", "is_remote", "featured",
        "is_active", "created_at", "region_list",
        "district_list", "town_list",
    )
    list_filter       = (
        "is_active", "is_remote", "pricing_type",
        "service", "regions", "districts", "towns",
        "created_at",
    )
    search_fields     = (
        "service__title",
        "provider__phone_number",
        "provider__email",
    )
    autocomplete_fields = (
        "service", "provider", "business",
        "pricing_type", "regions", "districts", "towns"
    )
    inlines           = (VendorServiceImageInline,)
    readonly_fields   = ("created_at", "updated_at")
    date_hierarchy    = "created_at"

    @admin.display(description="Regions")
    def region_list(self, obj):
        return ", ".join(obj.regions.values_list("name", flat=True))

    @admin.display(description="Districts")
    def district_list(self, obj):
        return ", ".join(obj.districts.values_list("name", flat=True))

    @admin.display(description="Towns")
    def town_list(self, obj):
        return ", ".join(obj.towns.values_list("name", flat=True))

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("service", "provider", "business", "pricing_type")
            .prefetch_related("regions", "districts", "towns")
        )
