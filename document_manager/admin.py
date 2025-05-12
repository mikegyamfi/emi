# document_manager/admin.py
from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline
from django.urls import reverse
from django.utils.html import format_html

from .models import DocumentType, Document


# ────────────────────────────────────────────────────────────
# 1.  Generic inline  (re-use in other apps if you wish)
# ────────────────────────────────────────────────────────────
class DocumentInline(GenericTabularInline):
    """
    Usage example in another app’s admin:

        from document_manager.admin import DocumentInline

        @admin.register(VendorProfile)
        class VendorProfileAdmin(admin.ModelAdmin):
            inlines = (DocumentInline,)
    """
    model = Document
    extra = 0
    fields = ("document_type", "label", "doc", "created_at")
    readonly_fields = ("created_at",)
    autocomplete_fields = ("document_type",)
    verbose_name_plural = "Attached documents"


# ────────────────────────────────────────────────────────────
# 2.  DocumentType  (simple lookup table)
# ────────────────────────────────────────────────────────────
@admin.register(DocumentType)
class DocumentTypeAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "description", "created_at")
    search_fields = ("name",)
    readonly_fields = ("created_at",)
    date_hierarchy = "created_at"
    ordering = ("-created_at",)


# ────────────────────────────────────────────────────────────
# 3.  Document  (generic FK viewer)
# ────────────────────────────────────────────────────────────
@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "document_type", "parent_link", "label", "doc_link", "created_at")
    list_filter = ("document_type", "content_type")
    search_fields = ("label", "document_type__name")
    readonly_fields = ("created_at",)
    autocomplete_fields = ("document_type",)

    date_hierarchy = "created_at"
    ordering = ("-created_at",)

    # ----- helpers ------------------------------------------------ #
    @admin.display(description="Attached to", ordering="content_type")
    def parent_link(self, obj: Document):
        if obj.content_object:
            url = reverse(
                f"admin:{obj.content_type.app_label}_{obj.content_type.model}_change",
                args=(obj.object_id,),
            )
            return format_html('<a href="{}">{}</a>', url, obj.content_object)
        return "—"

    @admin.display(description="File")
    def doc_link(self, obj: Document):
        if obj.doc:
            return format_html('<a href="{}" target="_blank">download</a>', obj.doc.url)
        return "—"
