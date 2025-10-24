"""
Export all NASDAQ sentiment analysis data to CSV files
Usage: python manage.py export_all_data
"""
import csv
import os
from datetime import datetime
from django.core.management.base import BaseCommand
from api.models import (
    AnalysisRun, TickerContribution, NewsArticle, 
    RedditPost, RedditComment, Ticker
)


class Command(BaseCommand):
    help = 'Export all sentiment analysis data to CSV files'

    def handle(self, *args, **options):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        export_dir = f'/tmp/nasdaq_export_{timestamp}'
        os.makedirs(export_dir, exist_ok=True)
        
        self.stdout.write(self.style.SUCCESS(f'\n📊 Exporting all data to: {export_dir}\n'))
        
        # Export Analysis Runs
        self.export_analysis_runs(export_dir)
        
        # Export Ticker Contributions
        self.export_ticker_contributions(export_dir)
        
        # Export News Articles
        self.export_news_articles(export_dir)
        
        # Export Reddit Data
        self.export_reddit_posts(export_dir)
        self.export_reddit_comments(export_dir)
        
        # Export Tickers
        self.export_tickers(export_dir)
        
        # Create summary report
        self.create_summary_report(export_dir)
        
        self.stdout.write(self.style.SUCCESS(f'\n✅ Export complete! Files saved to: {export_dir}\n'))
        self.stdout.write(self.style.WARNING(f'📥 Download with: railway ssh "cat {export_dir}/*.csv" > local_file.csv\n'))
        self.stdout.write(self.style.WARNING(f'📥 Or copy entire directory: railway ssh "tar -czf /tmp/export.tar.gz {export_dir}" && railway ssh "cat /tmp/export.tar.gz" > export.tar.gz\n'))

    def export_analysis_runs(self, export_dir):
        """Export all analysis runs with full details"""
        self.stdout.write('📈 Exporting analysis runs...')
        
        filename = os.path.join(export_dir, 'analysis_runs.csv')
        runs = AnalysisRun.objects.all().select_related('ticker').order_by('-timestamp')
        
        with open(filename, 'w', newline='') as csvfile:
            fieldnames = [
                'id', 'ticker_symbol', 'timestamp', 'composite_score', 'sentiment_label',
                'avg_base_sentiment', 'avg_surprise_factor', 'avg_novelty', 
                'avg_source_credibility', 'avg_recency_weight',
                'stock_price', 'price_change_percent', 'price_open', 'price_high', 'price_low', 'volume',
                'articles_analyzed', 'cached_articles', 'new_articles',
                'rsi_14', 'macd', 'macd_signal', 'macd_histogram',
                'bb_upper', 'bb_middle', 'bb_lower',
                'sma_20', 'sma_50', 'ema_9', 'ema_20',
                'stoch_k', 'stoch_d', 'williams_r', 'atr_14',
                'reddit_sentiment', 'reddit_posts_analyzed', 'reddit_comments_analyzed',
                'technical_composite_score',
                'analyst_recommendations_score', 'analyst_recommendations_count',
                'analyst_strong_buy', 'analyst_buy', 'analyst_hold', 'analyst_sell', 'analyst_strong_sell',
                'qqq_price'
            ]
            
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for run in runs:
                writer.writerow({
                    'id': run.id,
                    'ticker_symbol': run.ticker.symbol,
                    'timestamp': run.timestamp,
                    'composite_score': run.composite_score,
                    'sentiment_label': run.sentiment_label,
                    'avg_base_sentiment': run.avg_base_sentiment,
                    'avg_surprise_factor': run.avg_surprise_factor,
                    'avg_novelty': run.avg_novelty,
                    'avg_source_credibility': run.avg_source_credibility,
                    'avg_recency_weight': run.avg_recency_weight,
                    'stock_price': run.stock_price,
                    'price_change_percent': run.price_change_percent,
                    'price_open': run.price_open,
                    'price_high': run.price_high,
                    'price_low': run.price_low,
                    'volume': run.volume,
                    'articles_analyzed': run.articles_analyzed,
                    'cached_articles': run.cached_articles,
                    'new_articles': run.new_articles,
                    'rsi_14': run.rsi_14,
                    'macd': run.macd,
                    'macd_signal': run.macd_signal,
                    'macd_histogram': run.macd_histogram,
                    'bb_upper': run.bb_upper,
                    'bb_middle': run.bb_middle,
                    'bb_lower': run.bb_lower,
                    'sma_20': run.sma_20,
                    'sma_50': run.sma_50,
                    'ema_9': run.ema_9,
                    'ema_20': run.ema_20,
                    'stoch_k': run.stoch_k,
                    'stoch_d': run.stoch_d,
                    'williams_r': run.williams_r,
                    'atr_14': run.atr_14,
                    'reddit_sentiment': run.reddit_sentiment,
                    'reddit_posts_analyzed': run.reddit_posts_analyzed,
                    'reddit_comments_analyzed': run.reddit_comments_analyzed,
                    'technical_composite_score': run.technical_composite_score,
                    'analyst_recommendations_score': run.analyst_recommendations_score,
                    'analyst_recommendations_count': run.analyst_recommendations_count,
                    'analyst_strong_buy': run.analyst_strong_buy,
                    'analyst_buy': run.analyst_buy,
                    'analyst_hold': run.analyst_hold,
                    'analyst_sell': run.analyst_sell,
                    'analyst_strong_sell': run.analyst_strong_sell,
                    'qqq_price': run.qqq_price,
                })
        
        self.stdout.write(self.style.SUCCESS(f'  ✓ Exported {runs.count()} analysis runs'))

    def export_ticker_contributions(self, export_dir):
        """Export ticker contributions per analysis run"""
        self.stdout.write('📊 Exporting ticker contributions...')
        
        filename = os.path.join(export_dir, 'ticker_contributions.csv')
        contributions = TickerContribution.objects.all().select_related('ticker', 'analysis_run').order_by('-created_at')
        
        with open(filename, 'w', newline='') as csvfile:
            fieldnames = [
                'id', 'analysis_run_id', 'ticker_symbol', 'created_at',
                'sentiment_score', 'market_cap_weight', 'weighted_contribution', 'articles_analyzed'
            ]
            
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for contrib in contributions:
                writer.writerow({
                    'id': contrib.id,
                    'analysis_run_id': contrib.analysis_run.id,
                    'ticker_symbol': contrib.ticker.symbol,
                    'created_at': contrib.created_at,
                    'sentiment_score': contrib.sentiment_score,
                    'market_cap_weight': contrib.market_cap_weight,
                    'weighted_contribution': contrib.weighted_contribution,
                    'articles_analyzed': contrib.articles_analyzed,
                })
        
        self.stdout.write(self.style.SUCCESS(f'  ✓ Exported {contributions.count()} ticker contributions'))

    def export_news_articles(self, export_dir):
        """Export all news articles"""
        self.stdout.write('📰 Exporting news articles...')
        
        filename = os.path.join(export_dir, 'news_articles.csv')
        articles = NewsArticle.objects.all().select_related('ticker', 'analysis_run').order_by('-published_at')
        
        with open(filename, 'w', newline='') as csvfile:
            fieldnames = [
                'id', 'ticker_symbol', 'analysis_run_id', 'headline', 'summary', 
                'source', 'url', 'published_at', 'fetched_at',
                'base_sentiment', 'surprise_factor', 'novelty_score', 
                'source_credibility', 'recency_weight', 'article_score', 'weighted_contribution',
                'is_analyzed', 'sentiment_cached', 'article_type'
            ]
            
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for article in articles:
                writer.writerow({
                    'id': article.id,
                    'ticker_symbol': article.ticker.symbol if article.ticker else 'MARKET',
                    'analysis_run_id': article.analysis_run.id if article.analysis_run else None,
                    'headline': article.headline,
                    'summary': article.summary,
                    'source': article.source,
                    'url': article.url,
                    'published_at': article.published_at,
                    'fetched_at': article.fetched_at,
                    'base_sentiment': article.base_sentiment,
                    'surprise_factor': article.surprise_factor,
                    'novelty_score': article.novelty_score,
                    'source_credibility': article.source_credibility,
                    'recency_weight': article.recency_weight,
                    'article_score': article.article_score,
                    'weighted_contribution': article.weighted_contribution,
                    'is_analyzed': article.is_analyzed,
                    'sentiment_cached': article.sentiment_cached,
                    'article_type': article.article_type,
                })
        
        self.stdout.write(self.style.SUCCESS(f'  ✓ Exported {articles.count()} news articles'))

    def export_reddit_posts(self, export_dir):
        """Export Reddit posts"""
        self.stdout.write('💬 Exporting Reddit posts...')
        
        filename = os.path.join(export_dir, 'reddit_posts.csv')
        posts = RedditPost.objects.all().select_related('ticker', 'analysis_run').order_by('-created_utc')
        
        with open(filename, 'w', newline='') as csvfile:
            fieldnames = [
                'id', 'post_id', 'ticker_symbol', 'analysis_run_id', 'subreddit',
                'title', 'body', 'author', 'url', 'score', 'upvote_ratio', 'num_comments',
                'created_utc', 'fetched_at',
                'base_sentiment', 'surprise_factor', 'novelty_score', 
                'source_credibility', 'recency_weight', 'post_score', 'weighted_contribution',
                'is_relevant', 'mentions_nasdaq', 'mentions_stock_tickers',
                'is_analyzed', 'sentiment_cached', 'comments_analyzed'
            ]
            
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for post in posts:
                writer.writerow({
                    'id': post.id,
                    'post_id': post.post_id,
                    'ticker_symbol': post.ticker.symbol if post.ticker else None,
                    'analysis_run_id': post.analysis_run.id if post.analysis_run else None,
                    'subreddit': post.subreddit,
                    'title': post.title,
                    'body': post.body[:500] if post.body else '',  # Truncate for CSV
                    'author': post.author,
                    'url': post.url,
                    'score': post.score,
                    'upvote_ratio': post.upvote_ratio,
                    'num_comments': post.num_comments,
                    'created_utc': post.created_utc,
                    'fetched_at': post.fetched_at,
                    'base_sentiment': post.base_sentiment,
                    'surprise_factor': post.surprise_factor,
                    'novelty_score': post.novelty_score,
                    'source_credibility': post.source_credibility,
                    'recency_weight': post.recency_weight,
                    'post_score': post.post_score,
                    'weighted_contribution': post.weighted_contribution,
                    'is_relevant': post.is_relevant,
                    'mentions_nasdaq': post.mentions_nasdaq,
                    'mentions_stock_tickers': post.mentions_stock_tickers,
                    'is_analyzed': post.is_analyzed,
                    'sentiment_cached': post.sentiment_cached,
                    'comments_analyzed': post.comments_analyzed,
                })
        
        self.stdout.write(self.style.SUCCESS(f'  ✓ Exported {posts.count()} Reddit posts'))

    def export_reddit_comments(self, export_dir):
        """Export Reddit comments"""
        self.stdout.write('💬 Exporting Reddit comments...')
        
        filename = os.path.join(export_dir, 'reddit_comments.csv')
        comments = RedditComment.objects.all().select_related('post', 'ticker').order_by('-created_utc')
        
        with open(filename, 'w', newline='') as csvfile:
            fieldnames = [
                'id', 'comment_id', 'post_id', 'ticker_symbol', 'parent_comment_id',
                'body', 'author', 'score', 'is_submitter', 'depth',
                'created_utc', 'fetched_at',
                'base_sentiment', 'comment_score_weighted', 'is_analyzed'
            ]
            
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for comment in comments:
                writer.writerow({
                    'id': comment.id,
                    'comment_id': comment.comment_id,
                    'post_id': comment.post.post_id,
                    'ticker_symbol': comment.ticker.symbol if comment.ticker else None,
                    'parent_comment_id': comment.parent_comment.comment_id if comment.parent_comment else None,
                    'body': comment.body[:500] if comment.body else '',  # Truncate for CSV
                    'author': comment.author,
                    'score': comment.score,
                    'is_submitter': comment.is_submitter,
                    'depth': comment.depth,
                    'created_utc': comment.created_utc,
                    'fetched_at': comment.fetched_at,
                    'base_sentiment': comment.base_sentiment,
                    'comment_score_weighted': comment.comment_score_weighted,
                    'is_analyzed': comment.is_analyzed,
                })
        
        self.stdout.write(self.style.SUCCESS(f'  ✓ Exported {comments.count()} Reddit comments'))

    def export_tickers(self, export_dir):
        """Export ticker information"""
        self.stdout.write('🏢 Exporting tickers...')
        
        filename = os.path.join(export_dir, 'tickers.csv')
        tickers = Ticker.objects.all().order_by('symbol')
        
        with open(filename, 'w', newline='') as csvfile:
            fieldnames = ['id', 'symbol', 'company_name', 'exchange', 'created_at', 'updated_at']
            
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for ticker in tickers:
                writer.writerow({
                    'id': ticker.id,
                    'symbol': ticker.symbol,
                    'company_name': ticker.company_name,
                    'exchange': ticker.exchange,
                    'created_at': ticker.created_at,
                    'updated_at': ticker.updated_at,
                })
        
        self.stdout.write(self.style.SUCCESS(f'  ✓ Exported {tickers.count()} tickers'))

    def create_summary_report(self, export_dir):
        """Create a human-readable summary report"""
        self.stdout.write('📋 Creating summary report...')
        
        filename = os.path.join(export_dir, 'SUMMARY_REPORT.txt')
        
        with open(filename, 'w') as f:
            f.write("=" * 80 + "\n")
            f.write("NASDAQ SENTIMENT TRACKER - DATA EXPORT SUMMARY\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"Export Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            # Database statistics
            f.write("DATABASE STATISTICS:\n")
            f.write("-" * 80 + "\n")
            f.write(f"Total Analysis Runs: {AnalysisRun.objects.count()}\n")
            f.write(f"Total Ticker Contributions: {TickerContribution.objects.count()}\n")
            f.write(f"Total News Articles: {NewsArticle.objects.count()}\n")
            f.write(f"Total Reddit Posts: {RedditPost.objects.count()}\n")
            f.write(f"Total Reddit Comments: {RedditComment.objects.count()}\n")
            f.write(f"Total Tickers Tracked: {Ticker.objects.count()}\n\n")
            
            # Latest analysis
            latest = AnalysisRun.objects.order_by('-timestamp').first()
            if latest:
                f.write("LATEST ANALYSIS RUN:\n")
                f.write("-" * 80 + "\n")
                f.write(f"Timestamp: {latest.timestamp}\n")
                f.write(f"Ticker: {latest.ticker.symbol}\n")
                f.write(f"Composite Score: {latest.composite_score:.2f}\n")
                f.write(f"Sentiment Label: {latest.sentiment_label}\n")
                f.write(f"Stock Price: ${latest.stock_price}\n")
                f.write(f"Articles Analyzed: {latest.articles_analyzed}\n")
                f.write(f"Reddit Posts Analyzed: {latest.reddit_posts_analyzed}\n")
                f.write(f"Technical Composite Score: {latest.technical_composite_score}\n")
                f.write(f"Analyst Recommendations Score: {latest.analyst_recommendations_score}\n\n")
            
            # Files exported
            f.write("EXPORTED FILES:\n")
            f.write("-" * 80 + "\n")
            f.write("1. analysis_runs.csv - All sentiment analysis runs with full details\n")
            f.write("2. ticker_contributions.csv - Individual ticker contributions per run\n")
            f.write("3. news_articles.csv - All news articles with sentiment scores\n")
            f.write("4. reddit_posts.csv - Reddit posts with sentiment analysis\n")
            f.write("5. reddit_comments.csv - Reddit comments with sentiment\n")
            f.write("6. tickers.csv - All tracked tickers\n")
            f.write("7. SUMMARY_REPORT.txt - This file\n\n")
            
            f.write("=" * 80 + "\n")
            f.write("END OF REPORT\n")
            f.write("=" * 80 + "\n")
        
        self.stdout.write(self.style.SUCCESS(f'  ✓ Created summary report'))

