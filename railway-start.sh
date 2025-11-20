#!/bin/bash
# Railway startup script - runs migrations then starts the web server

set -e  # Exit on error

echo "Running database migrations..."
python manage.py migrate --noinput

echo "Starting Gunicorn..."
exec gunicorn backend.wsgi --bind 0.0.0.0:$PORT

