# cart_management/utils.py
from django.contrib.sessions.backends.base import SessionBase
from .models import Cart


def get_or_create_cart(request):
    """
    If the user is authenticated, use (or create) a Cart tied to them.
    Otherwise, use (or create) a Cart keyed by request.session.session_key.
    """
    if request.user.is_authenticated:
        cart, _ = Cart.objects.get_or_create(user=request.user)
    else:
        # ensure we have a session key
        if not request.session.session_key:
            request.session.create()
        sk = request.session.session_key
        cart, _ = Cart.objects.get_or_create(session_key=sk)
    return cart
