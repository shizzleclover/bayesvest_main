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
# Each risk level defines a target % of the portfolio per class.
# The generator picks the top assets from each class by suitability,
# then distributes each class's budget proportionally.
CLASS_TARGETS = {
    #                  Stock   ETF    Bond   REIT   Commodity  Crypto
    0: {"Stock": 0.00, "ETF": 0.15, "Bond": 0.55, "REIT": 0.05, "Commodity": 0.15, "Crypto": 0.00},
    1: {"Stock": 0.10, "ETF": 0.25, "Bond": 0.40, "REIT": 0.05, "Commodity": 0.10, "Crypto": 0.00},
    2: {"Stock": 0.20, "ETF": 0.30, "Bond": 0.15, "REIT": 0.08, "Commodity": 0.07, "Crypto": 0.05},
    3: {"Stock": 0.30, "ETF": 0.25, "Bond": 0.05, "REIT": 0.05, "Commodity": 0.05, "Crypto": 0.15},
    4: {"Stock": 0.35, "ETF": 0.20, "Bond": 0.00, "REIT": 0.00, "Commodity": 0.05, "Crypto": 0.25},
}

# Maximum assets to include per class (keeps portfolio readable)
MAX_PER_CLASS = {
    "Stock": 4, "ETF": 3, "Bond": 3, "REIT": 1, "Commodity": 1, "Crypto": 2,
}


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


def _build_asset_reason(ticker, asset, forecast, suitability, weight,
                        risk_score, risk_label, return_tier, volatility_tier):
    """Generate a human-readable explanation for why this asset was allocated a specific weight."""
    return_desc = RETURN_TIER_LABELS[return_tier]
    vol_desc = VOLATILITY_TIER_LABELS[volatility_tier]
    direction = "gain" if forecast.expected_return >= 0 else "loss"

    reason_parts = []

    reason_parts.append(
        f"{asset.name} ({ticker}) is forecasted a {abs(forecast.expected_return)*100:.1f}% {direction} over the next year "
        f"with {vol_desc} volatility ({forecast.volatility*100:.1f}%)."
    )

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

    forecasts = list(Forecast.objects.all())
    if not forecasts:
        raise ValueError("No market forecasts available. Has Prophet run?")

    # Build a map of ticker → Asset for class lookup
    asset_map = {a.ticker: a for a in Asset.objects.all()}

    # ── 1. Score every forecasted asset with the Bayesian network ──
    scored = []
    for f in forecasts:
        asset = asset_map.get(f.asset_ticker)
        if not asset:
            continue
        return_tier = _classify_return_tier(f.expected_return)
        volatility_tier = _classify_volatility_tier(f.volatility)
        suitability = bayes_engine.calculate_asset_suitability(
            risk_profile_score=band,
            expected_return_tier=return_tier,
            volatility_tier=volatility_tier,
        )
        scored.append({
            'ticker': f.asset_ticker,
            'asset': asset,
            'forecast': f,
            'suitability': suitability,
            'return_tier': return_tier,
            'volatility_tier': volatility_tier,
        })

    logger.info(
        "[PortfolioGen] user=%s band=%d scored %d assets",
        user_id, band, len(scored),
    )

    # ── 2. Group by asset class, pick top N per class by suitability ──
    by_class = defaultdict(list)
    for s in scored:
        by_class[s['asset'].asset_class].append(s)

    for cls in by_class:
        by_class[cls].sort(key=lambda x: -x['suitability'])

    targets = CLASS_TARGETS.get(band, CLASS_TARGETS[2])
    selected = []

    for cls, target_pct in targets.items():
        if target_pct <= 0:
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
        # Fallback: use everything, weighted by suitability
        selected = scored
        for item in selected:
            item['class_target'] = 1.0 / max(len(scored), 1)
            item['class_count'] = len(scored)

    # ── 3. Allocate within each class proportionally to suitability ──
    final_allocation = {}
    expected_portfolio_return = 0.0
    reasoning = []

    class_groups = defaultdict(list)
    for item in selected:
        class_groups[item['asset'].asset_class].append(item)

    for cls, items in class_groups.items():
        class_budget = items[0]['class_target']
        total_suit = sum(i['suitability'] for i in items) or 1.0

        for item in items:
            weight = class_budget * (item['suitability'] / total_suit)
            weight = max(weight, 0.01)  # floor at 1%
            final_allocation[item['ticker']] = weight
            expected_portfolio_return += item['forecast'].expected_return * weight

            reason = _build_asset_reason(
                item['ticker'], item['asset'], item['forecast'],
                item['suitability'], weight,
                band, risk_label,
                item['return_tier'], item['volatility_tier'],
            )
            reasoning.append(reason)

    # Normalise weights to sum to 1.0
    total_weight = sum(final_allocation.values()) or 1.0
    for ticker in final_allocation:
        final_allocation[ticker] /= total_weight

    # Recompute expected return with normalised weights
    expected_portfolio_return = sum(
        final_allocation[item['ticker']] * item['forecast'].expected_return
        for item in selected
    )

    # Re-stamp allocation_pct in reasoning after normalisation
    for r in reasoning:
        r['allocation_pct'] = round(final_allocation[r['ticker']] * 100, 1)

    reasoning.sort(key=lambda x: -x['allocation_pct'])

    logger.info(
        "[PortfolioGen] user=%s final assets=%d return=%.2f%%",
        user_id, len(final_allocation), expected_portfolio_return * 100,
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
