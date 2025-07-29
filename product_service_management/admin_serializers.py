"""
Serialisers used ONLY by the staff-side API.
They extend the public mini/card serialisers so the payload
remains consistent for the front-end dashboard.
"""
from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import VendorProduct, VendorService
from .serializers import (
    VendorProductSerializer,
    VendorServiceSerializer,
    BusinessBriefSerializer,  # was created earlier
    VendorProfileSerializer,
)

User = get_user_model()


# ──────────────────────────────────────────────────────────
# 1.  Product / Service admin actions
# ──────────────────────────────────────────────────────────
class _AdminToggleMixin(serializers.Serializer):
    """
    Returned when staff flips a Product / Service `is_active` flag.

    The serializer is the *same* for Product and Service – it just
    embeds their respective mini-serialiser.
    """
    was_active = serializers.BooleanField()
    is_active = serializers.BooleanField()
    item = serializers.SerializerMethodField()

    def get_item(self, obj):
        # obj is either Product or Service
        if isinstance(obj, VendorProduct):
            return VendorProductSerializer(obj, context=self.context).data
        return VendorServiceSerializer(obj, context=self.context).data


# ──────────────────────────────────────────────────────────
# 2.  Seller overview  (one stop shop for staff)
# ──────────────────────────────────────────────────────────
class SellerOverviewSerializer(serializers.Serializer):
    """
    • vendor_profile      – may be null
    • businesses[]        – with *their* products / services attached
    • standalone_products – products *not* tied to a business
    • standalone_services – services *not* tied to a business
    """
    vendor_profile = VendorProfileSerializer(read_only=True, allow_null=True)
    businesses = serializers.SerializerMethodField()
    standalone_products = VendorProductSerializer(many=True, read_only=True)
    standalone_services = VendorServiceSerializer(many=True, read_only=True)

    # helper --------------------------------------------------------
    def _business_block(self, biz):
        return {
            "business": BusinessBriefSerializer(biz, context=self.context).data,
            "products": VendorProductSerializer(
                biz.products.all(), many=True, context=self.context
            ).data,
            "services": VendorServiceSerializer(
                biz.services.all(), many=True, context=self.context
            ).data,
        }

    def get_businesses(self, seller):
        return [
            self._business_block(b)
            for b in seller.business_set.all()
        ]
