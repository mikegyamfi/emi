from datetime import timedelta

from django.conf import settings
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.contrib.contenttypes.fields import GenericRelation
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from core import utils
from market_intelligence.models import Region, Town, District


class CustomUserManager(BaseUserManager):
    """UserManager that uses *phone_number* as the canonical login key."""

    use_in_migrations = True

    def _create_user(self, phone_number, password=None, **extra_fields):
        if not phone_number:
            raise ValueError("The phone number must be set")

        phone_number = self.normalize_phone(phone_number)
        extra_fields.setdefault("email", None)  # email may be blank
        user = self.model(phone_number=phone_number, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    # ↓ helpers ----------------------------------------------------
    def normalize_phone(self, phone):
        # strip spaces, enforce leading “+” if you wish …
        return phone.strip()

    def create_user(self, phone_number, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(phone_number, password, **extra_fields)

    def create_superuser(self, phone_number, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(phone_number, password, **extra_fields)


class Role(models.Model):
    """
    System roles that can be assigned to users. e.g. buyer, vendor…
    """
    slug = models.SlugField(primary_key=True)
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name


# Create your models here.
class CustomUser(AbstractUser):
    """
    Custom user model extending Django's AbstractUser to include
    extra fields such as phone_number, status, unique_identifier,
    and user roles (aggregator, supplier, buyer, rider).
    """
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('pending', 'Pending Verification'),
    )
    # Extra Fields
    email = models.EmailField(unique=True, null=True, blank=True)
    phone_number = models.CharField(
        max_length=10,
        unique=True,
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='active',
        help_text="Account status."
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        help_text="Timestamp when the account was created."
    )
    last_login = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Timestamp of the last successful login."
    )
    role = models.ManyToManyField(
        max_length=100, blank=False, to=Role
    )
    active = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False)
    phone_verified = models.BooleanField(default=False)
    username = models.CharField(null=True, blank=True)

    USERNAME_FIELD = "phone_number"
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    def __str__(self):
        return f"{self.phone_number}"

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ["-date_joined"]


class UserProfile(models.Model):
    user_image = models.ImageField(upload_to='user_images', blank=True, null=True)
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE)

    def __str__(self):
        return self.user.phone_number


class VendorProfile(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    display_name = models.CharField(null=True, blank=True, max_length=250, unique=True)
    ghana_card_id = models.CharField(null=True, blank=True)
    ghana_card_verified = models.BooleanField(default=False)
    vendor_profile_verified = models.BooleanField(default=False)
    region = models.ForeignKey('market_intelligence.Region', on_delete=models.SET_NULL, null=True, blank=True)
    district = models.ForeignKey('market_intelligence.District', on_delete=models.SET_NULL, null=True, blank=True)
    town = models.ForeignKey('market_intelligence.Town', on_delete=models.SET_NULL, null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    bio = models.TextField(null=True, blank=True)
    documents = GenericRelation('document_manager.Document', related_query_name='vendor')

    # ───── verification helpers ──────────────────────────────
    @property
    def is_verified(self) -> bool:
        return self.ghana_card_verified and self.vendor_profile_verified

    def mark_verified(self, by_user=None) -> None:
        """Mark as verified & persist."""
        if not self.ghana_card_verified:
            self.ghana_card_verified = True
            self.save(update_fields=["ghana_card_verified"])


class AggregatorProfile(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE)


class AgentProfile(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE)


class VendorAdministratorProfile(models.Model):
    """
    Grants global “vendor administrator” privileges.
    """
    user = models.OneToOneField(
        'account.CustomUser',
        on_delete=models.CASCADE,
        related_name='vendor_admin_profile'
    )

    # in the custom user role, the role name is vendor_admin

    def __str__(self):
        return f"Vendor Administrator: {self.user.phone_number}"


class VendorManagerProfile(models.Model):
    """
    Grants scoped “vendor manager” privileges.
    Manager may be tied to:
      - one or more Regions, OR
      - one or more Districts, OR
      - one or more Towns.
    Cannot mix levels.
    """
    user = models.OneToOneField(
        'account.CustomUser',
        on_delete=models.CASCADE,
        related_name='vendor_manager_profile'
    )

    regions = models.ManyToManyField(
        Region, blank=True, related_name='vendor_managers'
    )
    districts = models.ManyToManyField(
        District, blank=True, related_name='vendor_managers'
    )
    towns = models.ManyToManyField(
        Town, blank=True, related_name='vendor_managers'
    )

    def clean(self):
        super().clean()
        if not (self.regions.exists() or
                self.districts.exists() or
                self.towns.exists()):
            raise ValidationError(
                "VendorManagerProfile must have at least one region, district, or town."
            )

    def save(self, *args, **kwargs):
        # full_clean won’t check M2M until after save, so save first then validate
        super().save(*args, **kwargs)
        # Now validate the m2m constraints
        try:
            self.clean()
        except ValidationError:
            # rollback if invalid
            raise

    def __str__(self):
        if self.regions.exists():
            juris = ", ".join(r.name for r in self.regions.all())
        elif self.districts.exists():
            juris = ", ".join(d.name for d in self.districts.all())
        elif self.towns.exists():
            juris = ", ".join(t.name for t in self.towns.all())
        else:
            juris = "–"
        return f"Vendor Manager ({juris}): {self.user.phone_number}"
