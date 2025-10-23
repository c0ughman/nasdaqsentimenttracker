"""
NASDAQ Sentiment Scorer - Django Management Command
Run with: python manage.py run_sentiment_analysis
"""

import os
import time
import hashlib
from datetime import datetime, timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Avg, Min, Max, Count, Sum
from django.db import transaction
import requests
import finnhub
from dotenv import load_dotenv

# Load environment variables from project root
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '.env'))

# Import models
from api.models import Ticker, AnalysisRun, NewsArticle, SentimentHistory

# ============================================================================
# CONFIGURATION
# ============================================================================

FINNHUB_API_KEY = os.environ.get('FINNHUB_API_KEY', '')
HUGGINGFACE_API_KEY = os.environ.get('HUGGINGFACE_API_KEY', '')

# Weights for composite score
WEIGHTS = {
    'base_sentiment': 0.40,
    'surprise_factor': 0.25,
    'novelty': 0.15,
    'source_credibility': 0.10,
    'recency': 0.10
}

# Source credibility ratings
SOURCE_CREDIBILITY = {
    'Bloomberg': 1.0,
    'Reuters': 1.0,
    'Wall Street Journal': 0.95,
    'Financial Times': 0.95,
    'CNBC': 0.8,
    'MarketWatch': 0.75,
    'Seeking Alpha': 0.7,
    'Yahoo Finance': 0.7,
    'Benzinga': 0.75,
    'PR Newswire': 0.6,
    'Business Wire': 0.6,
}

# Cache to track seen articles in current session
seen_articles = set()

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_article_hash(headline, summary):
    """Generate unique hash for article deduplication"""
    content = f"{headline}{summary}".lower()
    return hashlib.md5(content.encode()).hexdigest()


def get_cached_sentiment_from_db(article_hash):
    """Get cached sentiment from database"""
    try:
        article = NewsArticle.objects.filter(article_hash=article_hash).first()
        if article and article.is_analyzed:
            return article.base_sentiment
    except Exception as e:
        print(f"⚠️ Error fetching cached sentiment: {e}")
    return None


def analyze_sentiment_finbert_api(text):
    """Analyze sentiment using FinBERT via HuggingFace API"""
    API_URL = "https://api-inference.huggingface.co/models/ProsusAI/finbert"
    headers = {"Authorization": f"Bearer {HUGGINGFACE_API_KEY}"}
    text = text[:512]
    
    try:
        response = requests.post(API_URL, headers=headers, json={"inputs": text})
        
        if response.status_code == 200:
            result = response.json()
            sentiment_map = {'positive': 0, 'negative': 0, 'neutral': 0}
            
            for item in result[0]:
                label = item['label'].lower()
                score = item['score']
                sentiment_map[label] = score
            
            sentiment_score = sentiment_map['positive'] - sentiment_map['negative']
            return sentiment_score
            
        elif response.status_code == 503:
            print("  ⏳ Model loading, retrying in 20 seconds...")
            time.sleep(20)
            return analyze_sentiment_finbert_api(text)
        else:
            print(f"  ⚠️ API error: {response.status_code}")
            return 0.0
            
    except Exception as e:
        print(f"  ⚠️ Error analyzing sentiment: {e}")
        return 0.0


def calculate_surprise_factor(text):
    """Detect if news is surprising/unexpected"""
    text_lower = text.lower()
    
    surprise_keywords = {
        'unexpected': 1.5, 'surprise': 1.5, 'beats expectations': 1.8,
        'misses estimates': 1.8, 'exceeds expectations': 1.8, 'shock': 2.0,
        'unprecedented': 1.7, 'sudden': 1.4, 'abrupt': 1.4, 'breaking': 1.3
    }
    
    expected_keywords = {
        'as expected': 0.4, 'in line with': 0.4, 'anticipated': 0.5,
        'scheduled': 0.6, 'planned': 0.6
    }
    
    multiplier = 1.0
    for keyword, weight in surprise_keywords.items():
        if keyword in text_lower:
            multiplier = max(multiplier, weight)
    for keyword, weight in expected_keywords.items():
        if keyword in text_lower:
            multiplier = min(multiplier, weight)
    
    return multiplier


def calculate_novelty(article_hash):
    """Check if article is novel or duplicate"""
    if article_hash in seen_articles:
        return 0.2
    seen_articles.add(article_hash)
    return 1.0


def get_source_credibility(source):
    """Get credibility weight for news source"""
    for known_source, weight in SOURCE_CREDIBILITY.items():
        if known_source.lower() in source.lower():
            return weight
    return 0.5


def calculate_recency_weight(published_timestamp):
    """Calculate weight based on how recent the article is"""
    try:
        published_time = datetime.fromtimestamp(published_timestamp)
        hours_old = (datetime.now() - published_time).total_seconds() / 3600
        decay_factor = 2 ** (-hours_old / 6)
        return max(0, min(1.0, decay_factor))
    except:
        return 0.5


def fetch_news(finnhub_client, ticker_symbol, lookback_hours=24):
    """Fetch recent news from Finnhub"""
    try:
        to_date = datetime.now()
        from_date = to_date - timedelta(hours=lookback_hours)
        
        from_str = from_date.strftime('%Y-%m-%d')
        to_str = to_date.strftime('%Y-%m-%d')
        
        news = finnhub_client.company_news(ticker_symbol, _from=from_str, to=to_str)
        return news
    except Exception as e:
        print(f"❌ Error fetching news: {e}")
        return []


def fetch_stock_price(finnhub_client, ticker_symbol):
    """Fetch current stock price from Finnhub"""
    try:
        quote = finnhub_client.quote(ticker_symbol)
        if quote and quote.get('c'):
            return {
                'price': Decimal(str(quote.get('c', 0))),
                'open': Decimal(str(quote.get('o', 0))) if quote.get('o') else None,
                'high': Decimal(str(quote.get('h', 0))) if quote.get('h') else None,
                'low': Decimal(str(quote.get('l', 0))) if quote.get('l') else None,
                'change_percent': float(quote.get('dp', 0)) if quote.get('dp') else None,
            }
        return None
    except Exception as e:
        print(f"⚠️ Error fetching stock price: {e}")
        return None


def run_complete_analysis(finnhub_client, ticker):
    """
    MAIN FUNCTION: Run complete analysis and save everything to AnalysisRun
    Returns the saved AnalysisRun object
    """
    print(f"\n{'='*60}")
    print(f"📊 Running Complete Analysis for {ticker.symbol}")
    print(f"🕐 Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")
    
    # Step 1: Fetch stock price
    print("💰 Fetching stock price...")
    stock_data = fetch_stock_price(finnhub_client, ticker.symbol)
    if not stock_data:
        print("⚠️ Could not fetch stock price")
        return None
    print(f"   Current Price: ${stock_data['price']}")
    if stock_data['change_percent']:
        print(f"   Change: {stock_data['change_percent']:.2f}%")
    
    # Step 2: Fetch news articles
    print("\n📰 Fetching news articles...")
    articles = fetch_news(finnhub_client, ticker.symbol, lookback_hours=24)
    
    if not articles:
        print("ℹ️  No articles found in the last 24 hours.")
        return None
    
    print(f"   Found {len(articles)} articles\n")
    
    # Step 3: Analyze each article and collect data
    article_data_list = []
    weighted_scores = []
    total_weight = 0
    new_articles_count = 0
    cached_articles_count = 0
    
    # Component score accumulators
    base_sentiments = []
    surprise_factors = []
    novelties = []
    credibilities = []
    recencies = []
    
    for idx, article in enumerate(articles):
        headline = article.get('headline', '')
        summary = article.get('summary', '')
        source = article.get('source', 'Unknown')
        published = article.get('datetime', 0)
        
        if not headline and not summary:
            continue
        
        full_text = f"{headline}. {summary}"
        article_hash = get_article_hash(headline, summary)
        
        print(f"📄 Article {idx + 1}:")
        print(f"   Source: {source}")
        print(f"   Headline: {headline[:70]}...")
        
        # Check cache
        cached_sentiment = get_cached_sentiment_from_db(article_hash)
        was_cached = False
        
        if cached_sentiment is not None:
            base_sentiment = cached_sentiment
            cached_articles_count += 1
            was_cached = True
            print(f"   💭 Base Sentiment (CACHED): {base_sentiment:.3f} 🚀")
        else:
            base_sentiment = analyze_sentiment_finbert_api(full_text)
            new_articles_count += 1
            print(f"   💭 Base Sentiment (NEW): {base_sentiment:.3f}")
        
        # Calculate other factors
        surprise_multiplier = calculate_surprise_factor(full_text)
        print(f"   ⚡ Surprise Factor: {surprise_multiplier:.2f}x")
        
        novelty = calculate_novelty(article_hash)
        print(f"   🆕 Novelty: {novelty:.2f}")
        
        source_cred = get_source_credibility(source)
        print(f"   ✅ Source Credibility: {source_cred:.2f}")
        
        recency = calculate_recency_weight(published)
        print(f"   ⏱️  Recency Weight: {recency:.2f}")
        
        # Combine factors
        article_score = (base_sentiment * WEIGHTS['base_sentiment']) * surprise_multiplier
        article_weight = (
            novelty * WEIGHTS['novelty'] +
            source_cred * WEIGHTS['source_credibility'] +
            recency * WEIGHTS['recency']
        )
        weighted_score = article_score * article_weight
        
        print(f"   → Article Score: {article_score:.3f}")
        print(f"   → Weighted Contribution: {weighted_score:.3f}\n")
        
        # Accumulate component scores
        base_sentiments.append(base_sentiment)
        surprise_factors.append(surprise_multiplier)
        novelties.append(novelty)
        credibilities.append(source_cred)
        recencies.append(recency)
        
        weighted_scores.append(weighted_score)
        total_weight += article_weight
        
        # Store article data for saving
        article_data_list.append({
            'article': article,
            'article_hash': article_hash,
            'base_sentiment': base_sentiment,
            'surprise_factor': surprise_multiplier,
            'novelty': novelty,
            'source_cred': source_cred,
            'recency': recency,
            'article_score': article_score,
            'weighted_contribution': weighted_score,
            'was_cached': was_cached
        })
    
    # Step 4: Calculate final composite score
    if total_weight == 0:
        final_score = 0
    else:
        final_score = (sum(weighted_scores) / total_weight) * 100
    
    final_score = max(-100, min(100, final_score))
    
    # Step 5: Calculate average component scores
    avg_base_sentiment = sum(base_sentiments) / len(base_sentiments) if base_sentiments else 0
    avg_surprise = sum(surprise_factors) / len(surprise_factors) if surprise_factors else 1.0
    avg_novelty = sum(novelties) / len(novelties) if novelties else 1.0
    avg_credibility = sum(credibilities) / len(credibilities) if credibilities else 0.5
    avg_recency = sum(recencies) / len(recencies) if recencies else 1.0
    
    print(f"{'='*60}")
    print(f"🎯 COMPOSITE SENTIMENT SCORE: {final_score:.2f}")
    print(f"📊 Component Averages:")
    print(f"   Base Sentiment: {avg_base_sentiment:.3f}")
    print(f"   Surprise Factor: {avg_surprise:.2f}")
    print(f"   Novelty: {avg_novelty:.2f}")
    print(f"   Credibility: {avg_credibility:.2f}")
    print(f"   Recency: {avg_recency:.2f}")
    print(f"💰 Stock Price: ${stock_data['price']}")
    print(f"📈 Articles: {len(articles)} ({cached_articles_count} cached, {new_articles_count} new)")
    print(f"{'='*60}\n")
    
    # Step 6: Save everything to database in ONE transaction
    print("💾 Saving to database...")
    
    try:
        with transaction.atomic():
            # Create the unified AnalysisRun record
            analysis_run = AnalysisRun.objects.create(
                ticker=ticker,
                # Sentiment data
                composite_score=final_score,
                avg_base_sentiment=avg_base_sentiment,
                avg_surprise_factor=avg_surprise,
                avg_novelty=avg_novelty,
                avg_source_credibility=avg_credibility,
                avg_recency_weight=avg_recency,
                # Stock price data
                stock_price=stock_data['price'],
                price_open=stock_data.get('open'),
                price_high=stock_data.get('high'),
                price_low=stock_data.get('low'),
                price_change_percent=stock_data.get('change_percent'),
                # Metadata
                articles_analyzed=len(articles),
                cached_articles=cached_articles_count,
                new_articles=new_articles_count
            )
            
            print(f"✅ Created AnalysisRun #{analysis_run.id}")
            
            # Save all news articles linked to this analysis run
            for article_data in article_data_list:
                article = article_data['article']
                NewsArticle.objects.update_or_create(
                    article_hash=article_data['article_hash'],
                    defaults={
                        'ticker': ticker,
                        'analysis_run': analysis_run,
                        'headline': article.get('headline', ''),
                        'summary': article.get('summary', ''),
                        'source': article.get('source', 'Unknown'),
                        'url': article.get('url', ''),
                        'published_at': datetime.fromtimestamp(article.get('datetime', 0)),
                        'base_sentiment': article_data['base_sentiment'],
                        'surprise_factor': article_data['surprise_factor'],
                        'novelty_score': article_data['novelty'],
                        'source_credibility': article_data['source_cred'],
                        'recency_weight': article_data['recency'],
                        'article_score': article_data['article_score'],
                        'weighted_contribution': article_data['weighted_contribution'],
                        'is_analyzed': True,
                        'sentiment_cached': article_data['was_cached'],
                    }
                )
            
            print(f"✅ Saved {len(article_data_list)} news articles")
            
            # Update sentiment history
            update_sentiment_history(ticker)
            
            print(f"✅ Updated sentiment history")
            print(f"\n🎉 Analysis complete! Saved as AnalysisRun #{analysis_run.id}")
            
            return analysis_run
            
    except Exception as e:
        print(f"❌ Error saving to database: {e}")
        import traceback
        traceback.print_exc()
        return None


def update_sentiment_history(ticker):
    """Update daily sentiment history aggregate"""
    try:
        today = timezone.now().date()
        
        # Get today's analysis runs
        today_runs = AnalysisRun.objects.filter(
            ticker=ticker,
            timestamp__date=today
        )
        
        if not today_runs.exists():
            return
        
        # Calculate aggregates
        aggregates = today_runs.aggregate(
            avg=Avg('composite_score'),
            min=Min('composite_score'),
            max=Max('composite_score'),
            total_analyses=Count('id'),
            total_articles=Sum('articles_analyzed')
        )
        
        # Get latest stock price for today
        latest_run = today_runs.order_by('-timestamp').first()
        
        # Update or create history entry
        SentimentHistory.objects.update_or_create(
            ticker=ticker,
            date=today,
            defaults={
                'avg_sentiment': aggregates['avg'],
                'min_sentiment': aggregates['min'],
                'max_sentiment': aggregates['max'],
                'total_analyses': aggregates['total_analyses'],
                'total_articles': aggregates.get('total_articles', 0) or 0,
                'closing_price': latest_run.stock_price if latest_run else None,
                'price_change_percent': float(latest_run.price_change_percent) if latest_run and latest_run.price_change_percent else None,
            }
        )
        
    except Exception as e:
        print(f"⚠️ Error updating sentiment history: {e}")


# ============================================================================
# DJANGO MANAGEMENT COMMAND
# ============================================================================

class Command(BaseCommand):
    help = 'Run sentiment analysis and save complete results to AnalysisRun table'

    def add_arguments(self, parser):
        parser.add_argument(
            '--ticker',
            type=str,
            default='AAPL',
            help='Stock ticker to analyze (default: AAPL)'
        )
        parser.add_argument(
            '--interval',
            type=int,
            default=60,
            help='Update interval in seconds (default: 60)'
        )
        parser.add_argument(
            '--once',
            action='store_true',
            help='Run once instead of continuously'
        )

    def handle(self, *args, **options):
        ticker_symbol = options['ticker'].upper()
        interval = options['interval']
        run_once = options['once']
        
        # Check API keys
        if not FINNHUB_API_KEY:
            self.stdout.write(self.style.ERROR(
                '❌ FINNHUB_API_KEY not set! Set it in .env file.'
            ))
            return
        
        if not HUGGINGFACE_API_KEY:
            self.stdout.write(self.style.ERROR(
                '❌ HUGGINGFACE_API_KEY not set! Set it in .env file.'
            ))
            return
        
        # Initialize Finnhub client
        finnhub_client = finnhub.Client(api_key=FINNHUB_API_KEY)
        
        # Get or create ticker
        ticker, created = Ticker.objects.get_or_create(
            symbol=ticker_symbol,
            defaults={'company_name': f'{ticker_symbol} Inc.'}
        )
        if created:
            self.stdout.write(f'✨ Created new ticker: {ticker_symbol}')
        
        self.stdout.write(self.style.SUCCESS(
            f'\n🚀 Starting sentiment analysis for {ticker.symbol}'
        ))
        self.stdout.write('💾 All data will be saved to AnalysisRun table (unified model)\n')
        
        if run_once:
            # Run once
            analysis_run = run_complete_analysis(finnhub_client, ticker)
            if analysis_run:
                self.interpret_score(analysis_run.composite_score)
                self.stdout.write(self.style.SUCCESS(
                    f'\n✅ Analysis complete! View at http://localhost:8000/admin/api/analysisrun/{analysis_run.id}/change/'
                ))
        else:
            # Run continuously
            self.stdout.write(f'⏱️  Update interval: {interval} seconds')
            self.stdout.write('⌨️  Press Ctrl+C to stop\n')
            
            iteration = 0
            
            try:
                while True:
                    iteration += 1
                    self.stdout.write(f"\n{'>'*20} ITERATION {iteration} {'<'*20}")
                    
                    analysis_run = run_complete_analysis(finnhub_client, ticker)
                    if analysis_run:
                        self.interpret_score(analysis_run.composite_score)
                    
                    self.stdout.write(f"\n💤 Next update in {interval} seconds...")
                    time.sleep(interval)
                    
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING(
                    f'\n\n⛔ Monitoring stopped by user.'
                ))
                self.stdout.write(f'📊 Total iterations: {iteration}')
                self.stdout.write(f'📰 Unique articles seen: {len(seen_articles)}')
    
    def interpret_score(self, score):
        """Interpret and display the sentiment score"""
        if score > 50:
            sentiment = self.style.SUCCESS("STRONGLY BULLISH 🚀")
        elif score > 20:
            sentiment = self.style.SUCCESS("BULLISH 📈")
        elif score > -20:
            sentiment = self.style.WARNING("NEUTRAL ➡️")
        elif score > -50:
            sentiment = self.style.ERROR("BEARISH 📉")
        else:
            sentiment = self.style.ERROR("STRONGLY BEARISH 🔻")
        
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(f"Current Sentiment: {sentiment}")
        self.stdout.write(f"Score: {score:.2f}/100")
        self.stdout.write(f"{'='*60}")
