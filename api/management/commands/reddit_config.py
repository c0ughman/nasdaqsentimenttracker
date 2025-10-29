"""
Reddit Sentiment Tracker Configuration
Subreddits, filtering keywords, and settings for Reddit-based sentiment analysis
"""

# Subreddits to monitor for NASDAQ/stock sentiment
REDDIT_SUBREDDITS = [
    'stocks',
    'StockMarket',
    'investing',
    'wallstreetbets',
    'options',
    'DueDiligence',
    'ValueInvesting',
    'dividends',
    'UndervaluedStocks',
    'SPACs',
    'pennystocks',
    'RobinHood',
    'trading',
    'securityanalysis',
    'EducatedInvesting',
    'greeninvestor',
    'investing_discussion',
    'smallstreetbets',
    'Weedstocks',
    'stocktrader',
]

# Keywords for filtering relevant posts (NASDAQ, stocks, economy, short-term trading)
REDDIT_FILTER_KEYWORDS = {
    # NASDAQ Index & ETFs
    'nasdaq', 'qqq', 'nasdaq-100', 'nasdaq composite', 'tech stocks', 'technology sector',

    # Top 20 NASDAQ Stocks (from nasdaq_config.py)
    'aapl', 'apple', 'msft', 'microsoft', 'nvda', 'nvidia', 'googl', 'google', 'alphabet',
    'amzn', 'amazon', 'meta', 'facebook', 'tsla', 'tesla', 'avgo', 'broadcom',
    'cost', 'costco', 'nflx', 'netflix', 'asml', 'amd', 'adbe', 'adobe',
    'pep', 'pepsi', 'csco', 'cisco', 'tmus', 't-mobile', 'intc', 'intel',
    'cmcsa', 'comcast', 'qcom', 'qualcomm', 'intu', 'intuit',

    # Economic Indicators (relevant to short-term trading)
    'fed', 'federal reserve', 'interest rate', 'rate hike', 'rate cut', 'fomc',
    'inflation', 'cpi', 'pce', 'jobs report', 'unemployment', 'nonfarm payroll',
    'gdp', 'recession', 'bear market', 'bull market', 'correction',
    'treasury', 'bond yield', 'volatility', 'vix',

    # Market Movements & Trading
    'breakout', 'resistance', 'support', 'trend', 'momentum', 'rally', 'selloff',
    'gap up', 'gap down', 'squeeze', 'short squeeze', 'gamma squeeze',
    'earnings', 'earnings beat', 'earnings miss', 'guidance',
    'upgrade', 'downgrade', 'price target', 'analyst', 'bull', 'bear',

    # Day Trading & Short-term Trading
    'day trade', 'day trading', 'swing trade', 'scalp', 'scalping',
    'intraday', 'pre-market', 'after hours', 'extended hours',
    'calls', 'puts', 'options', 'strike', 'expiry', 'contracts',
    '0dte', 'weekly options', 'theta', 'delta', 'gamma', 'iv', 'implied volatility',

    # Technical Analysis (short-term indicators)
    'rsi', 'macd', 'bollinger', 'moving average', 'ema', 'sma',
    'fibonacci', 'retracement', 'channel', 'wedge', 'triangle',
    'candlestick', 'doji', 'hammer', 'engulfing',

    # Market Catalysts
    'catalyst', 'news', 'announcement', 'merger', 'acquisition', 'buyout',
    'ipo', 'direct listing', 'spac', 'split', 'stock split', 'reverse split',
    'dividend', 'buyback', 'share buyback',

    # Trading Terminology
    'long', 'short', 'position', 'entry', 'exit', 'stop loss', 'take profit',
    'dd', 'due diligence', 'yolo', 'fomo', 'diamond hands', 'paper hands',
    'moon', 'rocket', 'tendies', 'loss porn', 'gain porn',

    # Sector/Industry (tech-heavy for NASDAQ)
    'tech', 'semiconductor', 'chip', 'ai', 'artificial intelligence',
    'cloud', 'saas', 'software', 'hardware', 'consumer tech',
    'ev', 'electric vehicle', 'autonomous', 'biotech', 'pharma',

    # Indices & Benchmarks
    'spy', 's&p 500', 'dow', 'djia', 'russell', 'nasdaq futures',
    'index', 'market', 'equities',
}

# Convert to lowercase set for efficient filtering
REDDIT_FILTER_KEYWORDS = {keyword.lower() for keyword in REDDIT_FILTER_KEYWORDS}

# Posts/comments fetching configuration (OPTIMIZED FOR SPEED)
REDDIT_POSTS_LIMIT = 5  # Fetch top 5 hot posts per subreddit (reduced from 50)
REDDIT_COMMENTS_LIMIT = 3  # Top 3 comments per post (reduced from 20)
REDDIT_SUBCOMMENTS_LIMIT = 0  # No subcomments (too slow)

# Reddit API rate limiting
REDDIT_REQUEST_DELAY = 0.1  # 100ms between subreddit requests (reduced from 500ms)

# Minimum post age to analyze (avoid spam/very new posts)
REDDIT_MIN_POST_AGE_MINUTES = 5

# Minimum upvotes to consider a post relevant
REDDIT_MIN_UPVOTES = 5

# Minimum comment score to analyze
REDDIT_MIN_COMMENT_SCORE = 2

# Cache duration (minutes) - how long to remember analyzed posts
REDDIT_CACHE_DURATION_MINUTES = 60 * 24  # 24 hours
