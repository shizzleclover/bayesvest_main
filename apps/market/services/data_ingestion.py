import yfinance as yf
from pycoingecko import CoinGeckoAPI
import pandas as pd
import datetime

cg = CoinGeckoAPI()

def fetch_yfinance_data(ticker, years=5):
    end_date = datetime.datetime.now()
    start_date = end_date - datetime.timedelta(days=years*365)
    data = yf.download(ticker, start=start_date.strftime('%Y-%m-%d'), end=end_date.strftime('%Y-%m-%d'))
    historical_prices = []
    if not data.empty:
        for date, row in data.iterrows():
            close_val = row['Close']
            if isinstance(close_val, pd.Series): close_val = close_val.iloc[0]
            historical_prices.append({'date': date.strftime('%Y-%m-%d'), 'close': float(close_val)})
    return historical_prices

def fetch_coingecko_data(coin_id, vs_currency='usd', days=1825):
    data = cg.get_coin_market_chart_by_id(id=coin_id, vs_currency=vs_currency, days=days)
    historical_prices = []
    if 'prices' in data:
        for item in data['prices']:
            date = datetime.datetime.fromtimestamp(item[0]/1000.0)
            historical_prices.append({'date': date.strftime('%Y-%m-%d'), 'close': float(item[1])})
    if historical_prices:
        df = pd.DataFrame(historical_prices)
        df = df.drop_duplicates(subset=['date'], keep='last')
        historical_prices = df.to_dict('records')
    return historical_prices
