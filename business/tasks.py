from celery import shared_task
from django.core.mail import EmailMultiAlternatives, EmailMessage
from django.template.loader import render_to_string
from django.conf import settings

from core.models import OTPPurpose, OTP, OTPChannel


def _send(template, subject, email, ctx):
    html = render_to_string(f"business/emails/{template}.html", ctx)
    # txt = render_to_string(f"business/emails/{template}.txt", ctx)
    mail = EmailMultiAlternatives(subject, html, settings.DEFAULT_FROM_EMAIL, [email])
    mail.attach_alternative(html, "text/html")
    mail.send(fail_silently=False)


@shared_task
def send_business_submitted(email, biz_name):
    _send("submitted_request", "Business submitted for review", email, {"biz": biz_name})


@shared_task
def send_business_approved(email, biz_name, note):
    _send("approved_request", f"{biz_name} approved!", email, {"biz": biz_name})


@shared_task
def send_business_rejected(email, biz_name, note):
    _send("rejected_request", f"{biz_name} rejected", email, {"biz": biz_name, "note": note})


# ------------------------------------------------------------------
# 3.  BUSINESS -- e-mail verification
# ------------------------------------------------------------------
@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_business_email_otp(self, otp_id: int):
    _send_email_otp(
        otp_id=otp_id,
        expected_purpose=OTPPurpose.BUSINESS_EMAIL,
        template="business/emails/business_email_otp.html",
        subject="Verify your business e-mail address",
    )


# ------------------------------------------------------------------
# 4.  BUSINESS -- phone (SMS) verification
# ------------------------------------------------------------------
@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_business_phone_otp(self, otp_id: int):
    _send_sms_otp(otp_id, expected_purpose=OTPPurpose.BUSINESS_PHONE)


# ==================================================================
#  Internal helpers (one for mail, one for SMS)
# ==================================================================
def _send_email_otp(*, otp_id: int, expected_purpose: str,
                    template: str, subject: str):
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
        "expires_at": otp.expires_at,
        "app_name": getattr(settings, "APP_NAME", "EMI"),
    }
    body_html = render_to_string(template, ctx)

    msg = EmailMessage(
        subject=f"{ctx['app_name']} | {subject}",
        body=body_html,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[otp.target],        # stored e-mail address
    )
    msg.content_subtype = "html"
    msg.send(fail_silently=False)


def _send_sms_otp(otp_id: int, expected_purpose: str):
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

    # --- integrate with your SMS provider here ----------
    # e.g. twilio_client.messages.create(...)
    sms_text = f"Your verification code is {otp.code}. " \
               f"It expires at {otp.expires_at.strftime('%H:%M')}."
    _send_sms_via_provider(to=otp.target, body=sms_text)


# Dummy provider stub – replace with Twilio, etc.
def _send_sms_via_provider(*, to: str, body: str):
    print(f"[SMS] to={to} body='{body}'")     # replace with real call














