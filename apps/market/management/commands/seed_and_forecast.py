"""
Management command to run the full data pipeline:
  1. Seed default assets
  2. Ingest market data (yfinance + CoinGecko)
  3. Train Prophet models and produce forecasts

Usage:
    python manage.py seed_and_forecast
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Seed assets, ingest market data, and run Prophet training."

    def handle(self, *args, **options):
        from apps.market.tasks import seed_default_assets, run_daily_market_ingestion
        from apps.engine.tasks import run_daily_prophet_training

        self.stdout.write("Step 1/3: Seeding assets...")
        seed_default_assets()
        self.stdout.write(self.style.SUCCESS("  Assets seeded."))

        self.stdout.write("Step 2/3: Ingesting market data...")
        result = run_daily_market_ingestion()
        self.stdout.write(self.style.SUCCESS(f"  {result}"))

        self.stdout.write("Step 3/3: Training Prophet models...")
        result = run_daily_prophet_training()
        self.stdout.write(self.style.SUCCESS(f"  {result}"))

        self.stdout.write(self.style.SUCCESS("\nPipeline complete."))
