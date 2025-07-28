from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from account import models as account_models


# Create your models here.
class BusinessStatus(models.TextChoices):
    PENDING = "pending", "Pending review"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


# def cert_upload(instance, filename):
#     return f"business_certificates/{instance.vendor.user_id}/{filename}"


def doc_upload(instance, filename):
    return f"business_docs/{instance.business_id}/{filename}"


class BusinessCategory(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Business Categories"


class Business(models.Model):
    vendor = models.ForeignKey('account.VendorProfile', on_delete=models.CASCADE, related_name="businesses")
    business_name = models.CharField(max_length=255, unique=True)
    tin_number = models.CharField(max_length=100, unique=True)
    business_category = models.ForeignKey(BusinessCategory, on_delete=models.CASCADE, related_name="businesses", null=True, blank=True)
    # business_type = models.CharField(max_length=100, null=True, blank=True)
    # business_presence = models.CharField(max_length=100,
    #                                      choices=(("Online", "Online"), ("Physical", "Physical"), ("Hybrid", "Hybrid")))
    business_active = models.BooleanField(default=False)
    business_location = models.URLField(blank=True)
    address = models.TextField(null=True, blank=True)
    district = models.ForeignKey('market_intelligence.District', on_delete=models.SET_NULL, null=True, blank=True)
    region = models.ForeignKey('market_intelligence.Region', on_delete=models.SET_NULL, null=True, blank=True)
    town = models.ForeignKey('market_intelligence.Town', on_delete=models.SET_NULL, null=True, blank=True)
    gps_code = models.CharField(max_length=20, null=True, blank=True)  # Ghana GPS location code
    business_email = models.EmailField(null=True, blank=True)
    business_phone = models.CharField(max_length=100, blank=True)
    business_phone_verified = models.BooleanField(default=False)
    business_email_verified = models.BooleanField(default=False)
    business_logo = models.ImageField(upload_to='business_logos/', null=True, blank=True)
    business_description = models.TextField(blank=True)
    # ghana_card_id = models.CharField(max_length=100)
    # certificate = models.FileField(upload_to=cert_upload)
    status = models.CharField(max_length=10, choices=BusinessStatus.choices, default=BusinessStatus.PENDING)
    admin_note = models.TextField(blank=True)
    latest_visit = models.DateTimeField(default=timezone.now)
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                 on_delete=models.SET_NULL, related_name="+")  # admin
    documents = GenericRelation('document_manager.Document', related_query_name='business')

    @property
    def prerequisites_met(self) -> bool:
        """All checks required before a business may be activated."""
        return (
                self.business_email_verified
                and self.business_phone_verified
                and self.status == BusinessStatus.APPROVED
        )

    def clean(self):
        # If someone tries to activate without prerequisites → error
        if self.business_active and not self.prerequisites_met:
            raise ValidationError(
                "Cannot activate: e-mail & phone must be verified and the "
                "business must be approved by an admin."
            )

    def save(self, *args, **kwargs):
        # Ensure clean() is always honoured
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.business_name} ({self.vendor.display_name})"

