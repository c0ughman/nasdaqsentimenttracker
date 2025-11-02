"""
Reddit Sentiment Analyzer
Analyzes Reddit posts and comments using FinBERT (adapted from news sentiment analyzer)
"""

import hashlib
import os
import time
import requests
from datetime import datetime, timedelta
from django.utils import timezone
from django.db import transaction

from api.models import Ticker, RedditPost, RedditComment, RedditAnalysisRun
from .reddit_config import REDDIT_CACHE_DURATION_MINUTES

# Get API keys and sentiment provider
HUGGINGFACE_API_KEY = os.getenv('HUGGINGFACE_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
SENTIMENT_PROVIDER = os.getenv('SENTIMENT_PROVIDER', 'huggingface').lower()  # 'openai' or 'huggingface'


def analyze_sentiment_finbert_api(text):
    """Analyze sentiment using FinBERT via HuggingFace API (single text)"""
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


def analyze_sentiment_openai_api(text):
    """Analyze sentiment using OpenAI GPT-4o-mini (single text)"""
    from openai import OpenAI

    client = OpenAI(api_key=OPENAI_API_KEY)
    text = text[:8000]  # GPT-4o-mini supports longer context

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a financial sentiment analyzer for social media. Analyze the sentiment and respond ONLY with a single number between -1.0 (very negative) and +1.0 (very positive). Do not include any other text."
                },
                {
                    "role": "user",
                    "content": f"Analyze the sentiment:\n\n{text}"
                }
            ],
            max_tokens=10,
            temperature=0
        )

        sentiment_text = response.choices[0].message.content.strip()
        sentiment_score = float(sentiment_text)
        return max(-1.0, min(1.0, sentiment_score))

    except Exception as e:
        print(f"  ⚠️ Error analyzing sentiment with OpenAI: {e}")
        return 0.0


def analyze_sentiment_api(text):
    """
    Factory function: Route to the appropriate sentiment API based on SENTIMENT_PROVIDER
    Returns sentiment score from -1 to +1
    """
    if SENTIMENT_PROVIDER == 'openai':
        return analyze_sentiment_openai_api(text)
    else:
        return analyze_sentiment_finbert_api(text)


# Subreddit credibility scores (similar to news source credibility)
SUBREDDIT_CREDIBILITY = {
    'stocks': 0.85,
    'StockMarket': 0.85,
    'investing': 0.90,
    'wallstreetbets': 0.65,  # Lower due to meme nature
    'options': 0.75,
    'DueDiligence': 0.90,
    'ValueInvesting': 0.90,
    'dividends': 0.85,
    'UndervaluedStocks': 0.80,
    'SPACs': 0.70,
    'pennystocks': 0.60,  # Lower credibility
    'RobinHood': 0.65,
    'trading': 0.75,
    'securityanalysis': 0.90,
    'EducatedInvesting': 0.85,
    'greeninvestor': 0.75,
    'investing_discussion': 0.80,
    'smallstreetbets': 0.65,
    'Weedstocks': 0.70,
    'stocktrader': 0.75,
}


def get_subreddit_credibility(subreddit_name):
    """Get credibility score for a subreddit"""
    return SUBREDDIT_CREDIBILITY.get(subreddit_name, 0.5)


def calculate_recency_weight(created_utc):
    """
    Calculate recency weight (more recent = higher weight).
    Reddit posts decay faster than news.

    Args:
        created_utc: Datetime when post was created

    Returns:
        Float weight (1.0 for very recent, decays to 0.1)
    """
    hours_old = (timezone.now() - created_utc).total_seconds() / 3600

    if hours_old < 1:
        return 1.0
    elif hours_old < 6:
        return 0.9
    elif hours_old < 12:
        return 0.7
    elif hours_old < 24:
        return 0.5
    else:
        return 0.3


def calculate_novelty_score(post_score, num_comments):
    """
    Calculate novelty/engagement score based on Reddit metrics.

    Args:
        post_score: Reddit post score (upvotes - downvotes)
        num_comments: Number of comments

    Returns:
        Float score (1.0 to 3.0, higher = more engaging)
    """
    # Normalize score (viral posts get higher novelty)
    if post_score > 1000:
        score_factor = 2.5
    elif post_score > 500:
        score_factor = 2.0
    elif post_score > 100:
        score_factor = 1.5
    elif post_score > 50:
        score_factor = 1.2
    else:
        score_factor = 1.0

    # Comments indicate engagement
    if num_comments > 500:
        comment_factor = 1.3
    elif num_comments > 100:
        comment_factor = 1.2
    elif num_comments > 50:
        comment_factor = 1.1
    else:
        comment_factor = 1.0

    return min(score_factor * comment_factor, 3.0)


def calculate_surprise_factor(base_sentiment, post_score):
    """
    Calculate surprise factor based on sentiment strength and engagement.

    Args:
        base_sentiment: FinBERT sentiment (-1 to 1)
        post_score: Reddit post score

    Returns:
        Float multiplier (0.5 to 2.0)
    """
    # Strong sentiment + high engagement = higher surprise
    sentiment_strength = abs(base_sentiment)

    if sentiment_strength > 0.8 and post_score > 500:
        return 2.0
    elif sentiment_strength > 0.6 and post_score > 100:
        return 1.5
    elif sentiment_strength > 0.4:
        return 1.2
    else:
        return 1.0


def analyze_reddit_post(post_data, ticker_obj):
    """
    Analyze sentiment of a single Reddit post (title + body).

    Args:
        post_data: Dictionary with post information
        ticker_obj: Ticker model instance

    Returns:
        Dictionary with sentiment scores and metadata
    """
    # Combine title and body for sentiment analysis
    full_text = f"{post_data['title']} {post_data['body']}"

    # Get sentiment from configured provider
    base_sentiment = analyze_sentiment_api(full_text)

    # Calculate component scores
    recency_weight = calculate_recency_weight(post_data['created_utc'])
    novelty_score = calculate_novelty_score(post_data['score'], post_data['num_comments'])
    source_credibility = get_subreddit_credibility(post_data['subreddit'])
    surprise_factor = calculate_surprise_factor(base_sentiment, post_data['score'])

    # Calculate final post score (scale to -100 to 100)
    post_score = (
        base_sentiment * 100 *
        surprise_factor *
        novelty_score *
        source_credibility *
        recency_weight
    )

    return {
        'post_id': post_data['post_id'],
        'base_sentiment': base_sentiment,
        'recency_weight': recency_weight,
        'novelty_score': novelty_score,
        'source_credibility': source_credibility,
        'surprise_factor': surprise_factor,
        'post_score': post_score,
        'full_text': full_text,
        'is_cached': False,
    }


def analyze_reddit_comment(comment_data):
    """
    Analyze sentiment of a Reddit comment.

    Args:
        comment_data: Dictionary with comment information

    Returns:
        Dictionary with sentiment and weighted score
    """
    # Get sentiment from configured provider
    base_sentiment = analyze_sentiment_api(comment_data['body'])

    # Weight comment by its score (upvotes indicate agreement/importance)
    # Normalize comment score (Reddit comments can have huge scores)
    normalized_score = min(comment_data['score'] / 100.0, 10.0)  # Cap at 10x multiplier

    comment_score_weighted = base_sentiment * (1 + normalized_score)

    return {
        'comment_id': comment_data['comment_id'],
        'base_sentiment': base_sentiment,
        'comment_score_weighted': comment_score_weighted,
        'is_cached': False,
    }


def save_reddit_post(post_data, sentiment_data, ticker_obj, analysis_run=None):
    """Save RedditPost to database"""
    try:
        # Check if post already exists
        existing = RedditPost.objects.filter(post_id=post_data['post_id']).first()

        if existing:
            # Update sentiment if not analyzed yet
            if not existing.is_analyzed:
                existing.base_sentiment = sentiment_data['base_sentiment']
                existing.surprise_factor = sentiment_data['surprise_factor']
                existing.novelty_score = sentiment_data['novelty_score']
                existing.source_credibility = sentiment_data['source_credibility']
                existing.recency_weight = sentiment_data['recency_weight']
                existing.post_score = sentiment_data['post_score']
                existing.is_analyzed = True
                existing.save()
            return existing, True  # True = cached

        # Create new post
        reddit_post = RedditPost.objects.create(
            ticker=ticker_obj,
            analysis_run=analysis_run,
            post_id=post_data['post_id'],
            subreddit=post_data['subreddit'],
            title=post_data['title'],
            body=post_data['body'],
            author=post_data['author'],
            url=post_data['url'],
            score=post_data['score'],
            upvote_ratio=post_data.get('upvote_ratio'),
            num_comments=post_data['num_comments'],
            created_utc=post_data['created_utc'],
            content_hash=post_data['content_hash'],
            is_relevant=post_data['is_relevant'],
            mentions_nasdaq=post_data['mentions_nasdaq'],
            mentions_stock_tickers=post_data['mentions_stock_tickers'],
            base_sentiment=sentiment_data['base_sentiment'],
            surprise_factor=sentiment_data['surprise_factor'],
            novelty_score=sentiment_data['novelty_score'],
            source_credibility=sentiment_data['source_credibility'],
            recency_weight=sentiment_data['recency_weight'],
            post_score=sentiment_data['post_score'],
            is_analyzed=True,
        )

        return reddit_post, False  # False = not cached

    except Exception as e:
        print(f"    ⚠️  Error saving post: {e}")
        return None, False


def save_reddit_comment(comment_data, sentiment_data, post_obj, ticker_obj):
    """Save RedditComment to database"""
    try:
        # Check if comment already exists
        existing = RedditComment.objects.filter(comment_id=comment_data['comment_id']).first()

        if existing:
            return existing, True  # cached

        # Create new comment
        reddit_comment = RedditComment.objects.create(
            post=post_obj,
            ticker=ticker_obj,
            comment_id=comment_data['comment_id'],
            body=comment_data['body'],
            author=comment_data['author'],
            score=comment_data['score'],
            is_submitter=comment_data['is_submitter'],
            depth=comment_data['depth'],
            created_utc=comment_data['created_utc'],
            content_hash=comment_data['content_hash'],
            base_sentiment=sentiment_data['base_sentiment'],
            comment_score_weighted=sentiment_data['comment_score_weighted'],
            is_analyzed=True,
        )

        return reddit_comment, False  # not cached

    except Exception as e:
        print(f"    ⚠️  Error saving comment: {e}")
        return None, False


def analyze_reddit_content_batch(posts_data, comments_data, ticker_obj):
    """
    OPTIMIZED: Batch analyze Reddit posts and comments with minimal API calls.

    Args:
        posts_data: List of post dictionaries
        comments_data: List of comment dictionaries
        ticker_obj: Ticker model instance

    Returns:
        Dictionary with analyzed posts, comments, and composite score
    """
    print(f"\n🔴 REDDIT: Analyzing {len(posts_data)} posts (FAST MODE)...")

    # Filter only relevant posts
    relevant_posts = [p for p in posts_data if p.get('is_relevant', False)]

    if not relevant_posts:
        print(f"  ⚠️  No relevant posts found")
        return {
            'composite_score': 0.0,
            'posts_analyzed': 0,
            'comments_analyzed': 0,
        }

    # Check cache for existing posts (skip sentiment analysis if already done)
    posts_to_analyze = []
    cached_posts = []

    for post_data in relevant_posts[:20]:  # Limit to 20 posts max
        existing = RedditPost.objects.filter(post_id=post_data['post_id']).first()
        if existing and existing.base_sentiment is not None:
            cached_posts.append(existing)
        else:
            posts_to_analyze.append(post_data)

    print(f"   {len(cached_posts)} cached, {len(posts_to_analyze)} new posts")

    # BATCHED sentiment analysis for new posts only
    analyzed_posts = []
    if posts_to_analyze:
        # Collect all texts to analyze at once
        post_texts = [f"{p['title']} {p['body']}" for p in posts_to_analyze]

        # Single batched API call for all posts
        provider_name = "OpenAI" if SENTIMENT_PROVIDER == 'openai' else "FinBERT"
        print(f"   🔬 Analyzing {len(post_texts)} posts with {provider_name} (batched)...")
        from .run_nasdaq_sentiment import analyze_sentiment_batch

        try:
            sentiments = analyze_sentiment_batch(post_texts)
        except:
            # Fallback to individual if batch fails
            sentiments = [analyze_sentiment_api(text) for text in post_texts]

        # Process each post with its sentiment
        for i, post_data in enumerate(posts_to_analyze):
            # Safety check: ensure we have a sentiment for this post
            if i >= len(sentiments):
                print(f"    ⚠️  Skipping post {i+1} - no sentiment available")
                continue

            base_sentiment = sentiments[i]

            # Skip if sentiment analysis failed
            if base_sentiment is None:
                print(f"    ⚠️  Skipping post {i+1} - sentiment analysis failed")
                continue

            # Calculate lightweight scores (skip complex calculations)
            recency_weight = 1.0  # Simplified
            novelty_score = min(post_data['score'] / 100.0, 5.0)  # Simplified
            source_credibility = get_subreddit_credibility(post_data['subreddit'])
            surprise_factor = 1.0  # Simplified

            post_score = base_sentiment * 100 * novelty_score * source_credibility

            # Save to database (simplified)
            try:
                reddit_post = RedditPost.objects.create(
                    ticker=ticker_obj,
                    post_id=post_data['post_id'],
                    subreddit=post_data['subreddit'],
                    title=post_data['title'],
                    body=post_data['body'],
                    author=post_data['author'],
                    url=post_data.get('url', ''),
                    score=post_data['score'],
                    num_comments=post_data['num_comments'],
                    created_utc=post_data['created_utc'],
                    content_hash=post_data.get('content_hash', ''),
                    is_relevant=True,
                    mentions_nasdaq=post_data.get('mentions_nasdaq', False),
                    mentions_stock_tickers=post_data.get('mentions_stock_tickers', ''),
                    base_sentiment=base_sentiment,
                    surprise_factor=surprise_factor,
                    novelty_score=novelty_score,
                    source_credibility=source_credibility,
                    recency_weight=recency_weight,
                    post_score=post_score,
                )
                analyzed_posts.append({'post_score': post_score})
            except:
                pass  # Skip duplicates

    # Add cached post scores
    for cached_post in cached_posts:
        analyzed_posts.append({'post_score': cached_post.post_score or 0})

    # SKIP COMMENTS FOR SPEED (optional: can enable for more accuracy)
    analyzed_comments = []

    # Calculate composite Reddit sentiment
    if analyzed_posts:
        composite_score = sum(p['post_score'] for p in analyzed_posts) / len(analyzed_posts)
    else:
        composite_score = 0.0

    print(f"✅ Reddit analysis complete: {composite_score:+.2f}")
    print(f"   Posts: {len(analyzed_posts)} | Comments: {len(analyzed_comments)} (skipped for speed)")

    return {
        'composite_score': composite_score,
        'posts_analyzed': len(analyzed_posts),
        'comments_analyzed': len(analyzed_comments),
    }
