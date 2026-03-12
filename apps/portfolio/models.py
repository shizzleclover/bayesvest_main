from mongoengine import Document, StringField, DateTimeField, FloatField, DictField, ListField
import datetime

class Recommendation(Document):
    user_id = StringField(required=True)
    asset_allocation = DictField(required=True) 
    expected_return_1y = FloatField()
    portfolio_volatility = FloatField()
    risk_summary = StringField()            # Explains the user's risk profile
    reasoning = ListField(DictField())      # Per-asset reasoning
    created_at = DateTimeField(default=datetime.datetime.utcnow)
    meta = {'collection': 'recommendations'}
