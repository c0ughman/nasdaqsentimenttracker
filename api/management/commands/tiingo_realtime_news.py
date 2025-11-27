"""
Tiingo Real-Time News Integration with Threading

Queries Tiingo every 5 seconds for breaking news (hybrid approach: top tickers + general market).
Scores articles using OpenAI API (same method as run_nasdaq_sentiment.py).
Adds impact to news score immediately when scoring completes.

Uses threading to avoid blocking the second-by-second collector.
Completely isolated - failures do not affect SecondSnapshot generation.

ENVIRONMENT VARIABLES:
- TIINGO_API_KEY: Your Tiingo API key (required)
- ENABLE_TIINGO_NEWS: Set to "True" to activate (default: False)
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

# Try to import tiingo
try:
    from tiingo import TiingoClient
    TIINGO_AVAILABLE = True
except ImportError:
    TIINGO_AVAILABLE = False
    logger.warning("Tiingo not installed. Install with: pip install tiingo")


# ============================================================================
# CONFIGURATION
# ============================================================================

# Tiingo API configuration (set in environment)
import os
TIINGO_API_KEY = os.getenv('TIINGO_API_KEY', '')
ENABLE_TIINGO_NEWS = os.getenv('ENABLE_TIINGO_NEWS', 'False').lower() == 'true'

# Top 40 NASDAQ stocks to monitor (same as Finnhub for consistency)
TOP_TICKERS = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'AVGO',
    'COST', 'NFLX', 'AMD', 'PEP', 'ADBE', 'CSCO', 'CMCSA', 'INTC',
    'TMUS', 'QCOM', 'INTU', 'TXN', 'AMGN', 'HON', 'AMAT', 'SBUX',
    'ISRG', 'BKNG', 'ADP', 'GILD', 'ADI', 'VRTX', 'MDLZ', 'REGN',
    'LRCX', 'PANW', 'MU', 'PYPL', 'SNPS', 'KLAC', 'CDNS', 'MELI'
]

# General market keywords for broad NASDAQ news
MARKET_KEYWORDS = [
    'NASDAQ', 'Nasdaq', 'nasdaq',  # NASDAQ general
    'QQQ',  # NASDAQ-100 ETF
    'tech stocks', 'technology sector',  # Tech market
    'market',  # General market
]

# Market cap weights (same as Finnhub for consistency)
from api.management.commands.nasdaq_config import COMPANY_NAMES
MARKET_CAP_WEIGHTS = {ticker: 1.0/len(COMPANY_NAMES) for ticker in COMPANY_NAMES.keys()}
# Override with known large caps
MARKET_CAP_WEIGHTS.update({
    'AAPL': 0.14, 'MSFT': 0.13, 'GOOGL': 0.08, 'AMZN': 0.07,
    'NVDA': 0.06, 'META': 0.04, 'TSLA': 0.03, 'AVGO': 0.03
})

# Query timing
POLL_INTERVAL = 5  # Poll Tiingo every 5 seconds
TIME_WINDOW_MINUTES = 15  # Fallback: last 15 minutes

# State tracking
_last_query_time = None
_tiingo_client = None
_query_count = 0

# Article cache (prevent re-processing)
ARTICLE_CACHE_KEY = 'tiingo_articles_processed'
ARTICLE_CACHE_DURATION = 3600  # 1 hour

# Queues for threading (same pattern as Finnhub)
article_to_score_queue = queue.Queue(maxsize=100)  # Higher limit since polling less frequently
scored_article_queue = queue.Queue()

# Scoring thread
_scoring_thread = None
_scoring_thread_running = False


# ============================================================================
# TIINGO CLIENT
# ============================================================================

def get_tiingo_client():
    """
    Get or create Tiingo client.

    Returns:
        TiingoClient or None if not available/configured
    """
    global _tiingo_client

    try:
        if not ENABLE_TIINGO_NEWS:
            logger.debug("Tiingo news integration is disabled (ENABLE_TIINGO_NEWS=False)")
            return None

        if not TIINGO_AVAILABLE:
            logger.error("Tiingo library not available - install with: pip install tiingo")
            return None

        if not TIINGO_API_KEY:
            logger.error("TIINGO_API_KEY not set in environment")
            return None

        if _tiingo_client is None:
            config = {
                'api_key': TIINGO_API_KEY,
                'session': True  # Reuse HTTP session for performance
            }
            _tiingo_client = TiingoClient(config)
            logger.info("Tiingo client initialized successfully")

        return _tiingo_client

    except Exception as e:
        logger.error(f"Error initializing Tiingo client: {e}", exc_info=True)
        return None


# ============================================================================
# ARTICLE CACHING (prevent duplicates)
# ============================================================================

def get_article_hash(article_url):
    """Generate hash for article URL."""
    try:
        return hashlib.md5(article_url.encode('utf-8')).hexdigest()
    except Exception as e:
        logger.error(f"Error hashing article URL: {e}")
        return None


def is_article_processed(article_url):
    """Check if article has already been processed."""
    try:
        article_hash = get_article_hash(article_url)
        if not article_hash:
            return False

        processed = cache.get(ARTICLE_CACHE_KEY, set())
        return article_hash in processed

    except Exception as e:
        logger.error(f"Error checking article cache: {e}")
        return False


def mark_article_processed(article_url):
    """Mark article as processed in cache."""
    try:
        article_hash = get_article_hash(article_url)
        if not article_hash:
            return

        processed = cache.get(ARTICLE_CACHE_KEY, set())
        processed.add(article_hash)
        cache.set(ARTICLE_CACHE_KEY, processed, ARTICLE_CACHE_DURATION)

    except Exception as e:
        logger.error(f"Error marking article as processed: {e}")


# ============================================================================
# ARTICLE SCORING (reuses existing code from Finnhub)
# ============================================================================

def score_article_with_ai(headline, summary, symbol):
    """
    Score article using AI sentiment analysis.

    IMPORTANT: This reuses the exact same scoring logic as finnhub_realtime_v2.py
    and run_nasdaq_sentiment.py for consistency.

    Args:
        headline: Article headline
        summary: Article summary/description
        symbol: Primary stock symbol

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
            logger.warning(f"No sentiment returned for {symbol} article: {headline[:50]}")
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
        logger.error(f"Error scoring article for {symbol}: {e}", exc_info=True)
        return 0.0


# ============================================================================
# SCORING THREAD (runs in background, same as Finnhub)
# ============================================================================

def scoring_worker():
    """
    Background thread that scores articles from queue.
    This prevents blocking the polling loop and SecondSnapshot generation.
    """
    global _scoring_thread_running

    logger.info("Tiingo article scoring thread started")

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

            # Put result in scored queue
            scored_article_queue.put(impact)

            # Mark as processed
            mark_article_processed(article_data['url'])

            logger.info(f"Tiingo article scored: {article_data['symbol']} impact={impact:+.2f}")

        except Exception as e:
            logger.error(f"Error in Tiingo scoring worker: {e}", exc_info=True)

    logger.info("Tiingo article scoring thread stopped")


def start_scoring_thread():
    """Start the background scoring thread."""
    global _scoring_thread, _scoring_thread_running

    try:
        if _scoring_thread and _scoring_thread.is_alive():
            logger.warning("Tiingo scoring thread already running")
            return

        _scoring_thread_running = True
        _scoring_thread = threading.Thread(target=scoring_worker, daemon=True)
        _scoring_thread.start()
        logger.info("Tiingo scoring thread started successfully")

    except Exception as e:
        logger.error(f"Error starting Tiingo scoring thread: {e}", exc_info=True)


def stop_scoring_thread():
    """Stop the background scoring thread."""
    global _scoring_thread_running

    try:
        _scoring_thread_running = False
        if _scoring_thread:
            _scoring_thread.join(timeout=5.0)
        logger.info("Tiingo scoring thread stopped")

    except Exception as e:
        logger.error(f"Error stopping Tiingo scoring thread: {e}", exc_info=True)


# ============================================================================
# TIINGO NEWS QUERY (hybrid approach)
# ============================================================================

def query_tiingo_for_news():
    """
    Query Tiingo for news using hybrid approach:
    1. Top 40 NASDAQ tickers (specific company news)
    2. General market keywords (broad NASDAQ news)

    Uses "since last query" time window with 15-minute fallback.
    Returns immediately - scoring happens in background thread.

    Returns:
        dict: {
            'articles_found': int,
            'queued_for_scoring': int,
            'time_window_start': datetime,
            'error': str or None
        }
    """
    global _last_query_time, _query_count

    try:
        # Check if enabled
        if not ENABLE_TIINGO_NEWS:
            return {
                'articles_found': 0,
                'queued_for_scoring': 0,
                'reason': 'disabled'
            }

        # Get Tiingo client
        client = get_tiingo_client()
        if not client:
            return {
                'articles_found': 0,
                'queued_for_scoring': 0,
                'error': 'client_unavailable'
            }

        # Determine time window (since last query, or last 15 minutes)
        now = timezone.now()
        if _last_query_time:
            start_time = _last_query_time
            # Fallback to 15 minutes if gap is too large
            if (now - start_time).total_seconds() > 900:  # 15 minutes
                start_time = now - timedelta(minutes=TIME_WINDOW_MINUTES)
        else:
            start_time = now - timedelta(minutes=TIME_WINDOW_MINUTES)

        # Format dates for Tiingo API (ISO 8601)
        start_date_str = start_time.strftime('%Y-%m-%dT%H:%M:%S')
        end_date_str = now.strftime('%Y-%m-%dT%H:%M:%S')

        logger.info(f"Querying Tiingo for news from {start_date_str} to {end_date_str}")

        total_articles_found = 0
        queued_count = 0

        # Query 1: Top tickers (specific company news)
        try:
            # Tiingo get_news expects tickers as list, not string
            news_data = client.get_news(
                tickers=TOP_TICKERS,  # Already a list
                startDate=start_date_str,
                endDate=end_date_str,
                limit=1000  # Get as many as possible (Tiingo paid plan)
            )

            if news_data and isinstance(news_data, list):
                total_articles_found += len(news_data)
                queued_count += process_news_articles(news_data, 'ticker_query')
                logger.info(f"Tiingo ticker query returned {len(news_data)} articles")
            else:
                logger.debug("Tiingo ticker query returned no articles")

        except Exception as e:
            logger.error(f"Error querying Tiingo for tickers: {e}", exc_info=True)
            # Continue even if ticker query fails

        # Query 2: General market keywords (broad NASDAQ news)
        # Query QQQ separately as it represents NASDAQ-100
        try:
            # Query QQQ (NASDAQ-100 ETF) for general market news
            market_news = client.get_news(
                tickers=['QQQ'],  # NASDAQ-100 ETF as proxy for market news
                startDate=start_date_str,
                endDate=end_date_str,
                limit=50  # Smaller limit for general news
            )

            if market_news and isinstance(market_news, list):
                total_articles_found += len(market_news)
                queued_count += process_news_articles(market_news, 'market_query')
                logger.info(f"Tiingo market query (QQQ) returned {len(market_news)} articles")
            else:
                logger.debug("Tiingo market query returned no articles")

        except Exception as e:
            # Market query failure is non-critical - we still have ticker data
            logger.debug(f"Tiingo market query failed (non-critical): {e}")

        # Update state
        _last_query_time = now
        _query_count += 1

        logger.info(f"Tiingo query #{_query_count}: {total_articles_found} articles, {queued_count} queued for scoring")

        return {
            'articles_found': total_articles_found,
            'queued_for_scoring': queued_count,
            'time_window_start': start_time,
            'query_count': _query_count
        }

    except Exception as e:
        logger.error(f"Error in Tiingo news query: {e}", exc_info=True)
        return {
            'articles_found': 0,
            'queued_for_scoring': 0,
            'error': str(e)
        }


def process_news_articles(articles, query_type):
    """
    Process a list of news articles from Tiingo.

    Filters duplicates and queues new articles for scoring.
    Uses PRIMARY TICKER ONLY (first ticker in list).

    Args:
        articles: List of article dicts from Tiingo API
        query_type: 'ticker_query' or 'market_query' (for logging)

    Returns:
        int: Number of articles queued for scoring
    """
    queued_count = 0

    try:
        if not articles:
            return 0

        for article in articles:
            try:
                # Safely extract article data with validation
                url = str(article.get('url', '')).strip()
                title = str(article.get('title', '')).strip()
                description = str(article.get('description', '')).strip()
                tickers = article.get('tickers', [])

                # Skip if missing critical data
                if not url or not title:
                    logger.debug(f"Skipping article with missing url or title")
                    continue

                # Validate URL format
                if not url.startswith('http'):
                    logger.debug(f"Skipping article with invalid URL: {url[:50]}")
                    continue

                # Skip if already processed
                if is_article_processed(url):
                    continue

                # Get primary ticker (first in list, or default to 'MARKET')
                if tickers and isinstance(tickers, list) and len(tickers) > 0:
                    primary_ticker = str(tickers[0]).upper().strip()
                else:
                    primary_ticker = 'MARKET'

                # Validate ticker format (alphanumeric only)
                if not primary_ticker.replace('-', '').replace('.', '').isalnum():
                    logger.warning(f"Invalid ticker format: {primary_ticker}, using MARKET")
                    primary_ticker = 'MARKET'

                # Queue for scoring
                article_data = {
                    'headline': title,
                    'summary': description if description else title,  # Use title if no description
                    'symbol': primary_ticker,
                    'url': url,
                    'published': str(article.get('publishedDate', '')),
                    'source': str(article.get('source', 'unknown'))
                }

                # Try to queue (non-blocking)
                try:
                    article_to_score_queue.put_nowait(article_data)
                    queued_count += 1
                    logger.debug(f"Queued {primary_ticker} article: {title[:60]}...")

                except queue.Full:
                    logger.warning(f"Tiingo article queue full, skipping article (system under load)")
                    break  # Stop processing if queue is full

            except Exception as e:
                logger.error(f"Error processing individual article: {e}")
                continue

        return queued_count

    except Exception as e:
        logger.error(f"Error in process_news_articles: {e}", exc_info=True)
        return 0


# ============================================================================
# GET SCORED ARTICLES (called from sentiment_realtime_v2.py)
# ============================================================================

def get_scored_articles():
    """
    Get all articles that have been scored and are ready to apply.

    This is called by sentiment_realtime_v2.py to retrieve scored impacts.

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

    except Exception as e:
        logger.error(f"Error getting scored articles: {e}")

    return impacts


# ============================================================================
# STATS (for monitoring)
# ============================================================================

def get_stats():
    """Get Tiingo integration statistics."""
    try:
        return {
            'enabled': ENABLE_TIINGO_NEWS and TIINGO_AVAILABLE and bool(TIINGO_API_KEY),
            'query_count': _query_count,
            'last_query_time': _last_query_time.isoformat() if _last_query_time else None,
            'queue_size': article_to_score_queue.qsize(),
            'scored_queue_size': scored_article_queue.qsize(),
            'scoring_thread_alive': _scoring_thread.is_alive() if _scoring_thread else False
        }

    except Exception as e:
        logger.error(f"Error getting Tiingo stats: {e}")
        return {'error': str(e)}


# ============================================================================
# INITIALIZATION
# ============================================================================

def initialize():
    """
    Initialize Tiingo integration.

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Check if enabled
        if not ENABLE_TIINGO_NEWS:
            logger.info("Tiingo news integration is DISABLED (set ENABLE_TIINGO_NEWS=True to enable)")
            return False

        if not TIINGO_AVAILABLE:
            logger.warning("Tiingo library not available - run: pip install tiingo")
            return False

        if not TIINGO_API_KEY:
            logger.warning("TIINGO_API_KEY not set - Tiingo news disabled")
            return False

        # Test client connection
        client = get_tiingo_client()
        if not client:
            logger.error("Failed to initialize Tiingo client")
            return False

        # Start scoring thread
        start_scoring_thread()

        logger.info("=" * 60)
        logger.info("Tiingo Real-Time News Integration INITIALIZED")
        logger.info(f"  - Top tickers: {len(TOP_TICKERS)}")
        logger.info(f"  - Poll interval: {POLL_INTERVAL} seconds")
        logger.info(f"  - Time window: {TIME_WINDOW_MINUTES} minutes (fallback)")
        logger.info("=" * 60)

        return True

    except Exception as e:
        logger.error(f"Error initializing Tiingo integration: {e}", exc_info=True)
        return False


# ============================================================================
# TESTING
# ============================================================================

if __name__ == '__main__':
    import django
    import os
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    django.setup()

    print("\n" + "=" * 60)
    print("Testing Tiingo Real-Time News Integration")
    print("=" * 60)

    # Initialize
    if initialize():
        print("✓ Initialization successful\n")

        # Simulate 3 polling cycles (15 seconds total)
        for i in range(3):
            print(f"\n--- Poll Cycle {i+1} ---")
            result = query_tiingo_for_news()

            print(f"Articles found: {result.get('articles_found', 0)}")
            print(f"Queued for scoring: {result.get('queued_for_scoring', 0)}")

            if result.get('error'):
                print(f"ERROR: {result['error']}")

            # Check for scored articles
            time.sleep(2)  # Give scoring thread time to work
            impacts = get_scored_articles()
            if impacts:
                print(f"Scored articles ready: {len(impacts)}")
                for idx, impact in enumerate(impacts, 1):
                    print(f"  Article {idx}: impact={impact:+.2f}")

            # Wait for next poll
            if i < 2:
                print(f"\nWaiting {POLL_INTERVAL} seconds for next poll...")
                time.sleep(POLL_INTERVAL)

        # Show stats
        print("\n--- Final Statistics ---")
        stats = get_stats()
        for key, value in stats.items():
            print(f"  {key}: {value}")

        # Stop
        stop_scoring_thread()
        print("\n✓ Test completed successfully")
        print("=" * 60)

    else:
        print("✗ Initialization failed")
        print("Check that:")
        print("  1. TIINGO_API_KEY is set in .env")
        print("  2. ENABLE_TIINGO_NEWS=True in .env")
        print("  3. tiingo library is installed (pip install tiingo)")
        print("=" * 60)
