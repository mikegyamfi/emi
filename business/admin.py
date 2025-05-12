# business/admin.py
from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline
from django.utils.html import format_html
from django.utils.timezone import localtime

from document_manager.models import Document
from .models import Business, BusinessStatus, BusinessCategory


# ────────────────────────────────────────────────────────────
#  Inline docs (shown inside Business)
# ────────────────────────────────────────────────────────────
class DocumentInline(GenericTabularInline):
    model = Document
    extra = 0
    fields = ("document_type", "label", "doc", "created_at")
    readonly_fields = ("created_at",)


# ────────────────────────────────────────────────────────────
#  Custom admin for Business
# ────────────────────────────────────────────────────────────
@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    inlines = (DocumentInline,)

    # -------- list view ------------------------------------ #
    list_display = (
        "business_name",
        "vendor_display",
        "status",
        "submitted_local",
        "reviewed_local",
    )
    list_filter = ("status",)
    search_fields = (
        "business_name",
        "vendor__display_name",
        "vendor__user__email",
    )
    date_hierarchy = "submitted_at"
    ordering = ("-submitted_at",)

    # -------- form layout ---------------------------------- #
    readonly_fields = (
        "submitted_at",
        "reviewed_at",
        "latest_visit",
        "reviewer",
        "logo_preview",
    )
    fieldsets = (
        ("Business info", {
            "fields": (
                "vendor",
                "business_name",
                ("business_type", "business_active"),
                ("business_email", "business_phone"),
                "business_location",
                "business_description",
            )
        }),
        ("Status", {
            "fields": (
                "status",
                "admin_note",
                ("submitted_at", "reviewed_at", "reviewer"),
                "latest_visit",
            )
        }),
        ("Media", {
            "fields": ("business_logo", "logo_preview")
        }),
    )

    list_editable = ("status",)

    # -------- custom actions ------------------------------- #
    actions = ["approve_selected", "reject_selected"]

    # -------------------------------------------------------- #
    #      helper / presentation methods
    # -------------------------------------------------------- #
    def vendor_display(self, obj):
        return f"{obj.vendor.display_name} ({obj.vendor.user.email})"

    vendor_display.short_description = "Vendor"

    def status_colored(self, obj):
        color = {
            BusinessStatus.PENDING: "#ff9800",
            BusinessStatus.APPROVED: "#4caf50",
            BusinessStatus.REJECTED: "#f44336",
        }[obj.status]
        return format_html(
            '<span style="color:{}; font-weight:600;">{}</span>', color, obj.get_status_display()
        )

    status_colored.short_description = "Status"

    def certificate_link(self, obj):
        if obj.certificate:
            return format_html(
                '<a href="{}" target="_blank">📑 Download</a>',
                obj.certificate.url
            )
        return "—"

    certificate_link.short_description = "Certificate"

    def logo_preview(self, obj):
        if obj.business_logo:
            return format_html('<img src="{}" style="max-height:120px;">', obj.business_logo.url)
        return "—"

    logo_preview.short_description = "Logo preview"

    def submitted_local(self, obj):
        return localtime(obj.submitted_at).strftime("%Y-%m-%d %H:%M")

    submitted_local.short_description = "Submitted"

    def reviewed_local(self, obj):
        if obj.reviewed_at:
            return localtime(obj.reviewed_at).strftime("%Y-%m-%d %H:%M")
        return "—"

    reviewed_local.short_description = "Reviewed"

    # -------- bulk actions --------------------------------- #
    def approve_selected(self, request, queryset):
        updated = queryset.filter(status=BusinessStatus.PENDING) \
            .update(status=BusinessStatus.APPROVED)
        self.message_user(request, f"{updated} business(es) approved.")

    approve_selected.short_description = "Approve selected businesses"

    def reject_selected(self, request, queryset):
        updated = queryset.filter(status=BusinessStatus.PENDING) \
            .update(status=BusinessStatus.REJECTED)
        self.message_user(request, f"{updated} business(es) rejected.")

    reject_selected.short_description = "Reject selected businesses"


admin.site.register(BusinessCategory)

