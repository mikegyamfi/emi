from django.contrib import admin
from django.utils.html import format_html

from .models import Cart, CartItem


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    readonly_fields = ("unit_price", "subtotal")
    fields = ("product", "quantity", "unit_price", "subtotal")
    raw_id_fields = ("product",)


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = (
        "cart_id",
        "user",
        "session_key",
        "created_at",
        "updated_at",
        "total_display",
    )
    list_filter = ("user",)
    search_fields = ("cart_id", "user__username", "session_key")
    raw_id_fields = ("user",)
    inlines = (CartItemInline,)

    def total_display(self, obj):
        return obj.total
    total_display.short_description = "Total"


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = (
        "cart_item_id",
        "cart_link",
        "product_link",
        "quantity",
        "unit_price",
        "subtotal",
    )
    list_filter = ("cart", "product")
    search_fields = (
        "cart_item_id",
        "cart__cart_id",
        "product__name",
    )
    raw_id_fields = ("cart", "product")
    readonly_fields = ("unit_price", "subtotal")

    def cart_link(self, obj):
        url = f"/admin/{obj._meta.app_label}/{Cart._meta.model_name}/{obj.cart.pk}/change/"
        return format_html('<a href="{}">{}</a>', url, obj.cart.cart_id)
    cart_link.short_description = "Cart"

    def product_link(self, obj):
        url = f"/admin/{obj._meta.app_label}/product/{obj.product.pk}/change/"
        return format_html('<a href="{}">{}</a>', url, obj.product)
    product_link.short_description = "Product"
