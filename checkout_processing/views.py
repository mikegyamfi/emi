# orders/views.py
from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from core.response import ok, fail
from core.utils import send_vendor_order_sms, send_vendor_booking_sms
from .models import DirectOrder, DirectBooking
from .serializers import DirectOrderCreateSerializer, DirectOrderSerializer, DirectBookingCreateSerializer, \
    DirectBookingSerializer
from account.permissions import IsVendor


class DirectOrderViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet
):
    lookup_field = "order_id"

    permission_classes = (IsAuthenticated,)
    queryset = DirectOrder.objects.all()

    def get_serializer_class(self):
        if self.action == "create":
            return DirectOrderCreateSerializer
        return DirectOrderSerializer

    def get_queryset(self):
        # buyers only see their own orders
        return DirectOrder.objects.filter(buyer=self.request.user)

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(qs, many=True)
        return ok("Buyer Orders retrieved", serializer.data)

    def retrieve(self, request, *args, **kwargs):
        order = self.get_object()
        serializer = self.get_serializer(order)
        return ok("Buyer Order retrieved", serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        try:
            order = serializer.save()
        except ValidationError as exc:
            print(exc)
            return fail(str(exc), status=status.HTTP_400_BAD_REQUEST)
        return ok("Order placed", DirectOrderSerializer(order).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"], url_path="count")
    def count(self, request):
        """
        GET /orders/direct/count/
        Returns how many orders *you* (buyer) have placed.
        """
        total = DirectOrder.objects.filter(buyer=request.user).count()
        return ok("Your order count", {"count": total})

    @action(detail=True, methods=["post"], url_path="request-contact")
    def request_contact(self, request, pk=None):
        order = self.get_object()
        send_vendor_order_sms(order.product.seller.phone_number, str(order.order_id))
        return ok("Vendor has been asked to contact you again")


class VendorOrderViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet
):
    lookup_field = "order_id"

    permission_classes = (IsAuthenticated, IsVendor)
    serializer_class = DirectOrderSerializer

    def get_queryset(self):
        # vendors see orders where they're the seller of the product
        return DirectOrder.objects.filter(product__seller=self.request.user)

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(qs, many=True)
        return ok("Vendor orders retrieved", serializer.data)

    def retrieve(self, request, *args, **kwargs):
        order = self.get_object()
        serializer = self.get_serializer(order)
        return ok("Vendor order retrieved", serializer.data)

    @action(detail=False, methods=["get"], url_path="count")
    def count(self, request):
        """
        GET /orders/vendor/count/
        Returns how many orders have been placed *for your products*.
        """
        total = DirectOrder.objects.filter(product__seller=request.user).count()
        return ok("Vendor order count", {"count": total})

    @action(detail=True, methods=["post"], url_path="mark-complete")
    def mark_complete(self, request, pk=None):
        order = self.get_object()
        if order.status == "completed":
            return fail("Order is already marked as completed", status=400)

        order.status = "completed"
        order.product.quantity -= order.quantity
        order.product.save(update_fields=["quantity"])
        order.save(update_fields=["status"])
        return ok("Order marked as completed")

    @action(detail=True, methods=["post"], url_path="cancel-order")
    def cancel_order(self, request, pk=None):
        order = self.get_object()
        if order.status == "canceled":
            return fail("Order is already canceled", status=400)

        order.status = "canceled"
        order.save(update_fields=["status"])
        return ok("Order Canceled")


class DirectBookingViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet
):
    lookup_field = "booking_id"

    permission_classes = (IsAuthenticated,)
    queryset = DirectBooking.objects.all()

    def get_serializer_class(self):
        return (
            DirectBookingCreateSerializer
            if self.action == "create"
            else DirectBookingSerializer
        )

    def get_queryset(self):
        # buyers see only their own
        return DirectBooking.objects.filter(buyer=self.request.user)

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        ser = self.get_serializer(page or qs, many=True)
        if page:
            return self.get_paginated_response(ser.data)
        return ok("Bookings retrieved", ser.data)

    def retrieve(self, request, *args, **kwargs):
        booking = self.get_object()
        return ok("Booking retrieved", self.get_serializer(booking).data)

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        try:
            booking = ser.save()
        except Exception as e:
            return fail(str(e), status=status.HTTP_400_BAD_REQUEST)
        return ok(
            "Booking created",
            DirectBookingSerializer(booking).data,
            status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["post"], url_path="request-contact")
    def request_contact(self, request, pk=None):
        booking = self.get_object()
        send_vendor_booking_sms(booking.service.provider.phone_number, str(booking.booking_id))
        return ok("Service provider has been asked to contact you again")


class ProviderBookingViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet
):
    lookup_field = "booking_id"

    permission_classes = (IsAuthenticated, IsVendor)
    serializer_class = DirectBookingSerializer

    def get_queryset(self):
        # providers see bookings where they’re the service owner
        return DirectBooking.objects.filter(service__provider=self.request.user)

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        ser = self.get_serializer(page or qs, many=True)
        if page:
            return self.get_paginated_response(ser.data)
        return ok("Provider bookings retrieved", ser.data)

    def retrieve(self, request, *args, **kwargs):
        booking = self.get_object()
        return ok("Provider booking retrieved", self.get_serializer(booking).data)

    @action(detail=True, methods=["post"], url_path="mark-complete")
    def mark_complete(self, request, pk=None):
        booking = self.get_object()
        if booking.status == "completed":
            return fail("Booking already completed", status=400)

        booking.status = "completed"
        booking.save(update_fields=["status"])
        return ok("Booking marked as completed")
























