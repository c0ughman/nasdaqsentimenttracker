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
from datetime import datetime, timedelta, timezone as dt_timezone
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

# Rate limiting (Finnhub free tier: 60 calls/minute)
# We'll be conservative and target 50 calls/minute with 1.2 second spacing
MIN_SECONDS_BETWEEN_CALLS = 1.2  # Ensures we stay well under 60/minute (50 calls/minute)
MAX_CALLS_PER_MINUTE = 50  # Conservative limit

# Rotation state
_current_index = 0
_last_query_time = None
_finnhub_client = None

# Rate limit tracking
_api_calls_this_minute = []  # List of timestamps for calls in current minute
_consecutive_429_errors = 0  # Track consecutive rate limit errors

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
        
        # Clamp to safe range
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
    """
    Clean and validate URL for database storage.
    
    Args:
        url: URL string to clean
        max_length: Maximum length
    
    Returns:
        Cleaned URL string
    """
    if not url:
        return ""
    
    original = url
    
    # Strip whitespace
    url = url.strip()
    
    # Remove control characters and newlines
    url = ''.join(char for char in url if ord(char) >= 32)
    
    # Replace spaces with %20 (basic encoding)
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
    
    ULTRA-ROBUST VERSION: Handles ALL possible save errors with comprehensive logging.
    Every log includes "NEWSSAVING" keyword for easy searching.

    Args:
        article_data: Dict with article info (headline, summary, url, symbol, published)
        impact: Calculated sentiment impact
    
    Returns:
        NewsArticle instance or None only if all retries fail
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

            logger.info(f"NEWSSAVING: 📥 ENTRY attempt={attempt+1}/{max_retries} source=Finnhub")

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
            if not headline or not headline.replace(' ', ''):  # Check for whitespace-only
                headline = f"[No headline] Article from {ticker_symbol}"
                logger.warning(f"NEWSSAVING: ⚠️ Missing/empty headline, using fallback: {headline}")
            
            # Sanitize headline (remove null bytes, control chars)
            headline = sanitize_text(headline, field_name="headline", max_length=500)
            
            if not headline:  # If sanitization resulted in empty string
                headline = f"[Sanitized empty] Article from {ticker_symbol}"
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
                url = f"https://finnhub.io/article/{ticker_symbol}/{int(time.time())}"
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
                    'source': 'Finnhub (Real-Time)',
                    'url': url,
                    'published_at': published_at,
                    'article_type': 'company',
                    'base_sentiment': safe_sentiment,
                    'surprise_factor': 1.0,
                    'novelty_score': 1.0,
                    'source_credibility': 0.8,
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
            # Constraint violation (unique, foreign key, etc.) - retry
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
                    f"ticker={ticker_symbol if 'ticker_symbol' in locals() else 'unknown'} error={e}"
                )
                return None

        except OperationalError as e:
            # Database connection, deadlock, timeout - retry
            error_msg = str(e).lower()
            if 'deadlock' in error_msg:
                error_type = "DEADLOCK"
            elif 'timeout' in error_msg or 'timed out' in error_msg:
                error_type = "TIMEOUT"
            elif 'connection' in error_msg:
                error_type = "CONNECTION"
            elif 'disk' in error_msg or 'space' in error_msg:
                error_type = "DISK_FULL"
            else:
                error_type = "OPERATIONAL"
            
            logger.warning(
                f"NEWSSAVING: 🔄 {error_type} attempt={attempt + 1}/{max_retries} "
                f"hash={article_hash[:8] if 'article_hash' in locals() else 'unknown'} "
                f"retrying_in={retry_delay}s error={e}"
            )
            
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2
                continue
            else:
                logger.error(
                    f"NEWSSAVING: ❌ FAILED_{error_type} after {max_retries} attempts "
                    f"hash={article_hash[:8] if 'article_hash' in locals() else 'unknown'} "
                    f"ticker={ticker_symbol if 'ticker_symbol' in locals() else 'unknown'} error={e}",
                    exc_info=True
                )
                return None

        except DatabaseError as e:
            # General database errors (encoding, data type, etc.)
            logger.error(
                f"NEWSSAVING: ❌ DATABASE_ERROR attempt={attempt + 1}/{max_retries} "
                f"hash={article_hash[:8] if 'article_hash' in locals() else 'unknown'} "
                f"ticker={ticker_symbol if 'ticker_symbol' in locals() else 'unknown'} error={e}",
                exc_info=True
            )
            
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2
                continue
            else:
                return None

        except MemoryError as e:
            # Out of memory (very rare, but possible with huge articles)
            logger.error(
                f"NEWSSAVING: ❌ MEMORY_ERROR attempt={attempt + 1}/{max_retries} "
                f"headline_len={len(headline) if 'headline' in locals() else 0} "
                f"summary_len={len(summary) if 'summary' in locals() else 0} error={e}"
            )
            return None  # Don't retry memory errors

        except Exception as e:
            # Unexpected error - catch all
            logger.error(
                f"NEWSSAVING: ❌ UNEXPECTED_ERROR attempt={attempt + 1}/{max_retries} "
                f"type={type(e).__name__} "
                f"hash={article_hash[:8] if 'article_hash' in locals() else 'unknown'} "
                f"ticker={ticker_symbol if 'ticker_symbol' in locals() else 'unknown'} "
                f"headline={headline[:50] if 'headline' in locals() else 'N/A'}... "
                f"error={e}",
                exc_info=True
            )
            
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2
                continue
            else:
                logger.error(
                    f"NEWSSAVING: ❌ FAILED_ALL_RETRIES after {max_retries} attempts "
                    f"hash={article_hash[:8] if 'article_hash' in locals() else 'unknown'}"
                )
                return None
    
    # Should never reach here, but just in case
    logger.error(
        f"NEWSSAVING: ❌ FAILED_UNEXPECTED_EXIT hash={article_hash[:8] if 'article_hash' in locals() else 'unknown'}"
    )
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
    global _current_index, _last_query_time, _api_calls_this_minute, _consecutive_429_errors
    
    # Check if we're in rest period (last 10 seconds of minute)
    current_second = timezone.now().second
    if current_second >= WORK_SECONDS:
        return {
            'symbol': None,
            'articles_found': 0,
            'queued_for_scoring': 0,
            'reason': 'rest_period'
        }
    
    # Enhanced rate limiting
    now = time.time()
    
    # Clean up old calls (remove calls older than 60 seconds)
    _api_calls_this_minute = [t for t in _api_calls_this_minute if now - t < 60]
    
    # Check if we've hit our per-minute limit
    if len(_api_calls_this_minute) >= MAX_CALLS_PER_MINUTE:
        logger.warning(
            f"Rate limit: {len(_api_calls_this_minute)} calls in last 60s "
            f"(max={MAX_CALLS_PER_MINUTE}). Skipping this query."
        )
        return {
            'symbol': None,
            'articles_found': 0,
            'queued_for_scoring': 0,
            'reason': 'rate_limit_per_minute'
        }
    
    # Enforce minimum time between calls
    if _last_query_time and (now - _last_query_time) < MIN_SECONDS_BETWEEN_CALLS:
        time_to_wait = MIN_SECONDS_BETWEEN_CALLS - (now - _last_query_time)
        return {
            'symbol': None,
            'articles_found': 0,
            'queued_for_scoring': 0,
            'reason': 'rate_limit_spacing',
            'wait_time': time_to_wait
        }
    
    # If we've had consecutive 429 errors, back off exponentially
    if _consecutive_429_errors > 0:
        backoff_time = min(60, 2 ** _consecutive_429_errors)  # Cap at 60 seconds
        if _last_query_time and (now - _last_query_time) < backoff_time:
            return {
                'symbol': None,
                'articles_found': 0,
                'queued_for_scoring': 0,
                'reason': 'backoff_after_429',
                'backoff_seconds': backoff_time,
                'consecutive_errors': _consecutive_429_errors
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
    
    try:
        # Record this API call
        _api_calls_this_minute.append(now)
        _last_query_time = now
        
        # Query Finnhub for company news (last 1 day)
        today = datetime.now()
        yesterday = today - timedelta(days=1)
        
        articles = client.company_news(
            symbol,
            _from=yesterday.strftime('%Y-%m-%d'),
            to=today.strftime('%Y-%m-%d')
        )
        
        # Reset consecutive errors on success
        _consecutive_429_errors = 0

        # Discovery-level logging for visibility into each API call
        total_returned = len(articles) if isinstance(articles, list) else 0
        logger.info(
            f"FINNHUB QUERY: symbol={symbol}, "
            f"from={yesterday.strftime('%Y-%m-%d')} to={today.strftime('%Y-%m-%d')}, "
            f"articles_returned={total_returned}, "
            f"api_calls_last_60s={len(_api_calls_this_minute)}"
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
        # Check if this is a 429 rate limit error
        error_str = str(e)
        if '429' in error_str or 'rate limit' in error_str.lower() or 'API limit reached' in error_str:
            _consecutive_429_errors += 1
            logger.error(
                f"⚠️ RATE LIMIT ERROR (429) for {symbol}: {e}\n"
                f"   Consecutive 429 errors: {_consecutive_429_errors}\n"
                f"   API calls in last 60s: {len(_api_calls_this_minute)}\n"
                f"   Next backoff: {min(60, 2 ** _consecutive_429_errors)} seconds"
            )
            return {
                'symbol': symbol,
                'articles_found': 0,
                'queued_for_scoring': 0,
                'error': 'rate_limit_429',
                'consecutive_errors': _consecutive_429_errors,
                'calls_last_minute': len(_api_calls_this_minute)
            }
        else:
            # Other error - reset consecutive 429 counter
            _consecutive_429_errors = 0
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

