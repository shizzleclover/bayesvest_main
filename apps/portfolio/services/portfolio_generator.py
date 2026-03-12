from apps.engine.models import Forecast
from apps.engine.services.inference import bayes_engine
from apps.market.models import Asset
from apps.portfolio.models import Recommendation
from apps.users.models import RiskAssessment

RISK_LABELS = {
    0: "Very Conservative",
    1: "Conservative",
    2: "Moderate",
    3: "Aggressive",
    4: "Very Aggressive"
}

RISK_DESCRIPTIONS = {
    0: "Your profile indicates a very low tolerance for risk. You prioritize capital preservation over growth. The portfolio is weighted heavily towards stable, low-volatility assets like bonds.",
    1: "Your profile indicates a conservative approach. You prefer steady, predictable returns with minimal exposure to volatile assets.",
    2: "Your profile indicates a balanced approach. You are comfortable with moderate risk in exchange for reasonable growth, blending equities and safer assets.",
    3: "Your profile indicates a high tolerance for risk. You are willing to accept significant short-term volatility in pursuit of higher long-term returns.",
    4: "Your profile indicates a very aggressive stance. You are comfortable with high volatility and prioritize maximum growth potential, including speculative assets like cryptocurrency."
}

RETURN_TIER_LABELS = {0: "low", 1: "moderate", 2: "high"}
VOLATILITY_TIER_LABELS = {0: "low", 1: "moderate", 2: "high"}

def _classify_return_tier(expected_return):
    if expected_return > 0.15: return 2
    elif expected_return < 0.05: return 0
    return 1

def _classify_volatility_tier(volatility):
    if volatility > 0.20: return 2
    elif volatility < 0.05: return 0
    return 1

def _build_asset_reason(ticker, asset, forecast, suitability, weight, risk_score, risk_label, return_tier, volatility_tier):
    """Generate a human-readable explanation for why this asset was allocated a specific weight."""
    
    return_desc = RETURN_TIER_LABELS[return_tier]
    vol_desc = VOLATILITY_TIER_LABELS[volatility_tier]
    direction = "gain" if forecast.expected_return >= 0 else "loss"
    
    # Core reasoning
    reason_parts = []
    
    # 1. What the market data says
    reason_parts.append(
        f"{asset.name} ({ticker}) is forecasted a {abs(forecast.expected_return)*100:.1f}% {direction} over the next year "
        f"with {vol_desc} volatility ({forecast.volatility*100:.1f}%)."
    )
    
    # 2. Why the Bayesian network scored it this way
    if suitability >= 0.7:
        reason_parts.append(f"The Bayesian model considers this asset highly suitable for a {risk_label} investor (suitability: {suitability:.0%}).")
    elif suitability >= 0.4:
        reason_parts.append(f"The Bayesian model considers this a moderately suitable asset for your {risk_label} profile (suitability: {suitability:.0%}).")
    else:
        reason_parts.append(f"This asset has lower suitability for a {risk_label} profile (suitability: {suitability:.0%}), but is included for diversification.")
    
    # 3. Risk-specific reasoning
    if risk_score <= 1:  # Conservative
        if vol_desc == "low":
            reason_parts.append("Its low volatility aligns well with your preference for stability.")
        elif vol_desc == "high":
            reason_parts.append("Despite its higher volatility, a small allocation provides growth potential without excessive risk.")
    elif risk_score >= 3:  # Aggressive
        if return_desc == "high":
            reason_parts.append("Its high expected return matches your appetite for aggressive growth.")
        elif vol_desc == "low":
            reason_parts.append("This stable asset is included to provide a safety buffer within your aggressive portfolio.")
    else:  # Moderate
        reason_parts.append("This allocation reflects a balance between growth potential and risk management.")
    
    return {
        "ticker": ticker,
        "asset_name": asset.name,
        "allocation_pct": round(weight * 100, 1),
        "expected_return": round(forecast.expected_return * 100, 2),
        "volatility": round(forecast.volatility * 100, 2),
        "suitability_score": round(suitability, 4),
        "explanation": " ".join(reason_parts)
    }


def generate_fractional_portfolio(user_id):
    risk_assessment = RiskAssessment.objects(user_id=user_id).order_by('-created_at').first()
    if not risk_assessment: raise ValueError("User has no completed risk assessment.")
    risk_score = bayes_engine.calculate_risk_score(risk_assessment.answers)
    risk_label = RISK_LABELS.get(risk_score, "Unknown")
    risk_summary = f"Risk Level: {risk_label} ({risk_score}/4). {RISK_DESCRIPTIONS.get(risk_score, '')}"
    
    forecasts = Forecast.objects.all()
    if not forecasts: raise ValueError("No market forecasts available. Has Prophet run?")
        
    raw_suitability_scores = {}
    return_tiers = {}
    volatility_tiers = {}
    expected_portfolio_return = 0.0
    
    for f in forecasts:
        return_tier = _classify_return_tier(f.expected_return)
        volatility_tier = _classify_volatility_tier(f.volatility)
        return_tiers[f.asset_ticker] = return_tier
        volatility_tiers[f.asset_ticker] = volatility_tier
            
        suitability = bayes_engine.calculate_asset_suitability(
            risk_profile_score=risk_score,
            expected_return_tier=return_tier,
            volatility_tier=volatility_tier
        )
        raw_suitability_scores[f.asset_ticker] = suitability

    filtered_scores = {k: v for k, v in raw_suitability_scores.items() if v >= 0.10}
    if not filtered_scores: filtered_scores = raw_suitability_scores
        
    total_score = sum(filtered_scores.values())
    final_allocation = {}
    reasoning = []
    
    for ticker, score in filtered_scores.items():
        weight = float(score / total_score)
        final_allocation[ticker] = weight
        f = [x for x in forecasts if x.asset_ticker == ticker][0]
        expected_portfolio_return += f.expected_return * weight
        
        # Build reasoning for this asset
        asset = Asset.objects(ticker=ticker).first()
        if asset:
            reason = _build_asset_reason(
                ticker, asset, f, score, weight,
                risk_score, risk_label,
                return_tiers[ticker], volatility_tiers[ticker]
            )
            reasoning.append(reason)
    
    # Sort reasoning by allocation (highest first)
    reasoning.sort(key=lambda x: -x['allocation_pct'])
        
    recommendation = Recommendation(
        user_id=user_id,
        asset_allocation=final_allocation,
        expected_return_1y=expected_portfolio_return,
        portfolio_volatility=0.0,
        risk_summary=risk_summary,
        reasoning=reasoning
    )
    recommendation.save()
    return recommendation
