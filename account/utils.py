# import secrets, logging
# from datetime import timedelta
#
# from django.conf import settings
# from django.utils import timezone
#
# from .models import EmailOTP
# from .tasks import send_email_otp
#
# logger = logging.getLogger(__name__)
#
# RESEND_COOLDOWN = getattr(settings, "EMAIL_OTP_RESEND_COOLDOWN_SECONDS", 60)
#
#
# def issue_email_otp(user, *, force_new: bool = False) -> EmailOTP:
#     """
#     Find the latest unexpired OTP or create a fresh one,
#     enqueue the e‑mail task, and return the OTP instance.
#
#     `force_new`  – always generate a new code (used for spam‑control reset).
#     """
#     now = timezone.now()
#
#     otp_qs = user.email_otps.filter(verified=False, expires_at__gt=now)
#     if not force_new:
#         otp = otp_qs.order_by("-created_at").first()
#     else:
#         otp = None
#
#     # Cool‑down: if we sent < RESEND_COOLDOWN seconds ago, keep same code
#     if otp and (now - otp.created_at).total_seconds() < RESEND_COOLDOWN:
#         send_email_otp.delay(otp.id)
#         return otp
#
#     # Otherwise generate a brand‑new code
#     code = f"{secrets.randbelow(1_000_000):06d}"
#     otp = EmailOTP.objects.create(user=user, code=code)  # default 10‑min expiry
#     send_email_otp.delay(otp.id)
#     return otp
