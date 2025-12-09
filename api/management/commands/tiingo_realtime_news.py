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

# Major market indices and ETFs for broad market news
MARKET_INDICES = [
    'QQQ',   # NASDAQ-100 ETF
    'SPY',   # S&P 500 ETF
    'DIA',   # Dow Jones Industrial Average ETF
    'IWM',   # Russell 2000 ETF (small caps)
    'VTI',   # Total Stock Market ETF
    'VOO',   # Vanguard S&P 500 ETF
]

# Sector ETFs for comprehensive sector coverage
SECTOR_ETFS = [
    'XLK',   # Technology Select Sector
    'XLF',   # Financial Select Sector
    'XLE',   # Energy Select Sector
    'XLV',   # Health Care Select Sector
    'XLY',   # Consumer Discretionary Select Sector
    'XLP',   # Consumer Staples Select Sector
    'XLI',   # Industrial Select Sector
    'XLB',   # Materials Select Sector
    'XLRE',  # Real Estate Select Sector
    'XLU',   # Utilities Select Sector
    'XLC',   # Communication Services Select Sector
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
article_to_score_queue = queue.Queue(maxsize=500)  # Increased to match database save queue capacity
scored_article_queue = queue.Queue()
database_save_queue = queue.Queue(maxsize=500)  # Articles to save to database (high limit)

# Scoring thread
_scoring_thread = None
_scoring_thread_running = False

# Database save worker thread (NEW)
_save_worker_thread = None
_save_worker_running = False


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
        article_data: Dict with article info (headline, summary, url, symbol, published, source)
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

            logger.info(f"NEWSSAVING: 📥 ENTRY attempt={attempt+1}/{max_retries} source=Tiingo")

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
                url = f"https://tiingo.com/article/{ticker_symbol}/{int(time.time())}"
                logger.warning(f"NEWSSAVING: ⚠️ Missing URL, generated: {url}")
            url = safe_url(url, max_length=500)
            
            # Get source name and build source field with proper truncation (max 100 chars total)
            source_name = str(article_data.get('source', 'unknown')).strip()
            if not source_name:
                source_name = 'unknown'
            
            # Sanitize source name
            source_name = sanitize_text(source_name, field_name="source_name", max_length=None)
            
            # Build source field with proper truncation
            source_prefix = "Tiingo (RT) - "  # 15 chars
            max_source_name_length = 100 - len(source_prefix)
            if len(source_name) > max_source_name_length:
                source_name = source_name[:max_source_name_length]
                logger.debug(f"NEWSSAVING: ✂️ Truncated source name to {max_source_name_length} chars")
            source = f"{source_prefix}{source_name}"
            
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
                    published_str = article_data['published']
                    published_at = parse_datetime(published_str)
                    
                    # Ensure timezone-aware
                    if published_at and timezone.is_naive(published_at):
                        published_at = published_at.replace(tzinfo=dt_timezone.utc)
                        logger.debug(f"NEWSSAVING: 🕐 Made datetime timezone-aware")
                        
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
            
            # Determine article type
            article_type = 'market' if ticker_symbol == 'MARKET' else 'company'

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
                    'source': source,
                    'url': url,
                    'published_at': published_at,
                    'article_type': article_type,
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

        # Tiered impact caps based on sentiment strength (reduces noise, amplifies strong signals)
        abs_sentiment = abs(sentiment)
        if abs_sentiment < 0.2:
            # Filter out weak/neutral sentiment (noise reduction)
            impact = 0.0
            logger.info(f"Scored {symbol} article: sentiment={sentiment:+.2f}, impact={impact:+.2f} (filtered: weak)")
        elif abs_sentiment < 0.4:
            # Weak signal
            impact = max(-2, min(2, impact))
            logger.info(f"Scored {symbol} article: sentiment={sentiment:+.2f}, impact={impact:+.2f} (weak)")
        elif abs_sentiment < 0.6:
            # Moderate signal
            impact = max(-5, min(5, impact))
            logger.info(f"Scored {symbol} article: sentiment={sentiment:+.2f}, impact={impact:+.2f} (moderate)")
        elif abs_sentiment < 0.8:
            # Strong signal
            impact = max(-15, min(15, impact))
            logger.info(f"Scored {symbol} article: sentiment={sentiment:+.2f}, impact={impact:+.2f} (strong)")
        else:
            # Critical news (very strong sentiment)
            impact = max(-25, min(25, impact))
            logger.info(f"Scored {symbol} article: sentiment={sentiment:+.2f}, impact={impact:+.2f} (critical)")

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

            # ⚡ PRIORITY 1: Put impact in scored queue IMMEDIATELY (sentiment update)
            scored_article_queue.put(impact)
            logger.info(f"TIINGO_SCORING: ✅ Scored and queued impact: {article_data['symbol']} impact={impact:+.2f}")

            # ⚡ PRIORITY 2: Queue for database save (async, non-blocking)
            try:
                save_job = {
                    'article_data': article_data,
                    'impact': impact,
                    'queued_time': timezone.now(),
                    'article_hash': get_article_hash(article_data['url'])
                }
                database_save_queue.put_nowait(save_job)
                logger.info(f"TIINGO_SAVEQUEUE: 📝 Queued for save: {article_data['symbol']} hash={save_job['article_hash'][:8]}")
            except queue.Full:
                logger.error(f"TIINGO_SAVEQUEUE: ❌ QUEUE_FULL (500 items) - cannot queue save for {article_data['symbol']}")

            # Mark as processed
            mark_article_processed(article_data['url'])

        except Exception as e:
            logger.error(f"Error in Tiingo scoring worker: {e}", exc_info=True)

    logger.info("Tiingo article scoring thread stopped")


def database_save_worker():
    """
    Dedicated background thread for database saves (Tiingo).
    Processes saves from queue with deadline enforcement and comprehensive logging.
    """
    global _save_worker_running
    
    logger.info("=" * 80)
    logger.info("TIINGO DATABASE SAVE WORKER: 🚀 STARTED")
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
                f"TIINGO_SAVEQUEUE: 🔄 Processing save job: hash={article_hash[:8]} "
                f"ticker={article_data.get('symbol')} wait_time={wait_time:.2f}s"
            )
            
            # Check deadline (60 seconds max)
            deadline_seconds = 60
            if wait_time > deadline_seconds:
                saves_deadline_exceeded += 1
                logger.error(
                    f"TIINGO_SAVEQUEUE: ⏰ DEADLINE_EXCEEDED hash={article_hash[:8]} "
                    f"wait_time={wait_time:.1f}s > deadline={deadline_seconds}s "
                    f"ticker={article_data.get('symbol')} "
                    f"total_exceeded={saves_deadline_exceeded}"
                )
                database_save_queue.task_done()
                continue
            
            # Attempt save with fast retries
            remaining_time = deadline_seconds - wait_time
            max_attempts = 3
            retry_delay = 0.1  # Start with 100ms
            save_succeeded = False
            
            for attempt in range(max_attempts):
                try:
                    logger.info(
                        f"TIINGO_SAVEQUEUE: 💾 SAVE_ATTEMPT attempt={attempt+1}/{max_attempts} "
                        f"hash={article_hash[:8]} ticker={article_data.get('symbol')} "
                        f"remaining_time={remaining_time:.2f}s"
                    )
                    
                    # Call the existing save function
                    article = save_article_to_db(article_data, impact)
                    
                    if article:
                        total_time = (timezone.now() - queued_time).total_seconds()
                        saves_succeeded += 1
                        logger.info(
                            f"TIINGO_SAVEQUEUE: ✅ SAVE_SUCCESS hash={article_hash[:8]} "
                            f"id={article.id} ticker={article_data.get('symbol')} "
                            f"total_time={total_time:.2f}s attempt={attempt+1} "
                            f"success_count={saves_succeeded}"
                        )
                        save_succeeded = True
                        break
                    else:
                        logger.warning(
                            f"TIINGO_SAVEQUEUE: ⚠️ SAVE_RETURNED_NONE attempt={attempt+1}/{max_attempts} "
                            f"hash={article_hash[:8]}"
                        )
                        
                except Exception as e:
                    logger.error(
                        f"TIINGO_SAVEQUEUE: ❌ SAVE_EXCEPTION attempt={attempt+1}/{max_attempts} "
                        f"hash={article_hash[:8]} ticker={article_data.get('symbol')} "
                        f"error={type(e).__name__}: {str(e)[:100]}"
                    )
                
                # Check if we have time to retry
                remaining_time = deadline_seconds - (timezone.now() - queued_time).total_seconds()
                if remaining_time <= 0:
                    logger.error(f"TIINGO_SAVEQUEUE: ⏰ NO_TIME_FOR_RETRY hash={article_hash[:8]}")
                    break
                
                # Retry with exponential backoff (but respect deadline)
                if attempt < max_attempts - 1:
                    sleep_time = min(retry_delay, remaining_time - 0.1)  # Leave 100ms buffer
                    if sleep_time > 0:
                        logger.info(f"TIINGO_SAVEQUEUE: 🔄 RETRY_DELAY sleep={sleep_time:.2f}s attempt={attempt+1}")
                        time.sleep(sleep_time)
                        retry_delay = min(retry_delay * 1.5, 2.0)  # Cap at 2s
            
            # Final status
            if not save_succeeded:
                saves_failed += 1
                total_time = (timezone.now() - queued_time).total_seconds()
                logger.error(
                    f"TIINGO_SAVEQUEUE: ❌ SAVE_FAILED_ALL_ATTEMPTS hash={article_hash[:8]} "
                    f"ticker={article_data.get('symbol')} "
                    f"attempts={max_attempts} total_time={total_time:.2f}s "
                    f"failed_count={saves_failed}"
                )
            
            # Log queue status periodically
            queue_size = database_save_queue.qsize()
            if queue_size > 100:
                logger.warning(
                    f"TIINGO_SAVEQUEUE: ⚠️ QUEUE_LARGE size={queue_size} "
                    f"success={saves_succeeded} failed={saves_failed} exceeded={saves_deadline_exceeded}"
                )
            
            database_save_queue.task_done()
            
        except Exception as e:
            logger.error(
                f"TIINGO_SAVEQUEUE: ❌ WORKER_ERROR unexpected error in save worker: {e}",
                exc_info=True
            )
    
    # Thread stopping
    logger.info("=" * 80)
    logger.info(
        f"TIINGO DATABASE SAVE WORKER: 🛑 STOPPED | "
        f"Success: {saves_succeeded} | Failed: {saves_failed} | Deadline exceeded: {saves_deadline_exceeded}"
    )
    logger.info("=" * 80)


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


def start_save_worker_thread():
    """Start the dedicated database save worker thread."""
    global _save_worker_thread, _save_worker_running
    
    try:
        if _save_worker_thread and _save_worker_thread.is_alive():
            logger.warning("TIINGO_SAVEQUEUE: ⚠️ Save worker thread already running")
            return
        
        _save_worker_running = True
        _save_worker_thread = threading.Thread(target=database_save_worker, daemon=True)
        _save_worker_thread.start()
        logger.info("TIINGO_SAVEQUEUE: 🚀 Save worker thread started")
    
    except Exception as e:
        logger.error(f"TIINGO_SAVEQUEUE: ❌ Error starting save worker thread: {e}", exc_info=True)


def stop_save_worker_thread():
    """Stop the database save worker thread."""
    global _save_worker_running
    
    try:
        logger.info("TIINGO_SAVEQUEUE: 🛑 Stopping save worker thread...")
        _save_worker_running = False
        
        # Wait for queue to drain (max 5 seconds)
        if _save_worker_thread:
            try:
                database_save_queue.join()
                logger.info("TIINGO_SAVEQUEUE: ✅ Queue drained successfully")
            except Exception as e:
                logger.warning(f"TIINGO_SAVEQUEUE: ⚠️ Error draining queue: {e}")
            
            _save_worker_thread.join(timeout=5.0)
            logger.info("TIINGO_SAVEQUEUE: 🛑 Save worker thread stopped")
    
    except Exception as e:
        logger.error(f"TIINGO_SAVEQUEUE: ❌ Error stopping save worker thread: {e}", exc_info=True)


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

        # Determine time window (current calendar day only - start of today to now)
        now = timezone.now()
        # Start of current calendar day (00:00:00) in UTC
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_time = today_start
        end_time = now
        
        # For Tiingo News API: Query only current calendar day
        # API uses date-only format, so we query today then filter by publishedDate
        start_date_for_api = now.date()  # Today only
        end_date_for_api = now.date()  # Today only

        # Extra logging about the computed time window
        logger.info(
            "Tiingo query window: "
            f"start={start_time.isoformat()} (start of today), "
            f"end={end_time.isoformat()}, "
            f"delta_sec={(end_time - start_time).total_seconds():.1f}"
        )

        # Format dates for Tiingo API (date-only format required)
        start_date_str = start_date_for_api.strftime('%Y-%m-%d')
        end_date_str = end_date_for_api.strftime('%Y-%m-%d')
        
        # For display/logging, show the actual time window we want
        start_datetime_str = start_time.strftime('%Y-%m-%dT%H:%M:%SZ')
        end_datetime_str = end_time.strftime('%Y-%m-%dT%H:%M:%SZ')

        msg1 = f"📰 TIINGO QUERY #{_query_count + 1} START: Target window {start_datetime_str} to {end_datetime_str}"
        msg2 = f"   API query: NO date parameters (getting latest news, limit=1000)"
        msg3 = f"   Will filter by publishedDate to get articles from current calendar day only"
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
                queued_count += process_news_articles(news_data, 'ticker_query', start_time, end_time)
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

        # Query 2: Major market indices (QQQ, SPY, DIA, etc.)
        try:
            msg = f"   → Querying {len(MARKET_INDICES)} market indices: {', '.join(MARKET_INDICES)} (limit=1000)"
            logger.info(msg)
            print(msg)  # Ensure appears in Railway logs

            # Query all major market indices for broad market news
            market_news = client.get_news(
                tickers=MARKET_INDICES,  # All major market ETFs
                limit=1000  # Maximum articles for market news
            )

            market_queued = 0
            if market_news and isinstance(market_news, list):
                total_articles_found += len(market_news)
                market_queued = process_news_articles(market_news, 'market_query', start_time, end_time)
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

        # Query 3: Sector ETFs for comprehensive sector coverage
        try:
            msg = f"   → Querying {len(SECTOR_ETFS)} sector ETFs: {', '.join(SECTOR_ETFS[:5])}... (limit=1000)"
            logger.info(msg)
            print(msg)  # Ensure appears in Railway logs

            # Query all sector ETFs for sector-specific news
            sector_news = client.get_news(
                tickers=SECTOR_ETFS,  # All major sector ETFs
                limit=1000  # Maximum articles for sector news
            )

            sector_queued = 0
            if sector_news and isinstance(sector_news, list):
                total_articles_found += len(sector_news)
                sector_queued = process_news_articles(sector_news, 'sector_query', start_time, end_time)
                queued_count += sector_queued
                msg = f"   ✓ Sector query: {len(sector_news)} articles found, {sector_queued} new articles queued"
                logger.info(msg)
                print(msg)  # Ensure appears in Railway logs
                if len(sector_news) > 0:
                    msg = f"      Sample: {sector_news[0].get('title', 'N/A')[:80]}..."
                    logger.info(msg)
                    print(msg)  # Ensure appears in Railway logs
            else:
                msg = (
                    f"   ✓ Sector query: No articles returned "
                    f"(raw_type={type(sector_news).__name__})"
                )
                logger.info(msg)
                print(msg)  # Ensure appears in Railway logs

        except Exception as e:
            # Sector query failure is non-critical
            msg = f"   ✗ Sector query failed (non-critical): {e}"
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
    filtered_by_duplicate = 0
    filtered_by_missing_data = 0
    filtered_by_invalid_url = 0
    filtered_by_no_published_date = 0

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
                    filtered_by_missing_data += 1
                    logger.debug(f"Skipping article with missing url or title")
                    continue

                # Validate URL format
                if not url.startswith('http'):
                    filtered_by_invalid_url += 1
                    logger.debug(f"Skipping article with invalid URL: {url[:50]}")
                    continue

                # Filter by current calendar day (date comparison, not datetime)
                published_date_str = article.get('publishedDate', '')
                if start_time and end_time:
                    if published_date_str:
                        try:
                            from django.utils.dateparse import parse_datetime
                            published_at = parse_datetime(published_date_str)
                            if published_at:
                                # Make timezone-aware if naive
                                if timezone.is_naive(published_at):
                                    published_at = published_at.replace(tzinfo=dt_timezone.utc)
                                
                                # Filter: only include articles from current calendar day (date comparison)
                                # Compare dates, not datetimes, to avoid timezone issues
                                published_date = published_at.date()
                                today_date = end_time.date()  # Use end_time (now) to get today's date
                                
                                if published_date != today_date:
                                    filtered_by_time += 1
                                    # Log first few filtered articles for debugging
                                    if filtered_by_time <= 3:
                                        logger.info(
                                            f"      ⏰ Filtered by date: {title[:60]}... "
                                            f"(published: {published_date}, today: {today_date})"
                                        )
                                    continue
                        except Exception as e:
                            logger.debug(f"Error parsing publishedDate '{published_date_str}': {e}")
                    else:
                        # No publishedDate - count but don't filter (allow through)
                        filtered_by_no_published_date += 1
                        if filtered_by_no_published_date <= 3:
                            logger.info(f"      ⚠️  Article missing publishedDate: {title[:60]}...")

                # Skip if already processed
                if is_article_processed(url):
                    filtered_by_duplicate += 1
                    # Log first few duplicates for debugging
                    if filtered_by_duplicate <= 3:
                        logger.info(f"      🔄 Duplicate (already processed): {title[:60]}...")
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
                    logger.warning(f"      ⚠️  Queue FULL (500 items), skipping this article (queue will drain)")
                    # Continue processing - queue drains asynchronously, might have space for next article
                    continue

            except Exception as e:
                logger.error(f"Error processing individual article: {e}")
                continue

        # Summary logging for this batch
        summary_msg = (
            f"Processed Tiingo articles batch: type={query_type}, "
            f"input={total_input}, "
            f"queued={queued_count}, "
            f"filtered: time={filtered_by_time}, duplicate={filtered_by_duplicate}, "
            f"missing_data={filtered_by_missing_data}, invalid_url={filtered_by_invalid_url}, "
            f"no_published_date={filtered_by_no_published_date}"
        )
        logger.info(summary_msg)
        
        # Also print to stdout for visibility in logs
        if queued_count == 0 and total_input > 0:
            print(f"   ⚠️  {query_type}: {total_input} articles found but 0 queued. "
                  f"Filtered: {filtered_by_time} by time, {filtered_by_duplicate} duplicates, "
                  f"{filtered_by_missing_data} missing data, {filtered_by_invalid_url} invalid URL")
        
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
            'save_queue_size': database_save_queue.qsize(),
            'scoring_thread_alive': _scoring_thread.is_alive() if _scoring_thread else False,
            'save_worker_alive': _save_worker_thread.is_alive() if _save_worker_thread else False
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
        
        # Start database save worker thread
        start_save_worker_thread()

        logger.info("=" * 60)
        logger.info("Tiingo Real-Time News Integration INITIALIZED")
        logger.info(f"  - Top tickers: {len(TOP_TICKERS)}")
        logger.info(f"  - Poll interval: {POLL_INTERVAL} seconds")
        logger.info(f"  - Time window: {TIME_WINDOW_HOURS} hours")
        logger.info(f"  - Threads: scoring + save worker running")
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
