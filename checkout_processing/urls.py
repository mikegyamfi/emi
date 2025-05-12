from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DirectOrderViewSet, VendorOrderViewSet, DirectBookingViewSet, ProviderBookingViewSet

router = DefaultRouter()
router.register(r"orders/direct", DirectOrderViewSet, basename="direct-order")
router.register(r"orders/vendor", VendorOrderViewSet, basename="vendor-order")
router.register(r"bookings/direct", DirectBookingViewSet, basename="booking")
router.register(r"bookings/provider", ProviderBookingViewSet, basename="provider-booking")

urlpatterns = [
    path("", include(router.urls)),
]



