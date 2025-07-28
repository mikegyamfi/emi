from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsSelf(BasePermission):
    """Allow user to act only on their own record (/users/me uses request.user so not needed)."""

    def has_object_permission(self, request, view, obj):
        return request.method in SAFE_METHODS or obj.pk == request.user.pk


class IsVendor(BasePermission):
    """True if request.user has vendor role."""

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and \
            request.user.role.filter(slug="vendor").exists()


class IsSelfOrAdmin(BasePermission):
    """Allow access if user is admin or acting on themselves."""

    def has_object_permission(self, request, view, obj):
        return request.user.is_staff or obj == request.user


class IsVendorAdminOrManager(BasePermission):
    """
    Allow only users who are vendor_administrators or vendor_managers.
    """
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user and user.is_authenticated and (
                hasattr(user, "vendor_admin_profile") or
                hasattr(user, "vendor_manager_profile")
            )
        )
