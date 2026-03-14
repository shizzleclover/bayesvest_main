from django.urls import path
from .views import PortfolioGenerateView, PortfolioLatestView

urlpatterns = [
    path('portfolio/generate/', PortfolioGenerateView.as_view(), name='portfolio-generate'),
    path('portfolio/latest/', PortfolioLatestView.as_view(), name='portfolio-latest'),
]
