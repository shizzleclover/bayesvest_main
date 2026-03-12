import pandas as pd
from prophet import Prophet
import datetime
from apps.market.models import MarketData
from apps.engine.models import Forecast

def train_and_forecast_asset(ticker):
    market_data = MarketData.objects(asset_ticker=ticker).first()
    if not market_data or not market_data.historical_prices: return None
    df = pd.DataFrame(market_data.historical_prices)
    df = df.rename(columns={'date': 'ds', 'close': 'y'})
    df['ds'] = pd.to_datetime(df['ds'])
    m = Prophet(daily_seasonality=False, weekly_seasonality=True, yearly_seasonality=True)
    m.fit(df)
    future = m.make_future_dataframe(periods=365)
    forecast = m.predict(future)
    last_row = forecast.iloc[-1]
    current_price = df.iloc[-1]['y']
    expected_future_price = last_row['yhat']
    expected_return = (expected_future_price - current_price) / current_price
    volatility = (last_row['yhat_upper'] - last_row['yhat_lower']) / expected_future_price
    forecast_doc = Forecast.objects(asset_ticker=ticker).first()
    if not forecast_doc: forecast_doc = Forecast(asset_ticker=ticker)
    forecast_doc.expected_return = float(expected_return)
    forecast_doc.volatility = float(volatility)
    forecast_doc.yhat_upper = float(last_row['yhat_upper'])
    forecast_doc.yhat_lower = float(last_row['yhat_lower'])
    forecast_doc.forecast_date = datetime.datetime.utcnow()
    forecast_doc.save()
    return forecast_doc
