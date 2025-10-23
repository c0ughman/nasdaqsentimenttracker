#!/bin/bash
# Railway startup script - runs migrations then starts the server

set -e  # Exit on error

# Add GCC library path for numpy/pandas C extensions
export LD_LIBRARY_PATH=/nix/store/*-gcc-*-lib/lib:$LD_LIBRARY_PATH

echo "Running database migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput --clear

echo "Starting Gunicorn server..."
exec gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
