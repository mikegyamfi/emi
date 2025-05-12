# business/urls.py
from django.urls import path
from .views import BusinessDocumentView, VendorDocumentListCreateView, DocumentTypeListView, \
    BusinessDocumentListView

app_name = 'document_manager'

urlpatterns = [
    path("document-types/", DocumentTypeListView.as_view()),
    path("businesses/<int:pk>/documents/", BusinessDocumentView.as_view()),
    path("vendor/documents/", VendorDocumentListCreateView.as_view()),
]
