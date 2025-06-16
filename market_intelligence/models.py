from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import CheckConstraint, Q, Avg, Min, Max
from django.utils import timezone


# Create your models here.
class Region(models.Model):
    name = models.CharField(max_length=255, unique=True, null=True, blank=True)

    def __str__(self):
        return self.name


class District(models.Model):
    name = models.CharField(max_length=255, null=True, blank=True)
    region = models.ForeignKey(Region, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return f"{self.name}, {self.region.name}"


class Town(models.Model):
    name = models.CharField(max_length=255, null=True, blank=True)
    district = models.ForeignKey(District, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return f"{self.name}, {self.district.name}"


class Market(models.Model):
    name = models.CharField(max_length=255, null=True, blank=True)
    town = models.ForeignKey(Town, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return f"{self.name}, {self.town.name}"


class Category(models.Model):
    name = models.CharField(max_length=255, unique=True, null=True, blank=True)
    image = models.ImageField(null=True, blank=True, upload_to='category-images/')
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE)

    def __str__(self):
        return self.name


class Tag(models.Model):
    name = models.CharField(max_length=255, unique=True, null=True, blank=True)

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField()
    sku = models.CharField(max_length=255)
    # TYPE_CHOICES = (
    #     ("Product", "Product"),
    #     ("Service", "Service")
    # )
    # type = models.CharField(max_length=100, null=True, blank=True, choices=TYPE_CHOICES)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    tags = models.ManyToManyField(Tag, blank=True)

    def __str__(self):
        return self.name


class Service(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField()
    sku = models.CharField(max_length=255)
    # TYPE_CHOICES = (
    #     ("Product", "Product"),
    #     ("Service", "Service")
    # )
    # type = models.CharField(max_length=100, null=True, blank=True, choices=TYPE_CHOICES)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    tags = models.ManyToManyField(Tag, blank=True)

    def __str__(self):
        return self.name


class ProductServiceImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True, blank=True, related_name='images')
    service = models.ForeignKey(Service, on_delete=models.CASCADE, null=True, blank=True, related_name='images')
    image = models.ImageField(upload_to="product_service_images/", null=True, blank=True)
    feature_image = models.BooleanField(default=False)
    status = models.BooleanField(default=True)


class PriceListing(models.Model):
    """
    A single row represents:
      • the product **or** service being offered
      • the geo-anchor (town and/or market)
      • the current price
      • live aggregate stats (avg / low / high)
    Historical snapshots live in PriceHistory (FK 👉 listing).
    """
    product = models.ForeignKey(
        "Product",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="listings",
    )
    service = models.ForeignKey(
        "Service",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="listings",
    )

    # -------- WHERE ------------------------------------------------
    town = models.ForeignKey(
        "Town",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
    )
    market = models.ForeignKey(
        "Market",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
    )

    # -------- PRICE ------------------------------------------------
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default="GHS")
    average_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        editable=False,
    )
    lowest_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        editable=False,
    )
    highest_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        editable=False,
    )
    note = models.TextField(blank=True)
    status = models.BooleanField(default=True)  # active/hidden
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # exactly one of product or service
            models.CheckConstraint(
                check=(
                    (Q(product__isnull=False) & Q(service__isnull=True)) |
                    (Q(product__isnull=True) & Q(service__isnull=False))
                ),
                name="price_listing_exactly_one_stem",
            ),
            # at least one geo anchor
            models.CheckConstraint(
                check=Q(town__isnull=False) | Q(market__isnull=False),
                name="price_listing_needs_town_or_market",
            ),
        ]

    def clean(self):
        super().clean()
        if bool(self.product) == bool(self.service):
            raise ValidationError(
                "Exactly one of product OR service must be provided."
            )
        if not (self.town or self.market):
            raise ValidationError(
                "A listing needs a town and/or a market reference."
            )

    @property
    def kind(self) -> str:
        return "Product" if self.product_id else "Service"

    def __str__(self):
        stem = self.product or self.service
        where = self.market or self.town or "—"
        return f"{stem} | {self.price} {self.currency} @ {where}"

    def _recalc_stats(self):
        agg = self.history.aggregate(
            avg=Avg("price"), lo=Min("price"), hi=Max("price")
        )
        self.average_price = agg.get("avg") or self.price
        self.lowest_price = agg.get("lo") or self.price
        self.highest_price = agg.get("hi") or self.price

    def save(self, *args, **kwargs):
        is_new = self._state.adding

        # pre-populate stats on create
        if is_new:
            initial = self.price or Decimal("0.00")
            self.average_price = initial
            self.lowest_price = initial
            self.highest_price = initial

        super().save(*args, **kwargs)

        price_changed = is_new or ("price" in (kwargs.get("update_fields") or []))
        if price_changed:
            PriceHistory.objects.create(
                listing=self,
                price=self.price,
                currency=self.currency,
                recorded_at=timezone.now(),
            )
            self._recalc_stats()
            super().save(update_fields=(
                "average_price", "lowest_price", "highest_price"
            ))


class PriceHistory(models.Model):
    listing = models.ForeignKey(
        "PriceListing",
        on_delete=models.CASCADE,
        related_name="history", null=True, blank=True
    )
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10)
    recorded_at = models.DateTimeField(default=timezone.now)

    class Meta:
        get_latest_by = "recorded_at"
        indexes = [
            models.Index(fields=("listing", "recorded_at")),
        ]
        verbose_name_plural = "Price history"

    def __str__(self):
        return f"{self.listing} @ {self.price} ({self.recorded_at:%Y-%m-%d})"
