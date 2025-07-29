# serializers.py
from rest_framework import serializers
from .models import Cart, CartItem
from account.models import CustomUser
from product_service_management.serializers import VendorProductSerializer  # your existing product serializer


# — lean user info for Cart —
class CartUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ("id", "first_name", "last_name", "email", "phone_number")
        read_only_fields = fields


# — lean Cart for embedding in CartItemDetail —
class CartSimpleSerializer(serializers.ModelSerializer):
    total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ("cart_id", "session_key", "total", "item_count")

    def get_item_count(self, obj):
        # number of distinct items
        return obj.items.count()


# — lean item for list/create/update endpoints —
class CartItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_details = VendorProductSerializer(source="product", read_only=True)
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = CartItem
        fields = (
            "cart_item_id",
            "product",  # still the PK for writes
            "product_name",
            "product_details",  # now expands into the full ProductSerializer
            "quantity",
            "unit_price",
            "subtotal",
        )


# — detail item with nested cart + product full info —
class CartItemDetailSerializer(serializers.ModelSerializer):
    cart = CartSimpleSerializer(read_only=True)
    product = VendorProductSerializer(read_only=True)
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = CartItem
        fields = (
            "cart_item_id",
            "cart",
            "product",
            "quantity",
            "unit_price",
            "subtotal",
        )
        read_only_fields = fields


# — lean Cart for list/create/update —
class CartSerializer(serializers.ModelSerializer):
    user = CartUserSerializer(read_only=True)
    items = CartItemSerializer(many=True, read_only=True)
    total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = (
            "cart_id",
            "user",
            "session_key",
            "items",
            "total",
            "item_count",
        )
        read_only_fields = ("cart_id", "user", "items", "total", "item_count")

    def get_item_count(self, obj):
        return obj.items.count()


# — detail Cart with full item info —
class CartDetailSerializer(serializers.ModelSerializer):
    user = CartUserSerializer(read_only=True)
    items = CartItemDetailSerializer(many=True, read_only=True)
    total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = (
            "cart_id",
            "user",
            "session_key",
            "items",
            "total",
            "item_count",
        )
        read_only_fields = fields

    def get_item_count(self, obj):
        return obj.items.count()
