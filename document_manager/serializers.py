# document_manager/serializers.py
from rest_framework import serializers

from account.models import VendorProfile
from document_manager.models import Document, DocumentType
from business.models import Business


class BusinessDocumentSerializer(serializers.ModelSerializer):
    document_type = serializers.PrimaryKeyRelatedField(
        queryset=DocumentType.objects.all()
    )
    label = serializers.CharField(required=False, allow_blank=True)
    name = serializers.CharField(source='document_type')

    class Meta:
        model = Document
        fields = ("id", "document_type", "name", "label", "doc", "created_at")
        read_only_fields = ("id", "created_at")

    # bind the uploaded doc to the Business passed in context
    def create(self, validated):
        business: Business = self.context["business"]
        validated["content_object"] = business  # GenericForeignKey
        return super().create(validated)


class DocumentTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentType
        fields = ("id", "name", "description")


class VendorDocumentUploadSerializer(serializers.ModelSerializer):
    """
    Upload a single document (front or back image) for the vendor.
    """
    document_type = serializers.PrimaryKeyRelatedField(
        queryset=DocumentType.objects.all(
    )
    )
    label = serializers.CharField(required=False, allow_blank=True, max_length=120)

    class Meta:
        model = Document
        fields = ("id", "document_type", "label", "doc", "created_at")
        read_only_fields = ("id", "created_at")

    def create(self, validated):
        # The view injects 'vendor' into context
        vendor: VendorProfile = self.context["vendor"]
        validated["content_object"] = vendor  # Generic FK
        return super().create(validated)


class VendorDocumentListSerializer(serializers.ModelSerializer):
    """
    Read-only representation for GET /…/documents/
    """
    document_type = serializers.StringRelatedField()

    class Meta:
        model = Document
        fields = ("id", "document_type", "label", "doc", "created_at")
