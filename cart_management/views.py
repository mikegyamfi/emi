# views.py
import csv
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response

from core.response import ok, fail
from .models import Cart, CartItem
from .serializers import (
    CartSerializer, CartDetailSerializer,
    CartItemSerializer, CartItemDetailSerializer
)
from .utils import get_or_create_cart


class CartViewSet(viewsets.ViewSet):
    """
    GET    /cart/               → fetch (and auto-create) your cart
    POST   /cart/clear/         → remove all items
    """
    permission_classes = (IsAuthenticated,)

    def list(self, request):
        # auto‐get or create
        cart = get_or_create_cart(request)
        data = CartDetailSerializer(cart, context={"request": request}).data
        return ok("Cart retrieved", data)

    @action(detail=False, methods=["post"])
    def clear(self, request):
        cart = get_or_create_cart(request)
        cart.items.all().delete()
        return ok("Cart cleared")

    @action(detail=False, methods=["get"])
    def count(self, request):
        """
        GET /cart/count/
        Returns the number of distinct items in the current user's cart.
        """
        cart, _ = Cart.objects.get_or_create(user=request.user)
        count = cart.items.count()
        return ok("Cart item count", {"count": count})


class CartItemViewSet(viewsets.ModelViewSet):
    """
    cart-items/
      GET      → list all items in your cart
      POST     → add item (auto‐create cart under the hood)
      PATCH    → change quantity
      DELETE   → remove item
      GET pk   → item detail
    """
    queryset = CartItem.objects.select_related("cart", "product").all()
    permission_classes = (IsAuthenticatedOrReadOnly,)

    def get_serializer_class(self):
        return (
            CartItemDetailSerializer
            if self.action == "retrieve"
            else CartItemSerializer
        )

    def get_queryset(self):
        return self.queryset.filter(cart=get_or_create_cart(self.request))

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        page = self.paginate_queryset(qs)
        ser = self.get_serializer(page or qs, many=True)
        return (
            self.get_paginated_response(ser.data)
            if page else ok("Cart items retrieved", ser.data)
        )

    def create(self, request, *args, **kwargs):
        # ensure cart exists
        cart = get_or_create_cart(request)

        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            item = ser.save(cart=cart)
        except Exception as e:
            return fail(str(e), status=status.HTTP_400_BAD_REQUEST)

        data = CartItemDetailSerializer(item, context={"request": request}).data
        return ok("Cart item added", data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        item = self.get_object()
        return ok("Cart item retrieved", self.get_serializer(item).data)

    def update(self, request, *args, **kwargs):
        item = self.get_object()
        ser = self.get_serializer(item, data=request.data)
        ser.is_valid(raise_exception=True)
        item = ser.save()
        return ok("Cart item updated", self.get_serializer(item).data)

    def partial_update(self, request, *args, **kwargs):
        item = self.get_object()
        ser = self.get_serializer(item, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        item = ser.save()
        return ok("Cart item partially updated", self.get_serializer(item).data)

    def destroy(self, request, *args, **kwargs):
        item = self.get_object()
        item.delete()
        return ok("Cart item removed")
