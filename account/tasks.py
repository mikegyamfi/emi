import logging
from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.mail.backends.base import BaseEmailBackend
from django.template.loader import render_to_string, TemplateDoesNotExist
from django.utils import timezone
from django.utils.html import strip_tags

from core.models import OTP, OTPChannel, OTPPurpose

log = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# USER  E-mail verification
# ----------------------------------------------------------------------
@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_user_email_otp(self, otp_id: int):
    _dispatch_email_otp(
        task=self,
        otp_id=otp_id,
        expected_purpose=OTPPurpose.USER_EMAIL,
        html_template="account/emails/send_activation_otp.html",
        subject="Verify your e-mail address",
    )


# ----------------------------------------------------------------------
# USER  Phone (SMS) verification
# ----------------------------------------------------------------------
@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_user_phone_otp(self, otp_id: int):
    _dispatch_sms_otp(self, otp_id, expected_purpose=OTPPurpose.USER_PHONE)


# ----------------------------------------------------------------------
# BUSINESS  E-mail verification
# ----------------------------------------------------------------------
@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_business_email_otp(self, otp_id: int):
    _dispatch_email_otp(
        task=self,
        otp_id=otp_id,
        expected_purpose=OTPPurpose.BUSINESS_EMAIL,
        html_template="business/emails/business_email_otp.html",
        subject="Verify your business e-mail address",
    )


# ----------------------------------------------------------------------
# BUSINESS  Phone (SMS) verification
# ----------------------------------------------------------------------
@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_business_phone_otp(self, otp_id: int):
    _dispatch_sms_otp(self, otp_id, expected_purpose=OTPPurpose.BUSINESS_PHONE)


# ======================================================================
#  Internal helpers
# ======================================================================
def _dispatch_email_otp(*, task, otp_id: int, expected_purpose: str,
                        html_template: str, subject: str):
    """Generic e-mail dispatcher."""
    try:
        otp = OTP.objects.select_related("user").get(id=otp_id)
    except OTP.DoesNotExist:
        return

    if (
            otp.channel != OTPChannel.EMAIL
            or otp.purpose != expected_purpose
            or otp.verified
            or otp.is_expired()
    ):
        return

    ctx = {
        "user": otp.user,
        "code": otp.code,
        "expires_at": timezone.localtime(otp.expires_at),
        "app_name": getattr(settings, "APP_NAME", "EMI"),
    }
    html_body = render_to_string(html_template, ctx)

    try:
        txt_template = html_template.replace(".html", ".txt")
        text_body = render_to_string(txt_template, ctx)
    except TemplateDoesNotExist:
        text_body = strip_tags(html_body)

    msg = EmailMultiAlternatives(
        subject=f"{ctx['app_name']} | {subject}",
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[otp.target],
        headers={"X-OTP-Purpose": expected_purpose},
    )
    msg.attach_alternative(html_body, "text/html")

    try:
        msg.send(fail_silently=False)
    except BaseEmailBackend.Exception as exc:  # covers SMTPException & co.
        log.warning("E-mail send failed, retrying: %s", exc)
        raise task.retry(exc=exc)


def _dispatch_sms_otp(task, otp_id: int, *, expected_purpose: str):
    """Generic SMS dispatcher (replace stub with Twilio etc.)."""
    try:
        otp = OTP.objects.select_related("user").get(id=otp_id)
    except OTP.DoesNotExist:
        return

    if (
            otp.channel != OTPChannel.SMS
            or otp.purpose != expected_purpose
            or otp.verified
            or otp.is_expired()
    ):
        return

    sms_text = (
        f"Your verification code is {otp.code}. "
        f"It expires at {otp.expires_at.strftime('%H:%M')}."
    )
    print(sms_text)
    try:
        _sms_provider_send(to=otp.target, body=sms_text)
    except Exception as exc:
        log.warning("SMS send failed, retrying: %s", exc)
        raise task.retry(exc=exc)


# ----------------------------------------------------------------------
# Replace this stub with Twilio / AWS SNS / any provider
# ----------------------------------------------------------------------
def _sms_provider_send(*, to: str, body: str):
    print(f"[SMS] to={to}  body='{body}'")


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_password_reset_email(self, email: str, uid: str, token: str):
    frontend_url = getattr(settings, "PASSWORD_RESET_FRONTEND_URL",
                           "https://app.example.com/reset-password")

    reset_link = f"{frontend_url}?uid={uid}&token={token}"

    ctx = {
        "reset_link": reset_link,
        "app_name": getattr(settings, "APP_NAME", "EMI"),
    }
    html_body = render_to_string("account/emails/password/password_reset.html", ctx)
    text_body = render_to_string("account/emails/password/password_reset.txt", ctx)

    msg = EmailMultiAlternatives(
        subject=f"{ctx['app_name']} | Password reset request",
        body=text_body,
        to=[email],
        from_email=settings.DEFAULT_FROM_EMAIL,
    )
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=False)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_vendor_welcome_email(self, email: str, display_name: str):
    ctx = {
        "app_name": getattr(settings, "APP_NAME", "EMI"),
        "display_name": display_name,
    }
    html = render_to_string("account/emails/vendor_welcome.html", ctx)
    txt = render_to_string("account/emails/vendor_welcome.txt", ctx)

    msg = EmailMultiAlternatives(
        subject=f"{ctx['app_name']} | Vendor account activated",
        body=txt,
        to=[email],
        from_email=settings.DEFAULT_FROM_EMAIL,
    )
    msg.attach_alternative(html, "text/html")
    msg.send(fail_silently=False)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_password_reset_otp(self, otp_id: int):
    """
    Sends password reset OTP via SMS using Arkesel.

    Expects:
        • otp_id: ID of an OTP object with purpose=USER_PASSWORD_RESET
    """
    try:
        otp = OTP.objects.select_related("user").get(id=otp_id)
    except OTP.DoesNotExist:
        return

    if (
        otp.channel != OTPChannel.SMS
        or otp.purpose != OTPPurpose.PASSWORD_RESET_CODE
        or otp.verified
        or otp.is_expired()
    ):
        return

    user = otp.user
    if not user or not user.phone_number:
        return

    # Format message
    sms_text = (
        f"Reset your password using this code: {otp.code}. "
        f"It expires at {otp.expires_at.strftime('%H:%M')}."
    )

    # Arkesel API
    try:
        ...
        # _arkesel_send_sms(to=user.phone_number, message=sms_text)
    except Exception as exc:
        log.warning("Arkesel SMS send failed, retrying: %s", exc)
        raise self.retry(exc=exc)
