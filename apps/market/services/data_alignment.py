import pandas as pd
import datetime

def forward_fill_weekends(historical_prices):
    if not historical_prices: return []
    df = pd.DataFrame(historical_prices)
    df['date'] = pd.to_datetime(df['date'])
    df = df.set_index('date')
    full_date_range = pd.date_range(start=df.index.min(), end=df.index.max(), freq='D')
    df = df.reindex(full_date_range)
    df['close'] = df['close'].ffill()
    df = df.reset_index().rename(columns={'index': 'date'})
    df['date'] = df['date'].dt.strftime('%Y-%m-%d')
    return df.to_dict('records')
