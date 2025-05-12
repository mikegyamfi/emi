from django.contrib import admin, messages
from django.utils.safestring import mark_safe
from django.utils import timezone

from .models import SiteConfig, OTP, OTPChannel, OTPPurpose


# ────────────────────────────────────────────────────────────
# 1.  Singleton “Site configuration”
# ────────────────────────────────────────────────────────────
@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    """
    There should **always be exactly one** `SiteConfig` row.
    * hides the “Add” button
    * redirects the changelist straight to the singleton record
    """

    # Show the most relevant knobs at a glance
    list_display = (
        "otp_expiry_minutes",
        "support_email",
        "throttle_anon_per_min",
        "updated_at",
    )
    readonly_fields = ("updated_at",)

    # ---------- enforce singleton -----------------------------
    def has_add_permission(self, request):
        """Disallow “Add” once the singleton exists."""
        return not SiteConfig.objects.exists()

    def changelist_view(self, request, extra_context=None):
        """
        If the singleton exists, jump straight to the edit form;
        otherwise fall back to default changelist (which will show the
        “Add” button).
        """
        qs = SiteConfig.objects.all()
        if qs.exists():
            obj = qs.first()
            return self.change_view(request, str(obj.pk))
        return super().changelist_view(request, extra_context)


# ────────────────────────────────────────────────────────────
# 2.  One-time passwords (OTP)
# ────────────────────────────────────────────────────────────
@admin.register(OTP)
class OTPAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "purpose",
        "channel",
        "code",
        "target",
        "created_at",
        "expires_at",
        "verified",
        "is_expired_display",
    )
    list_filter = (
        "verified",
        "purpose",
        "channel",
    )
    search_fields = (
        "user__email",
        "user__username",
        "code",
        "target",
    )
    readonly_fields = (
        "user",
        "purpose",
        "channel",
        "code",
        "target",
        "created_at",
        "expires_at",
        "verified",
        "is_expired_display",
    )
    ordering = ("-created_at",)

    # ---------- helpers --------------------------------------
    @admin.display(boolean=True, description="Expired?")
    def is_expired_display(self, obj):
        return timezone.now() >= obj.expires_at

    # OTP rows are **audit records** – disallow edits / deletes
    def has_add_permission(self, request):
        return True

    def has_change_permission(self, request, obj=None):  # read-only
        # allow detail *view* but stop saving
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return False

    def has_delete_permission(self, request, obj=None):
        return True
