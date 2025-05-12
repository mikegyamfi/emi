# market_intel/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CategoryViewSet, TagViewSet,
    ProductViewSet, ListingViewSet, RegionViewSet, DistrictViewSet, TownViewSet, MarketViewSet, ExplorerView,
    MarketProductView, ProductComparisonView, ServiceViewSet, ServiceComparisonView, GlobalSearchView, AutoCompleteView,
    RegionSearchView, DistrictSearchView, TownSearchView,
)

app_name = 'market_intelligence'

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("tags",       TagViewSet,       basename="tag")
router.register("products",   ProductViewSet,   basename="product")
router.register("services",  ServiceViewSet,  basename="services")
router.register("listings",   ListingViewSet,   basename="listing")
router.register("regions",   RegionViewSet,   basename="region")
router.register("districts", DistrictViewSet, basename="district")
router.register("towns",     TownViewSet,     basename="town")
router.register("markets",   MarketViewSet,   basename="market")
router.register(r"search/regions", RegionSearchView, basename="search-regions")
router.register(r"search/districts", DistrictSearchView, basename="search-districts")
router.register(r"search/towns", TownSearchView, basename="search-towns")

urlpatterns = [
    path("", include(router.urls)),
]

urlpatterns += [
    path("explorer/", ExplorerView.as_view(), name="explorer"),
    path("markets/<int:pk>/products/",
         MarketProductView.as_view(), name="market-products"),
    path("products/<int:pk>/compare/",
         ProductComparisonView.as_view(), name="product-compare"),
    path("services/<int:pk>/compare/",          # NEW
         ServiceComparisonView.as_view(), name="service-compare"),
    path("search/", GlobalSearchView.as_view(),      name="global-search"),
    path("search/autocomplete/", AutoCompleteView.as_view(),
         name="search-autocomplete"),
]












