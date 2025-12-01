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
from datetime import datetime, timedelta, timezone as dt_timezone
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
TIME_WINDOW_HOURS = 24  # Rolling window: last 24 hours of news

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
            msg = "Tiingo news integration is disabled (ENABLE_TIINGO_NEWS=False)"
            logger.debug(msg)
            print(f"⚠️  {msg}")  # Ensure appears in Railway logs
            return None

        if not TIINGO_AVAILABLE:
            msg = "Tiingo library not available - install with: pip install tiingo"
            logger.error(msg)
            print(f"❌ {msg}")  # Ensure appears in Railway logs
            return None

        if not TIINGO_API_KEY:
            msg = "TIINGO_API_KEY not set in environment"
            logger.error(msg)
            print(f"❌ {msg}")  # Ensure appears in Railway logs
            return None

        if _tiingo_client is None:
            msg = f"🔧 Initializing Tiingo client with API key: {TIINGO_API_KEY[:10]}..."
            logger.info(msg)
            print(msg)  # Ensure appears in Railway logs
            config = {
                'api_key': TIINGO_API_KEY,
                'session': True  # Reuse HTTP session for performance
            }
            _tiingo_client = TiingoClient(config)
            msg = "✅ Tiingo client initialized successfully"
            logger.info(msg)
            print(msg)  # Ensure appears in Railway logs

        return _tiingo_client

    except Exception as e:
        msg = f"Error initializing Tiingo client: {e}"
        logger.error(msg, exc_info=True)
        print(f"❌ {msg}")  # Ensure appears in Railway logs
        import traceback
        print(f"   Traceback: {traceback.format_exc()}")
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
# DATABASE SAVING
# ============================================================================

def save_article_to_db(article_data, impact):
    """
    Save article to NewsArticle database table.

    Args:
        article_data: Dict with article info (headline, summary, url, symbol, published, source)
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
            # For 'MARKET' or unknown tickers, use QLD (NASDAQ composite)
            logger.warning(f"Ticker {ticker_symbol} not found in database, using QLD as fallback")
            try:
                ticker = Ticker.objects.get(symbol='QLD')
            except Ticker.DoesNotExist:
                logger.error("QLD ticker not found in database - cannot save article")
                return None

        # Parse published date
        published_at = None
        if article_data.get('published'):
            try:
                published_str = article_data['published']
                published_at = parse_datetime(published_str)
                
                # Ensure timezone-aware (Tiingo should return ISO 8601 with Z, but be defensive)
                if published_at and timezone.is_naive(published_at):
                    # Make naive datetime aware by assuming UTC
                    published_at = published_at.replace(tzinfo=dt_timezone.utc)
                    logger.warning(f"Converted naive datetime to UTC: {published_str}")
                    
            except Exception as e:
                logger.error(f"Error parsing published date '{published_str}': {e}", exc_info=True)

        if not published_at:
            published_at = timezone.now()  # Fallback to current time
            logger.warning(f"No valid published date, using current time: {published_at}")

        # Generate article hash
        article_hash = get_article_hash(article_data['url'])
        if not article_hash:
            logger.error(f"Could not generate hash for article URL: {article_data.get('url', 'N/A')}")
            return None

        # Calculate sentiment from impact (reverse the scaling)
        weight = MARKET_CAP_WEIGHTS.get(ticker_symbol, 0.01)
        estimated_sentiment = impact / (weight * 100 * 100)
        estimated_sentiment = max(-1.0, min(1.0, estimated_sentiment))  # Clip to -1/+1

        # Determine article type
        article_type = 'market' if ticker_symbol == 'MARKET' else 'company'

        # Save to database (update_or_create prevents duplicates)
        article, created = NewsArticle.objects.update_or_create(
            article_hash=article_hash,
            defaults={
                'ticker': ticker,
                'analysis_run': None,  # Real-time articles don't have analysis_run
                'headline': article_data.get('headline', '')[:500],  # Truncate if too long
                'summary': article_data.get('summary', '')[:2000],
                'source': f"Tiingo (Real-Time) - {article_data.get('source', 'unknown')}",
                'url': article_data.get('url', ''),
                'published_at': published_at,
                'article_type': article_type,
                'base_sentiment': estimated_sentiment,
                'surprise_factor': 1.0,  # Real-time scoring doesn't calculate these
                'novelty_score': 1.0,
                'source_credibility': 0.8,  # Tiingo is credible
                'recency_weight': 1.0,
                'article_score': impact,  # Use the calculated impact
                'weighted_contribution': impact,
                'is_analyzed': True,
                'sentiment_cached': False  # Real-time articles are fresh
            }
        )

        if created:
            logger.info(f"✓ Saved new Tiingo article to database: {article_hash[:8]} [{ticker_symbol}]")
        else:
            logger.debug(f"✓ Updated existing Tiingo article: {article_hash[:8]} [{ticker_symbol}]")

        return article

    except Exception as e:
        logger.error(f"Error saving Tiingo article to database: {e}", exc_info=True)
        # Don't raise - we don't want to break sentiment calculation if DB save fails
        return None


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

            logger.info(f"   🤖 Scoring article: [{article_data['symbol']}] {article_data['headline'][:60]}...")

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
                logger.error(f"Error saving Tiingo article to database: {e}", exc_info=True)
                # Continue even if save fails - don't break sentiment calculation

            # Put result in scored queue
            scored_article_queue.put(impact)

            # Mark as processed
            mark_article_processed(article_data['url'])

            logger.info(f"   ✅ SCORED: [{article_data['symbol']}] impact={impact:+.2f} | {article_data['headline'][:50]}...")

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
            # Extra logging so we always know why the client is unavailable
            msg = (
                "Tiingo client unavailable. "
                f"ENABLE_TIINGO_NEWS={ENABLE_TIINGO_NEWS}, "
                f"TIINGO_AVAILABLE={TIINGO_AVAILABLE}, "
                f"has_api_key={bool(TIINGO_API_KEY)}"
            )
            logger.error(msg)
            print(f"❌ {msg}")  # Ensure appears in Railway logs

            return {
                'articles_found': 0,
                'queued_for_scoring': 0,
                'error': 'client_unavailable'
            }

        # Determine time window (rolling window based on TIME_WINDOW_HOURS)
        now = timezone.now()
        start_time = now - timedelta(hours=TIME_WINDOW_HOURS)
        
        # For Tiingo News API: Query last 2 days to handle timezone/indexing issues
        # API uses date-only format, so we query a bit broader then filter by publishedDate
        start_date_for_api = (now - timedelta(days=1)).date()  # Yesterday
        end_date_for_api = now.date()  # Today

        # Extra logging about the computed time window
        logger.info(
            "Tiingo query window: "
            f"hours={TIME_WINDOW_HOURS}, "
            f"start={start_time.isoformat()}, "
            f"end={now.isoformat()}, "
            f"delta_sec={(now - start_time).total_seconds():.1f}"
        )

        # Format dates for Tiingo API (date-only format required)
        start_date_str = start_date_for_api.strftime('%Y-%m-%d')
        end_date_str = end_date_for_api.strftime('%Y-%m-%d')
        
        # For display/logging, show the actual time window we want
        start_datetime_str = start_time.strftime('%Y-%m-%dT%H:%M:%SZ')
        end_datetime_str = now.strftime('%Y-%m-%dT%H:%M:%SZ')

        msg1 = f"📰 TIINGO QUERY #{_query_count + 1} START: Target window {start_datetime_str} to {end_datetime_str}"
        msg2 = f"   API query: NO date parameters (getting latest news, limit=1000)"
        msg3 = f"   Will filter by publishedDate to get articles from last 24 hours"
        logger.info(msg1)
        logger.info(msg2)
        logger.info(msg3)
        print(msg1)  # Ensure appears in Railway logs
        print(msg2)  # Ensure appears in Railway logs
        print(msg3)  # Ensure appears in Railway logs

        total_articles_found = 0
        queued_count = 0

        # Query 1: Top tickers (specific company news)
        try:
            msg = f"   → Querying {len(TOP_TICKERS)} tickers: {', '.join(TOP_TICKERS[:5])}... (limit=1000)"
            logger.info(msg)
            print(msg)  # Ensure appears in Railway logs

            # Tiingo get_news expects tickers as list, not string
            # DEBUG: Log the exact parameters being sent
            logger.info(f"   DEBUG: Calling client.get_news with:")
            logger.info(f"      tickers={TOP_TICKERS}")
            logger.info(f"      limit=1000")
            logger.info(f"      (NO date parameters - getting latest news)")
            
            # Try WITHOUT date parameters to get latest news
            news_data = client.get_news(
                tickers=TOP_TICKERS,  # Already a list
                limit=1000  # Get as many as possible (Tiingo paid plan)
            )
            
            # DEBUG: Log the response
            logger.info(f"   DEBUG: Response type: {type(news_data)}")
            logger.info(f"   DEBUG: Response length: {len(news_data) if isinstance(news_data, list) else 'N/A'}")
            if isinstance(news_data, list) and len(news_data) > 0:
                logger.info(f"   DEBUG: First article keys: {list(news_data[0].keys())}")
                logger.info(f"   DEBUG: First article: {news_data[0]}")

            if news_data and isinstance(news_data, list):
                total_articles_found += len(news_data)
                queued_count += process_news_articles(news_data, 'ticker_query', start_time, now)
                msg = f"   ✓ Ticker query: {len(news_data)} articles found, {queued_count} new articles queued"
                logger.info(msg)
                print(msg)  # Ensure appears in Railway logs
                if len(news_data) > 0:
                    msg = f"      Sample: {news_data[0].get('title', 'N/A')[:80]}..."
                    logger.info(msg)
                    print(msg)  # Ensure appears in Railway logs
            else:
                msg = (
                    f"   ✓ Ticker query: No articles returned "
                    f"(raw_type={type(news_data).__name__})"
                )
                logger.info(msg)
                print(msg)  # Ensure appears in Railway logs

        except Exception as e:
            msg = f"   ✗ Ticker query FAILED: {e}"
            logger.error(msg, exc_info=True)
            print(f"❌ {msg}")  # Ensure appears in Railway logs
            import traceback
            print(f"   Traceback: {traceback.format_exc()}")
            # Continue even if ticker query fails

        # Query 2: General market keywords (broad NASDAQ news)
        # Query QQQ separately as it represents NASDAQ-100
        try:
            msg = f"   → Querying QQQ market news (limit=50)"
            logger.info(msg)
            print(msg)  # Ensure appears in Railway logs

            # Query QQQ (NASDAQ-100 ETF) for general market news
            market_news = client.get_news(
                tickers=['QQQ'],  # NASDAQ-100 ETF as proxy for market news
                limit=50  # Smaller limit for general news
            )

            market_queued = 0
            if market_news and isinstance(market_news, list):
                total_articles_found += len(market_news)
                market_queued = process_news_articles(market_news, 'market_query', start_time, now)
                queued_count += market_queued
                msg = f"   ✓ Market query: {len(market_news)} articles found, {market_queued} new articles queued"
                logger.info(msg)
                print(msg)  # Ensure appears in Railway logs
                if len(market_news) > 0:
                    msg = f"      Sample: {market_news[0].get('title', 'N/A')[:80]}..."
                    logger.info(msg)
                    print(msg)  # Ensure appears in Railway logs
            else:
                msg = (
                    f"   ✓ Market query: No articles returned "
                    f"(raw_type={type(market_news).__name__})"
                )
                logger.info(msg)
                print(msg)  # Ensure appears in Railway logs

        except Exception as e:
            # Market query failure is non-critical - we still have ticker data
            msg = f"   ✗ Market query failed (non-critical): {e}"
            logger.warning(msg)
            print(f"⚠️  {msg}")  # Ensure appears in Railway logs

        # Update state
        _last_query_time = now
        _query_count += 1

        msg = f"📰 TIINGO QUERY #{_query_count} COMPLETE: {total_articles_found} total, {queued_count} queued for scoring"
        logger.info(msg)
        print(msg)  # Ensure appears in Railway logs

        return {
            'articles_found': total_articles_found,
            'queued_for_scoring': queued_count,
            'time_window_start': start_time,
            'query_count': _query_count
        }

    except Exception as e:
        msg = f"Error in Tiingo news query: {e}"
        logger.error(msg, exc_info=True)
        print(f"❌ {msg}")  # Ensure appears in Railway logs
        import traceback
        print(f"   Traceback: {traceback.format_exc()}")
        return {
            'articles_found': 0,
            'queued_for_scoring': 0,
            'error': str(e)
        }


def process_news_articles(articles, query_type, start_time=None, end_time=None):
    """
    Process a list of news articles from Tiingo.

    Filters duplicates, filters by time window, and queues new articles for scoring.
    Uses PRIMARY TICKER ONLY (first ticker in list).

    Args:
        articles: List of article dicts from Tiingo API
        query_type: 'ticker_query' or 'market_query' (for logging)
        start_time: Optional datetime - filter articles published after this time
        end_time: Optional datetime - filter articles published before this time

    Returns:
        int: Number of articles queued for scoring
    """
    queued_count = 0
    filtered_by_time = 0

    try:
        if not articles:
            return 0

        total_input = len(articles)

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

                # Filter by time window if provided
                if start_time and end_time:
                    published_date_str = article.get('publishedDate', '')
                    if published_date_str:
                        try:
                            from django.utils.dateparse import parse_datetime
                            published_at = parse_datetime(published_date_str)
                            if published_at:
                                # Make timezone-aware if naive
                                if timezone.is_naive(published_at):
                                    published_at = published_at.replace(tzinfo=dt_timezone.utc)
                                
                                # Filter: only include articles within our time window
                                if published_at < start_time or published_at > end_time:
                                    filtered_by_time += 1
                                    continue
                        except Exception as e:
                            logger.debug(f"Error parsing publishedDate '{published_date_str}': {e}")

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
                    logger.info(f"      📝 Queued: [{primary_ticker}] {title[:70]}...")

                except queue.Full:
                    logger.warning(f"      ⚠️  Queue FULL (100 items), skipping remaining articles")
                    break  # Stop processing if queue is full

            except Exception as e:
                logger.error(f"Error processing individual article: {e}")
                continue

        # Summary logging for this batch
        logger.info(
            f"Processed Tiingo articles batch: type={query_type}, "
            f"input_count={total_input}, filtered_by_time={filtered_by_time}, queued={queued_count}"
        )
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

        if len(impacts) > 0:
            total_impact = sum(impacts)
            logger.info(f"   💰 Consuming {len(impacts)} Tiingo impacts: Total={total_impact:+.2f}")

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
        logger.info(f"  - Time window: {TIME_WINDOW_HOURS} hours")
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
