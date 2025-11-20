"""
Technical Indicators Calculator
Fetches OHLCV data from Yahoo Finance and database, calculates technical indicators using the 'ta' library.
"""

import os
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from django.utils import timezone
from ta.momentum import RSIIndicator, StochasticOscillator, WilliamsRIndicator
from ta.trend import MACD, EMAIndicator, SMAIndicator
from ta.volatility import BollingerBands, AverageTrueRange
import yfinance as yf


def fetch_latest_ohlcv_from_yfinance(symbol='QQQ', interval='1m'):
    """
    Fetch the most recent OHLCV candle from Yahoo Finance.

    Handles both market hours and after-hours intelligently:
    - During market hours: Returns the current forming candle
    - After market hours: Returns the last completed candle from market close
    - Uses second-to-last candle to avoid incomplete data

    Args:
        symbol: Ticker symbol (default: 'QQQ' for NASDAQ-100 ETF)
        interval: Candle interval ('1m', '5m', etc.)

    Returns:
        Dict with open, high, low, close, volume, timestamp or None if failed
    """
    try:
        ticker = yf.Ticker(symbol)
        # Get intraday data for today
        df = ticker.history(period='1d', interval=interval)

        if df is None or len(df) == 0:
            print(f"  ⚠️  No data from Yahoo Finance for {symbol}")
            return None

        # Check how many candles we have
        num_candles = len(df)

        # Use second-to-last candle if we have more than 1, otherwise use last
        # This ensures we get a complete candle, not a forming one
        if num_candles >= 2:
            latest = df.iloc[-2]  # Second-to-last = most recent COMPLETE candle
            print(f"  📊 Using second-to-last candle (complete) from {num_candles} available")
        else:
            latest = df.iloc[-1]  # Only 1 candle available, use it
            print(f"  📊 Only 1 candle available, using it")

        # Get the timestamp of the candle
        candle_timestamp = latest.name if hasattr(latest, 'name') else None

        ohlcv = {
            'open': float(latest['Open']),
            'high': float(latest['High']),
            'low': float(latest['Low']),
            'close': float(latest['Close']),
            'volume': int(latest['Volume']) if not pd.isna(latest['Volume']) else None,
            'timestamp': candle_timestamp
        }

        print(f"  ✓ Yahoo Finance ({symbol}): O={ohlcv['open']:.2f} H={ohlcv['high']:.2f} L={ohlcv['low']:.2f} C={ohlcv['close']:.2f}")
        if candle_timestamp:
            print(f"    Candle time: {candle_timestamp}")

        return ohlcv

    except Exception as e:
        print(f"  ⚠️  Error fetching from Yahoo Finance: {e}")
        import traceback
        traceback.print_exc()
        return None


def fetch_vxn_price():
    """
    Fetch current VXN (NASDAQ-100 Volatility Index) from Yahoo Finance.

    Returns:
        Float: Current VXN value or None if failed
    """
    try:
        ticker = yf.Ticker('^VXN')
        info = ticker.info

        # Try to get the current/regular market price
        vxn_price = info.get('regularMarketPrice') or info.get('previousClose')

        if vxn_price is not None:
            vxn_value = float(vxn_price)
            print(f"  ✓ VXN (NASDAQ-100 Volatility Index): {vxn_value:.2f}")
            return vxn_value
        else:
            print(f"  ⚠️  No VXN price data available")
            return None

    except Exception as e:
        print(f"  ⚠️  Error fetching VXN: {e}")
        return None


def fetch_latest_ohlcv_from_websocket_db(symbol='QQQ', window_seconds=60):
    """
    Aggregate 1-minute OHLCV candle from SecondSnapshot data (1-second candles).
    
    This function reads pre-aggregated 1-second candles from SecondSnapshot table
    and aggregates them into a 1-minute candle.
    
    Args:
        symbol: Ticker symbol (default: 'QQQ' for NASDAQ-100 ETF)
        window_seconds: Time window to aggregate in seconds (default: 60 = 1 minute)
    
    Returns:
        Dict with open, high, low, close, volume, timestamp or None if no data available
    """
    from api.models import Ticker, SecondSnapshot
    from django.utils import timezone
    from datetime import timedelta
    
    try:
        # Get ticker object
        ticker = Ticker.objects.filter(symbol=symbol).first()
        if not ticker:
            print(f"  ⚠️  Ticker {symbol} not found in database")
            return None
        
        # Calculate cutoff time (look back N seconds)
        cutoff_time = timezone.now() - timedelta(seconds=window_seconds)
        
        # Query 1-second candles from the last N seconds
        snapshots = SecondSnapshot.objects.filter(
            ticker=ticker,
            timestamp__gte=cutoff_time
        ).order_by('timestamp')
        
        if not snapshots.exists():
            print(f"  ⚠️  No SecondSnapshot data in last {window_seconds} seconds")
            return None
        
        snapshot_count = snapshots.count()
        snapshot_list = list(snapshots)
        
        # Aggregate 1-minute OHLCV from 1-second candles
        open_price = float(snapshot_list[0].ohlc_1sec_open)
        close_price = float(snapshot_list[-1].ohlc_1sec_close)
        high_price = max(float(s.ohlc_1sec_high) for s in snapshot_list)
        low_price = min(float(s.ohlc_1sec_low) for s in snapshot_list)
        total_volume = sum(s.ohlc_1sec_volume for s in snapshot_list)
        latest_timestamp = snapshot_list[-1].timestamp
        
        ohlcv = {
            'open': open_price,
            'high': high_price,
            'low': low_price,
            'close': close_price,
            'volume': total_volume,
            'timestamp': latest_timestamp
        }
        
        print(f"  ✓ WebSocket OHLCV ({symbol}, {snapshot_count} second-candles aggregated):")
        print(f"    O={ohlcv['open']:.2f} H={ohlcv['high']:.2f} "
              f"L={ohlcv['low']:.2f} C={ohlcv['close']:.2f} V={ohlcv['volume']:,}")
        print(f"    Time window: {cutoff_time.strftime('%H:%M:%S')} - {latest_timestamp.strftime('%H:%M:%S')}")
        
        return ohlcv
    
    except Exception as e:
        print(f"  ⚠️  Error aggregating SecondSnapshot data: {e}")
        import traceback
        traceback.print_exc()
        return None


def fetch_latest_ohlcv_with_fallback(symbol='QQQ', interval='1m'):
    """
    Fetch latest OHLCV with intelligent fallback chain:
    1. Try WebSocket database (real-time second-by-second data aggregated)
    2. Fall back to Yahoo Finance if WebSocket unavailable or stale
    
    This provides seamless transition between data sources without breaking the analysis.
    
    Args:
        symbol: Ticker symbol (default: 'QQQ' for NASDAQ-100 ETF)
        interval: Y-finance interval, only used for fallback (default: '1m')
    
    Returns:
        Dict with open, high, low, close, volume, timestamp or None if all sources fail
    """
    print(f"\n📊 Fetching OHLCV data for {symbol}...")
    
    # Try WebSocket database first (primary source)
    print(f"  Attempting: WebSocket database (primary)")
    ohlcv = fetch_latest_ohlcv_from_websocket_db(symbol=symbol, window_seconds=60)
    
    if ohlcv:
        print(f"  ✅ Using WebSocket data (real-time)")
        return ohlcv
    
    # Fallback to Yahoo Finance
    print(f"  ⚠️  WebSocket data unavailable, falling back to Yahoo Finance...")
    ohlcv = fetch_latest_ohlcv_from_yfinance(symbol=symbol, interval=interval)
    
    if ohlcv:
        print(f"  ✅ Using Yahoo Finance data (fallback)")
        return ohlcv
    
    # All sources failed
    print(f"  ❌ All data sources failed for {symbol}")
    return None


def fetch_ohlcv_data_from_db(ticker_symbol='QQQ', hours_back=24):
    """
    Fetch OHLCV (Open, High, Low, Close, Volume) data from our database.

    Args:
        ticker_symbol: Ticker symbol ('QQQ' for NASDAQ-100 ETF)
        hours_back: How many hours of historical data to fetch

    Returns:
        pandas DataFrame with columns: timestamp, open, high, low, close, volume
        Returns None if insufficient data
    """
    from api.models import AnalysisRun, Ticker

    try:
        # Get the ticker object
        ticker = Ticker.objects.filter(symbol=ticker_symbol).first()
        if not ticker:
            print(f"⚠️  Ticker {ticker_symbol} not found in database")
            return None

        # Calculate cutoff time
        cutoff_time = timezone.now() - timedelta(hours=hours_back)

        # Query historical analysis runs with OHLCV data
        runs = AnalysisRun.objects.filter(
            ticker=ticker,
            timestamp__gte=cutoff_time
        ).exclude(
            price_open__isnull=True  # Only get runs with OHLCV data
        ).order_by('timestamp').values(
            'timestamp', 'price_open', 'price_high', 'price_low', 'stock_price', 'volume'
        )

        if not runs:
            print(f"  ℹ️  No OHLCV data found in database yet (need to collect over time)")
            return None

        # Convert to DataFrame
        df = pd.DataFrame(list(runs))
        df = df.rename(columns={
            'stock_price': 'close',
            'price_open': 'open',
            'price_high': 'high',
            'price_low': 'low'
        })

        # Ensure timestamp is datetime
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        # Sort by timestamp
        df = df.sort_values('timestamp').reset_index(drop=True)

        print(f"  ✓ Loaded {len(df)} data points from database (last {hours_back}h)")
        return df

    except Exception as e:
        print(f"⚠️  Error fetching OHLCV from database: {e}")
        return None


def calculate_rsi(df, period=14):
    """Calculate RSI (Relative Strength Index)"""
    if df is None or len(df) < period:
        return None
    try:
        rsi = RSIIndicator(close=df['close'], window=period)
        return round(float(rsi.rsi().iloc[-1]), 2)
    except Exception as e:
        print(f"  ⚠️  Error calculating RSI: {e}")
        return None


def calculate_macd(df, fast=12, slow=26, signal=9):
    """Calculate MACD (Moving Average Convergence Divergence)"""
    if df is None or len(df) < slow:
        return None, None, None
    try:
        macd = MACD(close=df['close'], window_slow=slow, window_fast=fast, window_sign=signal)
        macd_line = round(float(macd.macd().iloc[-1]), 4)
        signal_line = round(float(macd.macd_signal().iloc[-1]), 4)
        histogram = round(float(macd.macd_diff().iloc[-1]), 4)
        return macd_line, signal_line, histogram
    except Exception as e:
        print(f"  ⚠️  Error calculating MACD: {e}")
        return None, None, None


def calculate_bollinger_bands(df, period=20, std_dev=2.0):
    """Calculate Bollinger Bands"""
    if df is None or len(df) < period:
        return None, None, None
    try:
        bb = BollingerBands(close=df['close'], window=period, window_dev=std_dev)
        upper = round(float(bb.bollinger_hband().iloc[-1]), 2)
        middle = round(float(bb.bollinger_mavg().iloc[-1]), 2)
        lower = round(float(bb.bollinger_lband().iloc[-1]), 2)
        return upper, middle, lower
    except Exception as e:
        print(f"  ⚠️  Error calculating Bollinger Bands: {e}")
        return None, None, None


def calculate_sma(df, period=20):
    """Calculate SMA (Simple Moving Average)"""
    if df is None or len(df) < period:
        return None
    try:
        sma = SMAIndicator(close=df['close'], window=period)
        return round(float(sma.sma_indicator().iloc[-1]), 2)
    except Exception as e:
        print(f"  ⚠️  Error calculating SMA: {e}")
        return None


def calculate_ema(df, period=9):
    """Calculate EMA (Exponential Moving Average)"""
    if df is None or len(df) < period:
        return None
    try:
        ema = EMAIndicator(close=df['close'], window=period)
        return round(float(ema.ema_indicator().iloc[-1]), 2)
    except Exception as e:
        print(f"  ⚠️  Error calculating EMA: {e}")
        return None


def calculate_stochastic(df, k_period=14, k_smooth=3, d_period=3):
    """Calculate Stochastic Oscillator"""
    if df is None or len(df) < k_period:
        return None, None
    try:
        stoch = StochasticOscillator(
            high=df['high'],
            low=df['low'],
            close=df['close'],
            window=k_period,
            smooth_window=k_smooth
        )
        k_value = round(float(stoch.stoch().iloc[-1]), 2)
        d_value = round(float(stoch.stoch_signal().iloc[-1]), 2)
        return k_value, d_value
    except Exception as e:
        print(f"  ⚠️  Error calculating Stochastic: {e}")
        return None, None


def calculate_williams_r(df, period=14):
    """Calculate Williams %R"""
    if df is None or len(df) < period:
        return None
    try:
        williams = WilliamsRIndicator(high=df['high'], low=df['low'], close=df['close'], lbp=period)
        return round(float(williams.williams_r().iloc[-1]), 2)
    except Exception as e:
        print(f"  ⚠️  Error calculating Williams %R: {e}")
        return None


def calculate_atr(df, period=14):
    """Calculate ATR (Average True Range)"""
    if df is None or len(df) < period:
        return None
    try:
        atr = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=period)
        return round(float(atr.average_true_range().iloc[-1]), 2)
    except Exception as e:
        print(f"  ⚠️  Error calculating ATR: {e}")
        return None


def get_current_price(df):
    """Get the most recent close price from OHLCV data"""
    if df is None or len(df) == 0:
        return None
    try:
        return round(float(df['close'].iloc[-1]), 2)
    except Exception as e:
        print(f"  ⚠️  Error getting current price: {e}")
        return None


def calculate_all_indicators(symbol, resolution='5', hours_back=24, config=None):
    """
    Fetch OHLCV data from database and calculate all technical indicators.

    Args:
        symbol: Stock ticker (e.g., 'NASDAQ', 'QQQ') - not used anymore, kept for compatibility
        resolution: Time resolution - not used (data comes from database)
        hours_back: Hours of historical data to fetch from database
        config: Dictionary with indicator periods (from nasdaq_config.INDICATOR_PERIODS)

    Returns:
        Dictionary with all calculated indicators
    """
    print(f"\n📊 Calculating technical indicators from database history...")

    # Fetch OHLCV data from our database
    df = fetch_ohlcv_data_from_db(ticker_symbol='QQQ', hours_back=hours_back)

    if df is None or len(df) == 0:
        print(f"  ❌ No data available for {symbol}")
        return {
            'rsi_14': None,
            'macd': None,
            'macd_signal': None,
            'macd_histogram': None,
            'bb_upper': None,
            'bb_middle': None,
            'bb_lower': None,
            'sma_20': None,
            'sma_50': None,
            'ema_9': None,
            'ema_20': None,
            'stoch_k': None,
            'stoch_d': None,
            'williams_r': None,
            'atr_14': None,
            'qqq_price': None,
        }

    # Use default periods if config not provided
    if config is None:
        config = {
            'rsi': 14,
            'macd': {'fast': 12, 'slow': 26, 'signal': 9},
            'ema': [9, 20],
            'sma': [20, 50],
            'bbands': {'period': 20, 'std_dev': 2.0},
            'stochastic': {'k_period': 14, 'k_smooth': 3, 'd_period': 3},
            'williams_r': 14,
            'atr': 14,
        }

    indicators = {}

    # RSI
    print(f"  Calculating RSI ({config['rsi']}-period)...")
    indicators['rsi_14'] = calculate_rsi(df, config['rsi'])

    # MACD
    print(f"  Calculating MACD ({config['macd']['fast']}, {config['macd']['slow']}, {config['macd']['signal']})...")
    indicators['macd'], indicators['macd_signal'], indicators['macd_histogram'] = calculate_macd(
        df,
        config['macd']['fast'],
        config['macd']['slow'],
        config['macd']['signal']
    )

    # Bollinger Bands
    print(f"  Calculating Bollinger Bands ({config['bbands']['period']}-period)...")
    indicators['bb_upper'], indicators['bb_middle'], indicators['bb_lower'] = calculate_bollinger_bands(
        df,
        config['bbands']['period'],
        config['bbands']['std_dev']
    )

    # SMA
    print(f"  Calculating SMAs ({config['sma']})...")
    indicators['sma_20'] = calculate_sma(df, config['sma'][0])
    indicators['sma_50'] = calculate_sma(df, config['sma'][1])

    # EMA
    print(f"  Calculating EMAs ({config['ema']})...")
    indicators['ema_9'] = calculate_ema(df, config['ema'][0])
    indicators['ema_20'] = calculate_ema(df, config['ema'][1])

    # Stochastic (optional - not in core 5)
    # print(f"  Calculating Stochastic...")
    # indicators['stoch_k'], indicators['stoch_d'] = calculate_stochastic(
    #     df,
    #     config['stochastic']['k_period'],
    #     config['stochastic']['k_smooth'],
    #     config['stochastic']['d_period']
    # )
    indicators['stoch_k'] = None
    indicators['stoch_d'] = None

    # Williams %R (optional - not in core 5)
    # print(f"  Calculating Williams %R ({config['williams_r']}-period)...")
    # indicators['williams_r'] = calculate_williams_r(df, config['williams_r'])
    indicators['williams_r'] = None

    # ATR (optional - not in core 5)
    # print(f"  Calculating ATR ({config['atr']}-period)...")
    # indicators['atr_14'] = calculate_atr(df, config['atr'])
    indicators['atr_14'] = None

    # Current price
    indicators['qqq_price'] = get_current_price(df)

    # Count successful calculations
    successful = sum(1 for k, v in indicators.items() if v is not None and k in [
        'rsi_14', 'macd', 'bb_upper', 'sma_20', 'sma_50', 'ema_9', 'ema_20', 'qqq_price'
    ])
    total = 8  # Core 5 indicators + MACD signal/histogram + price

    print(f"  ✅ Successfully calculated {successful}/{total} core indicators")

    return indicators


def fetch_indicators_with_fallback(symbols=None, resolution='5', hours_back=24, config=None):
    """
    Calculate indicators from database history.

    Note: symbols parameter is ignored (kept for compatibility).
    All data comes from NASDAQ ticker in database.

    Args:
        symbols: Ignored (kept for compatibility)
        resolution: Ignored (data comes from database)
        hours_back: Hours of historical data to fetch from database
        config: Indicator configuration

    Returns:
        Tuple of (indicators_dict, 'database')
    """
    indicators = calculate_all_indicators(
        symbol='QQQ',  # Always use QQQ from database
        resolution=resolution,
        hours_back=hours_back,
        config=config
    )

    return indicators, 'database'


def calculate_technical_composite_score(indicators):
    """
    Convert technical indicators into a single sentiment-like score (-100 to +100).
    This creates a unified "Technical Sentiment" that can be combined with news/social sentiment.

    Components:
    - RSI (30%): Oversold (<30) = bullish, Overbought (>70) = bearish
    - MACD (25%): Positive histogram = bullish, negative = bearish
    - Bollinger Bands (20%): Price position relative to bands
    - Moving Average Crossover (15%): Short-term vs long-term trend
    - Stochastic (10%): Momentum indicator

    Args:
        indicators: Dictionary with calculated technical indicators

    Returns:
        Float: Technical composite score from -100 (very bearish) to +100 (very bullish)
    """
    print("\n" + "="*80)
    print("📊 CALCULATING TECHNICAL COMPOSITE SCORE")
    print("="*80)

    if not indicators:
        print("⚠️  ERROR: No indicators provided - returning 0.0")
        return 0.0

    print(f"✓ Received {len(indicators)} indicators:")
    for key, value in indicators.items():
        value_str = f"{value}" if value is not None else "None"
        type_str = type(value).__name__ if value is not None else "NoneType"
        print(f"  • {key:20s} = {value_str:>12s} (type: {type_str})")

    scores = []
    weights = []

    # 1. RSI Score (30% weight) - Mean reversion indicator
    print("\n1️⃣  RSI SCORE (30% weight):")
    rsi = indicators.get('rsi_14')
    if rsi is not None:
        try:
            rsi_val = float(rsi)
            # Check for NaN or infinity
            if np.isnan(rsi_val) or np.isinf(rsi_val):
                print(f"   ⚠️ RSI is NaN or Inf - skipping")
            else:
                if rsi_val < 30:
                    rsi_score = 100 * (30 - rsi_val) / 30
                    print(f"   RSI = {rsi_val:.2f} (OVERSOLD - Bullish)")
                elif rsi_val > 70:
                    rsi_score = -100 * (rsi_val - 70) / 30
                    print(f"   RSI = {rsi_val:.2f} (OVERBOUGHT - Bearish)")
                else:
                    rsi_score = ((rsi_val - 50) / 20) * 20
                    print(f"   RSI = {rsi_val:.2f} (NEUTRAL)")

                scores.append(rsi_score)
                weights.append(0.30)
                print(f"   ✓ RSI Score: {rsi_score:+.2f} (weight: 30%)")
        except Exception as e:
            print(f"   ✗ ERROR calculating RSI score: {e}")
    else:
        print("   ⊘ RSI is None - skipping")

    # 2. MACD Score (25% weight) - Trend momentum
    print("\n2️⃣  MACD SCORE (25% weight):")
    macd_histogram = indicators.get('macd_histogram')
    if macd_histogram is not None:
        try:
            macd_val = float(macd_histogram)
            macd_score = max(min(macd_val * 20, 100), -100)
            scores.append(macd_score)
            weights.append(0.25)
            direction = "Bullish" if macd_val > 0 else "Bearish" if macd_val < 0 else "Neutral"
            print(f"   MACD Histogram = {macd_val:.4f} ({direction})")
            print(f"   ✓ MACD Score: {macd_score:+.2f} (weight: 25%)")
        except Exception as e:
            print(f"   ✗ ERROR calculating MACD score: {e}")
    else:
        print("   ⊘ MACD Histogram is None - skipping")

    # 3. Bollinger Bands Score (20% weight) - Volatility & position
    print("\n3️⃣  BOLLINGER BANDS SCORE (20% weight):")
    bb_upper = indicators.get('bb_upper')
    bb_middle = indicators.get('bb_middle')
    bb_lower = indicators.get('bb_lower')
    current_price = indicators.get('qqq_price')

    if all(x is not None for x in [bb_upper, bb_middle, bb_lower, current_price]):
        try:
            # Convert to float to avoid Decimal type issues
            bb_upper_f = float(bb_upper)
            bb_lower_f = float(bb_lower)
            current_price_f = float(current_price)

            print(f"   BB Upper:  {bb_upper_f:.2f}")
            print(f"   BB Middle: {float(bb_middle):.2f}")
            print(f"   BB Lower:  {bb_lower_f:.2f}")
            print(f"   Price:     {current_price_f:.2f}")

            bb_range = bb_upper_f - bb_lower_f
            if bb_range > 0:
                position = (current_price_f - bb_lower_f) / bb_range
                bb_score = (0.5 - position) * 200

                if position < 0.3:
                    pos_desc = "Near Lower Band (Oversold - Bullish)"
                elif position > 0.7:
                    pos_desc = "Near Upper Band (Overbought - Bearish)"
                else:
                    pos_desc = "Middle of Bands (Neutral)"

                print(f"   Position in bands: {position:.2%} - {pos_desc}")
                scores.append(bb_score)
                weights.append(0.20)
                print(f"   ✓ BB Score: {bb_score:+.2f} (weight: 20%)")
            else:
                print(f"   ✗ ERROR: BB range is {bb_range} (should be > 0)")
        except Exception as e:
            print(f"   ✗ ERROR calculating BB score: {e}")
            import traceback
            traceback.print_exc()
    else:
        missing = [k for k, v in {'bb_upper': bb_upper, 'bb_middle': bb_middle, 'bb_lower': bb_lower, 'qqq_price': current_price}.items() if v is None]
        print(f"   ⊘ Missing values: {', '.join(missing)} - skipping")

    # 4. Moving Average Crossover Score (15% weight) - Trend direction
    print("\n4️⃣  MOVING AVERAGE CROSSOVER SCORE (15% weight):")
    ema_9 = indicators.get('ema_9')
    ema_20 = indicators.get('ema_20')

    if ema_9 is not None and ema_20 is not None:
        try:
            # Convert to float to avoid Decimal type issues
            ema_9_f = float(ema_9)
            ema_20_f = float(ema_20)

            print(f"   EMA 9:  {ema_9_f:.2f}")
            print(f"   EMA 20: {ema_20_f:.2f}")

            crossover_diff = ((ema_9_f - ema_20_f) / ema_20_f) * 100 if ema_20_f != 0 else 0
            ma_score = max(min(crossover_diff * 50, 100), -100)

            if ema_9_f > ema_20_f:
                print(f"   Short-term above long-term ({crossover_diff:+.2f}%) - Bullish")
            else:
                print(f"   Short-term below long-term ({crossover_diff:+.2f}%) - Bearish")

            scores.append(ma_score)
            weights.append(0.15)
            print(f"   ✓ MA Crossover Score: {ma_score:+.2f} (weight: 15%)")
        except Exception as e:
            print(f"   ✗ ERROR calculating MA score: {e}")
            import traceback
            traceback.print_exc()
    else:
        missing = [k for k, v in {'ema_9': ema_9, 'ema_20': ema_20}.items() if v is None]
        print(f"   ⊘ Missing values: {', '.join(missing)} - skipping")

    # 5. Stochastic Score (10% weight) - Momentum
    print("\n5️⃣  STOCHASTIC SCORE (10% weight):")
    stoch_k = indicators.get('stoch_k')
    stoch_d = indicators.get('stoch_d')

    if stoch_k is not None and stoch_d is not None:
        try:
            stoch_k_f = float(stoch_k)
            stoch_d_f = float(stoch_d)
            stoch_avg = (stoch_k_f + stoch_d_f) / 2

            print(f"   Stoch %K: {stoch_k_f:.2f}")
            print(f"   Stoch %D: {stoch_d_f:.2f}")
            print(f"   Average:  {stoch_avg:.2f}")

            if stoch_avg < 20:
                stoch_score = 100 * (20 - stoch_avg) / 20
                print(f"   Below 20 (Oversold - Bullish)")
            elif stoch_avg > 80:
                stoch_score = -100 * (stoch_avg - 80) / 20
                print(f"   Above 80 (Overbought - Bearish)")
            else:
                stoch_score = ((50 - stoch_avg) / 30) * 20
                print(f"   Middle range (Neutral)")

            scores.append(stoch_score)
            weights.append(0.10)
            print(f"   ✓ Stochastic Score: {stoch_score:+.2f} (weight: 10%)")
        except Exception as e:
            print(f"   ✗ ERROR calculating Stochastic score: {e}")
    else:
        print("   ⊘ Stochastic values are None - skipping")

    # Calculate weighted average
    print("\n" + "="*80)
    print("📊 FINAL CALCULATION")
    print("="*80)

    if not scores:
        print("⚠️  ERROR: No scores calculated - returning 0.0")
        print("   This means ALL indicators were None or had errors!")
        return 0.0

    # Normalize weights to sum to 1.0
    total_weight = sum(weights)
    normalized_weights = [w / total_weight for w in weights]

    print(f"✓ Calculated {len(scores)} component scores")
    print(f"  Total weight before normalization: {total_weight:.2f}")
    print(f"\n  Component Breakdown:")
    for i, (score, weight, norm_weight) in enumerate(zip(scores, weights, normalized_weights), 1):
        contribution = score * norm_weight
        print(f"    {i}. Score: {score:+7.2f} × Weight: {norm_weight:5.1%} = {contribution:+7.2f}")

    composite_score = sum(score * weight for score, weight in zip(scores, normalized_weights))

    print(f"\n🎯 TECHNICAL COMPOSITE SCORE: {composite_score:+.2f}")
    print("="*80 + "\n")

    return round(composite_score, 2)
