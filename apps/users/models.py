from mongoengine import Document, StringField, DateTimeField, DictField, IntField, FloatField
import datetime
from django.contrib.auth.hashers import make_password, check_password

class User(Document):
    email = StringField(required=True, unique=True, max_length=255)
    password_hash = StringField(required=True)
    created_at = DateTimeField(default=datetime.datetime.utcnow)
    meta = {'collection': 'users'}

    def set_password(self, raw_password):
        self.password_hash = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password_hash)

    @property
    def pk(self):
        return str(self.id)

    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return True

class FinancialProfile(Document):
    user_id = StringField(required=True)
    age = IntField()
    income = FloatField()
    savings = FloatField()
    goals = StringField()
    horizon = StringField()
    meta = {'collection': 'financial_profiles'}

class RiskAssessment(Document):
    user_id = StringField(required=True)
    answers = DictField()
    risk_score = FloatField()
    raw_score = IntField(default=0)
    risk_level = StringField()
    created_at = DateTimeField(default=datetime.datetime.utcnow)
    meta = {'collection': 'risk_assessments'}
