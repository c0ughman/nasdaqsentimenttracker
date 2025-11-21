"""
Reddit Content Fetcher
Fetches posts and comments from specified subreddits using PRAW
"""

import os
import time
import hashlib
from datetime import datetime, timedelta, timezone
import praw
from dotenv import load_dotenv

from .reddit_config import (
    REDDIT_SUBREDDITS,
    REDDIT_FILTER_KEYWORDS,
    REDDIT_POSTS_LIMIT,
    REDDIT_COMMENTS_LIMIT,
    REDDIT_SUBCOMMENTS_LIMIT,
    REDDIT_REQUEST_DELAY,
    REDDIT_MIN_POST_AGE_MINUTES,
    REDDIT_MIN_UPVOTES,
    REDDIT_MIN_COMMENT_SCORE,
)

# Load environment
load_dotenv()

# Reddit API credentials (add to .env file)
REDDIT_CLIENT_ID = os.getenv('REDDIT_CLIENT_ID')
REDDIT_CLIENT_SECRET = os.getenv('REDDIT_CLIENT_SECRET')
REDDIT_USER_AGENT = os.getenv('REDDIT_USER_AGENT', 'NASDAQ Sentiment Tracker v1.0')
REDDIT_USERNAME = os.getenv('REDDIT_USERNAME')
REDDIT_PASSWORD = os.getenv('REDDIT_PASSWORD')


def init_reddit_client():
    """Initialize PRAW Reddit client"""
    if not all([REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET]):
        print("⚠️  Reddit API credentials not found in .env file")
        print("  Please add REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD")
        return None

    try:
        reddit = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent=REDDIT_USER_AGENT,
            username=REDDIT_USERNAME,
            password=REDDIT_PASSWORD
        )
        # Test connection
        reddit.user.me()
        print(f"✅ Connected to Reddit as u/{reddit.user.me().name}")
        return reddit
    except Exception as e:
        print(f"⚠️  Failed to connect to Reddit: {e}")
        return None


def check_keyword_relevance(text, keywords=REDDIT_FILTER_KEYWORDS):
    """
    Check if text contains any relevant keywords.

    Args:
        text: Text to check (title, body, comment)
        keywords: Set of keywords to search for

    Returns:
        Boolean indicating if text is relevant
    """
    if not text:
        return False

    text_lower = text.lower()

    # Check if any keyword appears in the text
    for keyword in keywords:
        if keyword in text_lower:
            return True

    return False


def extract_stock_tickers(text):
    """
    Extract mentioned stock tickers from text.
    Looks for patterns like $AAPL, TSLA, etc.

    Returns:
        Set of ticker symbols mentioned
    """
    import re

    if not text:
        return set()

    # Top NASDAQ tickers to look for
    nasdaq_tickers = {
        'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'GOOG', 'AMZN', 'META', 'TSLA',
        'AVGO', 'COST', 'NFLX', 'ASML', 'AMD', 'ADBE', 'PEP', 'CSCO',
        'TMUS', 'INTC', 'CMCSA', 'QCOM', 'INTU', 'QLD', 'QQQ'
    }

    found_tickers = set()

    # Pattern 1: $TICKER format
    dollar_tickers = re.findall(r'\$([A-Z]{1,5})\b', text)
    found_tickers.update(t for t in dollar_tickers if t in nasdaq_tickers)

    # Pattern 2: Standalone ticker mentions (with word boundaries)
    for ticker in nasdaq_tickers:
        pattern = r'\b' + ticker + r'\b'
        if re.search(pattern, text, re.IGNORECASE):
            found_tickers.add(ticker)

    return found_tickers


def create_content_hash(text):
    """Create MD5 hash of content for deduplication"""
    return hashlib.md5(text.encode('utf-8')).hexdigest()


def fetch_subreddit_posts(reddit, subreddit_name, limit=REDDIT_POSTS_LIMIT):
    """
    Fetch hot posts from a subreddit.

    Args:
        reddit: PRAW Reddit instance
        subreddit_name: Name of subreddit (without r/)
        limit: Number of posts to fetch

    Returns:
        List of post dictionaries with relevant data
    """
    try:
        subreddit = reddit.subreddit(subreddit_name)
        posts_data = []

        # Fetch hot posts
        for post in subreddit.hot(limit=limit):
            # Skip stickied posts
            if post.stickied:
                continue

            # Check minimum post age (avoid very new posts that might be spam)
            post_age_minutes = (datetime.now(timezone.utc).timestamp() - post.created_utc) / 60
            if post_age_minutes < REDDIT_MIN_POST_AGE_MINUTES:
                continue

            # Check minimum upvotes
            if post.score < REDDIT_MIN_UPVOTES:
                continue

            # Combine title + body for keyword filtering
            full_text = f"{post.title} {post.selftext}"

            # Check if post is relevant
            is_relevant = check_keyword_relevance(full_text)

            # Extract mentioned tickers
            mentioned_tickers = extract_stock_tickers(full_text)

            # Create post data
            post_data = {
                'post_id': post.id,
                'subreddit': subreddit_name,
                'title': post.title,
                'body': post.selftext,
                'author': str(post.author) if post.author else '[deleted]',
                'url': f"https://reddit.com{post.permalink}",
                'score': post.score,
                'upvote_ratio': post.upvote_ratio,
                'num_comments': post.num_comments,
                'created_utc': datetime.fromtimestamp(post.created_utc, tz=timezone.utc),
                'content_hash': create_content_hash(f"{post.title}{post.selftext}"),
                'is_relevant': is_relevant,
                'mentions_nasdaq': 'nasdaq' in full_text.lower() or 'qqq' in full_text.lower(),
                'mentions_stock_tickers': ','.join(sorted(mentioned_tickers)),
                'praw_object': post  # Keep for fetching comments
            }

            posts_data.append(post_data)

        print(f"  ✓ r/{subreddit_name}: Fetched {len(posts_data)} posts")
        return posts_data

    except Exception as e:
        print(f"  ⚠️  Error fetching r/{subreddit_name}: {e}")
        return []


def fetch_post_comments(post, max_comments=REDDIT_COMMENTS_LIMIT, max_subcomments=REDDIT_SUBCOMMENTS_LIMIT):
    """
    Fetch top comments and their replies from a post.

    Args:
        post: PRAW submission object
        max_comments: Max top-level comments to fetch
        max_subcomments: Max replies per comment

    Returns:
        List of comment dictionaries
    """
    comments_data = []

    try:
        # Replace "MoreComments" objects with actual comments
        post.comments.replace_more(limit=0)

        # Get top comments sorted by score
        top_comments = sorted(post.comments, key=lambda c: c.score, reverse=True)[:max_comments]

        for comment in top_comments:
            # Skip if comment doesn't meet minimum score
            if comment.score < REDDIT_MIN_COMMENT_SCORE:
                continue

            # Create comment data
            comment_data = {
                'comment_id': comment.id,
                'parent_comment_id': None,
                'body': comment.body,
                'author': str(comment.author) if comment.author else '[deleted]',
                'score': comment.score,
                'is_submitter': comment.is_submitter,
                'depth': 0,
                'created_utc': datetime.fromtimestamp(comment.created_utc, tz=timezone.utc),
                'content_hash': create_content_hash(comment.body),
            }

            comments_data.append(comment_data)

            # Fetch top subcomments (replies)
            if hasattr(comment, 'replies'):
                replies = sorted(comment.replies, key=lambda r: r.score, reverse=True)[:max_subcomments]

                for reply in replies:
                    if reply.score < REDDIT_MIN_COMMENT_SCORE:
                        continue

                    reply_data = {
                        'comment_id': reply.id,
                        'parent_comment_id': comment.id,
                        'body': reply.body,
                        'author': str(reply.author) if reply.author else '[deleted]',
                        'score': reply.score,
                        'is_submitter': reply.is_submitter,
                        'depth': 1,
                        'created_utc': datetime.fromtimestamp(reply.created_utc, tz=timezone.utc),
                        'content_hash': create_content_hash(reply.body),
                    }

                    comments_data.append(reply_data)

        return comments_data

    except Exception as e:
        print(f"    ⚠️  Error fetching comments: {e}")
        return []


def fetch_all_reddit_content():
    """
    Fetch posts and comments from all configured subreddits.

    Returns:
        Dictionary with 'posts' and 'comments' lists
    """
    print(f"\n🔴 REDDIT: Fetching content from {len(REDDIT_SUBREDDITS)} subreddits...")

    reddit = init_reddit_client()
    if not reddit:
        return {'posts': [], 'comments': []}

    all_posts = []
    all_comments = []
    relevant_posts_count = 0

    for subreddit_name in REDDIT_SUBREDDITS:
        # Fetch posts from subreddit
        posts = fetch_subreddit_posts(reddit, subreddit_name)
        all_posts.extend(posts)

        # For relevant posts, fetch comments
        for post in posts:
            if post['is_relevant']:
                relevant_posts_count += 1
                comments = fetch_post_comments(post['praw_object'])

                # Associate comments with post
                for comment in comments:
                    comment['post_id'] = post['post_id']

                all_comments.extend(comments)
                print(f"    ✓ Fetched {len(comments)} comments from post: {post['title'][:50]}...")

        # Rate limiting
        time.sleep(REDDIT_REQUEST_DELAY)

    print(f"\n✅ Reddit fetch complete:")
    print(f"   Total posts: {len(all_posts)}")
    print(f"   Relevant posts: {relevant_posts_count}")
    print(f"   Comments fetched: {len(all_comments)}")

    return {
        'posts': all_posts,
        'comments': all_comments
    }
