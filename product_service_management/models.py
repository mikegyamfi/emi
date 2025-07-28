import secrets
import string
import uuid

from django.conf import settings
from django.db import models, transaction
from django.utils.text import slugify

# from account.models import CustomUser
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

    def __str__(self):
        return f"{self.name} ({self.get_type_display()})"


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


class Product(models.Model):
    """
    Physical goods.
    `product_id` remains the PK but we now *always* store a real UUID object.
    """
    product_id = models.UUIDField(primary_key=True, editable=False)
    seller = models.ForeignKey('account.CustomUser', on_delete=models.CASCADE,
                               related_name="products")
    business = models.ForeignKey("business.Business", on_delete=models.CASCADE,
                                 related_name="products", null=True, blank=True)

    # category = models.ForeignKey(Category, on_delete=models.PROTECT,
    #                              related_name="products")
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        limit_choices_to={'type': Category.PRODUCT},
        related_name='products'
    )
    name = models.CharField(max_length=255)
    slug = models.CharField(max_length=255, unique=True)

    status = models.ForeignKey(ProductServiceStatus, on_delete=models.PROTECT,
                               related_name="products", null=True, blank=True)
    sku = models.ForeignKey(SKU, on_delete=models.PROTECT,
                            related_name="products", null=True, blank=True)

    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default="GHS")
    discount_price = models.DecimalField(max_digits=10, decimal_places=2,
                                         null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1)

    condition = models.ForeignKey(ProductCondition, on_delete=models.PROTECT,
                                  related_name="products", null=True, blank=True)

    attributes = models.ManyToManyField(Attributes, related_name="products",
                                        blank=True, null=True)
    tags = models.ManyToManyField(Tag, related_name="products",
                                  blank=True, null=True)

    featured = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_updated_at = models.DateTimeField(auto_now=True)

    def _generate_unique_slug(self) -> str:
        """
        Slugify the name; if it collides, append -1, -2, …
        We wrap the loop in `transaction.atomic` to minimise race windows.
        """
        base = slugify(self.name)[:240] or uuid.uuid4().hex[:12]
        slug = base
        i = 1
        while (
            Product.objects.filter(slug=slug)
            .exclude(pk=self.pk)            # allow updating self
            .exists()
        ):
            slug = f"{base}-{i}"
            i += 1
        return slug

    def save(self, *args, **kwargs):
        # ensure UUID
        if not self.product_id:
            self.product_id = uuid.uuid4()

        # auto‑slug if blank
        if not self.slug:
            # wrap in a tiny transaction to avoid a race on insert
            with transaction.atomic():
                self.slug = self._generate_unique_slug()

        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class ProductImage(models.Model):
    """Product images"""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
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


class Service(models.Model):
    """
    Non-physical offerings.
    Same UUID logic as Product.
    """
    service_id = models.UUIDField(primary_key=True, editable=False)
    provider = models.ForeignKey('account.CustomUser', on_delete=models.CASCADE,
                                 related_name="services")
    business = models.ForeignKey("business.Business", on_delete=models.CASCADE,
                                 related_name="services", null=True, blank=True)

    # category = models.ForeignKey(Category, on_delete=models.PROTECT,
    #                              related_name="services")
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        limit_choices_to={'type': Category.SERVICE},
        related_name='services'
    )
    title = models.CharField(max_length=255)
    description = models.TextField()

    pricing_type = models.ForeignKey(ServicePricingChoices, on_delete=models.PROTECT,
                                     related_name="services")
    price = models.DecimalField(max_digits=10, decimal_places=2,
                                null=True, blank=True)

    # Geo coverage
    regions = models.ManyToManyField(Region, blank=True)
    district = models.ManyToManyField(District, blank=True)
    town = models.ManyToManyField(Town, blank=True)

    tags = models.ManyToManyField(Tag, blank=True, null=True)
    attributes = models.ManyToManyField(Attributes, blank=True, null=True)

    is_remote = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.service_id:
            self.service_id = uuid.uuid4()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class ServiceImage(models.Model):
    """Product images"""
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='service_images/')
    is_primary = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image for {self.service.title}"
