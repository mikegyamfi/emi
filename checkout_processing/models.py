import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from market_intelligence.models import Region, District, Town


class DirectOrder(models.Model):
    order_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="direct_orders"
    )
    product = models.ForeignKey(
        'product_service_management.VendorProduct',
        on_delete=models.PROTECT,
        related_name="direct_orders"
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    full_name = models.CharField(max_length=255)
    email = models.EmailField(null=True, blank=True)
    phone = models.CharField(max_length=20)
    street = models.CharField(max_length=255, null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True)
    region = models.ForeignKey(
        'market_intelligence.Region', on_delete=models.SET_NULL,
        null=True, blank=True
    )
    district = models.ForeignKey(
        'market_intelligence.District', on_delete=models.SET_NULL,
        null=True, blank=True
    )
    town = models.CharField(max_length=200, null=True, blank=True)
    location = models.CharField(max_length=200)
    google_map_url = models.URLField(
        blank=True, null=True,
        help_text="A Google Maps link (e.g. the ‘share’ URL) for this address"
    )
    postal_code = models.CharField(max_length=20, blank=True)
    note = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("completed", "Completed"),
        ("canceled", "Canceled"),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order {self.order_id} by {self.buyer_id}"

    @property
    def unit_price(self):
        """
        Use discount_price if set, otherwise regular price.
        """
        dp = getattr(self.product, "discount_price", None)
        return dp if dp is not None else self.product.price

    @property
    def total(self):
        """
        Total order amount = unit_price * quantity
        """
        return self.unit_price * self.quantity


class VendorNotification(models.Model):
    buyer = models.ForeignKey(
        'account.CustomUser',
        on_delete=models.CASCADE,
        related_name="buyer_notifications"
    )
    read = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    product = models.ForeignKey(
        'product_service_management.Product',
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="direct_orders_notifications"
    )
    service = models.ForeignKey(
        'product_service_management.Service',
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="direct_booking_notifications"
    )
    quantity = models.PositiveIntegerField(null=True, blank=True)
    location = models.CharField(max_length=200, null=True, blank=True)

    def __str__(self):
        return f"Notification for {self.product} → buyer {self.buyer_id}"


class DirectBooking(models.Model):
    booking_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    buyer = models.ForeignKey(
        'account.CustomUser',
        on_delete=models.CASCADE,
        related_name="direct_bookings"
    )
    service = models.ForeignKey(
        'product_service_management.VendorService',
        on_delete=models.PROTECT,
        related_name="direct_bookings"
    )
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("completed", "Completed"),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")











