#!/usr/bin/env python
"""Quick data export script - run directly without Django management command"""
import os
import csv
from datetime import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from api.models import AnalysisRun, TickerContribution, NewsArticle, RedditPost, Ticker

print("📊 Exporting NASDAQ Sentiment Data...")
print("=" * 80)

# Export Analysis Runs
print("\n1️⃣  Exporting Analysis Runs...")
runs = AnalysisRun.objects.all().select_related('ticker').order_by('-timestamp')
with open('/tmp/analysis_runs.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow([
        'id', 'ticker', 'timestamp', 'composite_score', 'sentiment_label',
        'stock_price', 'price_change_percent', 'articles_analyzed',
        'reddit_sentiment', 'reddit_posts_analyzed', 'technical_composite_score',
        'analyst_recommendations_score', 'analyst_recommendations_count',
        'rsi_14', 'macd', 'bb_upper', 'bb_middle', 'bb_lower'
    ])
    for run in runs:
        writer.writerow([
            run.id, run.ticker.symbol, run.timestamp, run.composite_score, run.sentiment_label,
            run.stock_price, run.price_change_percent, run.articles_analyzed,
            run.reddit_sentiment, run.reddit_posts_analyzed, run.technical_composite_score,
            run.analyst_recommendations_score, run.analyst_recommendations_count,
            run.rsi_14, run.macd, run.bb_upper, run.bb_middle, run.bb_lower
        ])
print(f"   ✓ Exported {runs.count()} analysis runs")

# Export Ticker Contributions
print("\n2️⃣  Exporting Ticker Contributions...")
contribs = TickerContribution.objects.all().select_related('ticker', 'analysis_run').order_by('-created_at')
with open('/tmp/ticker_contributions.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['id', 'analysis_run_id', 'ticker', 'sentiment_score', 'market_cap_weight', 'weighted_contribution', 'articles_analyzed'])
    for c in contribs:
        writer.writerow([c.id, c.analysis_run.id, c.ticker.symbol, c.sentiment_score, c.market_cap_weight, c.weighted_contribution, c.articles_analyzed])
print(f"   ✓ Exported {contribs.count()} ticker contributions")

# Export News Articles
print("\n3️⃣  Exporting News Articles...")
articles = NewsArticle.objects.all().select_related('ticker').order_by('-published_at')
with open('/tmp/news_articles.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['id', 'ticker', 'headline', 'source', 'published_at', 'base_sentiment', 'article_score', 'is_analyzed'])
    for a in articles:
        writer.writerow([a.id, a.ticker.symbol if a.ticker else 'MARKET', a.headline[:100], a.source, a.published_at, a.base_sentiment, a.article_score, a.is_analyzed])
print(f"   ✓ Exported {articles.count()} news articles")

# Export Reddit Posts
print("\n4️⃣  Exporting Reddit Posts...")
posts = RedditPost.objects.all().order_by('-created_utc')
with open('/tmp/reddit_posts.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['id', 'subreddit', 'title', 'score', 'base_sentiment', 'post_score', 'is_relevant', 'created_utc'])
    for p in posts:
        writer.writerow([p.id, p.subreddit, p.title[:100], p.score, p.base_sentiment, p.post_score, p.is_relevant, p.created_utc])
print(f"   ✓ Exported {posts.count()} Reddit posts")

print("\n" + "=" * 80)
print("✅ Export Complete!")
print("\nFiles created in /tmp/:")
print("  - analysis_runs.csv")
print("  - ticker_contributions.csv")
print("  - news_articles.csv")
print("  - reddit_posts.csv")
print("\nTo download, run:")
print("  railway ssh 'cat /tmp/analysis_runs.csv' > analysis_runs.csv")
print("  railway ssh 'cat /tmp/ticker_contributions.csv' > ticker_contributions.csv")
print("  railway ssh 'cat /tmp/news_articles.csv' > news_articles.csv")
print("  railway ssh 'cat /tmp/reddit_posts.csv' > reddit_posts.csv")

