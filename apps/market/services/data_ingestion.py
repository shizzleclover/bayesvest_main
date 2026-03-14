import logging
import time

import pandas as pd
import yfinance as yf
from pycoingecko import CoinGeckoAPI
import datetime

logger = logging.getLogger(__name__)

cg = CoinGeckoAPI()

COINGECKO_ID_MAP = {
    'BTC': 'bitcoin',
    'ETH': 'ethereum',
    'SOL': 'solana',
    'ADA': 'cardano',
}


def fetch_yfinance_data(ticker, years=5):
    """Fetch historical daily close prices from Yahoo Finance.

    Handles both flat and MultiIndex column formats returned by
    different yfinance versions (>=0.2.31 returns MultiIndex).
    """
    end_date = datetime.datetime.now()
    start_date = end_date - datetime.timedelta(days=years * 365)

    logger.info("[yfinance] Downloading %s (%s → %s)", ticker,
                start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))

    data = yf.download(
        ticker,
        start=start_date.strftime('%Y-%m-%d'),
        end=end_date.strftime('%Y-%m-%d'),
        progress=False,
        auto_adjust=True,
    )

    if data.empty:
        logger.warning("[yfinance] No data returned for %s", ticker)
        return []

    # Flatten MultiIndex columns if present (yfinance >= 0.2.31)
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    if 'Close' not in data.columns:
        logger.warning("[yfinance] 'Close' column missing for %s. Columns: %s",
                        ticker, list(data.columns))
        return []

    historical_prices = []
    for date_idx, row in data.iterrows():
        close_val = row['Close']
        if isinstance(close_val, pd.Series):
            close_val = close_val.iloc[0]
        try:
            close_float = float(close_val)
        except (TypeError, ValueError):
            continue
        if pd.isna(close_float):
            continue
        historical_prices.append({
            'date': date_idx.strftime('%Y-%m-%d'),
            'close': close_float,
        })

    logger.info("[yfinance] %s: got %d data points", ticker, len(historical_prices))
    return historical_prices


def fetch_coingecko_data(coin_id, vs_currency='usd', days=1825, max_retries=3):
    """Fetch historical daily prices from CoinGecko with retry logic."""
    for attempt in range(1, max_retries + 1):
        try:
            logger.info("[CoinGecko] Fetching %s (attempt %d/%d, days=%d)",
                        coin_id, attempt, max_retries, days)

            data = cg.get_coin_market_chart_by_id(
                id=coin_id, vs_currency=vs_currency, days=days)

            if 'prices' not in data or not data['prices']:
                logger.warning("[CoinGecko] No price data returned for %s", coin_id)
                return []

            historical_prices = []
            for item in data['prices']:
                date = datetime.datetime.fromtimestamp(item[0] / 1000.0)
                historical_prices.append({
                    'date': date.strftime('%Y-%m-%d'),
                    'close': float(item[1]),
                })

            if historical_prices:
                df = pd.DataFrame(historical_prices)
                df = df.drop_duplicates(subset=['date'], keep='last')
                historical_prices = df.to_dict('records')

            logger.info("[CoinGecko] %s: got %d data points", coin_id, len(historical_prices))
            return historical_prices

        except Exception as e:
            logger.warning("[CoinGecko] %s attempt %d failed: %s", coin_id, attempt, e)
            if attempt < max_retries:
                time.sleep(2 ** attempt)
            else:
                logger.error("[CoinGecko] %s: all %d attempts failed", coin_id, max_retries)
                return []

    return []
