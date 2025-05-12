# core/otp_service.py
import secrets
import sqlite3

from django.db import transaction, IntegrityError
from django.utils import timezone
from core.models import OTP, OTPChannel, OTPPurpose
from core.utils import get_config


def _random_code(digits: int) -> str:
    return f"{secrets.randbelow(10 ** digits):0{digits}d}"


def generate_otp(*, user, purpose, channel: OTPChannel,
                 digits: int = 6, target: str | None = None) -> OTP:
    """
    Create (or recycle) an OTP: never raises IntegrityError.
    """
    if target is None:
        target = user.email if channel == OTPChannel.EMAIL else user.phone_number

    ttl = int(get_config().otp_expiry_minutes)
    expires = timezone.now() + timezone.timedelta(minutes=ttl)

    try:
        with transaction.atomic():
            return OTP.objects.create(
                user=user,
                purpose=purpose,
                channel=channel,
                code=_random_code(digits),
                target=target,
                expires_at=expires,
            )
    except IntegrityError:
        print("got here")
        # An un-verified OTP already exists → update & reuse it
        otp = OTP.objects.get(user=user, purpose=purpose, verified=False)
        print(otp)
        otp.channel = channel
        otp.target = target
        otp.code = _random_code(digits)
        otp.expires_at = expires
        otp.save(update_fields=["channel", "target", "code", "expires_at"])
        return otp
    except sqlite3.IntegrityError:
        print("got here")
        # An un-verified OTP already exists → update & reuse it
        otp = OTP.objects.get(user=user, purpose=purpose, verified=False)
        print(otp)
        otp.channel = channel
        otp.target = target
        otp.code = _random_code(digits)
        otp.expires_at = expires
        otp.save(update_fields=["channel", "target", "code", "expires_at"])
        return otp


def verify_otp(*, user, purpose: OTPPurpose, code: str) -> bool:
    """
    Return True ↔ code is correct, still valid, and now marked verified.
    Return False otherwise (invalid, expired, or already used).

    Caller can then decide what to do (raise ValidationError, etc.).
    """
    # Only one active OTP per (user,purpose) because of unique_together
    try:
        otp = OTP.objects.get(
            user=user,
            purpose=purpose,
            verified=False,
        )
    except OTP.DoesNotExist:
        return False

    # Match & check expiry
    if otp.code != code or otp.is_expired():
        return False

    # Mark as verified (idempotent)
    otp.delete()
    return True
