# product_service_management/admin_filters.py
from django_filters import rest_framework as df
from .models import VendorProduct, VendorService
from business.models import Business


class AdminProductFilter(df.FilterSet):
    seller = df.NumberFilter(field_name="seller_id")
    business = df.NumberFilter(field_name="business_id")
    is_active = df.BooleanFilter()

    class Meta:
        model = VendorProduct
        # no Meta.fields list, so only the three declared above will be used
        fields = []


class AdminServiceFilter(df.FilterSet):
    provider = df.NumberFilter(field_name="provider_id")
    business = df.NumberFilter(field_name="business_id")
    is_active = df.BooleanFilter()

    class Meta:
        model = VendorService
        fields = []


class AdminBusinessFilter(df.FilterSet):
    owner = df.NumberFilter(field_name="owner_id")
    business_active = df.BooleanFilter(field_name="is_active")

    class Meta:
        model = Business
        fields = []
