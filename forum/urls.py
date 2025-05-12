from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CategoryViewSet, ThreadViewSet, ReplyViewSet, ForumNotificationViewSet


app_name = 'forum'

router = DefaultRouter()
router.register(r'categories', CategoryViewSet)
router.register(r'threads', ThreadViewSet)
router.register(r'replies', ReplyViewSet)
router.register(r'notifications', ForumNotificationViewSet, basename='notifications')

urlpatterns = [
    path('', include(router.urls)),
]










