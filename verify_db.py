#!/usr/bin/env python
"""Quick database verification script for Railway"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.conf import settings
from django.db import connection

print("="*60)
print("DATABASE VERIFICATION")
print("="*60)

# Check database engine
db_engine = settings.DATABASES['default']['ENGINE']
print(f"\nDatabase Engine: {db_engine}")

if 'postgresql' in db_engine:
    print("✅ Using PostgreSQL")
elif 'sqlite' in db_engine:
    print("❌ ERROR: Still using SQLite!")
else:
    print(f"⚠️  Unknown database: {db_engine}")

# Test connection
try:
    connection.ensure_connection()
    print("✅ Database connection successful!")
except Exception as e:
    print(f"❌ Connection failed: {e}")
    exit(1)

# Check data
try:
    from api.models import AnalysisRun
    count = AnalysisRun.objects.count()
    print(f"\nAnalysisRun records: {count}")
    
    if count > 0:
        latest = AnalysisRun.objects.latest('run_date')
        print(f"Latest run: {latest.run_date}")
        print(f"Overall sentiment: {latest.overall_sentiment_score}")
except Exception as e:
    print(f"Error querying data: {e}")

print("\n" + "="*60)

