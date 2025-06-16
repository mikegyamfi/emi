# market_intel/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import PriceListing, PriceHistory


@receiver(post_save, sender=PriceListing
          )
def snapshot_price(sender, instance, **_):
    PriceHistory.objects.create(
        listing=instance,
        price=instance.price,
        currency=instance.currency or "GHS",
    )
