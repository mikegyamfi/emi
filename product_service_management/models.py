import secrets
import string
import uuid

from django.conf import settings
from django.db import models, transaction
from django.utils.text import slugify

from account import models as account_models
from business.models import Business
from market_intelligence.models import Region, District, Town


# _ALPHABET = string.ascii_uppercase + string.digits  # 36 chars
# _BASE_LEN = 6
# _STEP = 2  # grow by 2 on collision
# _MAX_LEN = 16  # hard cap (VERY unlikely to hit)


# def _gen_code(n: int) -> str:
#     """Return an n-char random, URL-safe, upper-case string."""
#     return ''.join(secrets.choice(_ALPHABET) for _ in range(n))
#
#
# def get_unique_code(model, field: str, base_len: int = _BASE_LEN) -> str:
#     """
#     Generate a unique code for **model.field**.
#     Length starts at *base_len* and is increased by *_STEP*
#     only if (extremely unlikely) a collision happens.
#     """
#     length = base_len
#     while length <= _MAX_LEN:
#         code = _gen_code(length)
#         if not model.objects.filter(**{field: code}).exists():
#             return code
#         length += _STEP  # grow & try again
#     # If we ever get here something is very wrong
#     raise RuntimeError("Unable to generate a unique ID – increase _MAX_LEN")


class SKU(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()
    creator = models.ForeignKey(
        'account.CustomUser',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="created_skus",
        help_text="NULL = platform-wide / system SKU",
    )

    def __str__(self):
        return self.name


# Create your models here.
class Category(models.Model):
    PRODUCT = 'product'
    SERVICE = 'service'
    TYPE_CHOICES = [
        (PRODUCT, 'Product'),
        (SERVICE, 'Service'),
    ]

    name = models.CharField(max_length=100)
    type = models.CharField(max_length=8, choices=TYPE_CHOICES, db_index=True, null=True, blank=True)
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='children'
    )
    description = models.TextField()
    icon = models.ImageField(upload_to='category_icons/', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    featured = models.BooleanField(default=False)
    available_sku = models.ManyToManyField(SKU, blank=True)

    def save(self, *args, **kwargs):
        # 1) If this category has a parent, always inherit its type
        if self.parent:
            parent_type = self.parent.type
            if self.type != parent_type:
                self.type = parent_type

        # 2) Grab old_type so we know if it changed
        old_type = None
        if self.pk:
            old_type = (
                Category.objects
                .filter(pk=self.pk)
                .values_list("type", flat=True)
                .first()
            )

        # 3) Save self
        super().save(*args, **kwargs)

        # 4) If type is new or changed, push it down to all descendants
        if old_type != self.type:
            self._cascade_type_to_descendants()

    def _cascade_type_to_descendants(self):
        """
        Recursively set every child's `.type` to match this one,
        then let each child trigger the same on its own children.
        """
        for child in self.children.all():
            if child.type != self.type:
                child.type = self.type
                child.save()  # will in turn cascade further down

    def __str__(self):
        return f"{self.name} ({self.get_type_display()})"

    class Meta:
        verbose_name_plural = "Categories"


class ProductCondition(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()

    def __str__(self):
        return self.name


class ProductServiceStatus(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()

    def __str__(self):
        return self.name


class Tag(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class Attributes(models.Model):
    name = models.CharField(max_length=100)
    value = models.CharField(max_length=100, null=True, blank=True)
    description = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.name + self.value


# class Product(models.Model):
#     """
#     Physical goods.
#     `product_id` remains the PK but we now *always* store a real UUID object.
#     """
#     product_id = models.UUIDField(primary_key=True, editable=False)
#     seller = models.ForeignKey('account.CustomUser', on_delete=models.CASCADE,
#                                related_name="products")
#     business = models.ForeignKey("business.Business", on_delete=models.CASCADE,
#                                  related_name="products", null=True, blank=True)
#
#     # category = models.ForeignKey(Category, on_delete=models.PROTECT,
#     #                              related_name="products")
#     category = models.ForeignKey(
#         Category,
#         on_delete=models.PROTECT,
#         limit_choices_to={'type': Category.PRODUCT},
#         related_name='products'
#     )
#     name = models.CharField(max_length=255)
#     slug = models.CharField(max_length=255, unique=True)
#
#     status = models.ForeignKey(ProductServiceStatus, on_delete=models.PROTECT,
#                                related_name="products", null=True, blank=True)
#     sku = models.ForeignKey(SKU, on_delete=models.PROTECT,
#                             related_name="products", null=True, blank=True)
#
#     description = models.TextField()
#     price = models.DecimalField(max_digits=10, decimal_places=2)
#     currency = models.CharField(max_length=10, default="GHS")
#     discount_price = models.DecimalField(max_digits=10, decimal_places=2,
#                                          null=True, blank=True)
#     quantity = models.PositiveIntegerField(default=1)
#
#     condition = models.ForeignKey(ProductCondition, on_delete=models.PROTECT,
#                                   related_name="products", null=True, blank=True)
#
#     attributes = models.ManyToManyField(Attributes, related_name="products",
#                                         blank=True, null=True)
#     tags = models.ManyToManyField(Tag, related_name="products",
#                                   blank=True, null=True)
#
#     featured = models.BooleanField(default=False)
#     is_active = models.BooleanField(default=True)
#     created_at = models.DateTimeField(auto_now_add=True)
#     last_updated_at = models.DateTimeField(auto_now=True)
#
#     def _generate_unique_slug(self) -> str:
#         """
#         Slugify the name; if it collides, append -1, -2, …
#         We wrap the loop in `transaction.atomic` to minimise race windows.
#         """
#         base = slugify(self.name)[:240] or uuid.uuid4().hex[:12]
#         slug = base
#         i = 1
#         while (
#                 Product.objects.filter(slug=slug)
#                         .exclude(pk=self.pk)  # allow updating self
#                         .exists()
#         ):
#             slug = f"{base}-{i}"
#             i += 1
#         return slug
#
#     def save(self, *args, **kwargs):
#         # ensure UUID
#         if not self.product_id:
#             self.product_id = uuid.uuid4()
#
#         # auto‑slug if blank
#         if not self.slug:
#             # wrap in a tiny transaction to avoid a race on insert
#             with transaction.atomic():
#                 self.slug = self._generate_unique_slug()
#
#         super().save(*args, **kwargs)
#
#     def __str__(self):
#         return self.name


class ProductImage(models.Model):
    """Product images"""
    product = models.ForeignKey('GenericProduct', on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='product_images/')
    is_primary = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image for {self.product.name}"


class ServicePricingChoices(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()

    def __str__(self):
        return self.name


class GenericService(models.Model):
    """
    Master catalogue of all services.
    Analogous to GenericProduct.
    """
    service_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    description = models.TextField()

    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        limit_choices_to={"type": Category.SERVICE},
        related_name="catalogue_services"
    )
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def _generate_unique_slug(self) -> str:
        base = slugify(self.title)[:240] or uuid.uuid4().hex[:12]
        slug = base
        i = 1
        while GenericService.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug = f"{base}-{i}"
            i += 1
        return slug

    def save(self, *args, **kwargs):
        # auto-slug if blank
        if not self.slug:
            with transaction.atomic():
                self.slug = self._generate_unique_slug()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class VendorService(models.Model):
    """
    A seller’s specific offering of a GenericService:
    their own price, coverage, status, etc.
    """
    vendor_service_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    service = models.ForeignKey(
        GenericService,
        on_delete=models.CASCADE,
        related_name="listings"
    )
    provider = models.ForeignKey(
        'account_models.CustomUser',
        on_delete=models.CASCADE,
        related_name="service_listings"
    )
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="service_listings",
        null=True, blank=True
    )

    pricing_type = models.ForeignKey(
        ServicePricingChoices,
        on_delete=models.PROTECT,
        related_name="vendor_service_listings",
        null=True, blank=True,
    )
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    regions = models.ManyToManyField(Region, blank=True, related_name="vendor_services")
    districts = models.ManyToManyField(District, blank=True, related_name="vendor_services")
    towns = models.ManyToManyField(Town, blank=True, related_name="vendor_services")
    tags = models.ManyToManyField(Tag, blank=True)
    attributes = models.ManyToManyField(Attributes, blank=True)

    is_remote = models.BooleanField(default=False)
    featured = models.BooleanField(default=False)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("service", "provider", "business")
        indexes = [
            models.Index(fields=["provider", "is_active"]),
            models.Index(fields=["service", "price"]),
        ]

    def __str__(self):
        return f"{self.service.title} by {self.provider.username or self.provider.phone_number}"

    @property
    def category(self):
        """
        Shortcut to the GenericService’s category.
        Usage: vendor_service.category is the Category instance.
        """
        return self.service.category

    def save(self, *args, **kwargs):
        """
        If vendor hasn't provided a name/description, copy them from
        the underlying GenericService at save time (one‑off defaulting).
        """
        if not self.name and self.service_id:
            self.name = self.service.title
        if (self.description is None or (
                isinstance(self.description, str) and self.description.strip() == "")) and self.service_id:
            self.description = self.service.description or ""
        super().save(*args, **kwargs)


class VendorServiceImage(models.Model):
    """
    Optional seller-specific images (e.g. demos, slides).
    """
    vendor_service = models.ForeignKey(
        VendorService,
        on_delete=models.CASCADE,
        related_name="images"
    )
    image = models.ImageField(upload_to="vendor_service_images/")
    is_primary = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image for listing {self.vendor_service.listing_id}"


class ServiceImage(models.Model):
    """Product images"""
    service = models.ForeignKey(GenericService, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='service_images/')
    is_primary = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image for {self.service.title}"


class GenericProduct(models.Model):
    product_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    description = models.TextField()

    category = models.ForeignKey(
        "Category", on_delete=models.PROTECT,
        limit_choices_to={"type": Category.PRODUCT},
        related_name="catalogue_products"
    )

    featured = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    last_updated_at = models.DateTimeField(auto_now=True)

    def _generate_unique_slug(self) -> str:
        base = slugify(self.name)[:240] or uuid.uuid4().hex[:12]
        slug = base
        i = 1
        while GenericProduct.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug = f"{base}-{i}"
            i += 1
        return slug

    def save(self, *args, **kwargs):
        if not self.slug:
            with transaction.atomic():
                self.slug = self._generate_unique_slug()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class VendorProduct(models.Model):
    name = models.CharField(max_length=250, null=True, blank=True)
    description = models.TextField(blank=True)
    listing_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    product = models.ForeignKey(GenericProduct, on_delete=models.CASCADE, related_name="listings")
    seller = models.ForeignKey("account.CustomUser", on_delete=models.CASCADE, related_name="product_listings")
    business = models.ForeignKey("business.Business", on_delete=models.CASCADE, related_name="product_listings",
                                 null=True, blank=True)

    price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=10, default="GHS")
    quantity = models.PositiveIntegerField(default=1)

    condition = models.ForeignKey("ProductCondition", on_delete=models.PROTECT, related_name="product_listings",
                                  null=True, blank=True)
    status = models.ForeignKey("ProductServiceStatus", on_delete=models.PROTECT, related_name="product_listings",
                               null=True, blank=True)
    sku = models.ForeignKey("SKU", on_delete=models.PROTECT, related_name="catalogue_products", null=True, blank=True)
    tags = models.ManyToManyField("Tag", blank=True)
    attributes = models.ManyToManyField("Attributes", blank=True)

    featured = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    last_updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("product", "seller", "business")
        indexes = [
            models.Index(fields=["seller", "is_active"]),
            models.Index(fields=["product", "price"]),
        ]

    def save(self, *args, **kwargs):
        if not self.name:
            self.name = self.product.name
        if not (self.description and self.description.strip()):
            self.description = self.product.description or ""

        is_new = self._state.adding

        super().save(*args, **kwargs)

        if is_new and not self.images.exists():
            with transaction.atomic():
                for gen_img in self.product.images.all():
                    VendorProductImage.objects.create(
                        vendor_product=self,
                        image=gen_img.image,
                        is_primary=gen_img.is_primary,
                    )


    def __str__(self):
        return f"{self.product.name} @ {self.price} {self.currency} by {self.seller}"


class VendorProductImage(models.Model):
    vendor_product = models.ForeignKey(VendorProduct, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="vendor_product_image/")
    is_primary = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image for listing {self.vendor_product}"



