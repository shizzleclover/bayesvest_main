from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)

class MarketConfig(AppConfig):
    name = "apps.market"

    def ready(self):
        """On server startup, check if market data exists. If not, trigger ingestion."""
        import threading

        def _initial_ingestion():
            try:
                from apps.market.models import MarketData
                if MarketData.objects.count() == 0:
                    logger.info("[Bayesvest] No market data found. Running initial data ingestion...")
                    from apps.market.tasks import run_daily_market_ingestion
                    run_daily_market_ingestion.delay()
                    logger.info("[Bayesvest] Initial market data ingestion triggered.")
                else:
                    logger.info(f"[Bayesvest] Market data already exists ({MarketData.objects.count()} records). Skipping initial ingestion.")
            except Exception as e:
                logger.warning(f"[Bayesvest] Initial ingestion skipped: {e}")

        # Run in a background thread so it doesn't block server startup
        threading.Thread(target=_initial_ingestion, daemon=True).start()
