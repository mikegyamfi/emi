# admin.py

from django.contrib import admin
from .models import DirectOrder, VendorNotification, DirectBooking


@admin.register(DirectOrder)
class DirectOrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_id",
        "buyer",
        "product",
        "quantity",
        "full_name",
        "email",
        "phone",
        "created_at",
    )
    search_fields = (
        "order_id",
        "buyer__username",
        "buyer__email",
        "product__name",
        "full_name",
        "email",
        "phone",
    )
    list_filter = (
        "created_at",
        "region",
        "district",
    )
    raw_id_fields = (
        "buyer",
        "product",
        "region",
        "district",
    )
    readonly_fields = (
        "order_id",
        "created_at",
    )
    date_hierarchy = "created_at"
    list_select_related = (
        "buyer",
        "product",
        "region",
        "district",
    )


@admin.register(VendorNotification)
class VendorNotificationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "buyer",
        "product",
        "service",
        "quantity",
        "location",
        "delivered_at",
        "read",
    )
    search_fields = (
        "buyer__username",
        "buyer__email",
        "product__name",
        "service__title",
    )
    list_filter = (
        "delivered_at",
        "read",
    )
    raw_id_fields = (
        "buyer",
        "product",
        "service",
    )
    readonly_fields = (
        "delivered_at",
        "read",
    )
    date_hierarchy = "delivered_at"


@admin.register(DirectBooking)
class DirectBookingAdmin(admin.ModelAdmin):
    list_display = (
        "booking_id",
        "buyer",
        "service",
        "created_at",
    )
    search_fields = (
        "booking_id",
        "buyer__username",
        "buyer__email",
        "service__title",
        "message",
    )
    list_filter = (
        "created_at",
    )
    raw_id_fields = (
        "buyer",
        "service",
    )
    readonly_fields = (
        "booking_id",
        "created_at",
    )
    date_hierarchy = "created_at"
