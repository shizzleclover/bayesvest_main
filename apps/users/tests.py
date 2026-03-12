import json
from django.test import SimpleTestCase
from rest_framework.test import APIClient
from rest_framework import status
from apps.users.models import User, FinancialProfile, RiskAssessment

class UserEndpointTests(SimpleTestCase):
    def setUp(self):
        User.objects.delete()
        FinancialProfile.objects.delete()
        RiskAssessment.objects.delete()
        
        self.client = APIClient()
        self.email = "test@bayesvest.ai"
        self.password = "SecurePassword123!"
        
        self.user = User(email=self.email)
        self.user.set_password(self.password)
        self.user.save()
        
    def tearDown(self):
        User.objects.delete()
        FinancialProfile.objects.delete()
        RiskAssessment.objects.delete()

    def get_auth_token(self):
        response = self.client.post('/api/users/auth/login/', {'email': self.email, 'password': self.password}, format='json')
        return response.data['access']

    def test_register_success(self):
        response = self.client.post('/api/users/auth/register/', {'email': 'newuser@bayesvest.ai', 'password': 'Password123'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('access', response.data)

    def test_register_duplicate_email(self):
        response = self.client.post('/api/users/auth/register/', {'email': 'test@bayesvest.ai', 'password': 'Password123'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_success(self):
        response = self.client.post('/api/users/auth/login/', {'email': self.email, 'password': self.password}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)

    def test_login_invalid_credentials(self):
        response = self.client.post('/api/users/auth/login/', {'email': self.email, 'password': 'WrongPassword'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_financial_profile_not_found(self):
        token = self.get_auth_token()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)
        response = self.client.get('/api/users/profile/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_financial_profile(self):
        token = self.get_auth_token()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)
        data = {'age': 30, 'income': 100000, 'savings': 50000, 'goals': 'Retirement', 'horizon': 'Long-term'}
        response = self.client.post('/api/users/profile/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        response_get = self.client.get('/api/users/profile/')
        self.assertEqual(response_get.status_code, status.HTTP_200_OK)
        self.assertEqual(response_get.data['age'], 30)

    def test_submit_risk_assessment_success(self):
        token = self.get_auth_token()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)
        answers = {
            "age_bracket": "30 - 45", "horizon": "Medium-Term (3-10 years)", 
            "risk_tolerance": "Wait it out", "experience": "Intermediate (Stocks/ETFs)",
            "income_stability": "Highly Stable", "liquidity_needs": "None",
            "primary_goal": "Balanced Wealth Accumulation", "debt_to_income": "Low (Comfortable)",
            "dependents": "1-2", "reaction_to_volatility": "Slightly concerned but stay the course"
        }
        response = self.client.post('/api/users/risk/', {'answers': answers}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('computed_risk_score', response.data)

    def test_get_risk_assessment(self):
        answers = {"age_bracket": "30 - 45"}
        RiskAssessment(user_id=str(self.user.id), answers=answers, risk_score=2, risk_level="Moderate").save()
        token = self.get_auth_token()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)
        response = self.client.get('/api/users/risk/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['risk_score'], 2)
