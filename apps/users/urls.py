from django.urls import path
from .views import RegisterView, LoginView, FinancialProfileView, RiskAssessmentView

urlpatterns = [
    path('auth/register/', RegisterView.as_view(), name='register'),
    path('auth/login/', LoginView.as_view(), name='login'),
    path('profile/', FinancialProfileView.as_view(), name='profile'),
    path('risk/', RiskAssessmentView.as_view(), name='risk_assessment'),
]