from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)


class MarketConfig(AppConfig):
    name = "apps.market"

    def ready(self):
        """On server startup, seed assets and trigger ingestion + Prophet
        for any assets that are missing market data or forecasts."""
        import threading

        def _initial_pipeline():
            try:
                from apps.market.tasks import seed_default_assets, DEFAULT_ASSETS
                from apps.market.models import MarketData
                from apps.engine.models import Forecast

                seed_default_assets()

                expected_tickers = {a['ticker'] for a in DEFAULT_ASSETS}
                existing_market = {m.asset_ticker for m in MarketData.objects.only('asset_ticker')}
                existing_forecasts = {f.asset_ticker for f in Forecast.objects.only('asset_ticker')}
                missing_market = expected_tickers - existing_market
                missing_forecasts = expected_tickers - existing_forecasts

                if missing_market or missing_forecasts:
                    logger.info(
                        "[Bayesvest] Missing data — market: %s, forecasts: %s. Triggering pipeline.",
                        missing_market or "none", missing_forecasts or "none",
                    )
                    from apps.market.tasks import run_daily_market_ingestion
                    run_daily_market_ingestion()

                    from apps.engine.tasks import run_daily_prophet_training
                    run_daily_prophet_training()

                    logger.info("[Bayesvest] Startup pipeline complete.")
                else:
                    logger.info(
                        "[Bayesvest] All %d assets have market data and forecasts.",
                        len(expected_tickers),
                    )
            except Exception as e:
                logger.warning("[Bayesvest] Startup pipeline skipped: %s", e)

        threading.Thread(target=_initial_pipeline, daemon=True).start()
