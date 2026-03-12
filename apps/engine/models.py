from mongoengine import Document, StringField, FloatField, DateTimeField
import datetime

class Forecast(Document):
    asset_ticker = StringField(required=True, unique=True)
    expected_return = FloatField(required=True)
    volatility = FloatField(required=True)
    yhat_upper = FloatField()
    yhat_lower = FloatField()
    forecast_date = DateTimeField(default=datetime.datetime.utcnow)
    meta = {'collection': 'forecasts'}
