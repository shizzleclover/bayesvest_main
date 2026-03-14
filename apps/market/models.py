from mongoengine import Document, StringField, DateTimeField, ListField, DictField
import datetime

class Asset(Document):
    ticker = StringField(required=True, unique=True, max_length=10)
    name = StringField(max_length=100)
    asset_class = StringField(max_length=50)
    sector = StringField(max_length=100)
    risk_level = StringField(max_length=50)
    meta = {'collection': 'assets'}

class MarketData(Document):
    asset_ticker = StringField(required=True, unique=True)
    historical_prices = ListField(DictField())
    last_updated = DateTimeField(default=datetime.datetime.utcnow)
    meta = {'collection': 'market_data'}

class Watchlist(Document):
    user_id = StringField(required=True, unique=True)
    tickers = ListField(StringField(max_length=10))
    created_at = DateTimeField(default=datetime.datetime.utcnow)
    meta = {'collection': 'watchlists'}
