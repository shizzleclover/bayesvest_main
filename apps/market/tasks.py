from celery import shared_task
from .models import Asset, MarketData
from .services.data_ingestion import fetch_yfinance_data, fetch_coingecko_data
from .services.data_alignment import forward_fill_weekends
import datetime
import logging

logger = logging.getLogger(__name__)

# Default assets the system tracks
DEFAULT_ASSETS = [
    {"ticker": "AAPL", "name": "Apple Inc.", "asset_class": "Stock", "sector": "Technology", "risk_level": "Medium"},
    {"ticker": "SPY", "name": "SPDR S&P 500 ETF", "asset_class": "ETF", "sector": "Index", "risk_level": "Medium"},
    {"ticker": "TLT", "name": "iShares 20+ Year Treasury Bond ETF", "asset_class": "ETF", "sector": "Treasury", "risk_level": "Low"},
    {"ticker": "BTC", "name": "Bitcoin", "asset_class": "Crypto", "sector": "Currency", "risk_level": "High"},
    {"ticker": "ETH", "name": "Ethereum", "asset_class": "Crypto", "sector": "Currency", "risk_level": "High"},
]

def seed_default_assets():
    """Seed the database with default assets if none exist."""
    if Asset.objects.count() == 0:
        for asset_data in DEFAULT_ASSETS:
            Asset(**asset_data).save()
        logger.info(f"[Bayesvest] Seeded {len(DEFAULT_ASSETS)} default assets.")

@shared_task
def run_daily_market_ingestion():
    seed_default_assets()
    assets = Asset.objects.all()
    updated_count = 0
    failed_assets = []
    for asset in assets:
        aligned_data = []
        try:
            if asset.asset_class in ['Stock', 'ETF', 'Bond']:
                raw_data = fetch_yfinance_data(asset.ticker, years=5)
                aligned_data = forward_fill_weekends(raw_data)
            elif asset.asset_class == 'Crypto':
                coingecko_id_map = {'BTC': 'bitcoin', 'ETH': 'ethereum', 'SOL': 'solana', 'ADA': 'cardano'}
                coin_id = coingecko_id_map.get(asset.ticker.upper())
                if coin_id: aligned_data = fetch_coingecko_data(coin_id, days=1825)
            if aligned_data:
                market_data = MarketData.objects(asset_ticker=asset.ticker).first()
                if not market_data: market_data = MarketData(asset_ticker=asset.ticker)
                market_data.historical_prices = aligned_data
                market_data.last_updated = datetime.datetime.utcnow()
                market_data.save()
                updated_count += 1
                logger.info(f"[Bayesvest] Ingested {len(aligned_data)} data points for {asset.ticker}")
        except Exception as e:
            logger.error(f"[Bayesvest] Failed to ingest {asset.ticker}: {e}")
            failed_assets.append(asset.ticker)
    summary = f"Successfully ingested and aligned data for {updated_count} assets."
    if failed_assets: summary += f" Failed: {failed_assets}"
    logger.info(f"[Bayesvest] {summary}")
    return summary

