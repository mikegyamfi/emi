# account/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html

from .models import (
    CustomUser,
    Role,
    UserProfile,
    VendorProfile,
    AggregatorProfile,
    AgentProfile,
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


# ────────────────────────────────────────────────────────────
#  CustomUser admin
# ────────────────────────────────────────────────────────────
@admin.register(CustomUser)
class UserAdmin(BaseUserAdmin):
    ordering = ("-date_joined",)
    list_display = (
        "email", "first_name", "last_name", 'phone_number',
        "get_roles", "email_verified", "phone_verified", "is_staff", "date_joined",
    )
    list_filter = ("email_verified", "is_staff", "is_superuser", "role__slug")
    search_fields = ("email", "first_name", "last_name")
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
    )

    def get_roles(self, obj):
        slugs = obj.role.values_list("slug", flat=True)
        return ", ".join(slugs).upper()

    get_roles.short_description = "Roles"

    # remove username column inherited from AbstractUser
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if "username" in form.base_fields:
            form.base_fields["username"].widget = admin.widgets.AdminTextInputWidget()
            form.base_fields["username"].required = False
            form.base_fields["username"].help_text = "Unused (kept for compatibility)."
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


admin.site.register(VendorProfile)












