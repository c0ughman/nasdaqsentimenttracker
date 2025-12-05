#!/usr/bin/env python
"""
Test script to check how many news articles Tiingo has available for December 1st, 2025.

This script tests different query approaches to understand Tiingo's news volume.
"""

import os
import sys
import django
from datetime import datetime, date

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

def test_tiingo_news_volume():
    """Test Tiingo News API to see how many articles are available."""

    try:
        from tiingo import TiingoClient
    except ImportError:
        print("❌ Tiingo library not installed. Install with: pip install tiingo")
        return

    # Get API key from environment
    TIINGO_API_KEY = os.getenv('TIINGO_API_KEY', '')
    if not TIINGO_API_KEY:
        print("❌ TIINGO_API_KEY not set in environment")
        return

    print("=" * 80)
    print("TIINGO NEWS VOLUME TEST - December 1st, 2025")
    print("=" * 80)
    print(f"API Key: {TIINGO_API_KEY[:10]}...{TIINGO_API_KEY[-4:]}")
    print()

    # Initialize client
    config = {
        'api_key': TIINGO_API_KEY,
        'session': True
    }
    client = TiingoClient(config)
    print("✅ Tiingo client initialized")
    print()

    # Test different query approaches
    today = date(2025, 12, 1)
    today_str = today.strftime('%Y-%m-%d')

    print("-" * 80)
    print("TEST 1: Query with NO tickers (if supported)")
    print("-" * 80)
    try:
        # Try to get news without any ticker filter
        news = client.get_news(
            startDate=today_str,
            endDate=today_str,
            limit=10000  # Max limit
        )

        if news and isinstance(news, list):
            print(f"✅ SUCCESS: Retrieved {len(news)} articles")
            if len(news) > 0:
                print(f"\nSample article:")
                article = news[0]
                print(f"  Title: {article.get('title', 'N/A')}")
                print(f"  Published: {article.get('publishedDate', 'N/A')}")
                print(f"  Source: {article.get('source', 'N/A')}")
                print(f"  Tickers: {article.get('tickers', [])}")
        else:
            print(f"⚠️  No articles returned (type: {type(news).__name__})")

    except TypeError as e:
        print(f"❌ FAILED: {e}")
        print("   (Tiingo likely requires tickers parameter)")
    except Exception as e:
        print(f"❌ ERROR: {e}")

    print()
    print("-" * 80)
    print("TEST 2: Query with a broad ticker (QQQ - NASDAQ-100 ETF)")
    print("-" * 80)
    try:
        news = client.get_news(
            tickers=['QQQ'],
            startDate=today_str,
            endDate=today_str,
            limit=10000
        )

        if news and isinstance(news, list):
            print(f"✅ Retrieved {len(news)} articles for QQQ")
            print(f"   Date range: {today_str}")
        else:
            print(f"⚠️  No articles returned")

    except Exception as e:
        print(f"❌ ERROR: {e}")

    print()
    print("-" * 80)
    print("TEST 3: Query top 40 NASDAQ stocks")
    print("-" * 80)

    TOP_TICKERS = [
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'AVGO',
        'COST', 'NFLX', 'AMD', 'PEP', 'ADBE', 'CSCO', 'CMCSA', 'INTC',
        'TMUS', 'QCOM', 'INTU', 'TXN', 'AMGN', 'HON', 'AMAT', 'SBUX',
        'ISRG', 'BKNG', 'ADP', 'GILD', 'ADI', 'VRTX', 'MDLZ', 'REGN',
        'LRCX', 'PANW', 'MU', 'PYPL', 'SNPS', 'KLAC', 'CDNS', 'MELI'
    ]

    try:
        news = client.get_news(
            tickers=TOP_TICKERS,
            startDate=today_str,
            endDate=today_str,
            limit=10000
        )

        if news and isinstance(news, list):
            print(f"✅ Retrieved {len(news)} articles for top 40 NASDAQ stocks")

            # Count unique articles
            unique_urls = set()
            for article in news:
                url = article.get('url', '')
                if url:
                    unique_urls.add(url)

            print(f"   Unique articles (by URL): {len(unique_urls)}")
            print(f"   Date range: {today_str}")

            # Show sample
            if len(news) > 0:
                print(f"\nRecent articles:")
                for i, article in enumerate(news[:5], 1):
                    print(f"  {i}. {article.get('title', 'N/A')[:70]}...")
                    print(f"     Published: {article.get('publishedDate', 'N/A')}")
                    print(f"     Tickers: {', '.join(article.get('tickers', [])[:3])}")
                    print()
        else:
            print(f"⚠️  No articles returned")

    except Exception as e:
        print(f"❌ ERROR: {e}")

    print()
    print("-" * 80)
    print("TEST 4: Query WITHOUT date filter (to see latest available)")
    print("-" * 80)
    try:
        news = client.get_news(
            tickers=TOP_TICKERS,
            limit=1000  # Get latest 1000
        )

        if news and isinstance(news, list):
            print(f"✅ Retrieved {len(news)} latest articles (no date filter)")

            # Analyze date distribution
            from collections import Counter
            dates = []
            for article in news:
                pub_date = article.get('publishedDate', '')
                if pub_date:
                    # Extract just the date part
                    date_part = pub_date[:10]  # YYYY-MM-DD
                    dates.append(date_part)

            date_counts = Counter(dates)
            print(f"\nDate distribution (top 10 days):")
            for date_str, count in date_counts.most_common(10):
                print(f"  {date_str}: {count} articles")

            # Check if today's date is present
            if today_str in dates:
                today_count = dates.count(today_str)
                print(f"\n✅ December 1st, 2025: {today_count} articles found in latest 1000")
            else:
                print(f"\n⚠️  December 1st, 2025 NOT found in latest 1000 articles")
                print(f"   Most recent date: {max(dates) if dates else 'N/A'}")
        else:
            print(f"⚠️  No articles returned")

    except Exception as e:
        print(f"❌ ERROR: {e}")

    print()
    print("=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)


if __name__ == '__main__':
    test_tiingo_news_volume()
