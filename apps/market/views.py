import logging

import yfinance as yf
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from .models import Asset, MarketData
from apps.engine.models import Forecast

logger = logging.getLogger(__name__)


class AssetDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Retrieve asset metadata, price history, forecast, and live market stats for a single ticker.",
        manual_parameters=[
            openapi.Parameter('ticker', openapi.IN_PATH, type=openapi.TYPE_STRING),
        ],
        responses={200: "Success", 404: "Asset not found"},
    )
    def get(self, request, ticker):
        ticker = ticker.upper()
        asset = Asset.objects(ticker=ticker).first()
        if not asset:
            return Response({"error": f"Asset {ticker} not found"}, status=status.HTTP_404_NOT_FOUND)

        # Price history from DB
        market_data = MarketData.objects(asset_ticker=ticker).first()
        price_history = []
        if market_data and market_data.historical_prices:
            price_history = market_data.historical_prices

        # Forecast from DB
        forecast_doc = Forecast.objects(asset_ticker=ticker).first()
        forecast = None
        if forecast_doc:
            forecast = {
                "expected_return": round(forecast_doc.expected_return * 100, 2),
                "volatility": round(forecast_doc.volatility * 100, 2),
                "yhat_upper": forecast_doc.yhat_upper,
                "yhat_lower": forecast_doc.yhat_lower,
                "forecast_date": forecast_doc.forecast_date.isoformat() if forecast_doc.forecast_date else None,
            }

        # Live stats from yfinance (cached per-request)
        live_stats = _fetch_live_stats(ticker, asset.asset_class)

        return Response({
            "ticker": ticker,
            "name": asset.name,
            "asset_class": asset.asset_class,
            "sector": asset.sector,
            "risk_level": asset.risk_level,
            "price_history": price_history,
            "forecast": forecast,
            "live_stats": live_stats,
        })


def _fetch_live_stats(ticker, asset_class):
    """Best-effort live stats from yfinance. Returns {} on failure."""
    if asset_class == "Crypto":
        return _crypto_stub(ticker)

    try:
        info = yf.Ticker(ticker).info
        return {
            "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "previous_close": info.get("previousClose") or info.get("regularMarketPreviousClose"),
            "market_cap": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE"),
            "dividend_yield": info.get("dividendYield"),
            "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
            "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
            "avg_volume": info.get("averageDailyVolume10Day") or info.get("averageVolume"),
            "beta": info.get("beta"),
            "description": info.get("longBusinessSummary"),
        }
    except Exception as e:
        logger.warning("[MarketView] yfinance info failed for %s: %s", ticker, e)
        return {}


def _crypto_stub(ticker):
    """For crypto tickers, derive stats from stored price history."""
    market_data = MarketData.objects(asset_ticker=ticker).first()
    if not market_data or not market_data.historical_prices:
        return {}

    prices = [p['close'] for p in market_data.historical_prices if 'close' in p]
    if not prices:
        return {}

    return {
        "current_price": prices[-1],
        "previous_close": prices[-2] if len(prices) > 1 else None,
        "fifty_two_week_high": max(prices[-365:]) if len(prices) > 1 else prices[-1],
        "fifty_two_week_low": min(prices[-365:]) if len(prices) > 1 else prices[-1],
        "description": f"{ticker} is a cryptocurrency. Price data sourced from CoinGecko.",
    }
