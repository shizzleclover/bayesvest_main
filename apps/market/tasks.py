from celery import shared_task
from .models import Asset, MarketData
from .services.data_ingestion import (
    fetch_yfinance_data,
    fetch_coingecko_data,
    COINGECKO_ID_MAP,
)
from .services.data_alignment import forward_fill_weekends
import datetime
import logging

logger = logging.getLogger(__name__)

DEFAULT_ASSETS = [
    # ── Stocks ───────────────────────────────────────────────
    {"ticker": "AAPL", "name": "Apple Inc.", "asset_class": "Stock", "sector": "Technology", "risk_level": "Medium"},
    {"ticker": "MSFT", "name": "Microsoft Corp.", "asset_class": "Stock", "sector": "Technology", "risk_level": "Medium"},
    {"ticker": "JNJ", "name": "Johnson & Johnson", "asset_class": "Stock", "sector": "Healthcare", "risk_level": "Low"},
    {"ticker": "JPM", "name": "JPMorgan Chase & Co.", "asset_class": "Stock", "sector": "Finance", "risk_level": "Medium"},
    {"ticker": "PG", "name": "Procter & Gamble Co.", "asset_class": "Stock", "sector": "Consumer Staples", "risk_level": "Low"},
    {"ticker": "XOM", "name": "ExxonMobil Corp.", "asset_class": "Stock", "sector": "Energy", "risk_level": "Medium"},

    # ── Broad / Index ETFs ───────────────────────────────────
    {"ticker": "SPY", "name": "SPDR S&P 500 ETF", "asset_class": "ETF", "sector": "Index", "risk_level": "Medium"},
    {"ticker": "QQQ", "name": "Invesco QQQ Trust", "asset_class": "ETF", "sector": "Technology", "risk_level": "Medium"},
    {"ticker": "VWO", "name": "Vanguard FTSE Emerging Markets ETF", "asset_class": "ETF", "sector": "International", "risk_level": "High"},
    {"ticker": "VEA", "name": "Vanguard FTSE Developed Markets ETF", "asset_class": "ETF", "sector": "International", "risk_level": "Medium"},
    {"ticker": "IWM", "name": "iShares Russell 2000 ETF", "asset_class": "ETF", "sector": "Small Cap", "risk_level": "High"},

    # ── Bonds / Treasuries ───────────────────────────────────
    {"ticker": "TLT", "name": "iShares 20+ Year Treasury Bond ETF", "asset_class": "Bond", "sector": "Treasury", "risk_level": "Low"},
    {"ticker": "AGG", "name": "iShares Core U.S. Aggregate Bond ETF", "asset_class": "Bond", "sector": "Aggregate", "risk_level": "Low"},
    {"ticker": "TIP", "name": "iShares TIPS Bond ETF", "asset_class": "Bond", "sector": "Inflation-Protected", "risk_level": "Low"},

    # ── REITs ────────────────────────────────────────────────
    {"ticker": "VNQ", "name": "Vanguard Real Estate ETF", "asset_class": "REIT", "sector": "Real Estate", "risk_level": "Medium"},

    # ── Commodities ──────────────────────────────────────────
    {"ticker": "GLD", "name": "SPDR Gold Shares", "asset_class": "Commodity", "sector": "Precious Metals", "risk_level": "Medium"},

    # ── Crypto ───────────────────────────────────────────────
    {"ticker": "BTC", "name": "Bitcoin", "asset_class": "Crypto", "sector": "Currency", "risk_level": "High"},
    {"ticker": "ETH", "name": "Ethereum", "asset_class": "Crypto", "sector": "Currency", "risk_level": "High"},
]


def seed_default_assets():
    """Seed the database with default assets (idempotent)."""
    existing = {a.ticker for a in Asset.objects.only('ticker')}
    added = 0
    for asset_data in DEFAULT_ASSETS:
        if asset_data['ticker'] not in existing:
            Asset(**asset_data).save()
            added += 1
    if added:
        logger.info("[Bayesvest] Seeded %d new assets (total: %d).", added, len(DEFAULT_ASSETS))
    return added


@shared_task
def run_daily_market_ingestion():
    """Fetch historical prices for every Asset from yfinance / CoinGecko."""
    seed_default_assets()
    assets = Asset.objects.all()
    updated_count = 0
    failed_assets = []

    for asset in assets:
        aligned_data = []
        try:
            if asset.asset_class in ('Stock', 'ETF', 'Bond', 'REIT', 'Commodity'):
                raw_data = fetch_yfinance_data(asset.ticker, years=5)
                if raw_data:
                    aligned_data = forward_fill_weekends(raw_data)
                else:
                    logger.warning("[Bayesvest] yfinance returned no data for %s", asset.ticker)

            elif asset.asset_class == 'Crypto':
                coin_id = COINGECKO_ID_MAP.get(asset.ticker.upper())
                if coin_id:
                    aligned_data = fetch_coingecko_data(coin_id, days=365)
                else:
                    logger.warning("[Bayesvest] No CoinGecko ID mapping for %s", asset.ticker)

            if aligned_data:
                market_data = MarketData.objects(asset_ticker=asset.ticker).first()
                if not market_data:
                    market_data = MarketData(asset_ticker=asset.ticker)
                market_data.historical_prices = aligned_data
                market_data.last_updated = datetime.datetime.utcnow()
                market_data.save()
                updated_count += 1
                logger.info("[Bayesvest] Saved %d data points for %s", len(aligned_data), asset.ticker)
            else:
                logger.warning("[Bayesvest] No data to save for %s (%s)", asset.ticker, asset.asset_class)
                failed_assets.append(asset.ticker)

        except Exception as e:
            logger.error("[Bayesvest] Failed to ingest %s: %s", asset.ticker, e, exc_info=True)
            failed_assets.append(asset.ticker)

    summary = f"Successfully ingested and aligned data for {updated_count}/{len(list(assets))} assets."
    if failed_assets:
        summary += f" Failed: {failed_assets}"
    logger.info("[Bayesvest] %s", summary)
    return summary
