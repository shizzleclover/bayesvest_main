from django.urls import path
from .views import PortfolioGenerateView

urlpatterns = [path('portfolio/generate/', PortfolioGenerateView.as_view(), name='portfolio-generate')]
