from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


# Create your models here.
def doc_upload(instance, filename):
    # put under a predictable path, grouped by parent type + id
    parent = f"{instance.content_type.model}_{instance.object_id}"
    return f"generic_docs/{parent}/{filename}"


class DocumentType(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Document(models.Model):
    # polymorphic keys
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    document_type = models.ForeignKey(DocumentType, on_delete=models.CASCADE, related_name="documents")
    doc = models.FileField(upload_to=doc_upload)
    label = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
        ]

    def __str__(self):
        return f"{self.document_type.name} for {self.content_object}"
