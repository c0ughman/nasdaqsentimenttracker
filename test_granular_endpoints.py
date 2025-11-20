"""
Test script for the new granular data endpoints
Run with: python test_granular_endpoints.py
"""

import os
import django
import sys

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from api.models import Ticker, SecondSnapshot, TickCandle100
from django.utils import timezone
from datetime import timedelta

def test_data_availability():
    """Check if we have data to test with"""
    print("\n" + "="*70)
    print("🔍 Checking Data Availability")
    print("="*70)
    
    # Check for QLD ticker
    try:
        qld_ticker = Ticker.objects.get(symbol='QLD')
        print(f"✅ QLD ticker found: {qld_ticker.company_name}")
    except Ticker.DoesNotExist:
        print("❌ QLD ticker not found in database")
        return False
    
    # Check for second snapshots
    one_hour_ago = timezone.now() - timedelta(hours=1)
    second_count = SecondSnapshot.objects.filter(
        ticker=qld_ticker,
        timestamp__gte=one_hour_ago
    ).count()
    print(f"📊 Second snapshots (last hour): {second_count}")
    
    if second_count > 0:
        latest = SecondSnapshot.objects.filter(ticker=qld_ticker).first()
        print(f"   Latest: {latest.timestamp} - ${latest.ohlc_1sec_close}")
    
    # Check for 100-tick candles
    tick_count = TickCandle100.objects.filter(
        ticker=qld_ticker,
        completed_at__gte=one_hour_ago
    ).count()
    print(f"📊 100-tick candles (last hour): {tick_count}")
    
    if tick_count > 0:
        latest = TickCandle100.objects.filter(ticker=qld_ticker).first()
        print(f"   Latest: Candle #{latest.candle_number} - ${latest.close}")
    
    if second_count == 0 and tick_count == 0:
        print("\n⚠️  No data found in last hour. Endpoints will return empty data.")
        print("   Run the WebSocket collector to generate data first.")
    
    return True


def test_endpoint_logic():
    """Test the endpoint logic without making HTTP requests"""
    print("\n" + "="*70)
    print("🧪 Testing Endpoint Logic")
    print("="*70)
    
    from api.views import second_candles_data, tick_candles_data
    from rest_framework.test import APIRequestFactory
    
    factory = APIRequestFactory()
    
    # Test 1: Second candles default request
    print("\n1️⃣  Testing /api/second-candles/ (default)")
    request = factory.get('/api/second-candles/')
    response = second_candles_data(request)
    print(f"   Status: {response.status_code}")
    print(f"   Data count: {response.data['metadata']['count']}")
    print(f"   Timeframe: {response.data['metadata']['timeframe']}")
    
    # Test 2: Second candles with custom symbol
    print("\n2️⃣  Testing /api/second-candles/?symbol=QLD")
    request = factory.get('/api/second-candles/?symbol=QLD')
    response = second_candles_data(request)
    print(f"   Status: {response.status_code}")
    print(f"   Ticker: {response.data['ticker']}")
    print(f"   Data count: {response.data['metadata']['count']}")
    
    # Test 3: Tick candles default request
    print("\n3️⃣  Testing /api/tick-candles/ (default)")
    request = factory.get('/api/tick-candles/')
    response = tick_candles_data(request)
    print(f"   Status: {response.status_code}")
    print(f"   Data count: {response.data['metadata']['count']}")
    print(f"   Timeframe: {response.data['metadata']['timeframe']}")
    
    # Test 4: Tick candles with limit
    print("\n4️⃣  Testing /api/tick-candles/?symbol=QLD&limit=50")
    request = factory.get('/api/tick-candles/?symbol=QLD&limit=50')
    response = tick_candles_data(request)
    print(f"   Status: {response.status_code}")
    print(f"   Data count: {response.data['metadata']['count']}")
    print(f"   Limit: {response.data['metadata']['limit']}")
    
    # Test 5: Invalid symbol
    print("\n5️⃣  Testing /api/second-candles/?symbol=INVALID")
    request = factory.get('/api/second-candles/?symbol=INVALID')
    response = second_candles_data(request)
    print(f"   Status: {response.status_code}")
    print(f"   Error: {response.data.get('error')}")
    
    print("\n✅ All endpoint tests completed!")


def main():
    print("\n🚀 Testing Granular Data Endpoints")
    
    if test_data_availability():
        test_endpoint_logic()
    
    print("\n" + "="*70)
    print("✨ Testing Complete")
    print("="*70)
    print("\nTo test via HTTP requests:")
    print("  1. Start server: python manage.py runserver")
    print("  2. Visit: http://localhost:8000/api/second-candles/")
    print("  3. Visit: http://localhost:8000/api/tick-candles/")
    print()


if __name__ == '__main__':
    main()

