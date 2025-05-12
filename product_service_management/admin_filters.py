from django_filters import rest_framework as df

from business.models import Business
from .models import Product, Service


class AdminProductFilter(df.FilterSet):
    seller = df.NumberFilter(field_name="seller_id")
    business = df.NumberFilter(field_name="business_id")

    class Meta:
        model = Product
        fields = ["seller", "business", "is_active", "category"]


class AdminServiceFilter(df.FilterSet):
    provider = df.NumberFilter(field_name="provider_id")  # alias
    business = df.NumberFilter(field_name="business_id")

    class Meta:
        model = Service
        fields = ["provider", "business", "is_active", "category"]


class AdminBusinessFilter(df.FilterSet):
    owner = df.NumberFilter(field_name="owner_id")

    class Meta:
        model = Business
        fields = ["owner", "business_active"]
