# Bayesvest Backend

AI-powered fractional-portfolio advisory API built with Django, MongoEngine, Facebook Prophet, and a pgmpy Bayesian Inference Engine.

## Tech Stack

| Component | Technology |
|---|---|
| Framework | Django 5 + Django REST Framework |
| Database | MongoDB Atlas (MongoEngine) |
| Auth | JWT (djangorestframework-simplejwt) |
| ML — Risk | pgmpy Bayesian Network |
| ML — Forecast | Facebook Prophet |
| Task Queue | Celery (Redis / eager mode) |
| Data Sources | Yahoo Finance, CoinGecko |
| API Docs | Swagger + ReDoc (drf-yasg) |

## Prerequisites

- Python 3.11+
- MongoDB Atlas account (or local MongoDB)
- Redis (optional — not needed if using eager mode)

## Local Setup

```bash
# 1. Clone and navigate
cd backend

# 2. Create virtual environment
python -m venv venv

# 3. Activate it
.\venv\Scripts\Activate      # Windows
source venv/bin/activate     # macOS / Linux

# 4. Install dependencies
pip install -r requirements.txt

# 5. Configure environment
# Copy .env.example or edit .env with your MongoDB URI
# MONGO_URI=mongodb+srv://<user>:<pass>@<cluster>/bayesvest_db
# CELERY_TASK_ALWAYS_EAGER=True   (no Redis needed for local dev)

# 6. Run the server
python manage.py runserver
```

The server starts at **http://127.0.0.1:8000**.

On first startup, the app automatically:
1. Seeds 5 default assets (AAPL, SPY, TLT, BTC, ETH)
2. Ingests 5 years of market data from Yahoo Finance & CoinGecko
3. Trains Prophet forecasting models for each asset

## API Endpoints

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/api/users/auth/register/` | ❌ | Register a new user |
| POST | `/api/users/auth/login/` | ❌ | Login, returns JWT |
| GET | `/api/users/profile/` | ✅ | Get financial profile |
| POST | `/api/users/profile/` | ✅ | Create/update financial profile |
| GET | `/api/users/risk/` | ✅ | Get latest risk assessment |
| POST | `/api/users/risk/` | ✅ | Submit risk questionnaire |
| POST | `/api/portfolio/generate/` | ✅ | Generate AI portfolio |
| GET | `/swagger/` | ❌ | Swagger UI docs |
| GET | `/redoc/` | ❌ | ReDoc docs |

**Auth:** Send JWT in the header: `Authorization: Bearer <access_token>`

## Running Tests

```bash
# All tests
python manage.py test

# Specific app
python manage.py test apps.users
python manage.py test apps.market
python manage.py test apps.engine
python manage.py test apps.portfolio

# Live integration test (real APIs, ~2 min)
python live_integration_test.py
```

## Railway Deployment

The project includes a `Procfile` for Railway:

```
web: gunicorn bayesvest_project.wsgi --bind 0.0.0.0:$PORT
```

### Required Environment Variables on Railway

| Variable | Value |
|---|---|
| `MONGO_URI` | Your MongoDB Atlas connection string |
| `SECRET_KEY` | A strong random secret key |
| `ALLOWED_HOSTS` | Your Railway domain (e.g. `app-name.up.railway.app`) |
| `CELERY_TASK_ALWAYS_EAGER` | `True` (unless you have Redis on Railway) |

### Steps

1. Push the repo to GitHub
2. Connect the repo to Railway
3. Set the **Root Directory** to `backend` in Railway service settings
4. Add the environment variables above
5. Under **Networking**, click **Generate Domain** to get a public URL
6. Deploy — Railway auto-detects Python, installs from `requirements.txt`, and runs the `Procfile`

> **Port:** Railway assigns the port automatically via `$PORT`. You do not need to set it manually.

## Project Structure

```
backend/
├── bayesvest_project/        # Django project config
│   ├── settings.py           # MongoDB, Celery, JWT config
│   ├── urls.py               # Root router + Swagger
│   ├── celery.py             # Celery beat schedule
│   └── wsgi.py               # WSGI entry point
├── apps/
│   ├── users/                # Auth, profiles, risk assessment
│   ├── market/               # Asset DB, data ingestion
│   ├── engine/               # Bayesian network + Prophet ML
│   └── portfolio/            # Portfolio generation
├── Procfile                  # Railway/Heroku start command
├── requirements.txt          # Python dependencies
└── .env                      # Local environment variables
```
