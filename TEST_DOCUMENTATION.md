# Bayesvest Backend — Test Documentation

## Table of Contents

- [Test Environment](#test-environment)
- [How to Run Tests](#how-to-run-tests)
- [Unit Tests](#unit-tests)
  - [Users App](#1-users-app)
  - [Market App](#2-market-app)
  - [Engine App](#3-engine-app)
  - [Portfolio App](#4-portfolio-app)
- [Live Integration Test](#live-integration-test)
  - [Data Ingestion Results](#phase-1-data-ingestion)
  - [Prophet Training Results](#phase-2-prophet-model-training)
  - [Portfolio Advice Quality](#phase-3-portfolio-advice-quality)

---

## Test Environment

| Component              | Value                                                                              |
| ---------------------- | ---------------------------------------------------------------------------------- |
| **Framework**    | Django 5.x + Django REST Framework                                                 |
| **Database**     | MongoDB Atlas (via MongoEngine)                                                    |
| **Test Runner**  | `bayesvest_project.test_runner.NoDbTestRunner` (bypasses Django SQL DB creation) |
| **Task Queue**   | Celery with `CELERY_TASK_ALWAYS_EAGER=True` (synchronous, no Redis needed)       |
| **ML Libraries** | Prophet (forecasting), pgmpy (Bayesian Network)                                    |
| **Data Sources** | Yahoo Finance (`yfinance`), CoinGecko (`pycoingecko`)                          |
| **Auth**         | JWT via `djangorestframework-simplejwt` with custom `MongoJWTAuthentication`   |

---

## How to Run Tests

### Unit Tests (All Apps)

```bash
# Activate virtual environment
.\venv\Scripts\Activate      # Windows
source venv/bin/activate     # macOS/Linux

# Run all unit tests
python manage.py test

# Run tests for a specific app
python manage.py test apps.users
python manage.py test apps.market
python manage.py test apps.engine
python manage.py test apps.portfolio
```

### Live Integration Test (Real APIs + ML)

```bash
python live_integration_test.py
```

> **Note:** This script makes real API calls to YFinance and CoinGecko and trains Prophet models. It takes ~2 minutes to complete.

---

## Unit Tests

### 1. Users App

**File:** `apps/users/tests.py` — **8 tests**

| # | Test Name                                | Type      | Description                                                    | Expected Result                              |
| - | ---------------------------------------- | --------- | -------------------------------------------------------------- | -------------------------------------------- |
| 1 | `test_register_success`                | Endpoint  | POST `/api/users/auth/register/` with valid email & password | 201 Created, JWT tokens returned             |
| 2 | `test_register_duplicate_email`        | Edge Case | POST register with an email that already exists                | 400 Bad Request                              |
| 3 | `test_login_success`                   | Endpoint  | POST `/api/users/auth/login/` with correct credentials       | 200 OK, JWT tokens returned                  |
| 4 | `test_login_invalid_credentials`       | Edge Case | POST login with wrong password                                 | 401 Unauthorized                             |
| 5 | `test_get_financial_profile_not_found` | Edge Case | GET `/api/users/profile/` when no profile exists             | 404 Not Found                                |
| 6 | `test_create_financial_profile`        | Endpoint  | POST `/api/users/profile/` then GET to verify persistence    | 200 OK, data matches                         |
| 7 | `test_submit_risk_assessment_success`  | Endpoint  | POST `/api/users/risk/` with full questionnaire answers      | 201 Created,`computed_risk_score` returned |
| 8 | `test_get_risk_assessment`             | Endpoint  | GET `/api/users/risk/` retrieves latest saved assessment     | 200 OK,`risk_score` matches                |

**Result:** ✅ 8/8 Passed

---

### 2. Market App

**File:** `apps/market/tests.py` — **2 tests**

| # | Test Name                           | Type | Description                                                                                      | Expected Result                                                             |
| - | ----------------------------------- | ---- | ------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------- |
| 1 | `test_forward_fill_weekends`      | Unit | Tests `data_alignment.forward_fill_weekends()` fills Saturday/Sunday with Friday's close price | Output has 7 days (5 original + 2 weekend), weekend values = Friday's close |
| 2 | `test_run_daily_market_ingestion` | Task | Mocks `fetch_yfinance_data` and `fetch_coingecko_data`, runs Celery task                     | MarketData saved for both assets, summary string confirms 2 ingested        |

**Result:** ✅ 2/2 Passed

---

### 3. Engine App

**File:** `apps/engine/tests.py` — **2 tests**

| # | Test Name                             | Type        | Description                                                            | Expected Result                                    |
| - | ------------------------------------- | ----------- | ---------------------------------------------------------------------- | -------------------------------------------------- |
| 1 | `test_conservative_user_allocation` | Integration | Full pipeline: conservative profile → Bayesian inference → portfolio | Allocations sum to 1.0. TLT (bonds) > BTC (crypto) |
| 2 | `test_aggressive_user_allocation`   | Integration | Full pipeline: aggressive profile → Bayesian inference → portfolio   | Allocations sum to 1.0. BTC (crypto) > TLT (bonds) |

**Result:** ✅ 2/2 Passed

---

### 4. Portfolio App

**File:** `apps/portfolio/tests.py` — **2 tests**

| # | Test Name                                           | Type        | Description                                                        | Expected Result                                                                    |
| - | --------------------------------------------------- | ----------- | ------------------------------------------------------------------ | ---------------------------------------------------------------------------------- |
| 1 | `test_generate_portfolio_without_risk_assessment` | Edge Case   | POST `/api/portfolio/generate/` without completing questionnaire | 400 Bad Request                                                                    |
| 2 | `test_generate_portfolio_success`                 | Integration | Mocked Bayesian Engine → fractional portfolio generation          | 201 Created, allocations sum to 1.0, highest-suitability asset gets largest weight |

**Result:** ✅ 2/2 Passed

---

## Live Integration Test

**File:** `live_integration_test.py`
**Date:** March 12, 2026

This test uses **real API data** and **real Prophet ML training** — no mocks.

### Phase 1: Data Ingestion

| Test           | Source         | Status  | Details                                           |
| -------------- | -------------- | ------- | ------------------------------------------------- |
| AAPL (Stock)   | YFinance       | ✅ PASS | 251 trading days. Latest: $260.81 (Mar 11, 2026)  |
| TLT (Bond ETF) | YFinance       | ✅ PASS | 251 trading days. Latest: $87.14 (Mar 11, 2026)   |
| BTC (Crypto)   | CoinGecko      | ✅ PASS | 365 calendar days. Latest: $70,479 (Mar 12, 2026) |
| Weekend Fill   | Data Alignment | ✅ PASS | Filled 114 weekend/holiday gaps (251 → 365 days) |

### Phase 2: Prophet Model Training

| Asset | Expected 1Y Return | Volatility | Predicted Price Range |
| ----- | ------------------ | ---------- | --------------------- |
| AAPL  | **+23.0%**   | 4.1%       | $314.23 – $327.42    |
| TLT   | **+4.7%**    | 2.0%       | $90.28 – $92.13      |
| BTC   | **-21.3%**   | 12.0%      | $52,184 – $58,831    |

### Phase 3: Portfolio Advice Quality

Five dummy user profiles were created to test the full inference-to-recommendation pipeline:

| Profile                         | Risk Score | Top Asset    | Allocation | Expected Return | Quality |
| ------------------------------- | ---------- | ------------ | ---------- | --------------- | ------- |
| Very Conservative (Retiree)     | 0/4        | TLT (Bonds)  | 39.8%      | +5.05%          | ✅ PASS |
| Conservative (Near-Retirement)  | 1/4        | TLT (Bonds)  | 38.1%      | +3.38%          | ✅ PASS |
| Moderate (Mid-Career)           | 2/4        | AAPL (Stock) | 37.9%      | +2.68%          | ✅ PASS |
| Aggressive (Young Professional) | 4/4        | BTC (Crypto) | 47.6%      | -1.57%          | ✅ PASS |
| Very Aggressive (Crypto Trader) | 4/4        | BTC (Crypto) | 47.6%      | -1.57%          | ✅ PASS |

**Sanity checks applied:**

- All allocations sum to exactly 1.0 (100%)
- Conservative users (score ≤ 1) → bonds weighted higher than crypto
- Aggressive users (score ≥ 3) → crypto/stock weighted higher than bonds

**Result: 5/5 profiles received sensible, financially coherent advice.**
