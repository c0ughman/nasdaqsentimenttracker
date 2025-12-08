"""
RSS Real-Time News Integration with Threading

Queries RSS feeds every second in rotation for breaking news.
Scores articles using OpenAI API (same method as other real-time collectors).
Adds impact to news score immediately when scoring completes.

Uses threading to avoid blocking the second-by-second collector.
Completely isolated - failures do not affect SecondSnapshot generation.

ENVIRONMENT VARIABLES:
- ENABLE_RSS_NEWS: Set to "True" to activate (default: False)
"""

import logging
import threading
import queue
import time
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone as dt_timezone
from django.utils import timezone
from django.core.cache import cache
from email.utils import parsedate_to_datetime

logger = logging.getLogger(__name__)

# Try to import feedparser
try:
    import feedparser
    FEEDPARSER_AVAILABLE = True
except ImportError:
    FEEDPARSER_AVAILABLE = False
    logger.warning("feedparser not installed. Install with: pip install feedparser")

# Try to import requests
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    logger.warning("requests not installed. Install with: pip install requests")


# ============================================================================
# CONFIGURATION
# ============================================================================

# RSS configuration (set in environment)
ENABLE_RSS_NEWS = os.getenv('ENABLE_RSS_NEWS', 'False').lower() == 'true'

# RSS feed configuration file path
RSS_FEEDS_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    'config',
    'rss_feeds.json'
)

# Query timing
RSS_TICK_INTERVAL = 1  # Poll every second (process 1 feed per call)
PER_FEED_MIN_INTERVAL = 60  # Don't poll same feed more than once per 60 seconds

# HTTP configuration
REQUEST_TIMEOUT = 3  # seconds
USER_AGENT = 'Mozilla/5.0 (compatible; NasdaqSentimentBot/1.0)'

# Market cap weights (same as other collectors for consistency)
from api.management.commands.nasdaq_config import COMPANY_NAMES
MARKET_CAP_WEIGHTS = {ticker: 1.0/len(COMPANY_NAMES) for ticker in COMPANY_NAMES.keys()}
# Override with known large caps
MARKET_CAP_WEIGHTS.update({
    'AAPL': 0.14, 'MSFT': 0.13, 'GOOGL': 0.08, 'AMZN': 0.07,
    'NVDA': 0.06, 'META': 0.04, 'TSLA': 0.03, 'AVGO': 0.03
})

# State tracking
_feeds = []  # List of feed URLs loaded from config
_current_feed_index = 0  # Current position in rotation
_feed_last_polled = {}  # Dict of feed_url -> timestamp of last poll
_query_count = 0

# Article cache (prevent re-processing)
ARTICLE_CACHE_KEY = 'rss_articles_processed'
ARTICLE_CACHE_DURATION = 3600  # 1 hour

# Queues for threading (same pattern as other collectors)
article_to_score_queue = queue.Queue(maxsize=500)  # Articles needing scoring
scored_article_queue = queue.Queue()  # Articles that have been scored
database_save_queue = queue.Queue(maxsize=500)  # Articles to save to database

# Worker threads
_scoring_thread = None
_scoring_thread_running = False
_save_worker_thread = None
_save_worker_running = False


# ============================================================================
# FEED LOADING
# ============================================================================

def load_rss_feeds():
    """
    Load RSS feed URLs from config/rss_feeds.json.
    
    Expected format:
    {
        "feeds": [
            {"url": "https://example.com/rss", "source": "Example News"},
            {"url": "https://another.com/feed"},
            ...
        ]
    }
    
    Returns:
        list: List of feed dicts, or empty list if loading fails
    """
    global _feeds
    
    try:
        if not os.path.exists(RSS_FEEDS_CONFIG_PATH):
            msg = f"RSS feeds config file not found at {RSS_FEEDS_CONFIG_PATH}"
            logger.warning(f"RSSNEWS: ⚠️ {msg}")
            print(f"⚠️ {msg}")
            return []
        
        with open(RSS_FEEDS_CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        if not isinstance(config, dict) or 'feeds' not in config:
            msg = f"Invalid RSS feeds config format (expected {{'feeds': [...]}})"
            logger.error(f"RSSNEWS: ❌ {msg}")
            print(f"❌ {msg}")
            return []
        
        feeds = config['feeds']
        
        if not isinstance(feeds, list):
            msg = "RSS feeds 'feeds' field must be a list"
            logger.error(f"RSSNEWS: ❌ {msg}")
            print(f"❌ {msg}")
            return []
        
        if len(feeds) == 0:
            msg = "RSS feeds config is empty"
            logger.warning(f"RSSNEWS: ⚠️ {msg}")
            print(f"⚠️ {msg}")
            return []
        
        # Validate and extract feed URLs
        valid_feeds = []
        for idx, feed in enumerate(feeds):
            if isinstance(feed, dict) and 'url' in feed and feed['url']:
                valid_feeds.append(feed)
            elif isinstance(feed, str) and feed:
                # Support simple string URLs too
                valid_feeds.append({'url': feed, 'source': 'RSS'})
            else:
                logger.warning(f"RSSNEWS: ⚠️ Skipping invalid feed at index {idx}: {feed}")
        
        _feeds = valid_feeds
        
        msg = f"✅ Loaded {len(valid_feeds)} RSS feeds from {RSS_FEEDS_CONFIG_PATH}"
        logger.info(f"RSSNEWS: {msg}")
        print(msg)
        
        return valid_feeds
    
    except json.JSONDecodeError as e:
        msg = f"Failed to parse RSS feeds JSON: {e}"
        logger.error(f"RSSNEWS: ❌ {msg}")
        print(f"❌ {msg}")
        return []
    
    except Exception as e:
        msg = f"Error loading RSS feeds config: {e}"
        logger.error(f"RSSNEWS: ❌ {msg}", exc_info=True)
        print(f"❌ {msg}")
        return []


# ============================================================================
# ARTICLE CACHING (prevent duplicates)
# ============================================================================

def get_article_hash(article_url):
    """Generate hash for article URL."""
    try:
        return hashlib.md5(article_url.encode('utf-8')).hexdigest()
    except Exception as e:
        logger.error(f"RSSNEWS: Error hashing article URL: {e}")
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
        logger.error(f"RSSNEWS: Error checking article cache: {e}")
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
        logger.error(f"RSSNEWS: Error marking article as processed: {e}")


# ============================================================================
# DATABASE SAVING (copied from finnhub_realtime_v2.py with RSS adaptations)
# ============================================================================

def sanitize_text(text, field_name="text", max_length=None):
    """
    Sanitize text for database storage - removes null bytes, control chars, normalizes whitespace.
    
    Args:
        text: Text to sanitize
        field_name: Name of field for logging
        max_length: Maximum length to truncate to
    
    Returns:
        Sanitized text string
    """
    if not text:
        return ""
    
    original_length = len(text)
    issues_found = []
    
    # Remove null bytes (PostgreSQL can't store these)
    if '\x00' in text:
        text = text.replace('\x00', '')
        issues_found.append("null_bytes")
    
    # Remove other control characters (0x01-0x1F) except tab, newline, carriage return
    text_clean = ''.join(char for char in text if ord(char) >= 32 or char in '\t\n\r')
    if len(text_clean) != len(text):
        issues_found.append("control_chars")
        text = text_clean
    
    # Normalize whitespace (collapse multiple spaces)
    text = ' '.join(text.split())
    
    # Truncate if needed
    if max_length and len(text) > max_length:
        text = text[:max_length]
        issues_found.append(f"truncated_to_{max_length}")
    
    # Log if sanitization occurred
    if issues_found:
        logger.info(
            f"NEWSSAVING: 🧹 Sanitized {field_name}: "
            f"issues={','.join(issues_found)} original_len={original_length} final_len={len(text)}"
        )
    
    return text.strip()


def safe_float(value, field_name="float", default=0.0, min_val=-1e10, max_val=1e10):
    """
    Validate float is not NaN/Inf and within safe range.
    
    Args:
        value: Float value to validate
        field_name: Name of field for logging
        default: Default value if invalid
        min_val: Minimum allowed value
        max_val: Maximum allowed value
    
    Returns:
        Safe float value
    """
    import math
    
    if value is None:
        return default
    
    try:
        value = float(value)
        
        # Check for NaN/Infinity
        if math.isnan(value):
            logger.warning(f"NEWSSAVING: ⚠️ {field_name} was NaN, using default={default}")
            return default
        
        if math.isinf(value):
            logger.warning(f"NEWSSAVING: ⚠️ {field_name} was Infinity, using default={default}")
            return default
        
        # Clamp to range
        if value < min_val or value > max_val:
            clamped = max(min_val, min(max_val, value))
            logger.warning(
                f"NEWSSAVING: ⚠️ {field_name} out of range: {value}, clamped to {clamped}"
            )
            return clamped
        
        return value
    except (ValueError, TypeError) as e:
        logger.warning(f"NEWSSAVING: ⚠️ {field_name} conversion error: {e}, using default={default}")
        return default


def safe_url(url, max_length=500):
    """Clean and validate URL for database storage."""
    if not url:
        return ""
    
    original = url
    url = str(url).strip()
    
    # Replace spaces with %20
    url = url.replace(' ', '%20')
    
    # Remove null bytes
    url = url.replace('\x00', '')
    
    # Truncate if needed
    if len(url) > max_length:
        url = url[:max_length]
    
    if url != original:
        logger.info(f"NEWSSAVING: 🔗 Cleaned URL: original_len={len(original)} final_len={len(url)}")
    
    return url


def save_article_to_db(article_data, impact):
    """
    Save article to NewsArticle database table.
    
    Ultra-robust version adapted from finnhub_realtime_v2.py for RSS sources.
    Every log includes "NEWSSAVING" keyword for easy searching.

    Args:
        article_data: Dict with article info (headline, summary, url, symbol, published)
        impact: Calculated sentiment impact
    
    Returns:
        NewsArticle instance or None if all retries fail
    """
    max_retries = 3
    retry_delay = 0.5  # seconds
    
    for attempt in range(max_retries):
        try:
            from api.models import NewsArticle, Ticker
            from django.utils.dateparse import parse_datetime
            from django.utils import timezone
            from django.db import IntegrityError, OperationalError, DatabaseError
            import time

            logger.info(f"NEWSSAVING: 📥 ENTRY attempt={attempt+1}/{max_retries} source=RSS")

            # ============================================================
            # 1. VALIDATE AND CLEAN ARTICLE DATA
            # ============================================================
            
            # Get ticker symbol with fallback
            ticker_symbol = str(article_data.get('symbol', 'QLD')).strip().upper()
            if not ticker_symbol:
                ticker_symbol = 'QLD'
                logger.info(f"NEWSSAVING: ⚠️ Empty symbol, using QLD")
            
            # Get headline with fallback and sanitization
            headline = str(article_data.get('headline', '')).strip()
            if not headline or not headline.replace(' ', ''):
                headline = f"[No headline] Article from RSS"
                logger.warning(f"NEWSSAVING: ⚠️ Missing/empty headline, using fallback: {headline}")
            
            # Sanitize headline
            headline = sanitize_text(headline, field_name="headline", max_length=500)
            
            if not headline:
                headline = f"[Sanitized empty] Article from RSS"
                logger.warning(f"NEWSSAVING: ⚠️ Headline became empty after sanitization")
            
            # Get summary with fallback and sanitization
            summary = str(article_data.get('summary', '')).strip()
            if not summary:
                summary = headline  # Use headline as summary if missing
            summary = sanitize_text(summary, field_name="summary", max_length=2000)
            
            # Get URL with fallback and cleaning
            url = str(article_data.get('url', '')).strip()
            if not url:
                # Generate a placeholder URL if missing
                url = f"https://rss-feed.local/article/{ticker_symbol}/{int(time.time())}"
                logger.warning(f"NEWSSAVING: ⚠️ Missing URL, generated: {url}")
            url = safe_url(url, max_length=500)

            logger.info(f"NEWSSAVING: 📊 DATA ticker={ticker_symbol} headline_len={len(headline)} url_len={len(url)} impact={impact:.2f}")

            # ============================================================
            # 2. GET OR CREATE TICKER
            # ============================================================
            
            ticker = None
            try:
                ticker = Ticker.objects.get(symbol=ticker_symbol)
                logger.debug(f"NEWSSAVING: ✓ Ticker found: {ticker_symbol}")
            except Ticker.DoesNotExist:
                logger.warning(f"NEWSSAVING: ⚠️ Ticker {ticker_symbol} not found, trying QLD fallback")
                try:
                    ticker = Ticker.objects.get(symbol='QLD')
                    logger.info(f"NEWSSAVING: ✓ Using QLD fallback for {ticker_symbol}")
                except Ticker.DoesNotExist:
                    # Last resort: create QLD ticker if it doesn't exist
                    logger.warning("NEWSSAVING: ⚠️ QLD ticker missing! Creating it now...")
                    ticker, created = Ticker.objects.get_or_create(
                        symbol='QLD',
                        defaults={'company_name': 'ProShares Ultra QQQ (2x Leveraged NASDAQ-100 ETF)'}
                    )
                    if created:
                        logger.info("NEWSSAVING: ✓ Created QLD ticker")

            # ============================================================
            # 3. PARSE AND VALIDATE PUBLISHED DATE
            # ============================================================
            
            published_at = None
            if article_data.get('published'):
                try:
                    published_timestamp = article_data['published']
                    if isinstance(published_timestamp, (int, float)):
                        # Validate timestamp is in reasonable range
                        if published_timestamp < 0 or published_timestamp > 4102444800:  # Year 2100
                            logger.warning(f"NEWSSAVING: ⚠️ Timestamp out of range: {published_timestamp}, using now")
                            published_at = timezone.now()
                        else:
                            published_at = datetime.fromtimestamp(published_timestamp, tz=dt_timezone.utc)
                    else:
                        published_at = parse_datetime(str(published_timestamp))
                except Exception as e:
                    logger.warning(f"NEWSSAVING: ⚠️ Date parse error: {e}, using now")
            
            if not published_at:
                published_at = timezone.now()
            
            # Validate datetime is in reasonable range
            if published_at.year < 1900 or published_at.year > 2100:
                logger.warning(f"NEWSSAVING: ⚠️ Date year out of range: {published_at.year}, using now")
                published_at = timezone.now()
            
            # Ensure timezone-aware
            if timezone.is_naive(published_at):
                published_at = timezone.make_aware(published_at)
                logger.debug(f"NEWSSAVING: 🕐 Made datetime timezone-aware")

            # ============================================================
            # 4. GENERATE AND VALIDATE ARTICLE HASH
            # ============================================================
            
            article_hash = None
            try:
                article_hash = get_article_hash(url)
                # Validate hash is 32 chars (MD5 format)
                if article_hash and len(article_hash) != 32:
                    logger.warning(f"NEWSSAVING: ⚠️ Invalid hash length: {len(article_hash)}, regenerating")
                    article_hash = None
            except Exception as e:
                logger.warning(f"NEWSSAVING: ⚠️ Hash generation error: {e}")
            
            if not article_hash:
                # Fallback: generate hash from headline + timestamp
                import hashlib
                fallback_string = f"{headline}_{ticker_symbol}_{int(published_at.timestamp())}"
                article_hash = hashlib.md5(fallback_string.encode('utf-8', errors='ignore')).hexdigest()
                logger.warning(f"NEWSSAVING: ⚠️ Using fallback hash: {article_hash[:8]}")

            # ============================================================
            # 5. VALIDATE AND CALCULATE SENTIMENT (NaN/Inf safe)
            # ============================================================
            
            # Validate impact value
            impact = safe_float(impact, field_name="impact", default=0.0, min_val=-100, max_val=100)
            
            weight = MARKET_CAP_WEIGHTS.get(ticker_symbol, 0.01)
            if weight == 0 or weight is None:
                weight = 0.01  # Prevent division by zero
                logger.debug(f"NEWSSAVING: ⚠️ Weight was 0, using 0.01")
            
            # Calculate with overflow protection
            try:
                estimated_sentiment = impact / (weight * 100 * 100)
                estimated_sentiment = safe_float(
                    estimated_sentiment, 
                    field_name="estimated_sentiment",
                    default=0.0,
                    min_val=-1.0,
                    max_val=1.0
                )
            except (ZeroDivisionError, OverflowError) as e:
                logger.warning(f"NEWSSAVING: ⚠️ Sentiment calc error: {e}, using 0.0")
                estimated_sentiment = 0.0

            # ============================================================
            # 6. SAVE TO DATABASE WITH COMPREHENSIVE LOGGING
            # ============================================================
            
            logger.info(
                f"NEWSSAVING: 💾 SAVING hash={article_hash[:8]} ticker={ticker_symbol} "
                f"sentiment={estimated_sentiment:.3f} impact={impact:.2f}"
            )
            
            # Validate all float fields one more time before save
            safe_impact = safe_float(impact, "final_impact", 0.0, -100, 100)
            safe_sentiment = safe_float(estimated_sentiment, "final_sentiment", 0.0, -1.0, 1.0)
            
            article, created = NewsArticle.objects.update_or_create(
                article_hash=article_hash,
                defaults={
                    'ticker': ticker,
                    'analysis_run': None,
                    'headline': headline,
                    'summary': summary,
                    'source': 'RSS (Real-Time)',  # RSS-specific source label
                    'url': url,
                    'published_at': published_at,
                    'article_type': 'market',  # Default RSS articles to 'market' type
                    'base_sentiment': safe_sentiment,
                    'surprise_factor': 1.0,
                    'novelty_score': 1.0,
                    'source_credibility': 0.7,  # Slightly lower than Finnhub (0.8)
                    'recency_weight': 1.0,
                    'article_score': safe_impact,
                    'weighted_contribution': safe_impact,
                    'is_analyzed': True,
                    'sentiment_cached': False
                }
            )

            # Success!
            if created:
                logger.info(
                    f"NEWSSAVING: ✅ SAVED_NEW hash={article_hash[:8]} id={article.id} "
                    f"ticker={ticker_symbol} headline={headline[:50]}..."
                )
            else:
                logger.info(
                    f"NEWSSAVING: ♻️ UPDATED hash={article_hash[:8]} id={article.id} ticker={ticker_symbol}"
                )

            return article

        except IntegrityError as e:
            # Constraint violation - retry
            error_msg = str(e).lower()
            if 'unique constraint' in error_msg or 'duplicate key' in error_msg:
                logger.warning(
                    f"NEWSSAVING: 🔄 DUPLICATE hash={article_hash[:8] if 'article_hash' in locals() else 'unknown'} "
                    f"attempt={attempt + 1}/{max_retries}"
                )
            else:
                logger.warning(
                    f"NEWSSAVING: ⚠️ INTEGRITY_ERROR attempt={attempt + 1}/{max_retries} error={e}"
                )
            
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2
                continue
            else:
                logger.error(
                    f"NEWSSAVING: ❌ FAILED_INTEGRITY hash={article_hash[:8] if 'article_hash' in locals() else 'unknown'} "
                    f"error={e}"
                )
                return None

        except (OperationalError, DatabaseError) as e:
            # Database connection, deadlock, timeout - retry
            logger.warning(
                f"NEWSSAVING: 🔄 DATABASE_ERROR attempt={attempt + 1}/{max_retries} error={e}"
            )
            
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2
                continue
            else:
                logger.error(
                    f"NEWSSAVING: ❌ FAILED_DATABASE after {max_retries} attempts error={e}"
                )
                return None

        except MemoryError as e:
            logger.error(f"NEWSSAVING: ❌ MEMORY_ERROR (out of memory): {e}")
            return None

        except Exception as e:
            # Unexpected error - log and retry
            logger.error(
                f"NEWSSAVING: ❌ UNEXPECTED_ERROR attempt={attempt + 1}/{max_retries} error={e}",
                exc_info=True
            )
            
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2
                continue
            else:
                logger.error(
                    f"NEWSSAVING: ❌ FAILED_ALL_RETRIES after {max_retries} attempts"
                )
                return None
    
    # Should never reach here
    logger.error(f"NEWSSAVING: ❌ FAILED_UNEXPECTED_EXIT")
    return None


# ============================================================================
# AI SCORING (copied from finnhub_realtime_v2.py with RSS adaptations)
# ============================================================================

def score_article_with_ai(headline, summary, symbol):
    """
    Score article using OpenAI API (same as other real-time collectors).
    
    Args:
        headline: Article headline
        summary: Article summary
        symbol: Stock symbol
    
    Returns:
        float: Impact value (sentiment * weight * scale, capped at ±25)
    """
    try:
        import os
        from openai import OpenAI
        
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            logger.warning("RSSNEWS: OpenAI API key not set, returning 0 impact")
            return 0.0
        
        client = OpenAI(api_key=api_key)
        
        # Build prompt (same as other collectors)
        prompt = f"""
Analyze this news headline and summary for sentiment toward {symbol}.

Headline: {headline}

Summary: {summary[:500]}

Return ONLY a number from -1.0 to +1.0 where:
-1.0 = Very bearish/negative
 0.0 = Neutral
+1.0 = Very bullish/positive

Just the number, nothing else.
"""
        
        # Call OpenAI API with timeout
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=10,
            timeout=5.0
        )
        
        # Parse sentiment
        sentiment_str = response.choices[0].message.content.strip()
        sentiment = float(sentiment_str)
        sentiment = max(-1.0, min(1.0, sentiment))  # Clamp to range
        
        # Calculate impact (same formula as other collectors)
        article_score = sentiment * 100  # Scale to -100/+100
        weight = MARKET_CAP_WEIGHTS.get(symbol, 0.01)
        weighted_contribution = article_score * weight
        impact = weighted_contribution * 100
        
        # Cap at ±25 per article (same as other collectors)
        impact = max(-25, min(25, impact))
        
        logger.info(f"RSSNEWS: Scored {symbol} article: sentiment={sentiment:+.2f}, impact={impact:+.2f}")
        
        return float(impact)
    
    except Exception as e:
        logger.error(f"RSSNEWS: Error scoring article: {e}", exc_info=True)
        return 0.0


# ============================================================================
# SCORING THREAD (runs in background)
# ============================================================================

def scoring_worker():
    """
    Background thread that scores articles from queue.
    This prevents blocking the collector.
    """
    global _scoring_thread_running

    logger.info("RSSNEWS: Article scoring thread started")

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

            # Priority 1: Put impact in scored queue IMMEDIATELY (sentiment update)
            scored_article_queue.put(impact)
            logger.info(f"RSSNEWS_SCORING: ✅ Scored and queued impact: {article_data['symbol']} impact={impact:+.2f}")

            # Priority 2: Queue for database save (async, non-blocking)
            try:
                save_job = {
                    'article_data': article_data,
                    'impact': impact,
                    'queued_time': timezone.now(),
                    'article_hash': get_article_hash(article_data['url'])
                }
                database_save_queue.put_nowait(save_job)
                logger.info(f"RSSNEWS_SAVEQUEUE: 📝 Queued for save: {article_data['symbol']} hash={save_job['article_hash'][:8]}")
            except queue.Full:
                logger.error(f"RSSNEWS_SAVEQUEUE: ❌ QUEUE_FULL (500 items) - cannot queue save for {article_data['symbol']}")

            # Mark as processed
            mark_article_processed(article_data['url'])

        except Exception as e:
            logger.error(f"RSSNEWS: Error in scoring worker: {e}", exc_info=True)

    logger.info("RSSNEWS: Article scoring thread stopped")


def database_save_worker():
    """
    Dedicated background thread for database saves.
    Processes saves from queue with deadline enforcement and comprehensive logging.
    """
    global _save_worker_running
    
    logger.info("=" * 80)
    logger.info("RSSNEWS_SAVEQUEUE: 🚀 STARTED")
    logger.info("=" * 80)
    
    saves_succeeded = 0
    saves_failed = 0
    saves_deadline_exceeded = 0
    
    while _save_worker_running:
        try:
            # Get save job from queue (block for up to 1 second)
            try:
                save_job = database_save_queue.get(timeout=1.0)
            except queue.Empty:
                continue
            
            article_data = save_job['article_data']
            impact = save_job['impact']
            queued_time = save_job['queued_time']
            article_hash = save_job['article_hash']
            
            # Calculate time in queue
            now = timezone.now()
            wait_time = (now - queued_time).total_seconds()
            
            logger.info(
                f"RSSNEWS_SAVEQUEUE: 🔄 Processing save job: hash={article_hash[:8]} "
                f"ticker={article_data.get('symbol')} wait_time={wait_time:.2f}s"
            )
            
            # Check deadline (60 seconds max)
            deadline_seconds = 60
            if wait_time > deadline_seconds:
                saves_deadline_exceeded += 1
                logger.error(
                    f"RSSNEWS_SAVEQUEUE: ⏰ DEADLINE_EXCEEDED hash={article_hash[:8]} "
                    f"wait_time={wait_time:.1f}s > deadline={deadline_seconds}s (skipping)"
                )
                continue
            
            # Attempt save
            try:
                article = save_article_to_db(article_data, impact)
                
                if article:
                    saves_succeeded += 1
                    logger.info(
                        f"RSSNEWS_SAVEQUEUE: ✅ SAVE_SUCCESS hash={article_hash[:8]} "
                        f"id={article.id} total_succeeded={saves_succeeded}"
                    )
                else:
                    saves_failed += 1
                    logger.error(
                        f"RSSNEWS_SAVEQUEUE: ❌ SAVE_FAILED hash={article_hash[:8]} "
                        f"total_failed={saves_failed}"
                    )
            
            except Exception as e:
                saves_failed += 1
                logger.error(
                    f"RSSNEWS_SAVEQUEUE: ❌ SAVE_EXCEPTION hash={article_hash[:8]} "
                    f"error={e} total_failed={saves_failed}",
                    exc_info=True
                )
        
        except Exception as e:
            logger.error(f"RSSNEWS_SAVEQUEUE: ❌ Worker error: {e}", exc_info=True)
    
    logger.info("=" * 80)
    logger.info(
        f"RSSNEWS_SAVEQUEUE: 🛑 STOPPED - "
        f"succeeded={saves_succeeded}, failed={saves_failed}, deadline_exceeded={saves_deadline_exceeded}"
    )
    logger.info("=" * 80)


def start_scoring_thread():
    """Start the article scoring background thread."""
    global _scoring_thread, _scoring_thread_running
    
    try:
        if _scoring_thread is not None and _scoring_thread.is_alive():
            logger.warning("RSSNEWS: Scoring thread already running")
            return
        
        _scoring_thread_running = True
        _scoring_thread = threading.Thread(target=scoring_worker, daemon=True)
        _scoring_thread.start()
        logger.info("RSSNEWS: ✅ Scoring thread started")
    
    except Exception as e:
        logger.error(f"RSSNEWS: ❌ Error starting scoring thread: {e}", exc_info=True)


def start_save_worker_thread():
    """Start the database save worker background thread."""
    global _save_worker_thread, _save_worker_running
    
    try:
        if _save_worker_thread is not None and _save_worker_thread.is_alive():
            logger.warning("RSSNEWS_SAVEQUEUE: Save worker thread already running")
            return
        
        _save_worker_running = True
        _save_worker_thread = threading.Thread(target=database_save_worker, daemon=True)
        _save_worker_thread.start()
        logger.info("RSSNEWS_SAVEQUEUE: ✅ Save worker thread started")
    
    except Exception as e:
        logger.error(f"RSSNEWS_SAVEQUEUE: ❌ Error starting save worker thread: {e}", exc_info=True)


def stop_scoring_thread():
    """Stop the article scoring thread."""
    global _scoring_thread_running
    
    try:
        logger.info("RSSNEWS: 🛑 Stopping scoring thread...")
        _scoring_thread_running = False
        
        if _scoring_thread:
            _scoring_thread.join(timeout=5.0)
            logger.info("RSSNEWS: 🛑 Scoring thread stopped")
    
    except Exception as e:
        logger.error(f"RSSNEWS: ❌ Error stopping scoring thread: {e}", exc_info=True)


def stop_save_worker_thread():
    """Stop the database save worker thread."""
    global _save_worker_running
    
    try:
        logger.info("RSSNEWS_SAVEQUEUE: 🛑 Stopping save worker thread...")
        _save_worker_running = False
        
        if _save_worker_thread:
            _save_worker_thread.join(timeout=5.0)
            logger.info("RSSNEWS_SAVEQUEUE: 🛑 Save worker thread stopped")
    
    except Exception as e:
        logger.error(f"RSSNEWS_SAVEQUEUE: ❌ Error stopping save worker thread: {e}", exc_info=True)


# ============================================================================
# RSS POLLING (rotation-based, one feed per call)
# ============================================================================

def parse_rss_date(date_string):
    """
    Parse RSS date string to timezone-aware datetime.
    
    Args:
        date_string: Date string from RSS feed (RFC 822, ISO 8601, etc.)
    
    Returns:
        datetime or None if parsing fails
    """
    if not date_string:
        return None
    
    try:
        # Try RFC 822 format (common in RSS)
        dt = parsedate_to_datetime(date_string)
        if dt:
            # Ensure timezone-aware
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt)
            return dt
    except Exception:
        pass
    
    try:
        # Try ISO 8601 format
        from django.utils.dateparse import parse_datetime
        dt = parse_datetime(date_string)
        if dt:
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt)
            return dt
    except Exception:
        pass
    
    return None


def query_rss_for_news():
    """
    Query RSS feeds for news using rotation (one feed per call).
    
    Filters articles to current calendar day only.
    Returns immediately - scoring happens in background thread.
    
    Returns:
        dict: {
            'articles_found': int,
            'queued_for_scoring': int,
            'feeds_polled': int,
            'error': str or None
        }
    """
    global _current_feed_index, _query_count
    
    try:
        # Check if enabled
        if not ENABLE_RSS_NEWS:
            return {
                'articles_found': 0,
                'queued_for_scoring': 0,
                'feeds_polled': 0,
                'reason': 'disabled'
            }
        
        # Check dependencies
        if not FEEDPARSER_AVAILABLE:
            return {
                'articles_found': 0,
                'queued_for_scoring': 0,
                'feeds_polled': 0,
                'error': 'feedparser_not_available'
            }
        
        if not REQUESTS_AVAILABLE:
            return {
                'articles_found': 0,
                'queued_for_scoring': 0,
                'feeds_polled': 0,
                'error': 'requests_not_available'
            }
        
        # Check if feeds loaded
        if not _feeds:
            return {
                'articles_found': 0,
                'queued_for_scoring': 0,
                'feeds_polled': 0,
                'error': 'no_feeds_loaded'
            }
        
        _query_count += 1
        
        # Determine time window (current calendar day only)
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Select next feed in rotation
        if _current_feed_index >= len(_feeds):
            _current_feed_index = 0
        
        feed_config = _feeds[_current_feed_index]
        feed_url = feed_config['url']
        feed_source = feed_config.get('source', 'RSS')
        
        # Check if this feed was polled too recently
        last_polled = _feed_last_polled.get(feed_url, 0)
        time_since_last_poll = time.time() - last_polled
        
        if time_since_last_poll < PER_FEED_MIN_INTERVAL:
            # Skip this feed, move to next
            _current_feed_index += 1
            return {
                'articles_found': 0,
                'queued_for_scoring': 0,
                'feeds_polled': 0,
                'reason': f'feed_polled_recently ({time_since_last_poll:.1f}s ago)'
            }
        
        # Move to next feed for next call
        _current_feed_index += 1
        
        logger.info(
            f"RSSNEWS: 📰 Query #{_query_count}: Polling feed {feed_url[:60]}... "
            f"(source={feed_source}, window={today_start.isoformat()} to {now.isoformat()})"
        )
        
        # Fetch and parse feed
        try:
            response = requests.get(
                feed_url,
                timeout=REQUEST_TIMEOUT,
                headers={'User-Agent': USER_AGENT}
            )
            response.raise_for_status()
            
            # Update last polled time
            _feed_last_polled[feed_url] = time.time()
            
            # Parse feed
            feed = feedparser.parse(response.content)
            
            if feed.bozo and feed.bozo_exception:
                logger.warning(f"RSSNEWS: ⚠️ Feed parse warning for {feed_url[:60]}: {feed.bozo_exception}")
            
            entries = feed.entries if hasattr(feed, 'entries') else []
            
            logger.info(f"RSSNEWS: 📥 Fetched {len(entries)} entries from {feed_url[:60]}")
            
        except requests.Timeout:
            logger.warning(f"RSSNEWS: ⏰ Timeout fetching {feed_url[:60]}")
            return {
                'articles_found': 0,
                'queued_for_scoring': 0,
                'feeds_polled': 1,
                'error': 'timeout'
            }
        except requests.RequestException as e:
            logger.warning(f"RSSNEWS: ❌ Request error for {feed_url[:60]}: {e}")
            return {
                'articles_found': 0,
                'queued_for_scoring': 0,
                'feeds_polled': 1,
                'error': f'request_error: {e}'
            }
        except Exception as e:
            logger.error(f"RSSNEWS: ❌ Error fetching/parsing {feed_url[:60]}: {e}", exc_info=True)
            return {
                'articles_found': 0,
                'queued_for_scoring': 0,
                'feeds_polled': 1,
                'error': f'parse_error: {e}'
            }
        
        # Process entries
        articles_found = 0
        queued_count = 0
        
        for entry in entries:
            try:
                # Extract article fields with fallbacks
                headline = entry.get('title', '').strip()
                summary = entry.get('summary', entry.get('description', '')).strip()
                url = entry.get('link', '').strip()
                
                # Skip if missing critical fields
                if not headline or not url:
                    continue
                
                # Parse published date
                published_str = entry.get('published', entry.get('updated', ''))
                published_at = parse_rss_date(published_str)
                
                if not published_at:
                    # No date available, skip
                    logger.debug(f"RSSNEWS: ⏭️ Skipping article with no date: {headline[:50]}")
                    continue
                
                # Filter to current day only
                if published_at < today_start or published_at > now:
                    continue
                
                articles_found += 1
                
                # Check if already processed
                if is_article_processed(url):
                    continue
                
                # Build article data
                article_data = {
                    'symbol': 'QLD',  # Default to QLD for general market news
                    'headline': headline,
                    'summary': summary if summary else headline,
                    'url': url,
                    'published': published_at.timestamp(),
                    'source': feed_source
                }
                
                # Queue for scoring (non-blocking)
                try:
                    article_to_score_queue.put_nowait(article_data)
                    queued_count += 1
                    logger.info(f"RSSNEWS: ✅ Queued article: {headline[:60]}...")
                except queue.Full:
                    logger.warning(f"RSSNEWS: ⚠️ Score queue full, dropping article: {headline[:60]}")
                    break  # Stop processing this feed
            
            except Exception as e:
                logger.error(f"RSSNEWS: ❌ Error processing entry: {e}", exc_info=True)
                continue
        
        logger.info(
            f"RSSNEWS: 📊 Summary: found={articles_found}, queued={queued_count} "
            f"from {feed_url[:60]}"
        )
        
        return {
            'articles_found': articles_found,
            'queued_for_scoring': queued_count,
            'feeds_polled': 1,
            'error': None
        }
    
    except Exception as e:
        logger.error(f"RSSNEWS: ❌ Unexpected error in query_rss_for_news: {e}", exc_info=True)
        return {
            'articles_found': 0,
            'queued_for_scoring': 0,
            'feeds_polled': 0,
            'error': f'unexpected: {e}'
        }


# ============================================================================
# GET SCORED ARTICLES (for real-time sentiment integration)
# ============================================================================

def get_scored_articles():
    """
    Get all scored articles from queue.
    
    Returns:
        list: List of impact floats (sentiment contributions)
    """
    impacts = []
    
    try:
        while not scored_article_queue.empty():
            try:
                impact = scored_article_queue.get_nowait()
                impacts.append(impact)
            except queue.Empty:
                break
    except Exception as e:
        logger.error(f"RSSNEWS: Error getting scored articles: {e}")
    
    return impacts


# ============================================================================
# INITIALIZATION
# ============================================================================

def initialize():
    """
    Initialize RSS integration.
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Check if enabled
        if not ENABLE_RSS_NEWS:
            logger.info("RSSNEWS: RSS news integration is DISABLED (set ENABLE_RSS_NEWS=True to enable)")
            return False
        
        if not FEEDPARSER_AVAILABLE:
            logger.warning("RSSNEWS: feedparser library not available - run: pip install feedparser")
            return False
        
        if not REQUESTS_AVAILABLE:
            logger.warning("RSSNEWS: requests library not available (should be installed)")
            return False
        
        # Load RSS feeds
        feeds = load_rss_feeds()
        if not feeds:
            logger.error("RSSNEWS: No RSS feeds loaded")
            return False
        
        # Start scoring thread
        start_scoring_thread()
        
        # Start database save worker thread
        start_save_worker_thread()
        
        logger.info("=" * 60)
        logger.info("RSSNEWS: RSS Real-Time News Integration INITIALIZED")
        logger.info(f"  - Feeds loaded: {len(feeds)}")
        logger.info(f"  - Poll interval: {RSS_TICK_INTERVAL} second(s)")
        logger.info(f"  - Min per-feed interval: {PER_FEED_MIN_INTERVAL} seconds")
        logger.info(f"  - Threads: scoring + save worker running")
        logger.info("=" * 60)
        
        return True
    
    except Exception as e:
        logger.error(f"RSSNEWS: Error initializing RSS integration: {e}", exc_info=True)
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
    print("Testing RSS Real-Time News Integration")
    print("=" * 60)
    
    # Initialize
    if initialize():
        print("✓ Initialization successful\n")
        
        # Simulate 3 polling cycles
        for i in range(3):
            print(f"\n--- Poll Cycle {i+1} ---")
            result = query_rss_for_news()
            
            print(f"Articles found: {result.get('articles_found', 0)}")
            print(f"Queued for scoring: {result.get('queued_for_scoring', 0)}")
            print(f"Feeds polled: {result.get('feeds_polled', 0)}")
            
            if result.get('error'):
                print(f"ERROR: {result['error']}")
            
            # Check for scored articles
            time.sleep(2)  # Give scoring thread time to work
            impacts = get_scored_articles()
            if impacts:
                print(f"Scored articles ready: {len(impacts)}")
                for idx, impact in enumerate(impacts, 1):
                    print(f"  Article {idx}: impact={impact:+.2f}")
            
            time.sleep(1)
        
        # Stop
        stop_scoring_thread()
        stop_save_worker_thread()
        print("\n✓ Test completed")
    else:
        print("✗ Initialization failed")

