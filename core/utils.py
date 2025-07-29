# core/utils.py
import uuid

from decouple import config
from django.core.cache import cache
import requests
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from checkout_processing.models import DirectOrder, VendorNotification, DirectBooking
from core.models import OTP, OTPChannel
from product_service_management.models import VendorProduct


def get_config():
    """
    Return the singleton SiteConfig instance, cached for 60 s.
    Importing SiteConfig inside the function breaks any circular chain.
    """
    cfg = cache.get("site_config")
    if cfg is None:
        from core.models import SiteConfig  # ← local import avoids circular
        cfg, _ = SiteConfig.objects.get_or_create(pk=1)
        cache.set("site_config", cfg, 60)
    return cfg


import calendar
from datetime import datetime


def date_breakdown(dt: datetime) -> dict:
    """
    Split a datetime into handy analytics buckets.

    Returns
    -------
    {
        "date"          : "2025-04-25",
        "datetime"      : "2025-04-25T08:42:17Z",
        "year"          : 2025,
        "quarter"       : "Q2",
        "month"         : "April",
        "week_of_year"  : 17,
        "week_of_month" : 4
    }
    """
    month_idx = dt.month
    quarter_idx = (month_idx - 1) // 3 + 1
    week_of_year = dt.isocalendar().week

    # week-of-month = 1-based index of Monday-anchored week in that month
    first_day_week = datetime(dt.year, dt.month, 1).isocalendar().week
    week_of_month = week_of_year - first_day_week + 1

    return {
        "date": dt.date().isoformat(),
        "datetime": dt.isoformat(),
        "year": dt.year,
        "quarter": f"Q{quarter_idx}",
        "month": calendar.month_name[month_idx],
        "week_of_year": week_of_year,
        "week_of_month": week_of_month,
    }


def latest_price(listing):
    """
    Return the newest PriceHistory row for a listing or None.
    """
    p = listing.history.order_by("-recorded_at").first()
    return p


def flatten_error(detail):
    """
    Turn a DRF ValidationError.detail (which may be a list, dict or string)
    into a single human-readable string.
    """
    if isinstance(detail, (list, tuple)):
        # join each sub-detail
        return " ".join(flatten_error(d) for d in detail)
    if isinstance(detail, dict):
        # grab all values and flatten them too
        return " ".join(flatten_error(v) for v in detail.values())
    # base case: just cast to str
    return str(detail)


def send_sms(message, phone_number):
    truncated_phone_number = phone_number[1:]
    national_phone_number = f"233{truncated_phone_number}"
    ARKESEL_API_KEY = config("ARKESEL_API_KEY")
    base_url = f"https://sms.arkesel.com/sms/api?action=send-sms&api_key=R1ZGVG9Ma1BxcUdkdFlTZU9ac20&from=GI-KACE"
    sms_url = base_url + f"&to={national_phone_number}&sms={message}"

    try:
        response = requests.get(sms_url)
        response_json = response.json()
        print(response_json)
        return response_json
    except Exception as e:
        print(e)
        return 


def dispatch_sms_otp(otp_id: int, expected_purpose: str):
    print("got into dispatch")

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
        print("got into try")
        send_sms(sms_text, otp.target)
    except Exception as exc:
        print(exc)


def send_vendor_order_sms(vendor_phone: str, order_id: str):
    """
    1. POST to Arkesel to send the SMS.
    2. Parse their JSON response for delivery timestamps.
    3. Record a VendorNotification tied to the DirectOrder.
    """
    ARKESEL_API_KEY = config("ARKESEL_API_KEY")
    order = DirectOrder.objects.get(order_id=uuid.UUID(order_id))

    truncated_phone_number = order.product.seller.phone_number
    national_phone_number = f"233{truncated_phone_number}"

    if not order.note:
        msg = f"{order.full_name} ({order.phone}) requests {order.quantity} of {order.product.name}."
    else:
        msg = f"{order.full_name} ({order.phone}) requests {order.quantity} of {order.product.name}. Note: {order.note}"

    base_url = f"https://sms.arkesel.com/sms/api?action=send-sms&api_key={ARKESEL_API_KEY}&from=GI-KACE"
    sms_url = base_url + f"&to={national_phone_number}&sms={msg}"

    try:
        response = requests.get(sms_url)
        response.raise_for_status()
        data = response.json()
        print(data)
    except Exception as e:
        print(e)
        # you may want to log this or retry
        return

    # 2) Extract a delivered timestamp if present

    if response.status_code == 200:
        if data["code"] == "ok":
            try:
                order = DirectOrder.objects.get(order_id=uuid.UUID(order_id))
            except DirectOrder.DoesNotExist:
                return

            VendorNotification.objects.create(
                buyer=order.buyer,
                product=order.product,
                quantity=order.quantity,
                location=getattr(order, "locations", "") or "",
                delivered_at=timezone.now(),
            )
        else:
            return
    else:
        return


# base message template
# user so will like to


def send_vendor_booking_sms(provider_phone: str, booking_id: str):
    """
    1) Build & send the SMS via Arkesel.
    2) Parse response for sent/delivered timestamp.
    3) Record a VendorNotification (optional).
    """
    ARKESEL_API_KEY = config("ARKESEL_API_KEY")

    try:
        booking = DirectBooking.objects.get(booking_id=uuid.UUID(booking_id))
    except DirectBooking.DoesNotExist:
        return

    truncated_phone_number = booking.service.provider.phone_number
    national_phone_number = f"233{truncated_phone_number}"

    buyer = booking.buyer
    svc = booking.service

    msg = (
        f"{buyer.first_name} {buyer.last_name} ({buyer.phone_number}) "
        f"requests your service “{svc.title}”: {booking.message}"
    )

    base_url = f"https://sms.arkesel.com/sms/api?action=send-sms&api_key={ARKESEL_API_KEY}&from=GI-KACE"
    sms_url = base_url + f"&to={national_phone_number}&sms={msg}"

    try:
        response = requests.get(sms_url)
        response.raise_for_status()
        data = response.json()
        print(data)
    except Exception as e:
        print(e)
        # you may want to log this or retry
        return

    # pick first sent_at or queued_at
    if response.status_code == 200:
        if data["code"] == "ok":
            try:
                booking = DirectBooking.objects.get(booking_id=uuid.UUID(booking_id))
            except DirectBooking.DoesNotExist:
                return

            VendorNotification.objects.create(
                buyer=booking.buyer,
                service=booking.service,
                delivered_at=timezone.now(),
            )
        else:
            return
    else:
        return
