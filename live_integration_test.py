"""
Bayesvest Live Integration Test
================================
This script tests the ENTIRE pipeline end-to-end with REAL data:
1. Fetches live market data from YFinance and CoinGecko
2. Aligns the data (forward-fills weekends)
3. Trains Prophet models on the real data
4. Creates 5 dummy user profiles ranging from Very Conservative to Very Aggressive
5. Runs the Bayesian Inference Engine + Portfolio Generator for each
6. Evaluates whether the advice is financially sensible
"""
import os, sys, io, django

# Fix Windows encoding for printing
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
from apps.market.services.data_ingestion import fetch_yfinance_data, fetch_coingecko_data
from apps.market.services.data_alignment import forward_fill_weekends
from apps.engine.services.prophet_pipeline import train_and_forecast_asset
from apps.engine.services.inference import bayes_engine
from apps.portfolio.services.portfolio_generator import generate_fractional_portfolio

PASS = "[PASS]"
FAIL = "[FAIL]"

# ============================================================
# PHASE 1: DATA INGESTION (Real API Calls)
# ============================================================
print("=" * 70)
print("PHASE 1: LIVE DATA INGESTION")
print("=" * 70)

# Clean up test data
Asset.objects.delete()
MarketData.objects.delete()
Forecast.objects.delete()
Recommendation.objects.delete()

# Seed assets
test_assets = [
    {"ticker": "AAPL", "name": "Apple Inc.", "asset_class": "Stock", "sector": "Tech", "risk_level": "Medium"},
    {"ticker": "TLT", "name": "iShares 20+ Year Treasury Bond ETF", "asset_class": "ETF", "sector": "Treasury", "risk_level": "Low"},
    {"ticker": "BTC", "name": "Bitcoin", "asset_class": "Crypto", "sector": "Currency", "risk_level": "High"},
]
for a in test_assets:
    Asset(**a).save()
print(f"  Seeded {len(test_assets)} assets: {[a['ticker'] for a in test_assets]}")

# Test 1.1: YFinance for AAPL
print("\n--- Test 1.1: Fetch AAPL from YFinance ---")
aapl_data = []
try:
    aapl_data = fetch_yfinance_data("AAPL", years=1)
    if aapl_data and len(aapl_data) > 100:
        print(f"  {PASS} | Fetched {len(aapl_data)} days of AAPL data")
        print(f"         | Sample: {aapl_data[-1]}")
    elif aapl_data and len(aapl_data) > 0:
        print(f"  {PASS} | Fetched {len(aapl_data)} days of AAPL data (less than expected but OK)")
    else:
        print(f"  {FAIL} | Got 0 days. YFinance may be rate-limited.")
except Exception as e:
    print(f"  {FAIL} | YFinance error: {e}")

# Test 1.2: YFinance for TLT
print("\n--- Test 1.2: Fetch TLT from YFinance ---")
tlt_data = []
try:
    tlt_data = fetch_yfinance_data("TLT", years=1)
    if tlt_data and len(tlt_data) > 100:
        print(f"  {PASS} | Fetched {len(tlt_data)} days of TLT data")
        print(f"         | Sample: {tlt_data[-1]}")
    elif tlt_data and len(tlt_data) > 0:
        print(f"  {PASS} | Fetched {len(tlt_data)} days of TLT data (less than expected but OK)")
    else:
        print(f"  {FAIL} | Got 0 days.")
except Exception as e:
    print(f"  {FAIL} | YFinance error: {e}")

# Test 1.3: CoinGecko for BTC
print("\n--- Test 1.3: Fetch BTC from CoinGecko ---")
btc_data = []
try:
    btc_data = fetch_coingecko_data("bitcoin", days=365)
    if btc_data and len(btc_data) > 100:
        print(f"  {PASS} | Fetched {len(btc_data)} days of BTC data")
        print(f"         | Sample: {btc_data[-1]}")
    elif btc_data and len(btc_data) > 0:
        print(f"  {PASS} | Fetched {len(btc_data)} days of BTC data (less than expected but OK)")
    else:
        print(f"  {FAIL} | Got 0 days.")
except Exception as e:
    print(f"  {FAIL} | CoinGecko error: {e}")

# If YFinance failed, use synthetic fallback data so the rest of the pipeline can be tested
if not aapl_data:
    print("\n  [INFO] YFinance AAPL failed. Using synthetic fallback data for testing.")
    import datetime
    base = datetime.datetime(2024, 3, 1)
    aapl_data = [{"date": (base + datetime.timedelta(days=i)).strftime('%Y-%m-%d'), "close": 170 + i * 0.1} for i in range(252)]
if not tlt_data:
    print("  [INFO] YFinance TLT failed. Using synthetic fallback data for testing.")
    import datetime
    base = datetime.datetime(2024, 3, 1)
    tlt_data = [{"date": (base + datetime.timedelta(days=i)).strftime('%Y-%m-%d'), "close": 90 + i * 0.02} for i in range(252)]
if not btc_data:
    print("  [INFO] CoinGecko BTC failed. Using synthetic fallback data for testing.")
    import datetime
    base = datetime.datetime(2024, 3, 1)
    btc_data = [{"date": (base + datetime.timedelta(days=i)).strftime('%Y-%m-%d'), "close": 45000 + i * 50} for i in range(365)]

# Test 1.4: Data Alignment
print("\n--- Test 1.4: Forward-Fill Weekends ---")
try:
    aligned_aapl = forward_fill_weekends(aapl_data)
    gap = len(aligned_aapl) - len(aapl_data)
    if gap > 0:
        print(f"  {PASS} | Filled {gap} weekend/holiday gaps ({len(aapl_data)} -> {len(aligned_aapl)} days)")
    else:
        print(f"  {PASS} | No gaps to fill (data already continuous)")
except Exception as e:
    print(f"  {FAIL} | Alignment error: {e}")

# Save to DB for Prophet
for ticker, raw_data in [("AAPL", aapl_data), ("TLT", tlt_data), ("BTC", btc_data)]:
    aligned = forward_fill_weekends(raw_data)
    md = MarketData(asset_ticker=ticker, historical_prices=aligned)
    md.save()
print(f"\n  Saved aligned data to MarketData for all {len(test_assets)} assets.")

# ============================================================
# PHASE 2: PROPHET MODEL TRAINING (Real ML)
# ============================================================
print("\n" + "=" * 70)
print("PHASE 2: PROPHET MODEL TRAINING")
print("=" * 70)

for ticker in ["AAPL", "TLT", "BTC"]:
    print(f"\n--- Test 2: Train Prophet for {ticker} ---")
    try:
        forecast = train_and_forecast_asset(ticker)
        if forecast:
            print(f"  {PASS} | Expected Return: {forecast.expected_return:.4f} ({forecast.expected_return*100:.1f}%)")
            print(f"         | Volatility:      {forecast.volatility:.4f} ({forecast.volatility*100:.1f}%)")
            print(f"         | Price Range:     [{forecast.yhat_lower:.2f}, {forecast.yhat_upper:.2f}]")
        else:
            print(f"  {FAIL} | Prophet returned None for {ticker}")
    except Exception as e:
        print(f"  {FAIL} | Prophet error for {ticker}: {e}")

# ============================================================
# PHASE 3: DUMMY USER PROFILES + PORTFOLIO GENERATION
# ============================================================
print("\n" + "=" * 70)
print("PHASE 3: DUMMY USER PROFILES & PORTFOLIO ADVICE QUALITY")
print("=" * 70)

dummy_profiles = {
    "Very Conservative (Retiree)": {
        "age_bracket": "60+", "horizon": "Short-Term (0-3 years)",
        "risk_tolerance": "Panic Sell", "experience": "Beginner (No experience)",
        "income_stability": "Unstable / Unemployed", "liquidity_needs": "High (May need cash soon)",
        "primary_goal": "Capital Preservation", "debt_to_income": "High (Strained)",
        "dependents": "3+", "reaction_to_volatility": "Anxious and want to sell"
    },
    "Conservative (Near-Retirement)": {
        "age_bracket": "46 - 60", "horizon": "Short-Term (0-3 years)",
        "risk_tolerance": "Wait it out", "experience": "Beginner (No experience)",
        "income_stability": "Variable / Freelance", "liquidity_needs": "Moderate",
        "primary_goal": "Capital Preservation", "debt_to_income": "Moderate (Manageable)",
        "dependents": "1-2", "reaction_to_volatility": "Anxious and want to sell"
    },
    "Moderate (Mid-Career)": {
        "age_bracket": "30 - 45", "horizon": "Medium-Term (3-10 years)",
        "risk_tolerance": "Wait it out", "experience": "Intermediate (Stocks/ETFs)",
        "income_stability": "Highly Stable", "liquidity_needs": "None",
        "primary_goal": "Balanced Wealth Accumulation", "debt_to_income": "Low (Comfortable)",
        "dependents": "1-2", "reaction_to_volatility": "Slightly concerned but stay the course"
    },
    "Aggressive (Young Professional)": {
        "age_bracket": "Under 30", "horizon": "Long-Term (10+ years)",
        "risk_tolerance": "Buy More", "experience": "Intermediate (Stocks/ETFs)",
        "income_stability": "Highly Stable", "liquidity_needs": "None",
        "primary_goal": "Aggressive Growth", "debt_to_income": "Low (Comfortable)",
        "dependents": "None", "reaction_to_volatility": "Excited by opportunity"
    },
    "Very Aggressive (Crypto Trader)": {
        "age_bracket": "Under 30", "horizon": "Long-Term (10+ years)",
        "risk_tolerance": "Buy More", "experience": "Advanced (Derivatives/Crypto)",
        "income_stability": "Highly Stable", "liquidity_needs": "None",
        "primary_goal": "Aggressive Growth", "debt_to_income": "Low (Comfortable)",
        "dependents": "None", "reaction_to_volatility": "Excited by opportunity"
    }
}

results = []

for profile_name, answers in dummy_profiles.items():
    print(f"\n--- Profile: {profile_name} ---")
    
    # Create dummy user
    email = f"{profile_name.split('(')[0].strip().lower().replace(' ', '_')}@livetest.bayesvest.ai"
    User.objects(email=email).delete()
    user = User(email=email)
    user.set_password("TestPassword123!")
    user.save()
    
    # Calculate risk score
    risk_score = bayes_engine.calculate_risk_score(answers)
    risk_labels = {0: "Very Conservative", 1: "Conservative", 2: "Moderate", 3: "Aggressive", 4: "Very Aggressive"}
    risk_label = risk_labels.get(risk_score, "Unknown")
    print(f"  Risk Score: {risk_score}/4 ({risk_label})")
    
    # Save risk assessment
    RiskAssessment(user_id=str(user.id), answers=answers, risk_score=risk_score, risk_level=risk_label).save()
    
    # Generate portfolio
    try:
        rec = generate_fractional_portfolio(str(user.id))
        alloc = rec.asset_allocation
        
        print(f"  Portfolio Allocation:")
        for ticker, weight in sorted(alloc.items(), key=lambda x: -x[1]):
            bar = "#" * int(weight * 40)
            print(f"    {ticker:5s}: {weight*100:5.1f}% {bar}")
        print(f"  Expected 1Y Return: {rec.expected_return_1y*100:.2f}%")
        
        # Sanity checks
        total = sum(alloc.values())
        sane = True
        issues = []
        
        if abs(total - 1.0) > 0.001:
            sane = False
            issues.append(f"Allocations sum to {total:.4f}, not 1.0")
        
        # Conservative users should favor TLT over BTC
        if risk_score <= 1:
            if alloc.get('BTC', 0) > alloc.get('TLT', 0):
                sane = False
                issues.append("Conservative user allocated MORE to BTC than TLT!")
        
        # Aggressive users should favor risky assets
        if risk_score >= 3:
            if alloc.get('TLT', 0) > alloc.get('BTC', 0) and alloc.get('TLT', 0) > alloc.get('AAPL', 0):
                sane = False
                issues.append("Aggressive user got mostly bonds!")
        
        if sane:
            print(f"  Advice Quality: {PASS}")
        else:
            print(f"  Advice Quality: {FAIL} | Issues: {'; '.join(issues)}")
        
        results.append({"profile": profile_name, "risk_score": risk_score, "allocation": alloc, "sane": sane, "issues": issues})
        
    except Exception as e:
        print(f"  {FAIL} | Portfolio generation error: {e}")
        results.append({"profile": profile_name, "risk_score": risk_score, "allocation": {}, "sane": False, "issues": [str(e)]})

# ============================================================
# SUMMARY
# ============================================================
print("\n" + "=" * 70)
print("FINAL SUMMARY")
print("=" * 70)
passed = sum(1 for r in results if r['sane'])
total = len(results)
print(f"\n  Profiles tested: {total}")
print(f"  Sensible advice: {passed}/{total}")

if passed == total:
    print(f"\n  {PASS} ALL PROFILES RECEIVED SENSIBLE ADVICE!")
else:
    print(f"\n  Some profiles received questionable advice:")
    for r in results:
        if not r['sane']:
            print(f"    - {r['profile']}: {'; '.join(r['issues'])}")

# Cleanup test users
for profile_name in dummy_profiles:
    email = f"{profile_name.split('(')[0].strip().lower().replace(' ', '_')}@livetest.bayesvest.ai"
    user = User.objects(email=email).first()
    if user:
        RiskAssessment.objects(user_id=str(user.id)).delete()
        Recommendation.objects(user_id=str(user.id)).delete()
        user.delete()

print("\n  Test data cleaned up. Done!")
