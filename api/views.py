from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.conf import settings
from .models import Ticker, AnalysisRun, NewsArticle, TickerContribution
from .serializers import AnalysisRunSerializer, TickerSerializer, TickerContributionSerializer
from api.utils.market_hours import get_market_status


@api_view(['GET'])
def health_check(request):
    """
    Simple health check endpoint to verify the API is running.
    """
    return Response({
        'status': 'ok',
        'message': 'API is running successfully'
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
def ticker_analysis(request, ticker_symbol):
    """
    Get all analysis runs for a specific ticker
    Returns current score and historical data
    """
    ticker_symbol = ticker_symbol.upper()
    
    try:
        ticker = get_object_or_404(Ticker, symbol=ticker_symbol)
        
        # Get all analysis runs for this ticker, ordered by most recent first
        analysis_runs = AnalysisRun.objects.filter(ticker=ticker).order_by('-timestamp')
        
        # Get latest run for current score
        latest_run = analysis_runs.first()
        
        # Serialize the data
        serializer = AnalysisRunSerializer(analysis_runs, many=True)
        
        return Response({
            'ticker': {
                'symbol': ticker.symbol,
                'company_name': ticker.company_name
            },
            'current_score': {
                'composite_score': latest_run.composite_score if latest_run else None,
                'sentiment_label': latest_run.sentiment_label if latest_run else None,
                'stock_price': str(latest_run.stock_price) if latest_run else None,
                'price_change_percent': latest_run.price_change_percent if latest_run else None,
                'articles_analyzed': latest_run.articles_analyzed if latest_run else None,
                'timestamp': latest_run.timestamp if latest_run else None,
            } if latest_run else None,
            'historical_runs': serializer.data,
            'total_runs': analysis_runs.count()
        }, status=status.HTTP_200_OK)
        
    except Ticker.DoesNotExist:
        return Response({
            'error': f'Ticker {ticker_symbol} not found',
            'message': 'No analysis data available for this ticker. Run analysis first.'
        }, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
def available_tickers(request):
    """
    Get list of all available tickers with analysis data
    """
    tickers = Ticker.objects.all()
    serializer = TickerSerializer(tickers, many=True)
    
    return Response({
        'tickers': serializer.data,
        'count': tickers.count()
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
def analysis_run_contributions(request, run_id):
    """
    Get individual ticker contributions for a specific analysis run
    Shows how each of the 20 stocks contributed to the composite NASDAQ score
    """
    try:
        analysis_run = get_object_or_404(AnalysisRun, id=run_id)
        
        # Get all ticker contributions for this run, ordered by weighted contribution (highest first)
        contributions = TickerContribution.objects.filter(
            analysis_run=analysis_run
        ).select_related('ticker').order_by('-weighted_contribution')
        
        serializer = TickerContributionSerializer(contributions, many=True)
        
        return Response({
            'analysis_run_id': run_id,
            'composite_score': analysis_run.composite_score,
            'timestamp': analysis_run.timestamp,
            'contributions': serializer.data,
            'total_stocks': contributions.count()
        }, status=status.HTTP_200_OK)
        
    except AnalysisRun.DoesNotExist:
        return Response({
            'error': f'Analysis run {run_id} not found'
        }, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
def nasdaq_composite_score(request):
    """
    Get the most recent NASDAQ composite sentiment score
    Returns the latest composite score for the NASDAQ index
    """
    try:
        # Get the NASDAQ ticker
        nasdaq_ticker = get_object_or_404(Ticker, symbol='^IXIC')
        
        # Get the most recent analysis run for NASDAQ
        latest_run = AnalysisRun.objects.filter(ticker=nasdaq_ticker).order_by('-timestamp').first()
        
        if not latest_run:
            return Response({
                'error': 'No NASDAQ analysis data available',
                'message': 'No composite sentiment data found for NASDAQ index'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get ticker contributions for context
        contributions = TickerContribution.objects.filter(
            analysis_run=latest_run
        ).select_related('ticker').order_by('-weighted_contribution')[:10]
        
        contribution_data = []
        for contrib in contributions:
            contribution_data.append({
                'ticker': contrib.ticker.symbol,
                'sentiment_score': contrib.sentiment_score,
                'market_cap_weight': contrib.market_cap_weight,
                'weighted_contribution': contrib.weighted_contribution,
                'articles_analyzed': contrib.articles_analyzed
            })
        
        return Response({
            'composite_score': latest_run.composite_score,
            'sentiment_label': latest_run.sentiment_label,
            'stock_price': str(latest_run.stock_price),
            'price_change_percent': latest_run.price_change_percent,
            'timestamp': latest_run.timestamp,
            'articles_analyzed': latest_run.articles_analyzed,
            'top_contributors': contribution_data
        }, status=status.HTTP_200_OK)
        
    except Ticker.DoesNotExist:
        return Response({
            'error': 'NASDAQ ticker not found',
            'message': 'NASDAQ composite index ticker (^IXIC) not found in database'
        }, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
def dashboard_data(request):
    """
    Single endpoint for nasdaq.html dashboard
    Returns everything needed: composite score, 3 drivers, historical data
    """
    try:
        # Get the NASDAQ ticker
        nasdaq_ticker = get_object_or_404(Ticker, symbol='^IXIC')

        # Get the most recent analysis run
        latest_run = AnalysisRun.objects.filter(ticker=nasdaq_ticker).order_by('-timestamp').first()

        if not latest_run:
            return Response({
                'error': 'No NASDAQ analysis data available',
                'message': 'No composite sentiment data found. Run analysis first.'
            }, status=status.HTTP_404_NOT_FOUND)

        # Helper function to safely convert values
        def safe_float(value, default=None):
            """Safely convert value to float, return default if None or invalid (including NaN)"""
            import math
            if value is None:
                return default
            try:
                result = float(value)
                # Check for NaN or Infinity
                if math.isnan(result) or math.isinf(result):
                    return default
                return result
            except (TypeError, ValueError):
                return default

        def safe_round(value, decimals=2, default=0):
            """Safely round a value, return default if None or invalid (including NaN)"""
            import math
            if value is None:
                return default
            try:
                result = float(value)
                # Check for NaN or Infinity
                if math.isnan(result) or math.isinf(result):
                    return default
                return round(result, decimals)
            except (TypeError, ValueError):
                return default

        # Calculate news composite (from company + market news)
        # The old composite was 70% company + 30% market
        # To extract just the news part from stored data, we use avg_base_sentiment * 100
        news_sentiment_raw = (latest_run.avg_base_sentiment * 100) if (latest_run.avg_base_sentiment is not None) else 0

        # Four sentiment drivers with optimized weights for market prediction
        drivers = {
            'news_sentiment': {
                'score': safe_round(news_sentiment_raw, 2),
                'weight': 35,  # Most impactful for immediate market reactions
                'label': 'News Sentiment',
                'articles_count': latest_run.articles_analyzed or 0
            },
            'social_media': {
                'score': safe_round(latest_run.reddit_sentiment, 2),
                'weight': 20,  # Retail sentiment and momentum indicator
                'label': 'Social Media',
                'posts_count': latest_run.reddit_posts_analyzed or 0,
                'comments_count': latest_run.reddit_comments_analyzed or 0
            },
            'technical_indicators': {
                'score': safe_round(latest_run.technical_composite_score, 2),
                'weight': 25,  # Price action and momentum signals
                'label': 'Technical Indicators',
                'rsi': safe_float(latest_run.rsi_14),
                'macd': safe_float(latest_run.macd)
            },
            'analyst_recommendations': {
                'score': safe_round(latest_run.analyst_recommendations_score, 2),
                'weight': 20,  # Professional institutional outlook
                'label': 'Analyst Recommendations',
                'recommendations_count': latest_run.analyst_recommendations_count or 0,
                'strong_buy': latest_run.analyst_strong_buy or 0,
                'buy': latest_run.analyst_buy or 0,
                'hold': latest_run.analyst_hold or 0,
                'sell': latest_run.analyst_sell or 0,
                'strong_sell': latest_run.analyst_strong_sell or 0
            },
            'market_breadth': {
                'score': safe_round(latest_run.technical_composite_score * 0.3, 2) if latest_run.technical_composite_score is not None else 0,
                'weight': 0,  # Not included in composite score yet
                'label': 'Market Breadth',
                'description': 'Based on technical indicators and market momentum'
            }
        }

        # Historical data for chart (last 24 hours - frontend will filter by timeframe)
        from django.utils import timezone
        from datetime import timedelta

        cutoff_time = timezone.now() - timedelta(hours=24)
        historical_runs = AnalysisRun.objects.filter(
            ticker=nasdaq_ticker,
            timestamp__gte=cutoff_time
        ).order_by('timestamp')

        historical_data = []
        for run in historical_runs:
            # Safely handle timestamp conversion
            try:
                timestamp_str = run.timestamp.isoformat() if run.timestamp else None
            except (AttributeError, TypeError):
                timestamp_str = None

            historical_data.append({
                'timestamp': timestamp_str,
                'composite_score': safe_round(run.composite_score, 2, 0),
                'stock_price': safe_float(run.stock_price),
                'news_score': safe_round((run.avg_base_sentiment * 100) if (run.avg_base_sentiment is not None) else None, 2),
                'social_score': safe_round(run.reddit_sentiment, 2),
                'technical_score': safe_round(run.technical_composite_score, 2)
            })

        # Get market status with error handling
        try:
            market_status_info = get_market_status()
        except Exception as e:
            # Fallback market status if utility fails
            market_status_info = {
                'is_open': False,
                'reason': 'Unable to determine market status',
                'current_time_ct': timezone.now().strftime('%Y-%m-%d %I:%M:%S %p %Z'),
            }

        # Safely handle timestamp for latest run
        try:
            timestamp_str = latest_run.timestamp.isoformat() if latest_run.timestamp else None
        except (AttributeError, TypeError):
            timestamp_str = None

        return Response({
            'composite_score': safe_round(latest_run.composite_score, 2, 0),
            'sentiment_label': latest_run.sentiment_label or 'NEUTRAL',
            'timestamp': timestamp_str,
            'price': safe_float(latest_run.stock_price),
            'price_change': safe_round(latest_run.price_change_percent, 2),
            'drivers': drivers,
            'historical': historical_data,
            'technical_indicators': {
                'rsi_14': safe_float(latest_run.rsi_14),
                'macd': safe_float(latest_run.macd),
                'macd_signal': safe_float(latest_run.macd_signal),
                'bb_upper': safe_float(latest_run.bb_upper),
                'bb_middle': safe_float(latest_run.bb_middle),
                'bb_lower': safe_float(latest_run.bb_lower)
            },
            'current_score': {
                'analyst_recommendations_score': safe_round(latest_run.analyst_recommendations_score, 2),
                'analyst_recommendations_count': latest_run.analyst_recommendations_count or 0,
                'analyst_strong_buy': latest_run.analyst_strong_buy or 0,
                'analyst_buy': latest_run.analyst_buy or 0,
                'analyst_hold': latest_run.analyst_hold or 0,
                'analyst_sell': latest_run.analyst_sell or 0,
                'analyst_strong_sell': latest_run.analyst_strong_sell or 0
            },
            'market_status': market_status_info
        }, status=status.HTTP_200_OK)

    except Ticker.DoesNotExist:
        return Response({
            'error': 'NASDAQ ticker not found',
            'message': 'NASDAQ composite index ticker (^IXIC) not found in database'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        # Catch all other exceptions and log them
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f'Error in dashboard_data endpoint: {str(e)}', exc_info=True)
        
        return Response({
            'error': 'Internal server error',
            'message': 'An error occurred while fetching dashboard data. Please try again later.',
            'detail': str(e) if settings.DEBUG else None
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def news_articles(request):
    """
    Get news articles from the last 24 hours
    Returns articles with sentiment analysis for the frontend news display
    """
    try:
        from django.utils import timezone
        from datetime import timedelta

        # Get articles from the last 24 hours
        cutoff_time = timezone.now() - timedelta(hours=24)
        
        # Fetch all news articles from the last day, ordered by most recent first
        articles = NewsArticle.objects.filter(
            published_at__gte=cutoff_time
        ).select_related('ticker').order_by('-published_at')

        # Helper function to convert sentiment score to label
        def get_sentiment_label(base_sentiment):
            """Convert base_sentiment (-1 to 1) to 'positive', 'negative', or 'neutral'"""
            if base_sentiment is None:
                return 'neutral'
            
            # Use thresholds: positive > 0.1, negative < -0.1, else neutral
            if base_sentiment > 0.1:
                return 'positive'
            elif base_sentiment < -0.1:
                return 'negative'
            else:
                return 'neutral'

        # Helper function to safely format datetime
        def safe_isoformat(dt):
            """Safely convert datetime to ISO format string"""
            if dt is None:
                return None
            try:
                # Datetimes from Django ORM should be timezone-aware
                # Just call isoformat() which handles both aware and naive datetimes
                return dt.isoformat()
            except (AttributeError, TypeError, ValueError):
                return None

        # Convert articles to the expected format
        articles_data = []
        for article in articles:
            # Use base_sentiment for sentiment_score, or article_score as fallback
            sentiment_score = float(article.base_sentiment) if article.base_sentiment is not None else (
                float(article.article_score) if article.article_score is not None else 0.0
            )
            
            articles_data.append({
                'title': article.headline,
                'summary': article.summary if article.summary else '',
                'source': article.source,
                'published_at': safe_isoformat(article.published_at),
                'url': article.url if article.url else '',
                'sentiment': get_sentiment_label(article.base_sentiment),
                'sentiment_score': round(sentiment_score, 3)
            })

        return Response({
            'articles': articles_data,
            'count': len(articles_data),
            'timeframe': 'last_24_hours'
        }, status=status.HTTP_200_OK)

    except Exception as e:
        # Catch all exceptions and log them
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f'Error in news_articles endpoint: {str(e)}', exc_info=True)
        
        return Response({
            'error': 'Internal server error',
            'message': 'An error occurred while fetching news articles. Please try again later.',
            'detail': str(e) if settings.DEBUG else None,
            'articles': []
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def nasdaq_historical_data(request):
    """
    Get historical NASDAQ composite sentiment data for charting
    Returns data points for the specified timeframe
    """
    try:
        # Get timeframe parameter (default to 240 minutes = 4 hours)
        timeframe_minutes = int(request.GET.get('timeframe', 240))
        
        # Get the NASDAQ ticker
        nasdaq_ticker = get_object_or_404(Ticker, symbol='^IXIC')
        
        # Get historical analysis runs within the timeframe
        from django.utils import timezone
        from datetime import timedelta
        
        cutoff_time = timezone.now() - timedelta(minutes=timeframe_minutes)
        historical_runs = AnalysisRun.objects.filter(
            ticker=nasdaq_ticker,
            timestamp__gte=cutoff_time
        ).order_by('timestamp')
        
        if not historical_runs.exists():
            return Response({
                'error': 'No historical data available',
                'message': f'No NASDAQ sentiment data found for the last {timeframe_minutes} minutes'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Convert to chart-friendly format
        data_points = []
        for run in historical_runs:
            # Calculate minutes ago from now
            minutes_ago = int((timezone.now() - run.timestamp).total_seconds() / 60)
            
            data_points.append({
                'minutes_ago': minutes_ago,
                'sentiment': run.composite_score,
                'timestamp': run.timestamp,
                'stock_price': str(run.stock_price),
                'articles_analyzed': run.articles_analyzed
            })
        
        return Response({
            'timeframe_minutes': timeframe_minutes,
            'data_points': data_points,
            'total_points': len(data_points),
            'current_score': data_points[-1]['sentiment'] if data_points else None,
            'latest_timestamp': data_points[-1]['timestamp'] if data_points else None
        }, status=status.HTTP_200_OK)
        
    except Ticker.DoesNotExist:
        return Response({
            'error': 'NASDAQ ticker not found',
            'message': 'NASDAQ composite index ticker (^IXIC) not found in database'
        }, status=status.HTTP_404_NOT_FOUND)
    except ValueError:
        return Response({
            'error': 'Invalid timeframe parameter',
            'message': 'Timeframe must be a valid integer (minutes)'
        }, status=status.HTTP_400_BAD_REQUEST)
