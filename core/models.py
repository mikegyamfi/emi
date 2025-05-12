from django.conf import settings
from django.db import models

# Create your models here.
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone


class SiteConfig(models.Model):
    """
    Exactly ONE row – holds mutable settings for the whole site.
    """
    # ------------- security / auth ------------------- #
    otp_expiry_minutes = models.PositiveSmallIntegerField(
        default=10,
        validators=[MinValueValidator(1), MaxValueValidator(60)],
        help_text="Minutes before an e-mail OTP expires."
    )
    # ------------- misc examples --------------------- #
    support_email = models.EmailField(default="support@example.com")
    throttle_anon_per_min = models.PositiveSmallIntegerField(default=20)

    updated_at = models.DateTimeField(auto_now=True)

    # ---- singleton enforcement ---------------------- #
    def save(self, *args, **kwargs):
        self.pk = 1  # force the primary key
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Site configuration"
        verbose_name_plural = "Site configuration"

    def __str__(self):
        return "Site configuration"


def expiry_default():
    from core.utils import get_config
    mins = int(get_config().otp_expiry_minutes)
    return timezone.now() + timezone.timedelta(minutes=mins)


class OTPChannel(models.TextChoices):
    EMAIL = "email", "E-mail"
    SMS = "sms", "SMS"


class OTPPurpose(models.TextChoices):
    USER_EMAIL = "user_email", "User e-mail verification"
    USER_PHONE = "user_phone", "User phone verification"
    BUSINESS_EMAIL = "business_email", "Business e-mail verification"
    BUSINESS_PHONE = "business_phone", "Business phone verification"
    PASSWORD_RESET_CODE = "password_reset", "Password Reset"


class OTP(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    purpose = models.CharField(max_length=30, choices=OTPPurpose.choices)
    channel = models.CharField(max_length=10, choices=OTPChannel.choices)
    code = models.CharField(max_length=8, db_index=True)
    target = models.CharField(max_length=255)  # e-mail or phone
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=expiry_default)
    verified = models.BooleanField(default=False)

    class Meta:
        unique_together = (("user", "purpose", "verified"),)

    def is_expired(self):
        return timezone.now() >= self.expires_at
