# cart_management/signals.py
from django.db.models import F
from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in
from .models import Cart, CartItem


@receiver(user_logged_in)
def merge_session_cart(sender, user, request, **kwargs):
    sk = request.session.session_key
    if not sk:
        return

    try:
        anon_cart = Cart.objects.get(session_key=sk)
    except Cart.DoesNotExist:
        return

    # get or create the user's permanent cart
    user_cart, _ = Cart.objects.get_or_create(user=user)

    # move/merge items
    for item in anon_cart.items.all():
        uc_item, created = CartItem.objects.get_or_create(
            cart=user_cart,
            product=item.product,
            defaults={"quantity": item.quantity}
        )
        if not created:
            # simply add the quantities (or you can choose max, override, whatever)
            uc_item.quantity = F("quantity") + item.quantity
            uc_item.save()

    # delete the anonymous cart
    anon_cart.delete()
