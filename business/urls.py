from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import VendorBusinessViewSet, AdminBusinessViewSet, ResendBusinessEmailOTPView, VerifyBusinessEmailOTPView, \
    ResendBusinessPhoneOTPView, VerifyBusinessPhoneOTPView, BusinessCategoryViewSet, BusinessCategorySearchView

vendor_router = DefaultRouter()
vendor_router.register(r"vendor_businesses", VendorBusinessViewSet, basename="vendor-business")

admin_router = DefaultRouter()
admin_router.register(r"admin/businesses", AdminBusinessViewSet, basename="admin-business")

business_router = DefaultRouter()
business_router.register(r"business-categories", BusinessCategoryViewSet, basename="business-category")
business_router.register(r"search/business-categories",
                         BusinessCategorySearchView, basename="search-business-cats")

urlpatterns = [
    path("otp/email/resend/", ResendBusinessEmailOTPView.as_view()),
    path("otp/email/verify/", VerifyBusinessEmailOTPView.as_view()),
    path("otp/phone/resend/", ResendBusinessPhoneOTPView.as_view()),
    path("otp/phone/verify/", VerifyBusinessPhoneOTPView.as_view()),
    path("", include(vendor_router.urls)),
    path("", include(admin_router.urls)),
    path("", include(business_router.urls)),
]
