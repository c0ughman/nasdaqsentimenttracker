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

echo "Starting Gunicorn server..."
exec gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
