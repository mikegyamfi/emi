# serializers.py
from rest_framework import serializers
from django.core.exceptions import ValidationError
from market_intelligence.models import Region, District, Town  # ← new imports
from product_service_management.serializers import VendorProductSerializer, VendorServiceSerializer
from .models import DirectOrder, DirectBooking
from product_service_management.models import VendorProduct, VendorService
from cart_management.serializers import CartUserSerializer
from core.utils import send_vendor_order_sms, send_vendor_booking_sms


class DirectOrderCreateSerializer(serializers.Serializer):
    product_id = serializers.UUIDField(write_only=True)
    quantity = serializers.IntegerField()
    full_name = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)
    street = serializers.CharField(required=False, allow_blank=True)
    city = serializers.CharField(required=False, allow_blank=True)
    google_map_url = serializers.URLField(required=False, allow_blank=True)
    town = serializers.CharField(
        required=False, allow_blank=True
    )

    # ← now FK fields
    region = serializers.PrimaryKeyRelatedField(
        queryset=Region.objects.all(), required=False, allow_null=True
    )
    district = serializers.PrimaryKeyRelatedField(
        queryset=District.objects.all(), required=False, allow_null=True
    )

    location = serializers.CharField()
    postal_code = serializers.CharField(required=False, allow_blank=True)
    note = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        try:
            prod = VendorProduct.objects.get(listing_id=attrs["product_id"])
        except VendorProduct.DoesNotExist:
            raise serializers.ValidationError({"product_id": "Invalid product."})
        if attrs["quantity"] > prod.quantity:
            raise serializers.ValidationError({"quantity": "Insufficient stock."})
        attrs["product"] = prod
        return attrs

    def create(self, validated):
        user = self.context["request"].user
        prod = validated.pop("product")
        qty = validated.pop("quantity")

        fn = validated.get("full_name") or f"{user.first_name} {user.last_name}"
        em = validated.get("email") or user.email
        ph = validated.get("phone") or getattr(user, "phone_number", "")

        order = DirectOrder.objects.create(
            buyer=user,
            product=prod,
            quantity=qty,
            full_name=fn,
            email=em,
            phone=ph,
            street=validated.get("street", ""),
            city=validated.get("city", ""),
            google_map_url=validated.get("google_map_url", ""),
            region=validated.get("region"),
            district=validated.get("district"),
            town=validated.get("town"),
            location=validated["location"],
            postal_code=validated.get("postal_code", ""),
            note=validated.get("note", "")
        )

        # prod.quantity -= qty
        # prod.save(update_fields=["quantity"])

        send_vendor_order_sms(prod.seller.phone_number, str(order.order_id))
        return order


class DirectOrderSerializer(serializers.ModelSerializer):
    buyer = CartUserSerializer(read_only=True)
    product = VendorProductSerializer(read_only=True)
    status = serializers.CharField(read_only=True)
    total = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True
    )
    google_map_url = serializers.URLField(read_only=True)

    class Meta:
        model = DirectOrder
        fields = (
            "order_id",
            "buyer",
            "product",
            "quantity",
            "unit_price",
            "total",
            "full_name",
            "email",
            "phone",
            "street",
            "city",
            "region",
            "district",
            "town",
            "location",
            "google_map_url",
            "postal_code",
            "note",
            "created_at",
            "status"
        )
        read_only_fields = (
            "order_id",
            "buyer",
            "unit_price",
            "total",
            "created_at",
            "google_map_url"
        )

    unit_price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True
    )


class DirectBookingCreateSerializer(serializers.Serializer):
    service_id = serializers.UUIDField(write_only=True)
    message = serializers.CharField()

    def validate_service_id(self, value):
        try:
            service = VendorService.objects.get(vendor_service_id=value, is_active=True)
        except VendorService.DoesNotExist:
            raise serializers.ValidationError("Invalid or inactive service.")
        return value

    def validate(self, attrs):
        # attach the Service instance for create()
        attrs['service_obj'] = VendorService.objects.get(vendor_service_id=attrs['service_id'])
        return attrs

    def create(self, validated_data):
        user = self.context['request'].user
        service = validated_data.pop('service_obj')
        message = validated_data.pop('message')

        booking = DirectBooking.objects.create(
            buyer=user,
            service=service,
            message=message
        )

        # fire off the SMS asynchronously
        send_vendor_booking_sms(
            provider_phone=str(service.provider.phone_number),
            booking_id=str(booking.booking_id)
        )

        return booking


class DirectBookingSerializer(serializers.ModelSerializer):
    booking_id = serializers.UUIDField(read_only=True)
    buyer = CartUserSerializer(read_only=True)
    service = VendorServiceSerializer(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    status = serializers.CharField(read_only=True)

    class Meta:
        model = DirectBooking
        fields = ("booking_id", "buyer", "service", "message", "created_at", "status")

