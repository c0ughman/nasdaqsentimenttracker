#!/bin/bash
# Railway startup script - runs migrations then starts the server

set -e  # Exit on error

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
    echo "⏰ [$(date '+%Y-%m-%d %H:%M:%S')] Running NASDAQ sentiment analysis..."
    python manage.py run_nasdaq_sentiment --once || echo "❌ Analysis failed, will retry in 60s"
    echo "✅ Analysis complete. Sleeping for 60 seconds..."
    sleep 60
  done
) &

echo "Starting Gunicorn server..."
exec gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
