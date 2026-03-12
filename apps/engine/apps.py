from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)

class EngineConfig(AppConfig):
    name = "apps.engine"

    def ready(self):
        """On server startup, check if forecasts exist. If not, trigger Prophet training."""
        import threading

        def _initial_training():
            import time
            # Wait for market ingestion to potentially complete first
            time.sleep(10)
            try:
                from apps.engine.models import Forecast
                if Forecast.objects.count() == 0:
                    logger.info("[Bayesvest] No forecasts found. Running initial Prophet training...")
                    from apps.engine.tasks import run_daily_prophet_training
                    run_daily_prophet_training.delay()
                    logger.info("[Bayesvest] Initial Prophet training triggered.")
                else:
                    logger.info(f"[Bayesvest] Forecasts already exist ({Forecast.objects.count()} records). Skipping initial training.")
            except Exception as e:
                logger.warning(f"[Bayesvest] Initial training skipped: {e}")

        threading.Thread(target=_initial_training, daemon=True).start()
