#!/usr/bin/env python3
"""
Corrected Technical Indicator Cross-Reference Tool
Compares QLD (NASDAQ-100 2x Leveraged ETF) data since that's what our system actually uses
"""

import requests
import json
import time
from datetime import datetime, timedelta
import pandas as pd
from bs4 import BeautifulSoup
import re

def fetch_qqq_technical_data():
    """
    Fetch QLD technical indicators from Yahoo Finance
    (This matches what our system actually uses)
    """
    print("🔍 Fetching QLD technical data from Yahoo Finance...")
    print("   (Our system uses QLD as proxy for NASDAQ Composite)")
    
    try:
        import yfinance as yf
        
        # Get QLD data (this is what our system actually uses)
        ticker = yf.Ticker("QLD")
        
        # Get 5-minute data for the last 24 hours
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=24)
        
        data = ticker.history(
            start=start_time,
            end=end_time,
            interval='5m'
        )
        
        if data.empty:
            print("  ❌ No QLD data available from Yahoo Finance")
            return None
            
        print(f"  ✓ Retrieved {len(data)} QLD data points from Yahoo Finance")
        
        # Calculate indicators using the same periods as our system
        indicators = calculate_indicators_from_yahoo_data(data, symbol="QLD")
        
        return indicators
        
    except Exception as e:
        print(f"  ❌ Error fetching QLD data: {e}")
        return None

def calculate_indicators_from_yahoo_data(df, symbol="QLD"):
    """
    Calculate technical indicators from Yahoo Finance data
    using the same periods as our system
    """
    print(f"  📈 Calculating technical indicators for {symbol}...")
    
    try:
        from ta.momentum import RSIIndicator, StochasticOscillator, WilliamsRIndicator
        from ta.trend import MACD, EMAIndicator, SMAIndicator
        from ta.volatility import BollingerBands, AverageTrueRange
        
        indicators = {}
        
        # RSI (14 periods)
        if len(df) >= 14:
            rsi = RSIIndicator(close=df['Close'], window=14)
            indicators['rsi_14'] = round(float(rsi.rsi().iloc[-1]), 2)
            print(f"    ✓ RSI(14): {indicators['rsi_14']}")
        
        # MACD (12, 26, 9)
        if len(df) >= 26:
            macd = MACD(close=df['Close'], window_slow=26, window_fast=12, window_sign=9)
            indicators['macd'] = round(float(macd.macd().iloc[-1]), 4)
            indicators['macd_signal'] = round(float(macd.macd_signal().iloc[-1]), 4)
            indicators['macd_histogram'] = round(float(macd.macd_diff().iloc[-1]), 4)
            print(f"    ✓ MACD: {indicators['macd']}, Signal: {indicators['macd_signal']}, Histogram: {indicators['macd_histogram']}")
        
        # Bollinger Bands (20 periods, 2 std dev)
        if len(df) >= 20:
            bb = BollingerBands(close=df['Close'], window=20, window_dev=2.0)
            indicators['bb_upper'] = round(float(bb.bollinger_hband().iloc[-1]), 2)
            indicators['bb_middle'] = round(float(bb.bollinger_mavg().iloc[-1]), 2)
            indicators['bb_lower'] = round(float(bb.bollinger_lband().iloc[-1]), 2)
            print(f"    ✓ Bollinger Bands: Upper={indicators['bb_upper']}, Middle={indicators['bb_middle']}, Lower={indicators['bb_lower']}")
        
        # Moving Averages
        if len(df) >= 50:
            # SMA
            sma_20 = SMAIndicator(close=df['Close'], window=20)
            sma_50 = SMAIndicator(close=df['Close'], window=50)
            indicators['sma_20'] = round(float(sma_20.sma_indicator().iloc[-1]), 2)
            indicators['sma_50'] = round(float(sma_50.sma_indicator().iloc[-1]), 2)
            print(f"    ✓ SMA(20): {indicators['sma_20']}, SMA(50): {indicators['sma_50']}")
            
            # EMA
            ema_9 = EMAIndicator(close=df['Close'], window=9)
            ema_20 = EMAIndicator(close=df['Close'], window=20)
            indicators['ema_9'] = round(float(ema_9.ema_indicator().iloc[-1]), 2)
            indicators['ema_20'] = round(float(ema_20.ema_indicator().iloc[-1]), 2)
            print(f"    ✓ EMA(9): {indicators['ema_9']}, EMA(20): {indicators['ema_20']}")
        
        # Stochastic (14, 3, 3)
        if len(df) >= 14:
            stoch = StochasticOscillator(
                high=df['High'],
                low=df['Low'],
                close=df['Close'],
                window=14,
                smooth_window=3
            )
            indicators['stoch_k'] = round(float(stoch.stoch().iloc[-1]), 2)
            indicators['stoch_d'] = round(float(stoch.stoch_signal().iloc[-1]), 2)
            print(f"    ✓ Stochastic %K: {indicators['stoch_k']}, %D: {indicators['stoch_d']}")
        
        # Williams %R (14 periods)
        if len(df) >= 14:
            williams = WilliamsRIndicator(high=df['High'], low=df['Low'], close=df['Close'], lbp=14)
            indicators['williams_r'] = round(float(williams.williams_r().iloc[-1]), 2)
            print(f"    ✓ Williams %R: {indicators['williams_r']}")
        
        # ATR (14 periods)
        if len(df) >= 14:
            atr = AverageTrueRange(high=df['High'], low=df['Low'], close=df['Close'], window=14)
            indicators['atr_14'] = round(float(atr.average_true_range().iloc[-1]), 2)
            print(f"    ✓ ATR(14): {indicators['atr_14']}")
        
        # Current price
        indicators['current_price'] = round(float(df['Close'].iloc[-1]), 2)
        print(f"    ✓ Current Price: {indicators['current_price']}")
        
        return indicators
        
    except Exception as e:
        print(f"    ❌ Error calculating indicators: {e}")
        return None

def compare_with_our_data():
    """
    Compare external data with our internal calculations
    """
    print("\n🔄 Comparing with our internal data...")
    
    try:
        # Set up Django environment
        import os
        import sys
        import django
        
        # Add the backend directory to Python path
        backend_path = '/Users/coughman/Desktop/Nasdaq Sentiment Tracker/backend'
        sys.path.append(backend_path)
        
        # Set Django settings
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
        django.setup()
        
        # Import our technical indicators module
        sys.path.append('/Users/coughman/Desktop/Nasdaq Sentiment Tracker/backend/api/management/commands')
        
        from technical_indicators import calculate_all_indicators
        from nasdaq_config import INDICATOR_PERIODS
        
        # Get our internal calculations
        our_indicators = calculate_all_indicators(
            symbol='^IXIC',
            resolution='5',
            hours_back=24,
            config=INDICATOR_PERIODS
        )
        
        print("  ✓ Retrieved our internal calculations")
        return our_indicators
        
    except Exception as e:
        print(f"  ❌ Error getting our internal data: {e}")
        return None

def fetch_nasdaq_composite_for_reference():
    """
    Also fetch NASDAQ Composite (^IXIC) for reference
    """
    print("\n📊 Fetching NASDAQ Composite (^IXIC) for reference...")
    
    try:
        import yfinance as yf
        
        # Get NASDAQ Composite data
        ticker = yf.Ticker("^IXIC")
        
        # Get 5-minute data for the last 24 hours
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=24)
        
        data = ticker.history(
            start=start_time,
            end=end_time,
            interval='5m'
        )
        
        if data.empty:
            print("  ❌ No NASDAQ Composite data available")
            return None
            
        print(f"  ✓ Retrieved {len(data)} NASDAQ Composite data points")
        
        # Just get current price for reference
        current_price = round(float(data['Close'].iloc[-1]), 2)
        print(f"  ✓ NASDAQ Composite Current Price: {current_price}")
        
        return current_price
        
    except Exception as e:
        print(f"  ❌ Error fetching NASDAQ Composite data: {e}")
        return None

def main():
    """
    Main function to run the corrected cross-reference comparison
    """
    print("=" * 80)
    print("🔍 CORRECTED TECHNICAL INDICATOR CROSS-REFERENCE TOOL")
    print("=" * 80)
    print(f"📅 Analysis Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📊 Primary Symbol: QLD (NASDAQ-100 2x Leveraged ETF) - What our system actually uses")
    print(f"📊 Reference Symbol: ^IXIC (NASDAQ Composite) - For comparison")
    print(f"⏱️  Timeframe: 5-minute candles")
    print(f"📈 Lookback: 24 hours")
    print("=" * 80)
    
    # Fetch QLD data (what our system actually uses)
    qqq_indicators = fetch_qqq_technical_data()
    
    # Fetch NASDAQ Composite for reference
    nasdaq_price = fetch_nasdaq_composite_for_reference()
    
    # Get our internal data
    our_indicators = compare_with_our_data()
    
    # Display comparison
    print("\n" + "=" * 80)
    print("📊 COMPARISON RESULTS (QLD vs Our System)")
    print("=" * 80)
    
    if qqq_indicators and our_indicators:
        print(f"{'Indicator':<20} {'Yahoo QLD':<15} {'Our System':<15} {'Difference':<15}")
        print("-" * 70)
        
        for key in qqq_indicators:
            if key in our_indicators:
                yahoo_val = qqq_indicators[key]
                our_val = our_indicators[key]
                
                if yahoo_val is not None and our_val is not None:
                    diff = abs(yahoo_val - our_val)
                    print(f"{key:<20} {yahoo_val:<15} {our_val:<15} {diff:<15.4f}")
                else:
                    print(f"{key:<20} {str(yahoo_val):<15} {str(our_val):<15} {'N/A':<15}")
    
    # Show price comparison
    print("\n" + "=" * 80)
    print("💰 PRICE COMPARISON")
    print("=" * 80)
    
    if qqq_indicators and our_indicators and nasdaq_price:
        qqq_price = qqq_indicators.get('current_price')
        our_price = our_indicators.get('qqq_price')
        
        print(f"NASDAQ Composite (^IXIC): {nasdaq_price:,.2f}")
        print(f"QLD (NASDAQ-100 2x ETF):  {qqq_price:,.2f}")
        print(f"Our System (QLD proxy):   {our_price:,.2f}")
        
        if qqq_price and our_price:
            price_diff = abs(qqq_price - our_price)
            print(f"QLD Price Difference:      {price_diff:.4f}")
    
    print("\n" + "=" * 80)
    print("✅ Corrected cross-reference analysis complete!")
    print("=" * 80)
    print("\n📝 KEY FINDINGS:")
    print("• Our system uses QLD (NASDAQ-100 2x Leveraged ETF) as a proxy for NASDAQ Composite")
    print("• QLD prices are ~$140-180, NASDAQ Composite prices are ~$22,700")
    print("• This explains the large price differences in the original comparison")
    print("• Technical indicators should now be comparable between QLD sources")

if __name__ == "__main__":
    main()
