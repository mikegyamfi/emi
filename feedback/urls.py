from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import FeedbackViewSet, FeedbackTagViewSet

router = DefaultRouter()
router.register(r'feedback', FeedbackViewSet, basename='feedback')
router.register(r'feedback-tags', FeedbackTagViewSet, basename='feedback-tag')

app_name = 'feedback'

urlpatterns = [
    path('', include(router.urls)),
]