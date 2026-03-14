import logging

from .bayesian_network import build_bayesian_network

logger = logging.getLogger(__name__)

RISK_LABELS = {
    0: "Very Conservative",
    1: "Conservative",
    2: "Moderate",
    3: "Aggressive",
    4: "Very Aggressive",
}


class InferenceEngine:
    def __init__(self):
        self.network = build_bayesian_network()

    def calculate_risk_score(self, answers):
        """Return (raw_score, band) where raw_score is 0-100 and band is 0-4."""
        total_score = 0

        # 1. Age (Capacity) [Max 15]
        age = answers.get('age_bracket', '')
        if age == "Under 30": total_score += 15
        elif age == "30 - 45": total_score += 10
        elif age == "46 - 60": total_score += 5

        # 2. Time Horizon (Capacity) [Max 15]
        horizon = answers.get('horizon', '')
        if horizon == "Long-Term (10+ years)": total_score += 15
        elif horizon == "Medium-Term (3-10 years)": total_score += 8

        # 3. Behavioral Risk Tolerance (Willingness) [Max 15]
        tolerance = answers.get('risk_tolerance', '')
        if tolerance == "Buy More": total_score += 15
        elif tolerance == "Wait it out": total_score += 8

        # 4. Investment Experience (Awareness) [Max 10]
        experience = answers.get('experience', '')
        if experience == "Advanced (Derivatives/Crypto)": total_score += 10
        elif experience == "Intermediate (Stocks/ETFs)": total_score += 5

        # 5. Income Stability (Capacity) [Max 10]
        income_stability = answers.get('income_stability', '')
        if income_stability == "Highly Stable": total_score += 10
        elif income_stability == "Variable / Freelance": total_score += 5

        # 6. Liquidity Needs (Capacity) [Max 10]
        liquidity = answers.get('liquidity_needs', '')
        if liquidity == "None": total_score += 10
        elif liquidity == "Moderate": total_score += 5

        # 7. Primary Investment Goal (Willingness/Trajectory) [Max 10]
        goal = answers.get('primary_goal', '')
        if goal == "Aggressive Growth": total_score += 10
        elif goal == "Balanced Wealth Accumulation": total_score += 5

        # 8. Debt-to-Income (Capacity) [Max 5]
        debt = answers.get('debt_to_income', '')
        if debt == "Low (Comfortable)": total_score += 5
        elif debt == "Moderate (Manageable)": total_score += 2

        # 9. Dependents (Capacity constraint) [Max 5]
        dependents = answers.get('dependents', '')
        if dependents == "None": total_score += 5
        elif dependents == "1-2": total_score += 2

        # 10. True Reaction to Volatility (Willingness/Emotional Factor) [Max 5]
        reaction = answers.get('reaction_to_volatility', '')
        if reaction == "Excited by opportunity": total_score += 5
        elif reaction == "Slightly concerned but stay the course": total_score += 2

        # Map raw 0-100 to band 0-4
        if total_score <= 25:
            band = 0
        elif total_score <= 45:
            band = 1
        elif total_score <= 65:
            band = 2
        elif total_score <= 85:
            band = 3
        else:
            band = 4

        logger.info(
            "[Inference] answers=%s  raw_score=%d  band=%d (%s)",
            {k: v for k, v in answers.items()},
            total_score, band, RISK_LABELS.get(band),
        )

        return total_score, band

    def calculate_asset_suitability(self, risk_profile_score, expected_return_tier, volatility_tier):
        evidence = {
            'Risk_Profile_Score': risk_profile_score,
            'Expected_Return': expected_return_tier,
            'Volatility': volatility_tier,
        }
        result = self.network.query(variables=['Asset_Suitability'], evidence=evidence)
        suitability = float(result.values[1])
        return suitability


bayes_engine = InferenceEngine()
