"""
NASDAQ Sentiment Tracker Configuration
Top 20 NASDAQ stocks by market cap (as of 2025) with approximate weights
"""

# Top 20 NASDAQ stocks with market cap weights (normalized to sum to 1.0)
# These weights represent approximate market cap percentage within NASDAQ
NASDAQ_TOP_20 = {
    'AAPL': 0.120,  # Apple Inc.
    'MSFT': 0.105,  # Microsoft Corporation
    'NVDA': 0.085,  # NVIDIA Corporation
    'GOOGL': 0.065,  # Alphabet Inc. Class A
    'AMZN': 0.060,  # Amazon.com Inc.
    'META': 0.045,  # Meta Platforms Inc.
    'TSLA': 0.040,  # Tesla Inc.
    'AVGO': 0.035,  # Broadcom Inc.
    'COST': 0.030,  # Costco Wholesale Corporation
    'NFLX': 0.028,  # Netflix Inc.
    'ASML': 0.027,  # ASML Holding N.V.
    'AMD': 0.026,   # Advanced Micro Devices Inc.
    'ADBE': 0.025,  # Adobe Inc.
    'PEP': 0.024,   # PepsiCo Inc.
    'CSCO': 0.023,  # Cisco Systems Inc.
    'TMUS': 0.022,  # T-Mobile US Inc.
    'INTC': 0.021,  # Intel Corporation
    'CMCSA': 0.020, # Comcast Corporation
    'QCOM': 0.019,  # Qualcomm Inc.
    'TXN': 0.018,   # Texas Instruments Inc.
}

# Normalize weights to sum to exactly 1.0
total_weight = sum(NASDAQ_TOP_20.values())
NASDAQ_TOP_20 = {k: v / total_weight for k, v in NASDAQ_TOP_20.items()}

# Company names for display
COMPANY_NAMES = {
    'AAPL': 'Apple Inc.',
    'MSFT': 'Microsoft Corporation',
    'NVDA': 'NVIDIA Corporation',
    'GOOGL': 'Alphabet Inc.',
    'AMZN': 'Amazon.com Inc.',
    'META': 'Meta Platforms Inc.',
    'TSLA': 'Tesla Inc.',
    'AVGO': 'Broadcom Inc.',
    'COST': 'Costco Wholesale Corporation',
    'NFLX': 'Netflix Inc.',
    'ASML': 'ASML Holding N.V.',
    'AMD': 'Advanced Micro Devices Inc.',
    'ADBE': 'Adobe Inc.',
    'PEP': 'PepsiCo Inc.',
    'CSCO': 'Cisco Systems Inc.',
    'TMUS': 'T-Mobile US Inc.',
    'INTC': 'Intel Corporation',
    'CMCSA': 'Comcast Corporation',
    'QCOM': 'Qualcomm Inc.',
    'TXN': 'Texas Instruments Inc.',
}

# Market-moving keywords for general news filtering
MARKET_MOVING_KEYWORDS = [
    # Federal Reserve & Monetary Policy
    'federal reserve', 'fed', 'jerome powell', 'interest rate', 'rate hike',
    'rate cut', 'fomc', 'monetary policy', 'quantitative',
    
    # Economic Indicators
    'inflation', 'cpi', 'consumer price', 'pce', 'jobs report', 
    'unemployment', 'nonfarm payroll', 'gdp', 'recession', 'economic growth',
    
    # Market Indices
    'nasdaq', 'nasdaq composite', 'nasdaq-100', 'tech stocks', 
    'technology sector', 'growth stocks', 'index',
    
    # Geopolitical
    'trade war', 'tariff', 'china', 'sanctions', 'taiwan',
    'war', 'conflict', 'regulation',
    
    # Market Structure
    'treasury', 'bond yield', 'volatility', 'vix', 'selloff', 
    'rally', 'correction', 'bear market', 'bull market',
    
    # Tech Sector Specific
    'ai', 'artificial intelligence', 'chip', 'semiconductor',
    'cloud', 'earnings', 'tech regulation', 'antitrust',
]

# Exclude noise and opinion pieces
EXCLUDE_KEYWORDS = [
    'opinion', 'column', 'editorial', 'commentary',
    'analyst says', 'expert predicts', 'chart analysis',
]

# Source credibility ratings (0.0 to 1.0)
SOURCE_CREDIBILITY = {
    'Bloomberg': 1.0,
    'Reuters': 1.0,
    'Wall Street Journal': 0.95,
    'Financial Times': 0.95,
    'CNBC': 0.85,
    'MarketWatch': 0.80,
    'Seeking Alpha': 0.70,
    'Yahoo Finance': 0.75,
    'Benzinga': 0.75,
    'PR Newswire': 0.60,
    'Business Wire': 0.60,
    'The Motley Fool': 0.50,
}

# Weights for hybrid approach
SENTIMENT_WEIGHTS = {
    'company_news': 0.70,  # 70% weight to company-specific news
    'market_news': 0.30,   # 30% weight to general market news
}

# API rate limiting (seconds between requests)
API_RATE_LIMIT_DELAY = 0.5  # 500ms between requests to avoid rate limiting

# ============================================================================
# TECHNICAL INDICATORS CONFIGURATION
# ============================================================================

# Symbol for technical indicators (prefer NASDAQ Composite, fallback to QQQ)
INDICATOR_SYMBOLS = ['^IXIC', 'QQQ']  # Try in order

# Timeframe for indicators (5-minute candles for day trading)
INDICATOR_RESOLUTION = '5'  # 5-minute intervals
INDICATOR_LOOKBACK_HOURS = 24  # Fetch last 24 hours of data

# Technical Indicator Periods (optimized for 5-minute day trading)
INDICATOR_PERIODS = {
    # RSI - Relative Strength Index (overbought/oversold momentum)
    'rsi': 14,  # 14 periods = 70 minutes on 5-min chart

    # MACD - Moving Average Convergence Divergence (trend momentum)
    'macd': {
        'fast': 12,    # 12 periods = 60 minutes
        'slow': 26,    # 26 periods = 130 minutes
        'signal': 9,   # 9 periods = 45 minutes
    },

    # EMA - Exponential Moving Average (trend following)
    'ema': [9, 20],  # 9 periods = 45 min, 20 periods = 100 min

    # SMA - Simple Moving Average (trend following)
    'sma': [20, 50],  # 20 periods = 100 min, 50 periods = 250 min (4+ hours)

    # Bollinger Bands - Volatility indicator
    'bbands': {
        'period': 20,      # 20 periods = 100 minutes
        'std_dev': 2.0,    # 2 standard deviations (95% confidence)
    },

    # Stochastic Oscillator - Momentum indicator
    'stochastic': {
        'k_period': 14,    # %K period
        'k_smooth': 3,     # %K smoothing
        'd_period': 3,     # %D period (signal line)
    },

    # Williams %R - Overbought/Oversold indicator
    'williams_r': 14,  # 14 periods = 70 minutes

    # ATR - Average True Range (volatility measure)
    'atr': 14,  # 14 periods = 70 minutes
}

# Thresholds for signals
INDICATOR_THRESHOLDS = {
    'rsi': {
        'overbought': 70,  # RSI > 70 = overbought
        'oversold': 30,    # RSI < 30 = oversold
    },
    'williams_r': {
        'overbought': -20,  # Williams %R > -20 = overbought
        'oversold': -80,    # Williams %R < -80 = oversold
    },
}

