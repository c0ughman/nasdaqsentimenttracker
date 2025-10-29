"""
Test script for calculated technical indicators
"""
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

# Import after Django setup
from api.management.commands.technical_indicators import fetch_indicators_with_fallback
from api.management.commands.nasdaq_config import (
    INDICATOR_SYMBOLS,
    INDICATOR_RESOLUTION,
    INDICATOR_LOOKBACK_HOURS,
    INDICATOR_PERIODS
)

print("=" * 80)
print("Testing Calculated Technical Indicators (OHLCV + Math)")
print("=" * 80)
print(f"Symbols to try: {INDICATOR_SYMBOLS}")
print(f"Resolution: {INDICATOR_RESOLUTION}-minute intervals")
print(f"Lookback: {INDICATOR_LOOKBACK_HOURS} hours")
print("=" * 80)

# Test fetching indicators with fallback
indicators, symbol_used = fetch_indicators_with_fallback(
    symbols=INDICATOR_SYMBOLS,
    resolution=INDICATOR_RESOLUTION,
    hours_back=INDICATOR_LOOKBACK_HOURS,
    config=INDICATOR_PERIODS
)

print("\n" + "=" * 80)
print("RESULTS:")
print("=" * 80)
print(f"Symbol used: {symbol_used}")
print("-" * 80)

# Core 5 indicators
core_indicators = ['rsi_14', 'macd', 'macd_signal', 'macd_histogram', 'bb_upper', 'bb_middle', 'bb_lower', 'sma_20', 'sma_50', 'ema_9', 'ema_20', 'qqq_price']

for key in core_indicators:
    value = indicators.get(key)
    if value is not None:
        print(f"✅ {key}: {value}")
    else:
        print(f"❌ {key}: None (not calculated)")

print("\n" + "=" * 80)
successful = sum(1 for k in core_indicators if indicators.get(k) is not None)
total = len(core_indicators)
print(f"Success Rate: {successful}/{total} ({successful/total*100:.1f}%)")
print("=" * 80)
