import logging
import time

import requests
import yfinance as yf
from django.conf import settings as django_settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from .models import Asset, MarketData, Watchlist
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


# ── News endpoint ──────────────────────────────────────────────

_news_cache = {'data': [], 'ts': 0}
_NEWS_TTL = 1800  # 30 minutes


class MarketNewsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        now = time.time()
        if _news_cache['data'] and now - _news_cache['ts'] < _NEWS_TTL:
            return Response(_news_cache['data'])

        articles = _fetch_news()
        _news_cache['data'] = articles
        _news_cache['ts'] = now
        return Response(articles)


def _fetch_news():
    """Fetch financial news, trying Finnhub first, then GNews as fallback."""
    articles = _try_finnhub()
    if articles:
        return articles
    articles = _try_gnews()
    if articles:
        return articles
    return _fallback_news()


def _try_finnhub():
    try:
        api_key = getattr(django_settings, 'FINNHUB_API_KEY', '') or ''
        if not api_key:
            return None
        url = f"https://finnhub.io/api/v1/news?category=general&token={api_key}"
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            logger.warning("[News] Finnhub returned %d", resp.status_code)
            return None
        items = resp.json()
        if not isinstance(items, list) or not items:
            return None
        return [
            {
                "title": a.get("headline", ""),
                "summary": a.get("summary", ""),
                "source": a.get("source", ""),
                "url": a.get("url", ""),
                "published_at": a.get("datetime", 0),
                "image_url": a.get("image", ""),
            }
            for a in items[:20]
            if a.get("headline")
        ]
    except Exception as e:
        logger.warning("[News] Finnhub failed: %s", e)
        return None


def _try_gnews():
    """GNews free tier — 10 results, no key needed for top headlines."""
    try:
        url = "https://gnews.io/api/v4/top-headlines?category=business&lang=en&max=15&apikey=demo"
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            logger.warning("[News] GNews returned %d", resp.status_code)
            return None
        data = resp.json()
        items = data.get("articles", [])
        if not items:
            return None
        return [
            {
                "title": a.get("title", ""),
                "summary": a.get("description", ""),
                "source": a.get("source", {}).get("name", ""),
                "url": a.get("url", ""),
                "published_at": _iso_to_ts(a.get("publishedAt", "")),
                "image_url": a.get("image", ""),
            }
            for a in items
            if a.get("title")
        ]
    except Exception as e:
        logger.warning("[News] GNews failed: %s", e)
        return None


def _iso_to_ts(iso_str):
    """Convert ISO 8601 datetime string to unix timestamp."""
    try:
        import datetime as _dt
        dt = _dt.datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return int(dt.timestamp())
    except Exception:
        return int(time.time())


def _fallback_news():
    """Static fallback articles when the API is unavailable."""
    return [
        {
            "title": "Diversification remains key in volatile markets",
            "summary": "Financial advisors continue to recommend spreading investments across asset classes to manage risk effectively.",
            "source": "Bayesvest Insights",
            "url": "",
            "published_at": int(time.time()),
            "image_url": "",
        },
        {
            "title": "Understanding compound interest and long-term growth",
            "summary": "Starting early and investing consistently can dramatically increase your portfolio value over decades.",
            "source": "Bayesvest Insights",
            "url": "",
            "published_at": int(time.time()),
            "image_url": "",
        },
    ]


# ── Watchlist endpoints ────────────────────────────────────────

class WatchlistView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        wl = Watchlist.objects(user_id=str(request.user.id)).first()
        tickers = wl.tickers if wl else []
        items = []
        for t in tickers:
            asset = Asset.objects(ticker=t).first()
            md = MarketData.objects(asset_ticker=t).first()
            price = None
            prev = None
            if md and md.historical_prices:
                prices = [p['close'] for p in md.historical_prices if 'close' in p]
                if prices:
                    price = prices[-1]
                    prev = prices[-2] if len(prices) > 1 else None
            items.append({
                "ticker": t,
                "name": asset.name if asset else t,
                "asset_class": asset.asset_class if asset else "",
                "current_price": price,
                "previous_close": prev,
            })
        return Response(items)


class WatchlistAddView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ticker = request.data.get('ticker', '').upper()
        if not ticker:
            return Response({"error": "ticker required"}, status=status.HTTP_400_BAD_REQUEST)
        wl = Watchlist.objects(user_id=str(request.user.id)).first()
        if not wl:
            wl = Watchlist(user_id=str(request.user.id), tickers=[])
        if ticker not in wl.tickers:
            wl.tickers.append(ticker)
            wl.save()
        return Response({"tickers": wl.tickers})


class WatchlistRemoveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ticker = request.data.get('ticker', '').upper()
        wl = Watchlist.objects(user_id=str(request.user.id)).first()
        if wl and ticker in wl.tickers:
            wl.tickers.remove(ticker)
            wl.save()
        return Response({"tickers": wl.tickers if wl else []})
