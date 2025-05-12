from django.apps import AppConfig


class CartManagementConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'cart_management'

    def ready(self):
        from . import signals
