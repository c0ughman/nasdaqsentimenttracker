#!/bin/bash
# Railway startup script - runs migrations then starts the server

set -e  # Exit on error

echo "Running database migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput --clear

echo "Starting Gunicorn server..."
exec gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
