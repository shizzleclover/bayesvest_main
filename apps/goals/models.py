import datetime
from mongoengine import Document, StringField, FloatField, DateTimeField

class SavingsGoal(Document):
    user_id = StringField(required=True)
    name = StringField(required=True, max_length=100)
    target_amount = FloatField(required=True)
    current_amount = FloatField(default=0)
    monthly_contribution = FloatField(default=0)
    deadline = DateTimeField()
    icon = StringField(max_length=50, default='savings')
    created_at = DateTimeField(default=datetime.datetime.utcnow)
    meta = {'collection': 'savings_goals'}
