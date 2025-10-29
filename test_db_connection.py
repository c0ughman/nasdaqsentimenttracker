#!/usr/bin/env python
"""
Test database connection and write capabilities on Railway
Run with: railway run python test_db_connection.py
"""
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import connection
from api.models import Ticker, AnalysisRun

print("="*80)
print("DATABASE CONNECTION TEST")
print("="*80)

# Test 1: Check database settings
from django.conf import settings
db_config = settings.DATABASES['default']
print(f"\n1️⃣  Database Configuration:")
print(f"   Engine: {db_config['ENGINE']}")
print(f"   Name: {db_config.get('NAME', 'N/A')}")
print(f"   Host: {db_config.get('HOST', 'N/A')}")
print(f"   Port: {db_config.get('PORT', 'N/A')}")

# Test 2: Test connection
print(f"\n2️⃣  Testing Connection...")
try:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        print(f"   ✅ Connection successful: {result}")
except Exception as e:
    print(f"   ❌ Connection failed: {e}")
    exit(1)

# Test 3: Check if tables exist
print(f"\n3️⃣  Checking Tables...")
try:
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema='public'
        """)
        tables = cursor.fetchall()
        print(f"   Found {len(tables)} tables:")
        for table in tables[:10]:  # Show first 10
            print(f"     - {table[0]}")
except Exception as e:
    print(f"   ❌ Error listing tables: {e}")

# Test 4: Check Ticker table
print(f"\n4️⃣  Checking Ticker table...")
try:
    ticker_count = Ticker.objects.count()
    print(f"   Ticker count: {ticker_count}")

    if ticker_count > 0:
        sample = Ticker.objects.first()
        print(f"   Sample ticker: {sample.symbol} - {sample.company_name}")
except Exception as e:
    print(f"   ❌ Error querying Ticker: {e}")

# Test 5: Check AnalysisRun table
print(f"\n5️⃣  Checking AnalysisRun table...")
try:
    run_count = AnalysisRun.objects.count()
    print(f"   AnalysisRun count: {run_count}")

    if run_count > 0:
        latest = AnalysisRun.objects.order_by('-timestamp').first()
        print(f"   Latest run: ID={latest.id}, Score={latest.composite_score}, Time={latest.timestamp}")
    else:
        print(f"   ⚠️  No analysis runs found in database")
except Exception as e:
    print(f"   ❌ Error querying AnalysisRun: {e}")

# Test 6: Try to create a test ticker
print(f"\n6️⃣  Testing Write Operations...")
try:
    test_ticker, created = Ticker.objects.get_or_create(
        symbol='TEST',
        defaults={'company_name': 'Test Company'}
    )
    if created:
        print(f"   ✅ Created test ticker: {test_ticker.symbol}")
        # Delete it
        test_ticker.delete()
        print(f"   ✅ Deleted test ticker")
    else:
        print(f"   ℹ️  Test ticker already exists: {test_ticker.symbol}")
except Exception as e:
    print(f"   ❌ Error creating test ticker: {e}")
    import traceback
    traceback.print_exc()

# Test 7: Check for NASDAQ ticker
print(f"\n7️⃣  Checking for ^IXIC ticker...")
try:
    nasdaq_ticker = Ticker.objects.filter(symbol='^IXIC').first()
    if nasdaq_ticker:
        print(f"   ✅ NASDAQ ticker exists: {nasdaq_ticker.symbol} - {nasdaq_ticker.company_name}")

        # Check analysis runs for NASDAQ
        nasdaq_runs = AnalysisRun.objects.filter(ticker=nasdaq_ticker).count()
        print(f"   NASDAQ analysis runs: {nasdaq_runs}")
    else:
        print(f"   ⚠️  NASDAQ ticker (^IXIC) not found!")
        print(f"   This ticker should be created during sentiment analysis")
except Exception as e:
    print(f"   ❌ Error checking NASDAQ ticker: {e}")

print(f"\n{'='*80}")
print(f"TEST COMPLETE")
print(f"{'='*80}\n")
