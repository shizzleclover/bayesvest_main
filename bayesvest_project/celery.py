import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bayesvest_project.settings')
app = Celery('bayesvest_project')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Daily schedule: ingest market data at 6:00 AM UTC, train Prophet at 6:30 AM UTC
app.conf.beat_schedule = {
    'daily-market-ingestion': {
        'task': 'apps.market.tasks.run_daily_market_ingestion',
        'schedule': crontab(hour=6, minute=0),
    },
    'daily-prophet-training': {
        'task': 'apps.engine.tasks.run_daily_prophet_training',
        'schedule': crontab(hour=6, minute=30),
    },
}
