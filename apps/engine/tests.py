import json, uuid
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
        answers = {
            "age_bracket": "60+", "horizon": "Short-Term (0-3 years)", 
            "risk_tolerance": "Panic Sell", "experience": "Beginner (No experience)",
            "income_stability": "Unstable / Unemployed", "liquidity_needs": "High (May need cash soon)",
            "primary_goal": "Capital Preservation", "debt_to_income": "High (Strained)",
            "dependents": "3+", "reaction_to_volatility": "Anxious and want to sell"
        }
        RiskAssessment(user_id=str(self.user.id), answers=answers, risk_score=0, risk_level="Very Conservative").save()
        token = self.get_auth_token()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)
        response = self.client.post('/api/portfolio/generate/')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        alloc = response.data['asset_allocation']
        self.assertAlmostEqual(sum(alloc.values()), 1.0, places=4)
        self.assertGreater(alloc.get('TLT', 0), alloc.get('BTC', 0))

    def test_aggressive_user_allocation(self):
        answers = {
            "age_bracket": "Under 30", "horizon": "Long-Term (10+ years)", 
            "risk_tolerance": "Buy More", "experience": "Advanced (Derivatives/Crypto)",
            "income_stability": "Highly Stable", "liquidity_needs": "None",
            "primary_goal": "Aggressive Growth", "debt_to_income": "Low (Comfortable)",
            "dependents": "None", "reaction_to_volatility": "Excited by opportunity"
        }
        RiskAssessment(user_id=str(self.user.id), answers=answers, risk_score=4, risk_level="Very Aggressive").save()
        token = self.get_auth_token()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)
        response = self.client.post('/api/portfolio/generate/')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        alloc = response.data['asset_allocation']
        self.assertAlmostEqual(sum(alloc.values()), 1.0, places=4)
        self.assertGreater(alloc.get('BTC', 0), alloc.get('TLT', 0))
