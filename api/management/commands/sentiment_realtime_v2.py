"""
Real-Time Sentiment Scoring System v2

UNIFIED SCORE ARCHITECTURE:
- ONE score that evolves continuously
- Updated every minute: Full analysis (all components)
- Updated every second: Incremental updates (news decay, technical micro, Finnhub)
- Next minute uses latest second as starting point

BACKWARDS COMPATIBILITY:
- Falls back to AnalysisRun if SecondSnapshot unavailable
- Does not break existing run_nasdaq_sentiment.py
- Extensive error logging and graceful degradation
"""

import logging
import numpy as np
import threading
import queue
from datetime import datetime, timedelta
from django.utils import timezone
from django.core.cache import cache

from api.models import AnalysisRun, Ticker, SecondSnapshot

logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURATION
# ============================================================================

# Decay rate (applied per second, NOT at minute boundary)
MINUTE_DECAY_RATE = 0.0383
SECOND_DECAY_RATE = MINUTE_DECAY_RATE / 60  # ~0.000638

# Technical score blending (weighted blend)
TECHNICAL_BASE_WEIGHT = 0.8  # 80% from base/macro
TECHNICAL_MICRO_WEIGHT = 0.2  # 20% from micro momentum

# Composite weights (MUST match run_nasdaq_sentiment.py)
# News: 45%, Social: 20%, Technical: 15%, Analyst: 10%, VIX: 10%
WEIGHT_NEWS = 0.45
WEIGHT_REDDIT = 0.20
WEIGHT_TECHNICAL = 0.15
WEIGHT_ANALYST = 0.10
WEIGHT_VIX = 0.10

# Macro technical cache duration
MACRO_CACHE_DURATION = 60  # seconds

# OpenAI article scoring queue (for threading)
article_queue = queue.Queue()
scored_articles = queue.Queue()


# ============================================================================
# CACHE
# ============================================================================

_macro_technical_cache = {
    'value': 0.0,
    'timestamp': None
}


# ============================================================================
# HELPER: Get Starting Point Scores
# ============================================================================

def get_base_scores(ticker_symbol='QLD'):
    """
    Get base scores to start from.
    
    Priority:
    1. Latest SecondSnapshot (if exists and recent)
    2. Latest AnalysisRun (fallback)
    
    Returns:
        dict: {
            'news': float,
            'reddit': float,
            'technical': float,
            'analyst': float,
            'composite': float,
            'source': str  # 'second_snapshot' or 'analysis_run'
        }
    """
    try:
        ticker = Ticker.objects.get(symbol=ticker_symbol)
        
        # Try SecondSnapshot first (preferred)
        latest_snapshot = SecondSnapshot.objects.filter(
            ticker=ticker
        ).order_by('-timestamp').first()
        
        if latest_snapshot:
            age_seconds = (timezone.now() - latest_snapshot.timestamp).total_seconds()
            
            # If snapshot is recent (< 2 minutes old), use it
            if age_seconds < 120:
                # Get reddit/analyst from corresponding AnalysisRun
                analysis_run = AnalysisRun.objects.filter(
                    ticker=ticker
                ).order_by('-timestamp').first()
                
                reddit_score = float(analysis_run.reddit_sentiment) if analysis_run and analysis_run.reddit_sentiment else 0.0
                analyst_score = float(analysis_run.analyst_recommendations_score) if analysis_run and analysis_run.analyst_recommendations_score else 0.0

                # Calculate VIX inverse score from VXN index
                vix_score = 0.0
                if analysis_run and analysis_run.vxn_index:
                    vxn = float(analysis_run.vxn_index)
                    if vxn < 15:
                        vix_score = 50.0
                    elif vxn < 20:
                        vix_score = 25.0
                    elif vxn < 25:
                        vix_score = 0.0
                    elif vxn < 30:
                        vix_score = -25.0
                    else:
                        vix_score = -50.0

                logger.info(f"Using SecondSnapshot from {age_seconds:.1f}s ago as base")

                return {
                    'news': float(latest_snapshot.news_score_cached) if latest_snapshot.news_score_cached else 0.0,
                    'reddit': reddit_score,
                    'technical': float(latest_snapshot.technical_score_cached) if latest_snapshot.technical_score_cached else 0.0,
                    'analyst': analyst_score,
                    'vix_inverse': vix_score,
                    'composite': float(latest_snapshot.composite_score) if latest_snapshot.composite_score else 0.0,
                    'source': 'second_snapshot',
                    'timestamp': latest_snapshot.timestamp
                }
        
        # Fallback to AnalysisRun
        latest_run = AnalysisRun.objects.filter(ticker=ticker).order_by('-timestamp').first()
        
        if not latest_run:
            logger.warning(f"No data found for {ticker_symbol}, returning zeros")
            return {
                'news': 0.0,
                'reddit': 0.0,
                'technical': 0.0,
                'analyst': 0.0,
                'vix_inverse': 0.0,
                'composite': 0.0,
                'source': 'none',
                'timestamp': timezone.now()
            }
        
        age_minutes = (timezone.now() - latest_run.timestamp).total_seconds() / 60
        logger.info(f"Using AnalysisRun from {age_minutes:.1f}min ago as base (SecondSnapshot unavailable)")
        
        # Extract component scores from AnalysisRun using correct field names
        # All scores are already in -100 to +100 range

        # avg_base_sentiment stores news_composite (with decay applied)
        news_score = float(latest_run.avg_base_sentiment) if latest_run.avg_base_sentiment is not None else 0.0

        # Direct component scores
        reddit_score = float(latest_run.reddit_sentiment) if latest_run.reddit_sentiment else 0.0
        technical_score = float(latest_run.technical_composite_score) if latest_run.technical_composite_score else 0.0
        analyst_score = float(latest_run.analyst_recommendations_score) if latest_run.analyst_recommendations_score else 0.0

        # Calculate VIX inverse score from VXN index
        vix_score = 0.0
        if latest_run.vxn_index:
            vxn = float(latest_run.vxn_index)
            if vxn < 15:
                vix_score = 50.0
            elif vxn < 20:
                vix_score = 25.0
            elif vxn < 25:
                vix_score = 0.0
            elif vxn < 30:
                vix_score = -25.0
            else:
                vix_score = -50.0

        return {
            'news': news_score,
            'reddit': reddit_score,
            'technical': technical_score,
            'analyst': analyst_score,
            'vix_inverse': vix_score,
            'composite': float(latest_run.composite_score) if latest_run.composite_score else 0.0,
            'source': 'analysis_run',
            'timestamp': latest_run.timestamp
        }
    
    except Exception as e:
        logger.error(f"Error getting base scores: {e}", exc_info=True)
        return {
            'news': 0.0,
            'reddit': 0.0,
            'technical': 0.0,
            'analyst': 0.0,
            'vix_inverse': 0.0,
            'composite': 0.0,
            'source': 'error',
            'timestamp': timezone.now()
        }


# ============================================================================
# NEWS DECAY
# ============================================================================

def apply_news_decay(base_news_score):
    """
    Apply one second of decay to news score.
    
    Args:
        base_news_score: News score from previous second
    
    Returns:
        float: Decayed news score
    """
    decayed = base_news_score * (1 - SECOND_DECAY_RATE)
    
    # Force to zero if negligible
    if abs(decayed) < 0.01:
        return 0.0
    
    return float(decayed)


# ============================================================================
# MICRO MOMENTUM (for technical blending)
# ============================================================================

def calculate_micro_momentum(last_n_snapshots):
    """
    Calculate micro momentum from recent price action.
    
    This measures short-term price velocity over ~30 seconds.
    
    Args:
        last_n_snapshots: List of SecondSnapshot objects (most recent last)
    
    Returns:
        float: Micro momentum score (-100 to +100)
    """
    if len(last_n_snapshots) < 10:
        return 0.0
    
    try:
        # Extract prices
        prices = np.array([float(s.ohlc_1sec_close) for s in last_n_snapshots])
        
        # Use last 30 seconds (or all available)
        window = min(30, len(prices))
        prices = prices[-window:]
        
        if len(prices) < 5:
            return 0.0
        
        # Calculate % change over window
        price_start = prices[0]
        price_end = prices[-1]
        
        if price_start == 0:
            return 0.0
        
        pct_change = ((price_end - price_start) / price_start) * 100
        
        # Scale to -100/+100 range
        # A 1% move in 30 seconds = strong momentum
        momentum_score = pct_change * 15
        
        # Clip
        momentum_score = np.clip(momentum_score, -100, 100)
        
        return float(momentum_score)
    
    except Exception as e:
        logger.error(f"Error calculating micro momentum: {e}")
        return 0.0


# ============================================================================
# MACRO TECHNICAL (cached)
# ============================================================================

def get_macro_technical_score(force_recalc=False):
    """
    Get 1-minute technical indicators (RSI, MACD, etc).
    Cached for 60 seconds to avoid expensive recalculation.
    
    Args:
        force_recalc: Force recalculation (at minute boundaries)
    
    Returns:
        float: Technical score (-100 to +100)
    """
    global _macro_technical_cache
    
    now = timezone.now()
    
    # Check cache validity
    if not force_recalc and _macro_technical_cache['timestamp']:
        age = (now - _macro_technical_cache['timestamp']).total_seconds()
        if age < MACRO_CACHE_DURATION:
            return _macro_technical_cache['value']
    
    # Recalculate
    try:
        from api.management.commands.technical_indicators import (
            fetch_latest_ohlcv_with_fallback,
            calculate_technical_composite_score
        )
        
        ohlcv = fetch_latest_ohlcv_with_fallback(symbol='QLD', interval='1m')
        
        if not ohlcv:
            logger.warning("No OHLCV data for macro technical")
            score = 0.0
        else:
            score = calculate_technical_composite_score(ohlcv)
        
        # Update cache
        _macro_technical_cache['value'] = float(score)
        _macro_technical_cache['timestamp'] = now
        
        logger.debug(f"Macro technical recalculated: {score:+.2f}")
        return float(score)
    
    except Exception as e:
        logger.error(f"Error calculating macro technical: {e}", exc_info=True)
        return _macro_technical_cache['value']  # Return cached on error


# ============================================================================
# TECHNICAL BLENDING
# ============================================================================

def blend_technical_scores(base_technical, micro_momentum):
    """
    Blend base technical score with micro momentum using weighted average.
    
    This allows micro momentum to influence technical score visually
    without causing massive swings.
    
    Args:
        base_technical: Base technical score from previous second
        micro_momentum: Current micro momentum
    
    Returns:
        float: Blended technical score
    """
    blended = (base_technical * TECHNICAL_BASE_WEIGHT) + (micro_momentum * TECHNICAL_MICRO_WEIGHT)
    return float(np.clip(blended, -100, 100))


# ============================================================================
# COMPOSITE CALCULATION
# ============================================================================

def calculate_composite(news, reddit, technical, analyst, vix_inverse):
    """
    Calculate composite score from 5 components.
    Uses EXACT same weights as run_nasdaq_sentiment.py

    Args:
        news: News sentiment score
        reddit: Reddit sentiment score
        technical: Technical score
        analyst: Analyst recommendations score
        vix_inverse: VIX inverse score (volatility gauge)

    Returns:
        float: Composite score (-100 to +100)
    """
    composite = (
        news * WEIGHT_NEWS +
        reddit * WEIGHT_REDDIT +
        technical * WEIGHT_TECHNICAL +
        analyst * WEIGHT_ANALYST +
        vix_inverse * WEIGHT_VIX
    )

    return float(np.clip(composite, -100, 100))


# ============================================================================
# MAIN REAL-TIME UPDATE FUNCTION
# ============================================================================

def update_realtime_sentiment(last_60_snapshots, ticker_symbol='QLD', force_macro_recalc=False):
    """
    Update sentiment scores for this second.
    
    This is called by WebSocket collector every second.
    
    Args:
        last_60_snapshots: Recent SecondSnapshot objects for micro calculation
        ticker_symbol: Ticker to analyze
        force_macro_recalc: Force recalculation of macro technical (at minute boundaries)
    
    Returns:
        dict: {
            'news': float,
            'reddit': float,
            'technical': float,
            'analyst': float,
            'composite': float,
            'micro_momentum': float,  # For logging
            'source': str
        }
    """
    try:
        # Get base scores
        base = get_base_scores(ticker_symbol)
        
        # 1. UPDATE NEWS: Apply decay
        news_decayed = apply_news_decay(base['news'])
        news_updated = news_decayed

        # Check for newly scored articles (from Finnhub thread)
        try:
            from api.management.commands.finnhub_realtime_v2 import get_scored_articles
            impacts = get_scored_articles()
            if impacts:
                total_impact = sum(impacts)
                logger.info(
                    f"FINNHUB_IMPACTS: count={len(impacts)}, total={total_impact:+.2f}"
                )
                for article_impact in impacts:
                    news_updated += article_impact
                    logger.info(f"Applied Finnhub article impact: {article_impact:+.2f}")
        except ImportError:
            logger.debug("Finnhub integration not available")
        except Exception as e:
            logger.error(f"Error getting Finnhub scored articles: {e}")

        # Check for newly scored articles (from Tiingo thread)
        try:
            from api.management.commands.tiingo_realtime_news import get_scored_articles as get_tiingo_scored_articles
            tiingo_impacts = get_tiingo_scored_articles()
            if tiingo_impacts:
                total_tiingo = sum(tiingo_impacts)
                logger.info(
                    f"TIINGO_IMPACTS: count={len(tiingo_impacts)}, total={total_tiingo:+.2f}"
                )
                for article_impact in tiingo_impacts:
                    news_updated += article_impact
                    logger.info(f"Applied Tiingo article impact: {article_impact:+.2f}")
        except ImportError:
            logger.debug("Tiingo integration not available")
        except Exception as e:
            logger.error(f"Error getting Tiingo scored articles: {e}")

        # Check for newly scored articles (from RSS thread)
        try:
            from api.management.commands.rss_realtime_news import get_scored_articles as get_rss_scored_articles
            rss_impacts = get_rss_scored_articles()
            if rss_impacts:
                total_rss = sum(rss_impacts)
                logger.info(
                    f"RSS_IMPACTS: count={len(rss_impacts)}, total={total_rss:+.2f}"
                )
                for article_impact in rss_impacts:
                    news_updated += article_impact
                    logger.info(f"Applied RSS article impact: {article_impact:+.2f}")
        except ImportError:
            logger.debug("RSS integration not available")
        except Exception as e:
            logger.error(f"Error getting RSS scored articles: {e}")

        # Clip news to range
        news_before_clip = news_updated
        news_updated = float(np.clip(news_updated, -100, 100))

        # Log end-to-end news update details
        logger.info(
            "NEWS_UPDATE: "
            f"base={base['news']:+.2f}, "
            f"after_decay={news_decayed:+.2f}, "
            f"after_impacts={news_before_clip:+.2f}, "
            f"final_clipped={news_updated:+.2f}"
        )
        
        # 2. UPDATE TECHNICAL: Blend base with micro momentum
        micro_momentum = calculate_micro_momentum(last_60_snapshots)
        
        # Get macro technical (cached or recalculated)
        macro_technical = get_macro_technical_score(force_recalc=force_macro_recalc)
        
        # Blend: previous technical influences next, but micro adds variation
        technical_updated = blend_technical_scores(base['technical'], micro_momentum)
        
        # Also incorporate macro at minute boundaries
        if force_macro_recalc:
            # At minute boundary, reset more toward macro
            technical_updated = (macro_technical * 0.7) + (technical_updated * 0.3)
        
        # 3. REDDIT, ANALYST, VIX: Unchanged (updated only at minute boundaries)
        reddit_updated = base['reddit']
        analyst_updated = base['analyst']
        vix_inverse_updated = base['vix_inverse']

        # If source is analysis_run and it's old, apply decay to reddit/analyst too
        if base['source'] == 'analysis_run':
            age_seconds = (timezone.now() - base['timestamp']).total_seconds()
            if age_seconds > 120:  # > 2 minutes old
                decay_factor = (1 - SECOND_DECAY_RATE) ** age_seconds
                reddit_updated *= decay_factor
                analyst_updated *= decay_factor
                logger.warning(f"Applied decay to reddit/analyst (analysis_run is {age_seconds:.0f}s old)")

        # 4. CALCULATE COMPOSITE
        composite_updated = calculate_composite(
            news_updated,
            reddit_updated,
            technical_updated,
            analyst_updated,
            vix_inverse_updated
        )
        
        return {
            'news': news_updated,
            'reddit': reddit_updated,
            'technical': technical_updated,
            'analyst': analyst_updated,
            'composite': composite_updated,
            'micro_momentum': micro_momentum,
            'macro_technical': macro_technical,
            'source': base['source']
        }
    
    except Exception as e:
        logger.error(f"Error in update_realtime_sentiment: {e}", exc_info=True)
        # Return safe defaults
        return {
            'news': 0.0,
            'reddit': 0.0,
            'technical': 0.0,
            'analyst': 0.0,
            'composite': 0.0,
            'micro_momentum': 0.0,
            'macro_technical': 0.0,
            'source': 'error'
        }


# ============================================================================
# FINNHUB INTEGRATION (with threading)
# ============================================================================

# Will be populated by finnhub_realtime_v2.py
def check_finnhub_for_articles():
    """
    Check Finnhub for new articles (called every second except last 10).
    This is a placeholder - implemented in finnhub_realtime_v2.py
    """
    pass


# ============================================================================
# UTILITIES
# ============================================================================

def clear_macro_cache():
    """Clear macro technical cache."""
    global _macro_technical_cache
    _macro_technical_cache['value'] = 0.0
    _macro_technical_cache['timestamp'] = None


def get_cache_age():
    """Get age of macro cache in seconds."""
    if _macro_technical_cache['timestamp']:
        return (timezone.now() - _macro_technical_cache['timestamp']).total_seconds()
    return None


# ============================================================================
# TESTING
# ============================================================================

if __name__ == '__main__':
    import django
    import os
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    django.setup()
    
    print("Testing sentiment_realtime_v2...")
    print("=" * 60)
    
    # Test base scores
    base = get_base_scores('QLD')
    print(f"\nBase scores (source: {base['source']}):")
    print(f"  News: {base['news']:+.2f}")
    print(f"  Reddit: {base['reddit']:+.2f}")
    print(f"  Technical: {base['technical']:+.2f}")
    print(f"  Analyst: {base['analyst']:+.2f}")
    print(f"  Composite: {base['composite']:+.2f}")
    
    # Test update
    ticker = Ticker.objects.get(symbol='QLD')
    snapshots = list(SecondSnapshot.objects.filter(ticker=ticker).order_by('-timestamp')[:60])
    
    result = update_realtime_sentiment(snapshots, 'QLD', force_macro_recalc=True)
    print(f"\nUpdated scores:")
    print(f"  News: {result['news']:+.2f}")
    print(f"  Reddit: {result['reddit']:+.2f}")
    print(f"  Technical: {result['technical']:+.2f}")
    print(f"  Analyst: {result['analyst']:+.2f}")
    print(f"  Composite: {result['composite']:+.2f}")
    print(f"  Micro momentum: {result['micro_momentum']:+.2f}")
    
    print("\n" + "=" * 60)
    print("✓ Tests completed")

