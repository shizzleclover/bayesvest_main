from django.test import SimpleTestCase
from rest_framework.test import APIClient
from rest_framework import status
from unittest.mock import patch
from apps.users.models import User, RiskAssessment
from apps.market.models import Asset
from apps.engine.models import Forecast
from apps.portfolio.models import Recommendation

class PortfolioAppTests(SimpleTestCase):
    def setUp(self):
        User.objects.delete()
        RiskAssessment.objects.delete()
        Asset.objects.delete()
        Forecast.objects.delete()
        Recommendation.objects.delete()
        
        self.client = APIClient()
        self.email = "portfolio_test@bayesvest.ai"
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
        User.objects.delete()
        RiskAssessment.objects.delete()
        Asset.objects.delete()
        Forecast.objects.delete()
        Recommendation.objects.delete()
        
    def get_auth_token(self):
        response = self.client.post('/api/users/auth/login/', {'email': self.email, 'password': self.password}, format='json')
        return response.data['access']

    def test_generate_portfolio_without_risk_assessment(self):
        token = self.get_auth_token()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)
        
        response = self.client.post('/api/portfolio/generate/')
        
        # Should return 400 Bad Request because the user has no Risk Assessment yet
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('apps.portfolio.services.portfolio_generator.bayes_engine')
    def test_generate_portfolio_success(self, mock_bayes_engine):
        # Provide a mock Risk Assessment
        answers = {
            "age_bracket": "30 - 45", "horizon": "Medium-Term (3-10 years)", 
            "risk_tolerance": "Wait it out", "experience": "Intermediate (Stocks/ETFs)",
            "income_stability": "Highly Stable", "liquidity_needs": "None",
            "primary_goal": "Balanced Wealth Accumulation", "debt_to_income": "Low (Comfortable)",
            "dependents": "1-2", "reaction_to_volatility": "Slightly concerned but stay the course"
        }
        RiskAssessment(user_id=str(self.user.id), answers=answers, risk_score=2, risk_level="Moderate").save()
        
        # Mock the Bayesian Engine
        mock_bayes_engine.calculate_risk_score.return_value = 2
        def mock_suitability(risk_profile_score, expected_return_tier, volatility_tier):
            if expected_return_tier == 1 and volatility_tier == 1:
                return 0.8  # AAPL
            elif expected_return_tier == 2 and volatility_tier == 2:
                return 0.1  # BTC
            else:
                return 0.1  # TLT
        mock_bayes_engine.calculate_asset_suitability.side_effect = mock_suitability

        token = self.get_auth_token()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)
        
        response = self.client.post('/api/portfolio/generate/')
        
        # Ensure it was created successfully
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Verify response structure
        data = response.data
        self.assertIn('asset_allocation', data)
        self.assertIn('expected_return_1y', data)
        self.assertEqual(data['user_id'], str(self.user.id))
        
        # Verify fractions sum to 1.0
        allocation = data['asset_allocation']
        self.assertAlmostEqual(sum(allocation.values()), 1.0, places=4)
        
        # Based on our mock, AAPL should have the highest fraction (0.8 / 1.0) = 80%
        self.assertGreater(allocation.get('AAPL', 0), allocation.get('BTC', 0))
        self.assertGreater(allocation.get('AAPL', 0), allocation.get('TLT', 0))
