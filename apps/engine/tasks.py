from celery import shared_task
from apps.market.models import Asset
from .services.prophet_pipeline import train_and_forecast_asset

@shared_task
def run_daily_prophet_training():
    assets = Asset.objects.all()
    trained_count, failed_assets = 0, []
    for asset in assets:
        try:
            if train_and_forecast_asset(asset.ticker): trained_count += 1
            else: failed_assets.append(asset.ticker)
        except Exception as e:
            print(f"Prophet Training Failed for {asset.ticker}: {str(e)}")
            failed_assets.append(asset.ticker)
    summary = f"Successfully trained Prophet models for {trained_count} assets."
    if failed_assets: summary += f" Failed Assets: {failed_assets}"
    return summary
