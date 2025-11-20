# Railway Procfile for NASDAQ Sentiment Tracker
# This file defines the processes that Railway will run

# Service 1: WebSocket Collector (second-by-second data collection)
# Connects during market hours (9:30 AM - 4:00 PM EST)
# Creates 1-second candles and 100-tick candles
collector: python manage.py run_websocket_collector_v2

# Service 2: Analysis Runner (minute-by-minute sentiment analysis)
# Runs every 60 seconds during market hours
# Analyzes news, Reddit, technical indicators, and creates composite scores
analysis: python manage.py run_nasdaq_sentiment

# Web server (runs migrations on startup, then starts Gunicorn)
web: bash railway-start.sh

