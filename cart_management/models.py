import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone


class Cart(models.Model):
    cart_id = models.UUIDField(primary_key=True, editable=False)
    # either tied to a logged-in user
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE)
    # or to an anonymous session key
    session_key = models.CharField(max_length=40, null=True, blank=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # one cart per user or session
            models.UniqueConstraint(fields=["user"], condition=models.Q(user__isnull=False), name="unique_user_cart"),
            models.UniqueConstraint(fields=["session_key"], condition=models.Q(session_key__isnull=False),
                                    name="unique_session_cart"),
        ]


    def save(self, *args, **kwargs):
        if not self.cart_id:
            self.cart_id = uuid.uuid4()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"<Cart #{self.pk} user={self.user_id} session={self.session_key}>"

    @property
    def total(self):
        return sum(item.subtotal for item in self.items.all())


class CartItem(models.Model):
    cart_item_id = models.UUIDField(primary_key=True, editable=False)
    cart = models.ForeignKey(Cart, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey("product_service_management.VendorProduct", on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()

    class Meta:
        unique_together = [("cart", "product")]

    @property
    def unit_price(self):
        if self.product.discount_price:
            return self.product.discount_price
        return self.product.price

    @property
    def subtotal(self):
        return self.unit_price * self.quantity

    def clean(self):
        if self.quantity < 1:
            raise ValidationError("Quantity must be at least 1.")
        if self.quantity > self.product.quantity:  # or inventory field
            raise ValidationError("Insufficient stock for this product.")

    def save(self, *args, **kwargs):
        self.full_clean()
        if not self.cart_item_id:
            self.cart_item_id = uuid.uuid4()
        super().save(*args, **kwargs)







