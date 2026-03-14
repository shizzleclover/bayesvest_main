import logging

from celery import shared_task
from apps.market.models import Asset
from .services.prophet_pipeline import train_and_forecast_asset

logger = logging.getLogger(__name__)


@shared_task
def run_daily_prophet_training():
    """Train Prophet models for all assets and store Forecast documents."""
    assets = list(Asset.objects.all())
    logger.info("[Prophet] Starting training for %d assets...", len(assets))

    trained_count = 0
    failed_assets = []

    for asset in assets:
        try:
            result = train_and_forecast_asset(asset.ticker)
            if result:
                trained_count += 1
            else:
                failed_assets.append(asset.ticker)
        except Exception as e:
            logger.error("[Prophet] Training failed for %s: %s", asset.ticker, e, exc_info=True)
            failed_assets.append(asset.ticker)

    summary = f"Successfully trained Prophet models for {trained_count}/{len(assets)} assets."
    if failed_assets:
        summary += f" Failed: {failed_assets}"
    logger.info("[Prophet] %s", summary)
    return summary
