from django.urls import path
from .views import PortfolioGenerateView, PortfolioLatestView, PortfolioHistoryView, PortfolioDriftView

urlpatterns = [
    path('portfolio/generate/', PortfolioGenerateView.as_view(), name='portfolio-generate'),
    path('portfolio/latest/', PortfolioLatestView.as_view(), name='portfolio-latest'),
    path('portfolio/history/', PortfolioHistoryView.as_view(), name='portfolio-history'),
    path('portfolio/drift/', PortfolioDriftView.as_view(), name='portfolio-drift'),
]
