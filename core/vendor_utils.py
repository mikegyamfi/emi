# core/vendor_utils.py
from account.models import VendorProfile


def vendor_is_verified(vendor: VendorProfile) -> bool:
    """
    Central place to ask, 'Is this vendor verified?'
    Future: call out to an external KYC API here.
    """
    return vendor.is_verified
