# product_service/serializers.py
#
# Compatible with models declared in product_service/models.py
# (the snippet you sent on 26 Apr 2025).
# -----------------------------------------------------------------
from django.contrib.contenttypes.models import ContentType
from django.db.models import Avg, Count
from rest_framework import serializers, generics
from django.db import transaction
from PIL import Image

from account.models import CustomUser, VendorProfile
from account.serializers import VendorProfileSerializer
from business.models import Business
from business.serializers import BusinessBriefSerializer
from core.response import ok
from feedback.models import Feedback
from feedback.serializers import FeedbackPublicSerializer
from .models import (
    Category, SKU,
    Tag, Attributes,
    ProductCondition, ProductServiceStatus,
    Product, ProductImage,
    Service, ServicePricingChoices,
    Region, District, Town, ServiceImage,
)


# ───────────────────────────────────────────────────────────────
# 0.  Small helpers – used in many places
# ───────────────────────────────────────────────────────────────
class _ImageURLMixin:
    """Return an absolute <scheme>//<host>/… URL for ImageField assets."""

    def _abs(self, request, image_field):
        if not image_field:
            return None
        url = image_field.url
        return request.build_absolute_uri(url) if request else url


# ---------- Location mini serialisers --------------------------
class RegionMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Region
        fields = ("id", "name")


class DistrictMiniSerializer(serializers.ModelSerializer):
    region = RegionMiniSerializer(read_only=True)

    class Meta:
        model = District
        fields = ("id", "name", "region")


class TownMiniSerializer(serializers.ModelSerializer):
    district = DistrictMiniSerializer(read_only=True)

    class Meta:
        model = Town
        fields = ("id", "name", "district")


class CategoryMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "name", "type")


class SKUSerializer(serializers.ModelSerializer):
    creator = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = SKU
        fields = ("id", "name", "description", "creator")
        read_only_fields = ("id", "creator")


class SKUMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = SKU
        fields = ("id", "name")


class ConditionMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductCondition
        fields = ("id", "name", "description")


class StatusMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductServiceStatus
        fields = ("id", "name", "description")


# ---------- Tag & Attribute ------------------------------------
class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ("id", "name")


class ServicePricingChoiceMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServicePricingChoices
        fields = ("id", "name")


class AttributeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Attributes
        fields = ("id", "name", "value", "description")


# ───────────────────────────────────────────────────────────────
# 1.  CATEGORIES  – full tree, unlimited depth
# ───────────────────────────────────────────────────────────────
class CategoryTreeSerializer(_ImageURLMixin, serializers.ModelSerializer):
    children = serializers.SerializerMethodField()
    icon_url = serializers.SerializerMethodField()
    sku_list = serializers.StringRelatedField(source="available_sku", many=True)

    class Meta:
        model = Category
        fields = (
            "id", "name", "type", "description",
            "icon_url", "is_active",
            "sku_list", "children",
        )

    def get_children(self, obj):
        qs = obj.children.filter(is_active=True)
        return CategoryTreeSerializer(qs, many=True, context=self.context).data

    def get_icon_url(self, obj):
        request = self.context.get("request")
        return self._abs(request, obj.icon)


class CategoryDetailSerializer(CategoryTreeSerializer):
    has_children = serializers.SerializerMethodField()
    attached_to = serializers.SerializerMethodField()
    parents = serializers.SerializerMethodField()

    class Meta(CategoryTreeSerializer.Meta):
        fields = CategoryTreeSerializer.Meta.fields + (
            "has_children", "attached_to", "parents"
        )

    def get_has_children(self, obj) -> bool:
        return obj.children.filter(is_active=True, type=obj.type).exists()

    def get_attached_to(self, obj) -> str:
        prod = obj.products.exists()
        serv = obj.services.exists()
        if prod and serv:
            return "both"
        if prod:
            return "product"
        if serv:
            return "service"
        return "none"

    def get_parents(self, obj):
        chain = []
        cur = obj.parent
        while cur:
            if cur.type == obj.type:
                chain.append({"id": cur.id, "name": cur.name})
            cur = cur.parent
        return chain[::-1]


# ───────────────────────────────────────────────────────────────
# 2.  PRODUCT
# ───────────────────────────────────────────────────────────────
class ProductImageSerializer(_ImageURLMixin, serializers.ModelSerializer):
    # ──────────────────────────────────────────────
    # NEW             ↓  write-only upload bucket
    # ──────────────────────────────────────────────
    image = serializers.ImageField(write_only=True, required=True)

    # existing read-only absolute URL
    url = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = ProductImage
        # include the raw `image` on writes, never on reads
        fields = ("id", "product", "is_primary", "image", "url", "created")
        read_only_fields = ("id", "url", "created")

    # ---------------------------------------------
    # helper that turns storage path → absolute URL
    # ---------------------------------------------
    def get_url(self, obj):
        return self._abs(self.context.get("request"), obj.image)


class SellerMiniSerializer(serializers.ModelSerializer):
    """Very small representation of the Django user who owns the product."""

    class Meta:
        model = CustomUser
        fields = ("id", "username", "email", "phone_number")


class ProductMiniSerializer(serializers.ModelSerializer):
    """
    A super-lean representation that is good for “related products”
    widgets – one image, seller name, price & currency.
    """
    image = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "product_id", "name", "slug",
            "price", "currency",
            "image",
        )

    # pick primary → else first image → else None
    def get_image(self, obj):
        req = self.context.get("request")
        img = obj.images.filter(is_primary=True).first() \
              or obj.images.first()
        return (
            req.build_absolute_uri(img.image.url) if img and req else None
        )


class _ProductBaseSerializer(serializers.ModelSerializer):
    condition = ConditionMiniSerializer(read_only=True)
    status = StatusMiniSerializer(read_only=True)
    sku = SKUMiniSerializer(read_only=True)
    seller = SellerMiniSerializer(read_only=True)
    vendor_profile = serializers.SerializerMethodField()
    business = BusinessBriefSerializer(read_only=True)
    stock_message = serializers.SerializerMethodField()

    tags = TagSerializer(many=True, read_only=True)
    attributes = AttributeSerializer(many=True, read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)

    seller_id = serializers.PrimaryKeyRelatedField(
        queryset=CustomUser.objects.all(), source="seller",
        write_only=True, required=False
    )
    business_id = serializers.PrimaryKeyRelatedField(
        queryset=Business.objects.all(), source="business",
        write_only=True, required=False, allow_null=True
    )

    category = CategoryDetailSerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.filter(type=Category.PRODUCT),
        source="category", write_only=True, required=True
    )
    condition_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductCondition.objects.all(), source="condition",
        write_only=True, required=True
    )
    status_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductServiceStatus.objects.all(), source="status",
        write_only=True, required=True
    )
    sku_id = serializers.PrimaryKeyRelatedField(
        queryset=SKU.objects.all(), source="sku",
        write_only=True, required=False
    )

    tag_ids = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Tag.objects.all(), source="tags",
        write_only=True, required=False
    )
    attribute_ids = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Attributes.objects.all(), source="attributes",
        write_only=True, required=False
    )

    new_images = serializers.ListField(
        child=serializers.ImageField(), write_only=True,
        required=False, help_text="Optional list of files → ProductImage"
    )

    object_type = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "product_id", "object_type",
            "name", "slug", "description",
            "seller", "seller_id", "vendor_profile",
            "business", "business_id",
            "category", "category_id",
            "condition", "condition_id",
            "status", "status_id",
            "sku", "sku_id",
            "price", "currency", "discount_price", "quantity", "stock_message",
            "featured", "is_active",
            "tags", "tag_ids",
            "attributes", "attribute_ids",
            "images", "new_images",
            "created_at", "last_updated_at",
        )
        read_only_fields = ("created_at", "last_updated_at")

    def get_object_type(self, _):
        return "Product"

    def get_stock_message(self, obj):
        if obj.quantity <= 5:
            return "Few units left"
        return None

    def get_vendor_profile(self, obj):
        try:
            vp = obj.seller.vendorprofile
        except VendorProfile.DoesNotExist:
            return None
        return VendorProfileSerializer(vp, context=self.context).data

    def validate_new_images(self, images):
        for img in images:
            try:
                Image.open(img).verify()
                img.seek(0)
            except Exception:
                raise serializers.ValidationError("All uploaded files must be valid image formats.")
        return images

    def create(self, validated_data):
        tags = validated_data.pop("tags", [])
        attrs = validated_data.pop("attributes", [])
        images = validated_data.pop("new_images", [])

        with transaction.atomic():
            product = Product.objects.create(**validated_data)
            if tags:
                product.tags.set(tags)
            if attrs:
                product.attributes.set(attrs)
            for img in images:
                ProductImage.objects.create(product=product, image=img)
        return product

    def update(self, instance, validated_data):
        tags = validated_data.pop("tags", None)
        attrs = validated_data.pop("attributes", None)
        images = validated_data.pop("new_images", [])

        with transaction.atomic():
            instance = super().update(instance, validated_data)
            if tags is not None:
                instance.tags.set(tags)
            if attrs is not None:
                instance.attributes.set(attrs)
            for img in images:
                ProductImage.objects.create(product=instance, image=img)
        return instance


class ProductSerializer(_ProductBaseSerializer):
    """
    Thin wrapper that simply re-uses the mapping defined in
    `_ProductBaseSerializer`.

    Keeping a separate class is handy if, in the future, you want
    to add product-specific read-only analytics _without_ changing
    the write contract that the FE already relies on.
    """
    average_rating = serializers.SerializerMethodField()

    class Meta(_ProductBaseSerializer.Meta):
        fields = _ProductBaseSerializer.Meta.fields + ("average_rating",)

    def get_average_rating(self, obj):
        # look up only “rating”-type Feedback for this product
        ct = ContentType.objects.get_for_model(obj)
        avg = (
            Feedback.objects
            .filter(
                content_type=ct,
                object_id=obj.product_id,
                feedback_type="rating",
                rating__isnull=False
            )
            .aggregate(a=Avg("rating"))["a"]
        )
        return float(avg or 0.0)


class ProductDetailSerializer(ProductSerializer):
    related_products = serializers.SerializerMethodField()
    feedback = serializers.SerializerMethodField()
    rating_stats = serializers.SerializerMethodField()

    class Meta(ProductSerializer.Meta):
        fields = ProductSerializer.Meta.fields + (
            "related_products", "feedback", "rating_stats"
        )

    def _root_category(self, cat):
        while cat.parent_id:
            cat = cat.parent
        return cat

    def get_related_products(self, obj):
        root = self._root_category(obj.category)
        qs = Product.objects.filter(
            category__in=[root] + list(root.children.all()),
            is_active=True
        ).exclude(pk=obj.pk).select_related("category").prefetch_related("images").order_by("?")[:8]
        return ProductMiniSerializer(qs, many=True, context=self.context).data

    def get_feedback(self, obj):
        ct = ContentType.objects.get_for_model(obj)
        qs = Feedback.objects.filter(content_type=ct, object_id=obj.product_id).order_by("-submitted_at")
        result = {}
        for key, _ in Feedback.FEEDBACK_TYPE_CHOICES:
            subset = qs.filter(feedback_type=key)
            result[key] = FeedbackPublicSerializer(subset, many=True, context=self.context).data
        return result

    def get_rating_stats(self, obj):
        ct = ContentType.objects.get_for_model(obj)
        qs = Feedback.objects.filter(
            content_type=ct,
            object_id=obj.product_id,
            feedback_type="rating",
            rating__isnull=False
        )
        avg = qs.aggregate(avg_rating=Avg("rating"))["avg_rating"] or 0
        dist_qs = qs.values("rating").annotate(count=Count("id"))
        dist = {str(i): 0 for i in range(1, 6)}
        for row in dist_qs:
            dist[str(row["rating"])] = row["count"]
        return {"average": float(avg), "distribution": dist}


# ───────────────────────────────────────────────────────────────
# 3.  SERVICE
# ───────────────────────────────────────────────────────────────
class _LocationWriteMixin(serializers.Serializer):
    """
    Accept region/district/town IDs *(many=True)* when **creating /
    updating** a Service.  We still return the expanded objects for reads.
    """
    region_ids = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Region.objects.all(), write_only=True,
        required=False, source="regions")
    district_ids = serializers.PrimaryKeyRelatedField(
        many=True, queryset=District.objects.all(), write_only=True,
        required=False, source="district")
    town_ids = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Town.objects.all(), write_only=True,
        required=False, source="town")


class ServiceImageSerializer(_ImageURLMixin, serializers.ModelSerializer):
    # write-only bucket for the actual file
    image = serializers.ImageField(write_only=True, required=True)

    # read-only absolute URL
    url = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = ServiceImage
        fields = (
            "id",
            "service",  # FK (writable)
            "is_primary",
            "image",  # <- upload here
            "url",  # <- serve on reads
            "created",
        )
        read_only_fields = ("id", "url", "created")

    # helper: build absolute URL
    def get_url(self, obj):
        return self._abs(self.context.get("request"), obj.image)


class ServicePricingChoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServicePricingChoices
        fields = ("id", "name", "description")


class ServiceSerializer(_LocationWriteMixin, serializers.ModelSerializer):
    category = CategoryTreeSerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.filter(type=Category.SERVICE),
        source="category", write_only=True, required=True
    )
    pricing_type = serializers.StringRelatedField(read_only=True)
    pricing_type_id = serializers.PrimaryKeyRelatedField(
        queryset=ServicePricingChoices.objects.all(),  # or correct ServicePricingChoices model
        source="pricing_type", write_only=True, required=True
    )

    regions = RegionMiniSerializer(many=True, read_only=True)
    region_ids = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Region.objects.all(),
        source="regions", write_only=True, required=False
    )
    district = DistrictMiniSerializer(many=True, read_only=True)
    district_ids = serializers.PrimaryKeyRelatedField(
        many=True, queryset=District.objects.all(),
        source="district", write_only=True, required=False
    )
    town = TownMiniSerializer(many=True, read_only=True)
    town_ids = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Town.objects.all(),
        source="town", write_only=True, required=False
    )

    tags = TagSerializer(many=True, read_only=True)
    tag_ids = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Tag.objects.all(),
        source="tags", write_only=True, required=False
    )
    attributes = AttributeSerializer(many=True, read_only=True)
    attribute_ids = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Attributes.objects.all(),
        source="attributes", write_only=True, required=False
    )

    images = ServiceImageSerializer(many=True, read_only=True)
    new_images = serializers.ListField(
        child=serializers.ImageField(), write_only=True, required=False,
        help_text="Optional list of files → ServiceImage"
    )

    business = BusinessBriefSerializer(read_only=True)
    business_id = serializers.PrimaryKeyRelatedField(
        queryset=Business.objects.all(), source="business", write_only=True,
        required=False, allow_null=True
    )
    provider = SellerMiniSerializer(read_only=True)
    vendor_profile = serializers.SerializerMethodField()
    average_rating = serializers.SerializerMethodField()
    object_type = serializers.SerializerMethodField()

    class Meta:
        model = Service
        fields = (
            "service_id", "object_type",
            "title", "description", "provider", "vendor_profile",
            "business", "business_id",
            "category", "category_id",
            "pricing_type", "pricing_type_id",
            "price", "is_remote",
            "regions", "region_ids",
            "district", "district_ids",
            "town", "town_ids",
            "is_active",
            "tags", "tag_ids",
            "attributes", "attribute_ids",
            "images", "new_images",
            "created_at", "updated_at", "average_rating"
        )
        read_only_fields = ("created_at", "updated_at")

    def get_object_type(self, _):
        return "Service"

    def get_vendor_profile(self, obj):
        try:
            vp = obj.provider.vendorprofile
        except VendorProfile.DoesNotExist:
            return None
        return VendorProfileSerializer(vp, context=self.context).data

    def validate_new_images(self, images):
        for img in images:
            try:
                Image.open(img).verify()
                img.seek(0)
            except Exception:
                raise serializers.ValidationError("All uploaded files must be valid image formats.")
        return images

    def get_average_rating(self, obj):
        # look up only “rating”-type Feedback for this product
        ct = ContentType.objects.get_for_model(obj)
        avg = (
            Feedback.objects
            .filter(
                content_type=ct,
                object_id=obj.service_id,
                feedback_type="rating",
                rating__isnull=False
            )
            .aggregate(a=Avg("rating"))["a"]
        )
        return float(avg or 0.0)

    def create(self, validated_data):
        new_images = validated_data.pop("new_images", [])
        tag_objs = validated_data.pop("tags", [])
        attr_objs = validated_data.pop("attributes", [])
        region_objs = validated_data.pop("regions", [])
        district_objs = validated_data.pop("district", [])
        town_objs = validated_data.pop("town", [])

        request = self.context.get("request")
        if not request or not request.user or not request.user.is_authenticated:
            raise serializers.ValidationError("Authentication credentials were not provided.")
        validated_data["provider"] = request.user

        service = Service.objects.create(**validated_data)
        if tag_objs:
            service.tags.set(tag_objs)
        if attr_objs:
            service.attributes.set(attr_objs)
        service.regions.set(region_objs)
        service.district.set(district_objs)
        service.town.set(town_objs)

        for img in new_images:
            ServiceImage.objects.create(service=service, image=img)
        return service

    def update(self, instance, validated_data):
        new_images = validated_data.pop("new_images", [])
        tag_objs = validated_data.pop("tags", None)
        attr_objs = validated_data.pop("attributes", None)
        region_objs = validated_data.pop("regions", None)
        district_objs = validated_data.pop("district", None)
        town_objs = validated_data.pop("town", None)

        instance = super().update(instance, validated_data)

        if tag_objs is not None:
            instance.tags.set(tag_objs)
        if attr_objs is not None:
            instance.attributes.set(attr_objs)
        if region_objs is not None:
            instance.regions.set(region_objs)
        if district_objs is not None:
            instance.district.set(district_objs)
        if town_objs is not None:
            instance.town.set(town_objs)

        for img in new_images:
            ServiceImage.objects.create(service=instance, image=img)
        return instance


class ServiceMiniSerializer(serializers.ModelSerializer):
    category = CategoryMiniSerializer(read_only=True)

    class Meta:
        model = Service
        fields = ("service_id", "title", "price", "is_active", "category")


class ServiceDetailSerializer(ServiceSerializer):
    related_services = serializers.SerializerMethodField()
    feedback = serializers.SerializerMethodField()
    rating_stats = serializers.SerializerMethodField()

    class Meta(ServiceSerializer.Meta):
        fields = ServiceSerializer.Meta.fields + (
            "related_services", "feedback", "rating_stats"
        )

    def _root_category(self, cat):
        while cat.parent_id:
            cat = cat.parent
        return cat

    def get_related_services(self, obj):
        root = self._root_category(obj.category)
        qs = Service.objects.filter(
            category__in=[root] + list(root.children.all()),
            is_active=True
        ).exclude(pk=obj.pk).select_related("category").prefetch_related("images").order_by("?")[:8]
        return ServiceMiniSerializer(qs, many=True, context=self.context).data

    def get_feedback(self, obj):
        ct = ContentType.objects.get_for_model(obj)
        qs = Feedback.objects.filter(content_type=ct, object_id=obj.service_id).order_by("-submitted_at")
        result = {}
        for key, _ in Feedback.FEEDBACK_TYPE_CHOICES:
            subset = qs.filter(feedback_type=key)
            result[key] = FeedbackPublicSerializer(subset, many=True, context=self.context).data
        return result

    def get_rating_stats(self, obj):
        ct = ContentType.objects.get_for_model(obj)
        qs = Feedback.objects.filter(
            content_type=ct,
            object_id=obj.service_id,
            feedback_type="rating",
            rating__isnull=False
        )
        avg = qs.aggregate(avg_rating=Avg("rating"))["avg_rating"] or 0
        dist_qs = qs.values("rating").annotate(count=Count("id"))
        dist = {str(i): 0 for i in range(1, 6)}
        for row in dist_qs:
            dist[str(row["rating"])] = row["count"]
        return {"average": float(avg), "distribution": dist}


















