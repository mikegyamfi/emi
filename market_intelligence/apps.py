from django.apps import AppConfig


class MarketIntelligenceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'market_intelligence'

    def ready(self):
        import market_intelligence.signals
