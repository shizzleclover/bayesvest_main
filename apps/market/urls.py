from django.urls import path
from .views import AssetDetailView, MarketNewsView, WatchlistView, WatchlistAddView, WatchlistRemoveView

urlpatterns = [
    path('market/asset/<str:ticker>/', AssetDetailView.as_view(), name='asset-detail'),
    path('market/news/', MarketNewsView.as_view(), name='market-news'),
    path('watchlist/', WatchlistView.as_view(), name='watchlist'),
    path('watchlist/add/', WatchlistAddView.as_view(), name='watchlist-add'),
    path('watchlist/remove/', WatchlistRemoveView.as_view(), name='watchlist-remove'),
]
