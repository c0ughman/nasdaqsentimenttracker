#!/usr/bin/env python
"""
Diagnose Railway PostgreSQL database issues
Run on Railway with: railway run python backend/diagnose_railway_db.py
OR in Railway shell: python diagnose_railway_db.py
"""
import os
import sys

print("="*80)
print("RAILWAY POSTGRESQL DIAGNOSTICS")
print("="*80)

# Check environment variables BEFORE Django setup
print("\n1️⃣  Environment Variables:")
print(f"   DATABASE_URL: {os.environ.get('DATABASE_URL', 'NOT SET')[:50]}...")
print(f"   USE_SQLITE: {os.environ.get('USE_SQLITE', 'NOT SET')}")
print(f"   DEBUG: {os.environ.get('DEBUG', 'NOT SET')}")

# Now setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from django.conf import settings
from django.db import connection, connections
from django.db.utils import OperationalError

# Check Django database configuration
print("\n2️⃣  Django Database Configuration:")
db_config = settings.DATABASES['default']
print(f"   Engine: {db_config['ENGINE']}")
if 'sqlite' in db_config['ENGINE']:
    print(f"   ❌ ERROR: Using SQLite instead of PostgreSQL!")
    print(f"   Name: {db_config.get('NAME')}")
    sys.exit(1)
else:
    print(f"   ✅ Using PostgreSQL")
    print(f"   Host: {db_config.get('HOST', 'N/A')}")
    print(f"   Port: {db_config.get('PORT', 'N/A')}")
    print(f"   Name: {db_config.get('NAME', 'N/A')}")

# Test connection
print("\n3️⃣  Testing PostgreSQL Connection:")
try:
    connection.ensure_connection()
    print(f"   ✅ Connection successful!")
except OperationalError as e:
    print(f"   ❌ Connection failed: {e}")
    sys.exit(1)

# Check if tables exist
print("\n4️⃣  Checking Database Tables:")
try:
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema='public'
            ORDER BY table_name
        """)
        tables = [row[0] for row in cursor.fetchall()]
        print(f"   Found {len(tables)} tables")

        # Check for critical tables
        required_tables = ['api_ticker', 'api_analysisrun', 'api_newsarticle', 'auth_user']
        missing_tables = [t for t in required_tables if t not in tables]

        if missing_tables:
            print(f"   ❌ MISSING TABLES: {missing_tables}")
            print(f"   This means migrations haven't run properly!")
        else:
            print(f"   ✅ All critical tables exist")

        print(f"\n   All tables:")
        for table in tables:
            print(f"     - {table}")

except Exception as e:
    print(f"   ❌ Error checking tables: {e}")

# Check migrations
print("\n5️⃣  Checking Migration Status:")
try:
    from django.db.migrations.executor import MigrationExecutor
    executor = MigrationExecutor(connection)
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())

    if plan:
        print(f"   ❌ {len(plan)} unapplied migrations found:")
        for migration, backwards in plan[:5]:
            print(f"      - {migration}")
    else:
        print(f"   ✅ All migrations applied")
except Exception as e:
    print(f"   ❌ Error checking migrations: {e}")

# Try to query models
print("\n6️⃣  Testing Model Queries:")
try:
    from api.models import Ticker, AnalysisRun, NewsArticle
    from django.contrib.auth.models import User

    ticker_count = Ticker.objects.count()
    run_count = AnalysisRun.objects.count()
    article_count = NewsArticle.objects.count()
    user_count = User.objects.count()

    print(f"   Ticker count: {ticker_count}")
    print(f"   AnalysisRun count: {run_count}")
    print(f"   NewsArticle count: {article_count}")
    print(f"   User count: {user_count}")

    if user_count == 0:
        print(f"   ⚠️  No users found - you need to create a superuser!")
        print(f"   Run: python manage.py createsuperuser")

    if run_count == 0:
        print(f"   ⚠️  No analysis runs - database is empty but functional")
    else:
        print(f"   ✅ Database has data")

except Exception as e:
    print(f"   ❌ Error querying models: {e}")
    import traceback
    traceback.print_exc()

# Try to write
print("\n7️⃣  Testing Write Operations:")
try:
    from api.models import Ticker
    test_ticker = Ticker.objects.create(
        symbol='DBTEST',
        company_name='Database Test Company'
    )
    print(f"   ✅ Created test ticker ID={test_ticker.id}")

    # Verify it exists
    verify = Ticker.objects.filter(symbol='DBTEST').first()
    if verify:
        print(f"   ✅ Verified test ticker exists")
        verify.delete()
        print(f"   ✅ Deleted test ticker")
    else:
        print(f"   ❌ Could not verify test ticker!")

except Exception as e:
    print(f"   ❌ Write operation failed: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*80)
print("DIAGNOSIS COMPLETE")
print("="*80 + "\n")
