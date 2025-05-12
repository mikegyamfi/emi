# product_service/urls.py
# =============================================================
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .admin_views import AdminProductViewSet, AdminServiceViewSet, AdminBusinessViewSet, AdminSellerOverview
from .views import (
    PublicProductViewSet, PublicServiceViewSet, PublicCategoryTree,
    RandomProducts, RandomServices, GlobalSearch,
    SellerProductViewSet, SellerServiceViewSet,
    TagViewSet, AttributeViewSet, SKUViewSet, PublicCategoryDetail, ProductImageViewSet, ProductSearchView,
    ServiceSearchView, BusinessSearchView, SellerSearchView, ServiceImageViewSet, CategorySearchView, VendorSKUViewSet,
    SKUSearchView, CategorySKUList, ProductConditionViewSet, ProductServiceStatusViewSet, ServicePricingChoiceViewSet,
)

app_name = 'product_service_mgt'

router = DefaultRouter()
# public
router.register(r'products', PublicProductViewSet, basename="product")
router.register(r'services', PublicServiceViewSet, basename="service")
router.register(r'tags', TagViewSet, basename="tag")
router.register(r'attributes', AttributeViewSet, basename="attribute")
router.register(r'sku', SKUViewSet, basename="sku")
router.register(r"my_sku", VendorSKUViewSet,  basename="my-sku")
router.register(r'product-images', ProductImageViewSet, basename='product-image')
router.register(r'service-images', ServiceImageViewSet, basename='service-image')
router.register(r"search/product-categories", CategorySearchView, basename="search-categories")
router.register(r'product-conditions', ProductConditionViewSet,   basename='product-condition')
router.register(r'product-statuses', ProductServiceStatusViewSet, basename='product-status')
router.register(r"pricing-choices", ServicePricingChoiceViewSet, basename="pricing-choice")

# seller / business dashboards
router.register(r"my_products_management", SellerProductViewSet, basename="my-products")
router.register(r'my_services_management', SellerServiceViewSet, basename="my-services")

admin_router = DefaultRouter()
admin_router.register("admin_mgt/products",  AdminProductViewSet,  basename="admin-products")
admin_router.register("admin_mgt/services",  AdminServiceViewSet,  basename="admin-services")
admin_router.register("admin_mgt/businesses", AdminBusinessViewSet, basename="admin-businesses")


urlpatterns = [
    path("", include(router.urls)),
    path("", include(admin_router.urls)),
    path("admin/sellers/<int:seller_pk>/overview/",
         AdminSellerOverview.as_view(),
         name="admin-seller-overview"),

    # tree & discovery
    path("categories/tree/", PublicCategoryTree.as_view(), name="category-tree"),
    path("categories/<int:pk>/", PublicCategoryDetail.as_view()),
    path("products_mgt/random/", RandomProducts.as_view(), name="random-products"),
    path("services_mgt/random/", RandomServices.as_view(), name="random-services"),

    path("my/services/<uuid:pk>/activate/",   SellerServiceViewSet.as_view({"post": "activate"})),
    path("my/services/<uuid:pk>/deactivate/", SellerServiceViewSet.as_view({"post": "deactivate"})),

    # global fuzzy search
    path("search/", GlobalSearch.as_view(), name="global-search"),
    path("search/products/",   ProductSearchView.as_view(), name="search-products"),
    path("search/services/",   ServiceSearchView.as_view(), name="search-services"),
    path("search/businesses/", BusinessSearchView.as_view(), name="search-businesses"),
    path("search/sellers/",    SellerSearchView.as_view(), name="search-sellers"),
    path("sku/search/", SKUSearchView.as_view(),  name="sku-search"),
    path("sku/by-category/<int:pk>/", CategorySKUList.as_view(), name="sku-by-category"),
]







