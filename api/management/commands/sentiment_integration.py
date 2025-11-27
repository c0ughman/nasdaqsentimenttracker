"""
Sentiment Integration Module

This module provides integration between:
- run_nasdaq_sentiment.py (minute-by-minute comprehensive analysis)
- sentiment_realtime_v2.py (second-by-second updates)

BACKWARDS COMPATIBILITY:
- If imported, provides helper functions
- If not imported, run_nasdaq_sentiment.py works independently
- No breaking changes to existing functionality
"""

import logging
from django.utils import timezone
from api.models import SecondSnapshot, AnalysisRun, Ticker

logger = logging.getLogger(__name__)


# ============================================================================
# GET STARTING POINT FOR MINUTE ANALYSIS
# ============================================================================

def get_starting_scores_for_minute_analysis(ticker_symbol='QLD'):
    """
    Get starting scores for minute-by-minute analysis.
    
    This function checks if second-by-second system is running.
    If yes: Use latest SecondSnapshot as starting point (decay already applied)
    If no: Return None (use normal decay in run_nasdaq_sentiment.py)
    
    Args:
        ticker_symbol: Ticker to analyze
    
    Returns:
        dict or None: {
            'news': float,
            'reddit': float,
            'technical': float,
            'analyst': float,
            'use_as_base': bool  # If True, don't apply decay
        }
    """
    try:
        ticker = Ticker.objects.get(symbol=ticker_symbol)
        
        # Check for recent SecondSnapshot
        latest_snapshot = SecondSnapshot.objects.filter(
            ticker=ticker
        ).order_by('-timestamp').first()
        
        if not latest_snapshot:
            logger.info("No SecondSnapshot found - using normal decay")
            return None
        
        # Check age
        age_seconds = (timezone.now() - latest_snapshot.timestamp).total_seconds()
        
        # If snapshot is recent (< 70 seconds), use it
        if age_seconds < 70:
            # Get reddit/analyst from AnalysisRun
            latest_run = AnalysisRun.objects.filter(
                ticker=ticker
            ).order_by('-timestamp').first()
            
            reddit_score = 0.0
            analyst_score = 0.0
            
            if latest_run:
                if hasattr(latest_run, 'reddit_composite') and latest_run.reddit_composite:
                    reddit_score = float(latest_run.reddit_composite)
                if hasattr(latest_run, 'analyst_composite') and latest_run.analyst_composite:
                    analyst_score = float(latest_run.analyst_composite)
            
            logger.info(f"Using SecondSnapshot from {age_seconds:.1f}s ago (decay already applied)")
            
            return {
                'news': float(latest_snapshot.news_score_cached) if latest_snapshot.news_score_cached else 0.0,
                'reddit': reddit_score,
                'technical': float(latest_snapshot.technical_score_cached) if latest_snapshot.technical_score_cached else 0.0,
                'analyst': analyst_score,
                'use_as_base': True,  # Don't apply decay - it's already applied
                'source': 'second_snapshot',
                'age_seconds': age_seconds
            }
        else:
            logger.info(f"SecondSnapshot is {age_seconds:.1f}s old - too stale, using normal decay")
            return None
    
    except Ticker.DoesNotExist:
        logger.warning(f"Ticker {ticker_symbol} not found")
        return None
    except Exception as e:
        logger.error(f"Error getting starting scores: {e}", exc_info=True)
        return None


# ============================================================================
# SAVE TO BOTH TABLES AT MINUTE BOUNDARY
# ============================================================================

def save_minute_analysis_to_both_tables(
    ticker,
    news_composite,
    reddit_composite,
    technical_composite,
    analyst_composite,
    composite_score,
    **kwargs
):
    """
    Save minute analysis results to both AnalysisRun AND SecondSnapshot.
    
    This creates consistency between the two systems.
    
    Args:
        ticker: Ticker object
        news_composite: News sentiment score
        reddit_composite: Reddit sentiment score
        technical_composite: Technical score
        analyst_composite: Analyst score
        composite_score: Final composite score
        **kwargs: Additional fields for AnalysisRun
    
    Returns:
        tuple: (analysis_run, second_snapshot)
    """
    try:
        from api.models import AnalysisRun, SecondSnapshot
        
        # Save to AnalysisRun (primary record)
        analysis_run = AnalysisRun.objects.create(
            ticker=ticker,
            composite_score=composite_score,
            news_composite=news_composite,
            reddit_composite=reddit_composite,
            technical_composite=technical_composite,
            analyst_composite=analyst_composite,
            **kwargs
        )
        
        logger.info(f"Saved AnalysisRun: composite={composite_score:+.2f}")
        
        # Also save to SecondSnapshot (for continuity)
        try:
            second_snapshot = SecondSnapshot.objects.create(
                ticker=ticker,
                timestamp=analysis_run.timestamp,
                ohlc_1sec_open=kwargs.get('price_open', 0),
                ohlc_1sec_high=kwargs.get('price_high', 0),
                ohlc_1sec_low=kwargs.get('price_low', 0),
                ohlc_1sec_close=kwargs.get('stock_price', 0),
                ohlc_1sec_volume=kwargs.get('volume', 0),
                ohlc_1sec_tick_count=0,
                composite_score=composite_score,
                news_score_cached=news_composite,
                technical_score_cached=technical_composite,
                source='analysis_run'
            )
            
            logger.info(f"Saved SecondSnapshot at minute boundary: {second_snapshot.timestamp}")
            
            return analysis_run, second_snapshot
        
        except Exception as e:
            logger.warning(f"Failed to save SecondSnapshot (non-critical): {e}")
            return analysis_run, None
    
    except Exception as e:
        logger.error(f"Error saving to both tables: {e}", exc_info=True)
        raise


# ============================================================================
# CHECK IF SECOND-BY-SECOND IS RUNNING
# ============================================================================

def is_second_by_second_active(ticker_symbol='QLD'):
    """
    Check if second-by-second system is actively running.
    
    Returns:
        bool: True if active (recent snapshots exist)
    """
    try:
        ticker = Ticker.objects.get(symbol=ticker_symbol)
        latest_snapshot = SecondSnapshot.objects.filter(
            ticker=ticker
        ).order_by('-timestamp').first()
        
        if not latest_snapshot:
            return False
        
        age_seconds = (timezone.now() - latest_snapshot.timestamp).total_seconds()
        
        # Consider active if latest snapshot < 70 seconds old
        return age_seconds < 70
    
    except:
        return False


# ============================================================================
# TESTING
# ============================================================================

if __name__ == '__main__':
    import django
    import os
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    django.setup()
    
    print("Testing sentiment integration...")
    print("=" * 60)
    
    # Check if second-by-second is active
    active = is_second_by_second_active('QLD')
    print(f"\nSecond-by-second active: {active}")
    
    # Get starting scores
    scores = get_starting_scores_for_minute_analysis('QLD')
    if scores:
        print(f"\nStarting scores (source: {scores['source']}):")
        print(f"  News: {scores['news']:+.2f}")
        print(f"  Reddit: {scores['reddit']:+.2f}")
        print(f"  Technical: {scores['technical']:+.2f}")
        print(f"  Analyst: {scores['analyst']:+.2f}")
        print(f"  Use as base (skip decay): {scores['use_as_base']}")
        print(f"  Age: {scores['age_seconds']:.1f} seconds")
    else:
        print("\nNo starting scores available - use normal decay")
    
    print("\n" + "=" * 60)
    print("✓ Test completed")


