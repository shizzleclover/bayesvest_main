from django.urls import path
from .views import AssetDetailView

urlpatterns = [
    path('market/asset/<str:ticker>/', AssetDetailView.as_view(), name='asset-detail'),
]
