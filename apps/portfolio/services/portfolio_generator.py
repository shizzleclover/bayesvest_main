import logging
from collections import defaultdict

from apps.engine.models import Forecast
from apps.engine.services.inference import bayes_engine, RISK_LABELS
from apps.market.models import Asset
from apps.portfolio.models import Recommendation
from apps.users.models import RiskAssessment

logger = logging.getLogger(__name__)

RISK_DESCRIPTIONS = {
    0: "Your profile indicates a very low tolerance for risk. You prioritize capital preservation over growth. The portfolio is weighted heavily towards stable, low-volatility assets like bonds.",
    1: "Your profile indicates a conservative approach. You prefer steady, predictable returns with minimal exposure to volatile assets.",
    2: "Your profile indicates a balanced approach. You are comfortable with moderate risk in exchange for reasonable growth, blending equities and safer assets.",
    3: "Your profile indicates a high tolerance for risk. You are willing to accept significant short-term volatility in pursuit of higher long-term returns.",
    4: "Your profile indicates a very aggressive stance. You are comfortable with high volatility and prioritize maximum growth potential, including speculative assets like cryptocurrency.",
}

RETURN_TIER_LABELS = {0: "low", 1: "moderate", 2: "high"}
VOLATILITY_TIER_LABELS = {0: "low", 1: "moderate", 2: "high"}

# ── Risk-Profile → Asset-Class target allocation weights ─────
# The raw_score (0-100) is used to interpolate between adjacent bands
# for finer differentiation within each risk level.
CLASS_TARGETS = {
    0: {"Stock": 0.00, "ETF": 0.15, "Bond": 0.55, "REIT": 0.05, "Commodity": 0.15, "Crypto": 0.00},
    1: {"Stock": 0.10, "ETF": 0.25, "Bond": 0.40, "REIT": 0.05, "Commodity": 0.10, "Crypto": 0.00},
    2: {"Stock": 0.20, "ETF": 0.30, "Bond": 0.15, "REIT": 0.08, "Commodity": 0.07, "Crypto": 0.05},
    3: {"Stock": 0.30, "ETF": 0.25, "Bond": 0.05, "REIT": 0.05, "Commodity": 0.05, "Crypto": 0.15},
    4: {"Stock": 0.35, "ETF": 0.20, "Bond": 0.00, "REIT": 0.00, "Commodity": 0.05, "Crypto": 0.25},
}

MAX_PER_CLASS = {
    "Stock": 4, "ETF": 3, "Bond": 3, "REIT": 1, "Commodity": 1, "Crypto": 2,
}

# ── Synthetic forecast defaults per (asset_class, risk_level) ─
# Used when Prophet forecasts are missing.  Values are
# (expected_return, volatility) – reasonable market-typical numbers.
_SYNTHETIC = {
    ("Stock",     "Low"):    (0.07, 0.11),
    ("Stock",     "Medium"): (0.10, 0.18),
    ("Stock",     "High"):   (0.16, 0.28),
    ("ETF",       "Low"):    (0.05, 0.07),
    ("ETF",       "Medium"): (0.08, 0.13),
    ("ETF",       "High"):   (0.13, 0.22),
    ("Bond",      "Low"):    (0.03, 0.04),
    ("Bond",      "Medium"): (0.04, 0.06),
    ("Bond",      "High"):   (0.05, 0.09),
    ("REIT",      "Low"):    (0.06, 0.10),
    ("REIT",      "Medium"): (0.08, 0.15),
    ("REIT",      "High"):   (0.12, 0.22),
    ("Commodity", "Low"):    (0.04, 0.12),
    ("Commodity", "Medium"): (0.06, 0.17),
    ("Commodity", "High"):   (0.10, 0.25),
    ("Crypto",    "Low"):    (0.20, 0.45),
    ("Crypto",    "Medium"): (0.30, 0.55),
    ("Crypto",    "High"):   (0.40, 0.70),
}
_SYNTHETIC_DEFAULT = (0.07, 0.15)


def _classify_return_tier(expected_return):
    if expected_return > 0.15:
        return 2
    elif expected_return < 0.05:
        return 0
    return 1


def _classify_volatility_tier(volatility):
    if volatility > 0.20:
        return 2
    elif volatility < 0.05:
        return 0
    return 1


def _interpolate_targets(raw_score, band):
    """Interpolate class targets between the current band and the adjacent one
    using raw_score position within the band for smoother differentiation."""
    band_boundaries = [0, 25, 45, 65, 85, 100]
    low = band_boundaries[band]
    high = band_boundaries[band + 1]
    t = (raw_score - low) / max(high - low, 1)

    current = CLASS_TARGETS[band]
    adjacent = CLASS_TARGETS.get(min(band + 1, 4), current)

    interpolated = {}
    for cls in current:
        interpolated[cls] = current[cls] * (1 - t) + adjacent[cls] * t
    return interpolated


class _SyntheticForecast:
    """Lightweight stand-in for a Forecast document when Prophet hasn't run."""
    def __init__(self, ticker, expected_return, volatility):
        self.asset_ticker = ticker
        self.expected_return = expected_return
        self.volatility = volatility


def _build_asset_reason(ticker, asset, forecast, suitability, weight,
                        risk_score, risk_label, return_tier, volatility_tier):
    return_desc = RETURN_TIER_LABELS[return_tier]
    vol_desc = VOLATILITY_TIER_LABELS[volatility_tier]
    direction = "gain" if forecast.expected_return >= 0 else "loss"

    reason_parts = [
        f"{asset.name} ({ticker}) is forecasted a {abs(forecast.expected_return)*100:.1f}% {direction} over the next year "
        f"with {vol_desc} volatility ({forecast.volatility*100:.1f}%)."
    ]

    if suitability >= 0.7:
        reason_parts.append(
            f"The Bayesian model considers this asset highly suitable for a {risk_label} investor (suitability: {suitability:.0%})."
        )
    elif suitability >= 0.4:
        reason_parts.append(
            f"The Bayesian model considers this a moderately suitable asset for your {risk_label} profile (suitability: {suitability:.0%})."
        )
    else:
        reason_parts.append(
            f"This asset has lower suitability for a {risk_label} profile (suitability: {suitability:.0%}), but is included for diversification."
        )

    if risk_score <= 1:
        if vol_desc == "low":
            reason_parts.append("Its low volatility aligns well with your preference for stability.")
        elif vol_desc == "high":
            reason_parts.append("Despite its higher volatility, a small allocation provides growth potential without excessive risk.")
    elif risk_score >= 3:
        if return_desc == "high":
            reason_parts.append("Its high expected return matches your appetite for aggressive growth.")
        elif vol_desc == "low":
            reason_parts.append("This stable asset is included to provide a safety buffer within your aggressive portfolio.")
    else:
        reason_parts.append("This allocation reflects a balance between growth potential and risk management.")

    return {
        "ticker": ticker,
        "asset_name": asset.name,
        "allocation_pct": round(weight * 100, 1),
        "expected_return": round(forecast.expected_return * 100, 2),
        "volatility": round(forecast.volatility * 100, 2),
        "suitability_score": round(suitability, 4),
        "explanation": " ".join(reason_parts),
    }


def generate_fractional_portfolio(user_id):
    risk_assessment = RiskAssessment.objects(user_id=user_id).order_by('-created_at').first()
    if not risk_assessment:
        raise ValueError("User has no completed risk assessment.")

    raw_score, band = bayes_engine.calculate_risk_score(risk_assessment.answers)
    risk_label = RISK_LABELS.get(band, "Unknown")
    risk_summary = (
        f"Risk Level: {risk_label} ({raw_score}/100, band {band}/4). "
        f"{RISK_DESCRIPTIONS.get(band, '')}"
    )

    # ── Gather all assets and their forecasts ─────────────────
    all_assets = {a.ticker: a for a in Asset.objects.all()}
    real_forecasts = {f.asset_ticker: f for f in Forecast.objects.all()}

    # Fill in synthetic forecasts for any asset that lacks a real one
    forecast_map = {}
    for ticker, asset in all_assets.items():
        if ticker in real_forecasts:
            forecast_map[ticker] = real_forecasts[ticker]
        else:
            key = (asset.asset_class, asset.risk_level)
            exp_ret, vol = _SYNTHETIC.get(key, _SYNTHETIC_DEFAULT)
            forecast_map[ticker] = _SyntheticForecast(ticker, exp_ret, vol)
            logger.info("[PortfolioGen] Using synthetic forecast for %s (%s)", ticker, key)

    if not forecast_map:
        raise ValueError("No assets or forecasts available. Has the market data been seeded?")

    logger.info(
        "[PortfolioGen] user=%s raw_score=%d band=%d total_assets=%d real_forecasts=%d synthetic=%d",
        user_id, raw_score, band, len(all_assets),
        len(real_forecasts), len(forecast_map) - len(real_forecasts),
    )

    # ── 1. Score every asset with the Bayesian network ────────
    scored = []
    for ticker, forecast in forecast_map.items():
        asset = all_assets.get(ticker)
        if not asset:
            continue
        return_tier = _classify_return_tier(forecast.expected_return)
        volatility_tier = _classify_volatility_tier(forecast.volatility)
        suitability = bayes_engine.calculate_asset_suitability(
            risk_profile_score=band,
            expected_return_tier=return_tier,
            volatility_tier=volatility_tier,
        )
        scored.append({
            'ticker': ticker,
            'asset': asset,
            'forecast': forecast,
            'suitability': suitability,
            'return_tier': return_tier,
            'volatility_tier': volatility_tier,
        })

    # ── 2. Group by class, pick top N per class by suitability ─
    by_class = defaultdict(list)
    for s in scored:
        by_class[s['asset'].asset_class].append(s)

    for cls in by_class:
        by_class[cls].sort(key=lambda x: -x['suitability'])

    targets = _interpolate_targets(raw_score, band)
    selected = []

    for cls, target_pct in targets.items():
        if target_pct < 0.01:
            continue
        candidates = by_class.get(cls, [])
        top_n = candidates[:MAX_PER_CLASS.get(cls, 3)]
        if not top_n:
            continue
        for item in top_n:
            item['class_target'] = target_pct
            item['class_count'] = len(top_n)
        selected.extend(top_n)

    if not selected:
        selected = scored
        for item in selected:
            item['class_target'] = 1.0 / max(len(scored), 1)
            item['class_count'] = len(scored)

    # ── 3. Allocate within each class proportionally to suitability
    final_allocation = {}
    reasoning = []

    class_groups = defaultdict(list)
    for item in selected:
        class_groups[item['asset'].asset_class].append(item)

    for cls, items in class_groups.items():
        class_budget = items[0]['class_target']
        total_suit = sum(i['suitability'] for i in items) or 1.0

        for item in items:
            weight = class_budget * (item['suitability'] / total_suit)
            weight = max(weight, 0.01)
            final_allocation[item['ticker']] = weight

    # Normalise weights to sum to 1.0
    total_weight = sum(final_allocation.values()) or 1.0
    for ticker in final_allocation:
        final_allocation[ticker] /= total_weight

    # Compute expected return with normalised weights
    expected_portfolio_return = sum(
        final_allocation[item['ticker']] * item['forecast'].expected_return
        for item in selected
    )

    # Build reasoning after normalisation
    for item in selected:
        weight = final_allocation[item['ticker']]
        reason = _build_asset_reason(
            item['ticker'], item['asset'], item['forecast'],
            item['suitability'], weight,
            band, risk_label,
            item['return_tier'], item['volatility_tier'],
        )
        reason['allocation_pct'] = round(weight * 100, 1)
        reasoning.append(reason)

    reasoning.sort(key=lambda x: -x['allocation_pct'])

    logger.info(
        "[PortfolioGen] user=%s final assets=%d return=%.2f%% classes=%s",
        user_id, len(final_allocation), expected_portfolio_return * 100,
        list(class_groups.keys()),
    )

    recommendation = Recommendation(
        user_id=user_id,
        asset_allocation=final_allocation,
        expected_return_1y=expected_portfolio_return,
        portfolio_volatility=0.0,
        risk_summary=risk_summary,
        reasoning=reasoning,
    )
    recommendation.save()
    return recommendation
