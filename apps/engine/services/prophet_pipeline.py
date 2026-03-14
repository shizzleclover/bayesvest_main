import logging
import datetime

import pandas as pd
from prophet import Prophet

from apps.market.models import MarketData
from apps.engine.models import Forecast

logger = logging.getLogger(__name__)


def train_and_forecast_asset(ticker):
    """Train a Prophet model on historical prices and save a 1-year forecast."""
    market_data = MarketData.objects(asset_ticker=ticker).first()
    if not market_data or not market_data.historical_prices:
        logger.warning("[Prophet] No market data for %s — skipping.", ticker)
        return None

    df = pd.DataFrame(market_data.historical_prices)
    df = df.rename(columns={'date': 'ds', 'close': 'y'})
    df['ds'] = pd.to_datetime(df['ds'])

    # Drop rows with NaN prices
    df = df.dropna(subset=['y'])

    if len(df) < 30:
        logger.warning("[Prophet] %s has only %d data points — too few to train.", ticker, len(df))
        return None

    logger.info("[Prophet] Training %s on %d data points...", ticker, len(df))

    m = Prophet(
        daily_seasonality=False,
        weekly_seasonality=True,
        yearly_seasonality=True,
    )
    m.fit(df)

    future = m.make_future_dataframe(periods=365)
    forecast = m.predict(future)
    last_row = forecast.iloc[-1]

    current_price = float(df.iloc[-1]['y'])
    expected_future_price = float(last_row['yhat'])
    yhat_upper = float(last_row['yhat_upper'])
    yhat_lower = float(last_row['yhat_lower'])

    # Guard against zero/negative predicted price
    if expected_future_price <= 0:
        logger.warning("[Prophet] %s predicted non-positive price (%.2f) — using abs.",
                        ticker, expected_future_price)
        expected_future_price = abs(expected_future_price) or current_price

    expected_return = (expected_future_price - current_price) / current_price
    volatility = (yhat_upper - yhat_lower) / expected_future_price if expected_future_price > 0 else 0.5

    logger.info(
        "[Prophet] %s: current=$%.2f → predicted=$%.2f, return=%.2f%%, vol=%.2f%%",
        ticker, current_price, expected_future_price,
        expected_return * 100, volatility * 100,
    )

    forecast_doc = Forecast.objects(asset_ticker=ticker).first()
    if not forecast_doc:
        forecast_doc = Forecast(asset_ticker=ticker)
    forecast_doc.expected_return = expected_return
    forecast_doc.volatility = volatility
    forecast_doc.yhat_upper = yhat_upper
    forecast_doc.yhat_lower = yhat_lower
    forecast_doc.forecast_date = datetime.datetime.utcnow()
    forecast_doc.save()

    return forecast_doc
