from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .serializers_vendor import VendorProfileAdminViewSet
from .vendor_views import BecomeVendorView, VendorMeView, VendorListView, VendorDetailView, AdminPromoteVendorView, \
    VerifyVendorGhanaCardView, VendorAdministratorViewSet, VendorManagerViewSet
from .views import SignUpView, VerifyEmailView, ResendActivationView, LoginView, RefreshView, VerifyView, LogoutView, \
    PasswordResetRequestView, PasswordResetConfirmView, MeView, ChangePasswordView, UserListView, UserDetailView, \
    VerifyPhoneView, ResendPhoneActivationView

app_name = 'account'

router = DefaultRouter()
router.register(r"vendor-administrators", VendorAdministratorViewSet, basename="vendor-admin")
router.register(r"vendor-managers", VendorManagerViewSet, basename="vendor-manager")
router.register(r"vendor-manager/vendors", VendorProfileAdminViewSet, basename="vendor-mgmt-vendors")

urlpatterns = [
    path("signup/", SignUpView.as_view(), name="signup"),
    path("verify-email/", VerifyEmailView.as_view(), name="verify-email"),
    path("resend-activation/", ResendActivationView.as_view(), name="resend-activation"),
    path("verify-phone/", VerifyPhoneView.as_view()),
    path("resend-phone-activation/", ResendPhoneActivationView.as_view()),
    path("login/", LoginView.as_view(), name="token_obtain_pair"),
    path("refresh/", RefreshView.as_view(), name="token_refresh"),
    path("verify/", VerifyView.as_view(), name="token_verify"),
    path("logout/", LogoutView.as_view(), name="token_blacklist"),
    path("password-reset/", PasswordResetRequestView.as_view(),
         name="password_reset_request"),
    path("password-reset/confirm/", PasswordResetConfirmView.as_view(),
         name="password_reset_confirm"),
    path("users/me/", MeView.as_view(), name="user_me"),
    path("users/change-password/", ChangePasswordView.as_view(), name="change_password"),
    path("users/", UserListView.as_view(), name="user_list"),
    path("users/<int:pk>/", UserDetailView.as_view(), name="user_detail"),

    path("vendors/become_a_vendor/", BecomeVendorView.as_view(), name="become_vendor"),
    path("vendors/me/", VendorMeView.as_view(), name="vendor_me"),

    # admin endpoints
    path("vendors/", VendorListView.as_view(), name="vendor_list"),
    path("vendors/<int:pk>/", VendorDetailView.as_view(), name="vendor_detail"),
    path("vendors/<int:user_id>/promote/",
         AdminPromoteVendorView.as_view(),
         name="admin_promote_vendor"),
    path(
        "admin/vendors/<int:vendor_id>/verify-ghana-card/",
        VerifyVendorGhanaCardView.as_view(),
    ),
    path("vendor_mgt/", include(router.urls)),
]
