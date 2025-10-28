#!/bin/bash
# Railway startup script - runs migrations then starts the server

set -e  # Exit on error

# Activate the virtual environment (CRITICAL - without this, python command won't be found)
source /opt/venv/bin/activate

# Add GCC and zlib library paths for numpy/pandas C extensions
GCC_LIB=$(find /nix/store -name "libstdc++.so.6" -path "*-gcc-*-lib/lib/*" 2>/dev/null | head -1 | xargs dirname)
ZLIB_LIB=$(find /nix/store -name "libz.so.1" 2>/dev/null | head -1 | xargs dirname)
export LD_LIBRARY_PATH=$GCC_LIB:$ZLIB_LIB:$LD_LIBRARY_PATH

echo "Running database migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput --clear

# Start background sentiment analysis loop (runs every 60 seconds)
(
  echo "🔄 Starting sentiment analysis loop (every 60 seconds)..."
  sleep 10  # Wait for Gunicorn to fully start
  while true; do
    START_TIME=$(date +%s)

    echo "⏰ [$(date '+%Y-%m-%d %H:%M:%S')] Running NASDAQ sentiment analysis..."
    python manage.py run_nasdaq_sentiment --once || echo "❌ Analysis failed, will retry in 60s"

    END_TIME=$(date +%s)
    ELAPSED=$((END_TIME - START_TIME))
    SLEEP_TIME=$((60 - ELAPSED))

    # Safety check: if analysis took longer than 60s, don't sleep
    if [ $SLEEP_TIME -lt 0 ]; then
      SLEEP_TIME=0
    fi

    echo "✅ Analysis took ${ELAPSED}s. Sleeping for ${SLEEP_TIME}s..."
    sleep $SLEEP_TIME
  done
) &

echo "Starting Gunicorn server..."
exec gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
