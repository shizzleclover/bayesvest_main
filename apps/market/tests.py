from django.test import SimpleTestCase
from unittest.mock import patch, MagicMock
from apps.market.models import Asset, MarketData
from apps.market.tasks import run_daily_market_ingestion
from apps.market.services.data_alignment import forward_fill_weekends

class MarketAppTests(SimpleTestCase):
    def setUp(self):
        Asset.objects.delete()
        MarketData.objects.delete()
        
        Asset(ticker='AAPL', name='Apple', asset_class='Stock', sector='Tech', risk_level='Medium').save()
        Asset(ticker='BTC', name='Bitcoin', asset_class='Crypto', sector='Currency', risk_level='High').save()

    def tearDown(self):
        Asset.objects.delete()
        MarketData.objects.delete()

    def test_forward_fill_weekends(self):
        # 1. Provide dates with missing weekends
        # Wednesday, Thursday, Friday, Monday, Tuesday
        sample_data = [
            {'date': '2023-11-01', 'close': 100},
            {'date': '2023-11-02', 'close': 105},
            {'date': '2023-11-03', 'close': 110},  # Friday
            {'date': '2023-11-06', 'close': 115},  # Monday
            {'date': '2023-11-07', 'close': 120},
        ]
        
        filled_data = forward_fill_weekends(sample_data)
        
        # Original 5 days + 2 weekend days = 7 days
        self.assertEqual(len(filled_data), 7)
        
        # Check that Saturday and Sunday were added with Friday's close value
        dates = [d['date'] for d in filled_data]
        self.assertIn('2023-11-04', dates)
        self.assertIn('2023-11-05', dates)
        
        for d in filled_data:
            if d['date'] == '2023-11-04' or d['date'] == '2023-11-05':
                self.assertEqual(d['close'], 110)

    @patch('apps.market.tasks.fetch_yfinance_data')
    @patch('apps.market.tasks.fetch_coingecko_data')
    def test_run_daily_market_ingestion(self, mock_fetch_coingecko, mock_fetch_yfinance):
        # Mock YFinance returning 2 days of data for AAPL
        mock_fetch_yfinance.return_value = [
            {'date': '2023-11-01', 'close': 150},
            {'date': '2023-11-02', 'close': 155}
        ]
        
        # Mock CoinGecko returning 2 days of data for BTC
        mock_fetch_coingecko.return_value = [
            {'date': '2023-11-01', 'close': 34000},
            {'date': '2023-11-02', 'close': 35000}
        ]
        
        # Run Celery task synchronously
        result = run_daily_market_ingestion()
        
        # Verify result output string
        self.assertTrue("Successfully ingested and aligned data for 2 assets" in result)
        
        # Verify db persistence
        aapl_data = MarketData.objects(asset_ticker='AAPL').first()
        btc_data = MarketData.objects(asset_ticker='BTC').first()
        
        self.assertIsNotNone(aapl_data)
        self.assertEqual(len(aapl_data.historical_prices), 2)
        self.assertEqual(aapl_data.historical_prices[-1]['close'], 155)
        
        self.assertIsNotNone(btc_data)
        self.assertEqual(len(btc_data.historical_prices), 2)
        self.assertEqual(btc_data.historical_prices[-1]['close'], 35000)
