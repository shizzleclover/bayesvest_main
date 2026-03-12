import os

files = {
    'apps/users/models.py': '''from mongoengine import Document, StringField, DateTimeField, DictField, IntField, FloatField
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
    risk_level = StringField()
    created_at = DateTimeField(default=datetime.datetime.utcnow)
    meta = {'collection': 'risk_assessments'}
''',
    'apps/users/views.py': '''from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from .models import User

class RegisterView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')
        if not email or not password: return Response({'error': 'Email and password required'}, status=status.HTTP_400_BAD_REQUEST)
        if User.objects(email=email).first(): return Response({'error': 'Email already exists'}, status=status.HTTP_400_BAD_REQUEST)
        user = User(email=email)
        user.set_password(password)
        user.save()
        refresh = RefreshToken()
        refresh['user_id'] = str(user.id)
        return Response({'refresh': str(refresh), 'access': str(refresh.access_token), 'user': {'id': str(user.id), 'email': user.email}}, status=status.HTTP_201_CREATED)

class LoginView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')
        user = User.objects(email=email).first()
        if not user or not user.check_password(password): return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
        refresh = RefreshToken()
        refresh['user_id'] = str(user.id)
        return Response({'refresh': str(refresh), 'access': str(refresh.access_token), 'user': {'id': str(user.id), 'email': user.email}}, status=status.HTTP_200_OK)
''',
    'apps/users/urls.py': '''from django.urls import path
from .views import RegisterView, LoginView

urlpatterns = [
    path('auth/register/', RegisterView.as_view(), name='register'),
    path('auth/login/', LoginView.as_view(), name='login'),
]''',
    'apps/market/models.py': '''from mongoengine import Document, StringField, DateTimeField, ListField, DictField
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
''',
    'apps/market/services/data_ingestion.py': '''import yfinance as yf
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
''',
    'apps/market/services/data_alignment.py': '''import pandas as pd
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
''',
    'apps/market/tasks.py': '''from celery import shared_task
from .models import Asset, MarketData
from .services.data_ingestion import fetch_yfinance_data, fetch_coingecko_data
from .services.data_alignment import forward_fill_weekends
import datetime

@shared_task
def run_daily_market_ingestion():
    assets = Asset.objects.all()
    updated_count = 0
    for asset in assets:
        aligned_data = []
        if asset.asset_class in ['Stock', 'ETF', 'Bond']:
            raw_data = fetch_yfinance_data(asset.ticker, years=5)
            aligned_data = forward_fill_weekends(raw_data)
        elif asset.asset_class == 'Crypto':
            coingecko_id_map = {'BTC': 'bitcoin', 'ETH': 'ethereum', 'SOL': 'solana', 'ADA': 'cardano'}
            coin_id = coingecko_id_map.get(asset.ticker.upper())
            if coin_id: aligned_data = fetch_coingecko_data(coin_id, days=1825)
        if aligned_data:
            market_data = MarketData.objects(asset_ticker=asset.ticker).first()
            if not market_data: market_data = MarketData(asset_ticker=asset.ticker)
            market_data.historical_prices = aligned_data
            market_data.last_updated = datetime.datetime.utcnow()
            market_data.save()
            updated_count += 1
    return f"Successfully ingested and aligned data for {updated_count} assets."
''',
    'apps/engine/models.py': '''from mongoengine import Document, StringField, FloatField, DateTimeField
import datetime

class Forecast(Document):
    asset_ticker = StringField(required=True, unique=True)
    expected_return = FloatField(required=True)
    volatility = FloatField(required=True)
    yhat_upper = FloatField()
    yhat_lower = FloatField()
    forecast_date = DateTimeField(default=datetime.datetime.utcnow)
    meta = {'collection': 'forecasts'}
''',
    'apps/engine/services/prophet_pipeline.py': '''import pandas as pd
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
''',
    'apps/engine/services/bayesian_network.py': '''from pgmpy.models import DiscreteBayesianNetwork
from pgmpy.factors.discrete import TabularCPD
from pgmpy.inference import VariableElimination

def build_bayesian_network():
    model = DiscreteBayesianNetwork([('Risk_Profile_Score', 'Asset_Suitability'), ('Expected_Return', 'Asset_Suitability'), ('Volatility', 'Asset_Suitability')])
    cpd_risk = TabularCPD(variable='Risk_Profile_Score', variable_card=5, values=[[0.2], [0.2], [0.2], [0.2], [0.2]])
    cpd_return = TabularCPD(variable='Expected_Return', variable_card=3, values=[[0.33], [0.33], [0.34]])
    cpd_volatility = TabularCPD(variable='Volatility', variable_card=3, values=[[0.33], [0.33], [0.34]])
    suitability_high_probs = build_heuristic_cpt_array()
    suitability_low_probs = [1 - p for p in suitability_high_probs]
    cpd_suitability = TabularCPD(
        variable='Asset_Suitability', variable_card=2, 
        values=[suitability_low_probs, suitability_high_probs],
        evidence=['Risk_Profile_Score', 'Expected_Return', 'Volatility'],
        evidence_card=[5, 3, 3]
    )
    model.add_cpds(cpd_risk, cpd_return, cpd_volatility, cpd_suitability)
    assert model.check_model()
    return VariableElimination(model)

def build_heuristic_cpt_array():
    probs = []
    for risk in range(5):        
        for ret in range(3):     
            for vol in range(3): 
                score = 0.5 
                if risk == 0:
                    if vol == 2: score = 0.05
                    elif vol == 0: score = 0.90
                elif risk == 4:
                    if vol == 2 and ret == 2: score = 0.95
                    elif vol == 0: score = 0.20
                elif risk == 2:
                    if vol == 1 and ret == 1: score = 0.80
                    if vol == 0 or vol == 2: score = 0.40
                else:
                    if vol >= risk: score = max(0.1, 0.5 - (vol - risk) * 0.2)
                    else: score = min(0.9, 0.5 + (risk - vol) * 0.2)
                if ret == 2 and risk >= 2: score = min(0.99, score + 0.15)
                if ret == 0 and risk <= 1: score = min(0.99, score + 0.10)
                probs.append(score)
    return probs
''',
    'apps/engine/services/inference.py': '''from apps.users.models import RiskAssessment
from .bayesian_network import build_bayesian_network

class InferenceEngine:
    def __init__(self):
        self.network = build_bayesian_network()

    def calculate_risk_score(self, answers):
        total_score = 0
        age = answers.get('age_bracket', '')
        if age == "Under 30": total_score += 20
        elif age == "30 - 45": total_score += 15
        elif age == "46 - 60": total_score += 5
        elif age == "60+": total_score += 0
        
        horizon = answers.get('horizon', '')
        if horizon == "Long-Term": total_score += 30
        elif horizon == "Medium-Term": total_score += 15
        elif horizon == "Short-Term": total_score += 0
        
        tolerance = answers.get('risk_tolerance', '')
        if tolerance == "Buy More": total_score += 50
        elif tolerance == "Wait it out": total_score += 25
        elif tolerance == "Panic Sell": total_score += 0
        
        if total_score <= 20: return 0
        elif total_score <= 45: return 1
        elif total_score <= 65: return 2
        elif total_score <= 85: return 3
        else: return 4

    def calculate_asset_suitability(self, risk_profile_score, expected_return_tier, volatility_tier):
        evidence = {'Risk_Profile_Score': risk_profile_score, 'Expected_Return': expected_return_tier, 'Volatility': volatility_tier}
        result = self.network.query(variables=['Asset_Suitability'], evidence=evidence)
        return float(result.values[1])

bayes_engine = InferenceEngine()
''',
    'apps/engine/tasks.py': '''from celery import shared_task
from apps.market.models import Asset
from .services.prophet_pipeline import train_and_forecast_asset

@shared_task
def run_daily_prophet_training():
    assets = Asset.objects.all()
    trained_count, failed_assets = 0, []
    for asset in assets:
        try:
            if train_and_forecast_asset(asset.ticker): trained_count += 1
            else: failed_assets.append(asset.ticker)
        except Exception as e:
            print(f"Prophet Training Failed for {asset.ticker}: {str(e)}")
            failed_assets.append(asset.ticker)
    summary = f"Successfully trained Prophet models for {trained_count} assets."
    if failed_assets: summary += f" Failed Assets: {failed_assets}"
    return summary
''',
    'apps/engine/tests.py': '''import json, uuid
from django.test import SimpleTestCase
from rest_framework.test import APIClient
from rest_framework import status
from apps.users.models import User, RiskAssessment
from apps.market.models import Asset
from apps.engine.models import Forecast

class EnginePipelineTests(SimpleTestCase):
    def setUp(self):
        User.objects.delete()
        RiskAssessment.objects.delete()
        Asset.objects.delete()
        Forecast.objects.delete()
        
        self.client = APIClient()
        self.email = "test@bayesvest.ai"
        self.password = "SecurePassword123!"
        
        self.user = User(email=self.email)
        self.user.set_password(self.password)
        self.user.save()
        
        Asset(ticker='AAPL', name='Apple', asset_class='Stock', sector='Tech', risk_level='Medium').save()
        Asset(ticker='BTC', name='Bitcoin', asset_class='Crypto', sector='Currency', risk_level='High').save()
        Asset(ticker='TLT', name='Bonds', asset_class='ETF', sector='Treasury', risk_level='Low').save()

        Forecast(asset_ticker='AAPL', expected_return=0.10, volatility=0.15).save() 
        Forecast(asset_ticker='BTC', expected_return=0.35, volatility=0.45).save()  
        Forecast(asset_ticker='TLT', expected_return=0.03, volatility=0.04).save()   
        
    def tearDown(self):
        User.objects.delete(); RiskAssessment.objects.delete(); Asset.objects.delete(); Forecast.objects.delete()

    def get_auth_token(self):
        response = self.client.post('/api/users/auth/login/', {'email': self.email, 'password': self.password}, format='json')
        return response.data['access']

    def test_conservative_user_allocation(self):
        RiskAssessment(user_id=str(self.user.id), answers={"age_bracket": "60+", "horizon": "Short-Term", "risk_tolerance": "Panic Sell"}, risk_score=0, risk_level="Very Conservative").save()
        token = self.get_auth_token()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)
        response = self.client.post('/api/portfolio/generate/')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        alloc = response.data['asset_allocation']
        self.assertAlmostEqual(sum(alloc.values()), 1.0, places=4)
        self.assertGreater(alloc.get('TLT', 0), alloc.get('BTC', 0))

    def test_aggressive_user_allocation(self):
        RiskAssessment(user_id=str(self.user.id), answers={"age_bracket": "Under 30", "horizon": "Long-Term", "risk_tolerance": "Buy More"}, risk_score=100, risk_level="Very Aggressive").save()
        token = self.get_auth_token()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)
        response = self.client.post('/api/portfolio/generate/')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        alloc = response.data['asset_allocation']
        self.assertAlmostEqual(sum(alloc.values()), 1.0, places=4)
        self.assertGreater(alloc.get('BTC', 0), alloc.get('TLT', 0))
''',
    'apps/portfolio/models.py': '''from mongoengine import Document, StringField, DateTimeField, FloatField, DictField
import datetime

class Recommendation(Document):
    user_id = StringField(required=True)
    asset_allocation = DictField(required=True) 
    expected_return_1y = FloatField()
    portfolio_volatility = FloatField()
    created_at = DateTimeField(default=datetime.datetime.utcnow)
    meta = {'collection': 'recommendations'}
''',
    'apps/portfolio/services/portfolio_generator.py': '''from apps.engine.models import Forecast
from apps.engine.services.inference import bayes_engine
from apps.portfolio.models import Recommendation
from apps.users.models import RiskAssessment

def generate_fractional_portfolio(user_id):
    risk_assessment = RiskAssessment.objects(user_id=user_id).order_by('-created_at').first()
    if not risk_assessment: raise ValueError("User has no completed risk assessment.")
    risk_score = bayes_engine.calculate_risk_score(risk_assessment.answers)
    
    forecasts = Forecast.objects.all()
    if not forecasts: raise ValueError("No market forecasts available. Has Prophet run?")
        
    raw_suitability_scores = {}
    expected_portfolio_return = 0.0
    
    for f in forecasts:
        return_tier = 1
        if f.expected_return > 0.15: return_tier = 2
        elif f.expected_return < 0.05: return_tier = 0
            
        volatility_tier = 1
        if f.volatility > 0.20: volatility_tier = 2
        elif f.volatility < 0.05: volatility_tier = 0
            
        suitability = bayes_engine.calculate_asset_suitability(risk_profile_score=risk_score, expected_return_tier=return_tier, volatility_tier=volatility_tier)
        raw_suitability_scores[f.asset_ticker] = suitability

    filtered_scores = {k: v for k, v in raw_suitability_scores.items() if v >= 0.10}
    if not filtered_scores: filtered_scores = raw_suitability_scores
        
    total_score = sum(filtered_scores.values())
    final_allocation = {}
    for ticker, score in filtered_scores.items():
        weight = float(score / total_score)
        final_allocation[ticker] = weight
        f = [x for x in forecasts if x.asset_ticker == ticker][0]
        expected_portfolio_return += f.expected_return * weight
        
    recommendation = Recommendation(user_id=user_id, asset_allocation=final_allocation, expected_return_1y=expected_portfolio_return, portfolio_volatility=0.0)
    recommendation.save()
    return recommendation
''',
    'apps/portfolio/urls.py': '''from django.urls import path
from .views import PortfolioGenerateView

urlpatterns = [path('portfolio/generate/', PortfolioGenerateView.as_view(), name='portfolio-generate')]
''',
    'apps/portfolio/views.py': '''from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from apps.portfolio.services.portfolio_generator import generate_fractional_portfolio

class PortfolioGenerateView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        try:
            recommendation = generate_fractional_portfolio(str(request.user.id))
            response_data = {"user_id": recommendation.user_id, "asset_allocation": recommendation.asset_allocation, "expected_return_1y": recommendation.expected_return_1y, "created_at": recommendation.created_at.isoformat()}
            return Response(response_data, status=status.HTTP_201_CREATED)
        except ValueError as e: return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e: return Response({"error": "An internal ML error occurred."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
'''
}

import os

# First recreate the basic django structure with the new correct name bayesvest_project
os.system("django-admin startproject bayesvest_project .")

for filepath, content in files.items():
    directory = os.path.dirname(filepath)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

app_configs = {
    'apps/users/apps.py': 'apps.users',
    'apps/market/apps.py': 'apps.market',
    'apps/engine/apps.py': 'apps.engine',
    'apps/portfolio/apps.py': 'apps.portfolio'
}

for filepath, name in app_configs.items():
    directory = os.path.dirname(filepath)
    if directory and not os.path.exists(directory): os.makedirs(directory, exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f'from django.apps import AppConfig\n\nclass {name.split(".")[1].capitalize()}Config(AppConfig):\n    name = "{name}"\n')
        
init_dirs = ['apps', 'apps/engine', 'apps/engine/services', 'apps/market', 'apps/market/services', 'apps/portfolio', 'apps/portfolio/services', 'apps/users']
for d in init_dirs:
    if not os.path.exists(d): os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, '__init__.py'), 'w', encoding='utf-8') as f: f.write('')

with open('bayesvest_project/settings.py', 'r', encoding='utf-8') as f:
    s = f.read()

if 'MONGO_URI' not in s: 
    addons = """
# MongoDB Config
import os
import mongoengine
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/bayesvest_db")
mongoengine.connect(host=MONGO_URI)

# DB Bypass
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.dummy'
    }
}

# Celery
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'

# Test runner
TEST_RUNNER = 'bayesvest_project.test_runner.NoDbTestRunner'
"""
    s = s.replace("INSTALLED_APPS = [", 'INSTALLED_APPS = [\n    "django.contrib.auth",\n    "rest_framework",\n    "apps.users",\n    "apps.market",\n    "apps.engine",\n    "apps.portfolio",\n')
    s = s.replace("    'django.contrib.admin',\n", "")
    s += addons
    with open('bayesvest_project/settings.py', 'w', encoding='utf-8') as f: f.write(s)

with open('bayesvest_project/celery.py', 'w', encoding='utf-8') as f:
    f.write("""import os\nfrom celery import Celery\nos.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bayesvest_project.settings')\napp = Celery('bayesvest_project')\napp.config_from_object('django.conf:settings', namespace='CELERY')\napp.autodiscover_tasks()\n""")

with open('bayesvest_project/__init__.py', 'w', encoding='utf-8') as f:
    f.write("from .celery import app as celery_app\n__all__ = ('celery_app',)\n")

with open('bayesvest_project/test_runner.py', 'w', encoding='utf-8') as f:
    f.write("""from django.test.runner import DiscoverRunner\n\nclass NoDbTestRunner(DiscoverRunner):\n    def setup_databases(self, **kwargs): pass\n    def teardown_databases(self, old_config, **kwargs): pass\n""")

with open('bayesvest_project/urls.py', 'w', encoding='utf-8') as f:
    f.write("""from django.urls import path, include\n\nurlpatterns = [\n    path("api/users/", include("apps.users.urls")),\n    path("api/", include("apps.portfolio.urls")),\n]\n""")

print("SUCCESSFULLY REBUILT EVERYTHING AS BAYESVEST.")
