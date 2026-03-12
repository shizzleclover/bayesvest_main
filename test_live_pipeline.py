"""
Test the live startup pipeline:
1. Clear all MarketData, Forecasts, and Assets
2. Manually trigger the startup hooks (simulating a fresh server boot)
3. Verify data was fetched, models were trained, and portfolio can be generated
"""
import os, sys, io, django, time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bayesvest_project.settings')
django.setup()

import warnings
warnings.filterwarnings("ignore")

from apps.market.models import Asset, MarketData
from apps.engine.models import Forecast
from apps.users.models import User, RiskAssessment
from apps.portfolio.models import Recommendation

print("=" * 60)
print("STEP 1: CLEAR DATABASE (simulate fresh deploy)")
print("=" * 60)
Asset.objects.delete()
MarketData.objects.delete()
Forecast.objects.delete()
print(f"  Assets:     {Asset.objects.count()}")
print(f"  MarketData: {MarketData.objects.count()}")
print(f"  Forecasts:  {Forecast.objects.count()}")
print("  DB cleared.\n")

print("=" * 60)
print("STEP 2: TRIGGER MARKET INGESTION (auto-seeds + fetches)")
print("=" * 60)
from apps.market.tasks import run_daily_market_ingestion
result = run_daily_market_ingestion()
print(f"  Result: {result}")
print(f"  Assets now:     {Asset.objects.count()}")
print(f"  MarketData now: {MarketData.objects.count()}")
for md in MarketData.objects.all():
    print(f"    {md.asset_ticker}: {len(md.historical_prices)} data points, last updated: {md.last_updated}")

print(f"\n{'=' * 60}")
print("STEP 3: TRIGGER PROPHET TRAINING")
print("=" * 60)
from apps.engine.tasks import run_daily_prophet_training
result = run_daily_prophet_training()
print(f"  Result: {result}")
print(f"  Forecasts now: {Forecast.objects.count()}")
for f in Forecast.objects.all():
    print(f"    {f.asset_ticker}: return={f.expected_return:.4f} ({f.expected_return*100:.1f}%), vol={f.volatility:.4f} ({f.volatility*100:.1f}%)")

print(f"\n{'=' * 60}")
print("STEP 4: END-TO-END PORTFOLIO GENERATION")
print("=" * 60)
# Create a test user and generate a portfolio
email = "pipeline_test@bayesvest.ai"
User.objects(email=email).delete()
user = User(email=email)
user.set_password("Test123!")
user.save()

from apps.engine.services.inference import bayes_engine
answers = {
    "age_bracket": "30 - 45", "horizon": "Medium-Term (3-10 years)",
    "risk_tolerance": "Wait it out", "experience": "Intermediate (Stocks/ETFs)",
    "income_stability": "Highly Stable", "liquidity_needs": "None",
    "primary_goal": "Balanced Wealth Accumulation", "debt_to_income": "Low (Comfortable)",
    "dependents": "1-2", "reaction_to_volatility": "Slightly concerned but stay the course"
}
risk_score = bayes_engine.calculate_risk_score(answers)
risk_labels = {0: "Very Conservative", 1: "Conservative", 2: "Moderate", 3: "Aggressive", 4: "Very Aggressive"}
RiskAssessment(user_id=str(user.id), answers=answers, risk_score=risk_score, risk_level=risk_labels[risk_score]).save()
print(f"  Test user: {email}")
print(f"  Risk score: {risk_score}/4 ({risk_labels[risk_score]})")

from apps.portfolio.services.portfolio_generator import generate_fractional_portfolio
try:
    rec = generate_fractional_portfolio(str(user.id))
    print(f"  Portfolio generated successfully!")
    print(f"  Allocation:")
    for ticker, weight in sorted(rec.asset_allocation.items(), key=lambda x: -x[1]):
        bar = "#" * int(weight * 40)
        print(f"    {ticker:5s}: {weight*100:5.1f}% {bar}")
    print(f"  Expected 1Y Return: {rec.expected_return_1y*100:.2f}%")
    print(f"\n  [PASS] FULL LIVE PIPELINE WORKS END-TO-END!")
except Exception as e:
    print(f"  [FAIL] Portfolio generation failed: {e}")

# Cleanup
RiskAssessment.objects(user_id=str(user.id)).delete()
Recommendation.objects(user_id=str(user.id)).delete()
user.delete()
print("\n  Test user cleaned up. Done!")
