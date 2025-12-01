"""
Finnhub Real-Time News Integration with Threading

Queries Finnhub every second (50 seconds work, 10 seconds rest) for breaking news.
Scores articles using OpenAI API (same method as run_nasdaq_sentiment.py).
Adds impact to news score immediately when scoring completes.

Uses threading to avoid blocking WebSocket collector.
"""

import logging
import threading
import queue
import time
import hashlib
from datetime import datetime, timedelta
from django.utils import timezone
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Try to import finnhub
try:
    import finnhub
    FINNHUB_AVAILABLE = True
except ImportError:
    FINNHUB_AVAILABLE = False
    logger.warning("Finnhub not installed. Install with: pip install finnhub-python")


# ============================================================================
# CONFIGURATION
# ============================================================================

# Finnhub API key (set in environment or here)
import os
FINNHUB_API_KEY = os.getenv('FINNHUB_API_KEY', '')

# Symbols to monitor (40 major NASDAQ stocks)
WATCHLIST = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'AVGO',
    'COST', 'NFLX', 'AMD', 'PEP', 'ADBE', 'CSCO', 'CMCSA', 'INTC',
    'TMUS', 'QCOM', 'INTU', 'TXN', 'AMGN', 'HON', 'AMAT', 'SBUX',
    'ISRG', 'BKNG', 'ADP', 'GILD', 'ADI', 'VRTX', 'MDLZ', 'REGN',
    'LRCX', 'PANW', 'MU', 'PYPL', 'SNPS', 'KLAC', 'CDNS', 'MELI'
]

# Market cap weights (approximate % of NASDAQ-100)
from api.management.commands.nasdaq_config import COMPANY_NAMES
MARKET_CAP_WEIGHTS = {ticker: 1.0/len(COMPANY_NAMES) for ticker in COMPANY_NAMES.keys()}
# Override with known large caps
MARKET_CAP_WEIGHTS.update({
    'AAPL': 0.14, 'MSFT': 0.13, 'GOOGL': 0.08, 'AMZN': 0.07,
    'NVDA': 0.06, 'META': 0.04, 'TSLA': 0.03, 'AVGO': 0.03
})

# Query timing
WORK_SECONDS = 50  # Query for first 50 seconds of each minute
REST_SECONDS = 10  # Rest for last 10 seconds

# Rotation state
_current_index = 0
_last_query_time = None
_finnhub_client = None

# Article cache (prevent re-processing)
ARTICLE_CACHE_KEY = 'finnhub_articles_processed'
ARTICLE_CACHE_DURATION = 3600  # 1 hour

# Queues for threading
article_to_score_queue = queue.Queue(maxsize=50)  # Articles needing scoring (capped to prevent memory exhaustion)
scored_article_queue = queue.Queue()  # Articles that have been scored

# Scoring thread
_scoring_thread = None
_scoring_thread_running = False


# ============================================================================
# FINNHUB CLIENT
# ============================================================================

def get_finnhub_client():
    """Get or create Finnhub client."""
    global _finnhub_client
    
    if not FINNHUB_AVAILABLE:
        logger.error("Finnhub not available")
        return None
    
    if not FINNHUB_API_KEY:
        logger.error("FINNHUB_API_KEY not set")
        return None
    
    if _finnhub_client is None:
        _finnhub_client = finnhub.Client(api_key=FINNHUB_API_KEY)
        logger.info("Finnhub client initialized")
    
    return _finnhub_client


# ============================================================================
# ARTICLE CACHING
# ============================================================================

def get_article_hash(article_url):
    """Generate hash for article URL."""
    return hashlib.md5(article_url.encode()).hexdigest()


def is_article_processed(article_url):
    """Check if article has been processed."""
    article_hash = get_article_hash(article_url)
    processed = cache.get(ARTICLE_CACHE_KEY, set())
    return article_hash in processed


def mark_article_processed(article_url):
    """Mark article as processed."""
    article_hash = get_article_hash(article_url)
    processed = cache.get(ARTICLE_CACHE_KEY, set())
    processed.add(article_hash)
    cache.set(ARTICLE_CACHE_KEY, processed, ARTICLE_CACHE_DURATION)


# ============================================================================
# DATABASE SAVING
# ============================================================================

def save_article_to_db(article_data, impact):
    """
    Save article to NewsArticle database table.

    Args:
        article_data: Dict with article info (headline, summary, url, symbol, published)
        impact: Calculated sentiment impact
    """
    try:
        from api.models import NewsArticle, Ticker
        from django.utils.dateparse import parse_datetime
        from django.utils import timezone

        # Get or create ticker
        ticker_symbol = article_data['symbol']
        try:
            ticker = Ticker.objects.get(symbol=ticker_symbol)
        except Ticker.DoesNotExist:
            logger.warning(f"Ticker {ticker_symbol} not found in database, using QLD as fallback")
            ticker = Ticker.objects.get(symbol='QLD')  # Fallback to NASDAQ composite

        # Parse published date
        published_at = None
        if article_data.get('published'):
            try:
                # Finnhub provides Unix timestamp
                published_timestamp = article_data['published']
                if isinstance(published_timestamp, (int, float)):
                    published_at = timezone.datetime.fromtimestamp(published_timestamp, tz=timezone.utc)
                else:
                    published_at = parse_datetime(str(published_timestamp))
            except Exception as e:
                logger.warning(f"Error parsing published date: {e}")

        if not published_at:
            published_at = timezone.now()  # Fallback to current time

        # Generate article hash (same method as run_nasdaq_sentiment.py)
        article_hash = get_article_hash(article_data['url'])

        # Calculate sentiment from impact (reverse the scaling)
        # impact is capped at ±25, and comes from: sentiment * 100 * weight * 100
        # For simplicity, estimate base_sentiment from impact
        weight = MARKET_CAP_WEIGHTS.get(ticker_symbol, 0.01)
        estimated_sentiment = impact / (weight * 100 * 100)
        estimated_sentiment = max(-1.0, min(1.0, estimated_sentiment))  # Clip to -1/+1

        # Save to database (update_or_create prevents duplicates)
        article, created = NewsArticle.objects.update_or_create(
            article_hash=article_hash,
            defaults={
                'ticker': ticker,
                'analysis_run': None,  # Real-time articles don't have analysis_run
                'headline': article_data.get('headline', '')[:500],  # Truncate if too long
                'summary': article_data.get('summary', '')[:2000],
                'source': 'Finnhub (Real-Time)',
                'url': article_data.get('url', ''),
                'published_at': published_at,
                'article_type': 'company',
                'base_sentiment': estimated_sentiment,
                'surprise_factor': 1.0,  # Real-time scoring doesn't calculate these
                'novelty_score': 1.0,
                'source_credibility': 0.8,  # Finnhub is credible
                'recency_weight': 1.0,
                'article_score': impact,  # Use the calculated impact
                'weighted_contribution': impact,
                'is_analyzed': True,
                'sentiment_cached': False  # Real-time articles are fresh
            }
        )

        if created:
            logger.info(f"✓ Saved new article to database: {article_hash[:8]} [{ticker_symbol}]")
        else:
            logger.debug(f"✓ Updated existing article: {article_hash[:8]} [{ticker_symbol}]")

        return article

    except Exception as e:
        logger.error(f"Error saving article to database: {e}", exc_info=True)
        # Don't raise - we don't want to break sentiment calculation if DB save fails
        return None


# ============================================================================
# ARTICLE SCORING (matches run_nasdaq_sentiment.py exactly)
# ============================================================================

def score_article_with_ai(headline, summary, symbol):
    """
    Score article using AI sentiment analysis (OpenAI or FinBERT based on config).
    
    This uses the same sentiment provider as run_nasdaq_sentiment.py for consistency.
    Respects SENTIMENT_PROVIDER environment variable.
    
    Args:
        headline: Article headline
        summary: Article summary
        symbol: Stock symbol
    
    Returns:
        float: Article impact on news score (already scaled and weighted)
    """
    try:
        # Import the sentiment analysis wrapper from run_nasdaq_sentiment
        # This automatically uses OpenAI or FinBERT based on SENTIMENT_PROVIDER env var
        from api.management.commands.run_nasdaq_sentiment import analyze_sentiment_batch
        
        # Score the article
        text = f"{headline}. {summary}" if summary else headline
        sentiments = analyze_sentiment_batch([text])
        
        if not sentiments or len(sentiments) == 0:
            logger.warning(f"No sentiment returned for {symbol} article")
            return 0.0
        
        sentiment = sentiments[0]  # -1 to +1
        
        # Calculate article score (simplified - just use base sentiment)
        # In run_nasdaq_sentiment, this would include surprise, novelty, credibility, recency
        # For real-time, we use just sentiment for speed
        article_score = sentiment * 100  # Scale to -100/+100
        
        # Get market cap weight for this symbol
        weight = MARKET_CAP_WEIGHTS.get(symbol, 0.01)
        
        # Calculate weighted contribution
        weighted_contribution = article_score * weight
        
        # Scale by 100 (to match run_nasdaq_sentiment.py normalization)
        impact = weighted_contribution * 100
        
        # Cap at ±25 per article (to prevent single-article spikes)
        impact = max(-25, min(25, impact))
        
        logger.info(f"Scored {symbol} article: sentiment={sentiment:+.2f}, impact={impact:+.2f}")
        
        return float(impact)
    
    except Exception as e:
        logger.error(f"Error scoring article: {e}", exc_info=True)
        return 0.0


# ============================================================================
# SCORING THREAD (runs in background)
# ============================================================================

def scoring_worker():
    """
    Background thread that scores articles from queue.
    This prevents blocking the WebSocket collector.
    """
    global _scoring_thread_running

    logger.info("Article scoring thread started")

    while _scoring_thread_running:
        try:
            # Get article from queue (block for up to 1 second)
            try:
                article_data = article_to_score_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            # Score the article
            impact = score_article_with_ai(
                article_data['headline'],
                article_data['summary'],
                article_data['symbol']
            )

            # Save article to database (NEW)
            try:
                save_article_to_db(article_data, impact)
            except Exception as e:
                logger.error(f"Error saving article to database: {e}", exc_info=True)
                # Continue even if save fails - don't break sentiment calculation

            # Put result in scored queue
            scored_article_queue.put(impact)

            # Mark as processed
            mark_article_processed(article_data['url'])

            logger.info(f"Article scored and queued: {article_data['symbol']} impact={impact:+.2f}")

        except Exception as e:
            logger.error(f"Error in scoring worker: {e}", exc_info=True)

    logger.info("Article scoring thread stopped")


def start_scoring_thread():
    """Start the background scoring thread."""
    global _scoring_thread, _scoring_thread_running
    
    if _scoring_thread and _scoring_thread.is_alive():
        logger.warning("Scoring thread already running")
        return
    
    _scoring_thread_running = True
    _scoring_thread = threading.Thread(target=scoring_worker, daemon=True)
    _scoring_thread.start()
    logger.info("Scoring thread started")


def stop_scoring_thread():
    """Stop the background scoring thread."""
    global _scoring_thread_running
    
    _scoring_thread_running = False
    if _scoring_thread:
        _scoring_thread.join(timeout=5.0)
    logger.info("Scoring thread stopped")


# ============================================================================
# FINNHUB QUERY (called every second from WebSocket)
# ============================================================================

def query_finnhub_for_news():
    """
    Query Finnhub for news on the next symbol in rotation.
    
    Called every second by WebSocket collector (except during rest period).
    Returns immediately - scoring happens in background thread.
    
    Returns:
        dict: {
            'symbol': str or None,
            'articles_found': int,
            'queued_for_scoring': int
        }
    """
    global _current_index, _last_query_time
    
    # Check if we're in rest period (last 10 seconds of minute)
    current_second = timezone.now().second
    if current_second >= WORK_SECONDS:
        return {
            'symbol': None,
            'articles_found': 0,
            'queued_for_scoring': 0,
            'reason': 'rest_period'
        }
    
    # Rate limiting (safety)
    now = time.time()
    if _last_query_time and (now - _last_query_time) < 0.9:
        return {
            'symbol': None,
            'articles_found': 0,
            'queued_for_scoring': 0,
            'reason': 'rate_limit'
        }
    
    # Get Finnhub client
    client = get_finnhub_client()
    if not client:
        return {
            'symbol': None,
            'articles_found': 0,
            'queued_for_scoring': 0,
            'reason': 'no_client'
        }
    
    # Get next symbol
    symbol = WATCHLIST[_current_index % len(WATCHLIST)]
    _current_index += 1
    _last_query_time = now
    
    try:
        # Query Finnhub for company news (last 1 day)
        today = datetime.now()
        yesterday = today - timedelta(days=1)
        
        articles = client.company_news(
            symbol,
            _from=yesterday.strftime('%Y-%m-%d'),
            to=today.strftime('%Y-%m-%d')
        )

        # Discovery-level logging for visibility into each API call
        total_returned = len(articles) if isinstance(articles, list) else 0
        logger.info(
            f"FINNHUB QUERY: symbol={symbol}, "
            f"from={yesterday.strftime('%Y-%m-%d')} to={today.strftime('%Y-%m-%d')}, "
            f"articles_returned={total_returned}"
        )
        
        if not articles:
            return {
                'symbol': symbol,
                'articles_found': 0,
                'queued_for_scoring': 0
            }
        
        # Process new articles (top 3 only)
        queued = 0
        for article in articles[:3]:
            url = article.get('url', '')
            
            if not url or is_article_processed(url):
                continue
            
            # New article! Queue for scoring
            article_data = {
                'headline': article.get('headline', ''),
                'summary': article.get('summary', ''),
                'symbol': symbol,
                'url': url,
                'published': article.get('datetime', 0)
            }
            
            # Try to queue, but don't block if queue is full (prevents memory exhaustion)
            try:
                article_to_score_queue.put_nowait(article_data)
                queued += 1
                logger.info(f"Queued {symbol} article for scoring: {article_data['headline'][:60]}...")
            except queue.Full:
                logger.warning(f"Article queue full, skipping {symbol} article (system under load)")
        
        return {
            'symbol': symbol,
            'articles_found': len(articles),
            'queued_for_scoring': queued
        }
    
    except Exception as e:
        logger.error(f"Error querying Finnhub for {symbol}: {e}", exc_info=True)
        return {
            'symbol': symbol,
            'articles_found': 0,
            'queued_for_scoring': 0,
            'error': str(e)
        }


# ============================================================================
# GET SCORED ARTICLES (called from sentiment_realtime_v2.py)
# ============================================================================

def get_scored_articles():
    """
    Get all articles that have been scored and are ready to apply.
    
    Returns:
        list: List of article impacts (floats)
    """
    impacts = []
    
    try:
        while not scored_article_queue.empty():
            impact = scored_article_queue.get_nowait()
            impacts.append(impact)
    except queue.Empty:
        pass
    
    return impacts


# ============================================================================
# STATS
# ============================================================================

def get_stats():
    """Get Finnhub integration statistics."""
    return {
        'enabled': FINNHUB_AVAILABLE and bool(FINNHUB_API_KEY),
        'current_index': _current_index,
        'current_symbol': WATCHLIST[_current_index % len(WATCHLIST)] if _current_index > 0 else None,
        'queue_size': article_to_score_queue.qsize(),
        'scored_queue_size': scored_article_queue.qsize(),
        'scoring_thread_alive': _scoring_thread.is_alive() if _scoring_thread else False
    }


# ============================================================================
# INITIALIZATION
# ============================================================================

def initialize():
    """Initialize Finnhub integration."""
    if not FINNHUB_AVAILABLE:
        logger.warning("Finnhub not available - real-time news disabled")
        return False
    
    if not FINNHUB_API_KEY:
        logger.warning("FINNHUB_API_KEY not set - real-time news disabled")
        return False
    
    # Start scoring thread
    start_scoring_thread()
    
    logger.info("Finnhub integration initialized")
    return True


# ============================================================================
# TESTING
# ============================================================================

if __name__ == '__main__':
    import django
    import os
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    django.setup()
    
    print("Testing Finnhub integration...")
    print("=" * 60)
    
    # Initialize
    if initialize():
        print("✓ Initialized")
        
        # Simulate 10 seconds of queries
        for i in range(10):
            result = query_finnhub_for_news()
            print(f"\nSecond {i+1}:")
            print(f"  Symbol: {result.get('symbol')}")
            print(f"  Articles found: {result.get('articles_found', 0)}")
            print(f"  Queued for scoring: {result.get('queued_for_scoring', 0)}")
            
            # Check for scored articles
            impacts = get_scored_articles()
            if impacts:
                print(f"  Scored articles ready: {len(impacts)}")
                for impact in impacts:
                    print(f"    Impact: {impact:+.2f}")
            
            time.sleep(1)
        
        # Stop
        stop_scoring_thread()
        print("\n✓ Test completed")
    else:
        print("✗ Initialization failed")

