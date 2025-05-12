"""
URL configuration for emi_skeleton project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from django.conf import settings

urlpatterns = [
                  path('admin/', admin.site.urls),
                  path('api/v1/auth/', include('account.urls')),
                  path('api/v1/business/', include('business.urls')),
                  path('api/v1/cart_management/', include('cart_management.urls')),
                  path('api/v1/checkout_processing/', include('checkout_processing.urls')),
                  path('api/v1/market_intelligence/', include('market_intelligence.urls')),
                  path('api/v1/product_service_mgt/', include('product_service_management.urls')),
                  path('api/v1/feedback_management/', include('feedback.urls')),
                  path('api/v1/forum/', include('forum.urls')),
                  path('api/v1/document_manager/', include('document_manager.urls')),
                  path("schema/", SpectacularAPIView.as_view(), name="schema"),  # raw OpenAPI json
                  path("swagger/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
                  path("redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),

              ] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL, document_root=settings.MEDIA_ROOT
    )































































































































































