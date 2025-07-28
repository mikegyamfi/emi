# account/admin.py

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.db import IntegrityError

from .models import (
    CustomUser,
    Role,
    UserProfile,
    VendorProfile,
    AggregatorProfile,
    AgentProfile, VendorManagerProfile, VendorAdministratorProfile,
)


# ────────────────────────────────────────────────────────────
#  Inline definitions
# ────────────────────────────────────────────────────────────
class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    extra = 0


class VendorProfileInline(admin.StackedInline):
    model = VendorProfile
    can_delete = False
    extra = 0
    verbose_name_plural = "Vendor profile"


class AggregatorProfileInline(admin.StackedInline):
    model = AggregatorProfile
    can_delete = False
    extra = 0
    verbose_name_plural = "Aggregator profile"


class AgentProfileInline(admin.StackedInline):
    model = AgentProfile
    can_delete = False
    extra = 0
    verbose_name_plural = "Agent profile"


class VendorManagerInline(admin.StackedInline):
    model = VendorManagerProfile
    can_delete = False
    extra = 0
    verbose_name_plural = "Vendor Manager profile"


class VendorAdminInline(admin.StackedInline):
    model = VendorAdministratorProfile
    can_delete = False
    extra = 0
    verbose_name_plural = "Vendor Admin profile"


# ────────────────────────────────────────────────────────────
#  CustomUser admin
# ────────────────────────────────────────────────────────────
@admin.register(CustomUser)
class UserAdmin(BaseUserAdmin):
    ordering = ("-date_joined",)
    list_display = (
        "email", "first_name", "last_name", "phone_number",
        "get_roles", "email_verified", "phone_verified", "is_staff", "date_joined",
    )
    list_filter = ("email_verified", "is_staff", "is_superuser", "role__slug")
    search_fields = ("email", "first_name", "last_name", "phone_number")
    readonly_fields = ("date_joined", "last_login")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "phone_number")}),
        ("Status", {"fields": ("email_verified", "phone_verified", "active", "is_staff", "is_superuser")}),
        ("Roles", {"fields": ("role",)}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "phone_number", "password1", "password2"),
        }),
    )

    inlines = (
        UserProfileInline,
        VendorProfileInline,
        AggregatorProfileInline,
        AgentProfileInline,
        VendorManagerInline,
        VendorAdminInline,
    )

    def get_roles(self, obj):
        slugs = obj.role.values_list("slug", flat=True)
        return ", ".join(slugs).upper()
    get_roles.short_description = "Roles"

    # Remove username field requirement
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if "username" in form.base_fields:
            f = form.base_fields["username"]
            f.widget = admin.widgets.AdminTextInputWidget()
            f.required = False
            f.help_text = "Unused (kept for compatibility)."
        return form

    def has_delete_permission(self, request, obj=None):
        return True


# ────────────────────────────────────────────────────────────
#  Role admin
# ────────────────────────────────────────────────────────────
@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("slug", "name")
    ordering = ("slug",)
    search_fields = ("slug", "name")


# ────────────────────────────────────────────────────────────
#  VendorProfile admin
# ────────────────────────────────────────────────────────────
@admin.register(VendorProfile)
class VendorProfileAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'display_name', 'ghana_card_id', 'is_verified',
        'region', 'district', 'town', 'date_of_birth'
    )
    list_filter = (
        'ghana_card_verified', 'vendor_profile_verified',
        'region', 'district', 'town'
    )
    search_fields = (
        'display_name', 'ghana_card_id', 'user__phone_number', 'user__email'
    )
    readonly_fields = ('ghana_card_verified', 'vendor_profile_verified')

    def delete_model(self, request, obj):
        """
        When deleting a VendorProfile, also strip the 'vendor' role.
        """
        try:
            vendor_role = Role.objects.get(slug='vendor')
            obj.user.role.remove(vendor_role)
        except Role.DoesNotExist:
            pass
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        """
        Bulk delete: remove the 'vendor' role from each user.
        """
        try:
            vendor_role = Role.objects.get(slug='vendor')
            for vp in queryset:
                vp.user.role.remove(vendor_role)
        except Role.DoesNotExist:
            pass
        super().delete_queryset(request, queryset)


admin.site.register(VendorManagerProfile)
admin.site.register(VendorAdministratorProfile)
