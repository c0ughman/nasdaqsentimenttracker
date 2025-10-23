from django.db import models
from django.contrib.auth.models import User


class Ticker(models.Model):
    """Stock ticker information"""
    symbol = models.CharField(max_length=10, unique=True, db_index=True)
    company_name = models.CharField(max_length=200, blank=True)
    exchange = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['symbol']
        verbose_name = "Ticker"
        verbose_name_plural = "Tickers"
    
    def __str__(self):
        return f"{self.symbol} - {self.company_name}" if self.company_name else self.symbol


class AnalysisRun(models.Model):
    """
    Complete analysis run - stores sentiment score, stock price, and all component scores
    One row per analysis execution per ticker
    """
    ticker = models.ForeignKey(Ticker, on_delete=models.CASCADE, related_name='analysis_runs')
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    
    # SENTIMENT ANALYSIS
    composite_score = models.FloatField(help_text="Final composite sentiment score from -100 to 100")
    sentiment_label = models.CharField(max_length=20, blank=True)
    
    # THE 5 COMPONENT SCORES (aggregated across all articles)
    avg_base_sentiment = models.FloatField(help_text="Average base sentiment (-1 to 1)")
    avg_surprise_factor = models.FloatField(help_text="Average surprise multiplier")
    avg_novelty = models.FloatField(help_text="Average novelty score")
    avg_source_credibility = models.FloatField(help_text="Average source credibility")
    avg_recency_weight = models.FloatField(help_text="Average recency weight")
    
    # STOCK PRICE DATA (captured at time of analysis)
    stock_price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Stock price at analysis time")
    price_open = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    price_high = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    price_low = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    price_change_percent = models.FloatField(null=True, blank=True, help_text="Price change percentage")
    volume = models.BigIntegerField(null=True, blank=True)
    
    # ANALYSIS METADATA
    articles_analyzed = models.IntegerField(default=0)
    cached_articles = models.IntegerField(default=0)
    new_articles = models.IntegerField(default=0)

    # TECHNICAL INDICATORS (from Alpha Vantage - 5min intervals for day trading)
    # All indicators calculated on QQQ (NASDAQ-100 ETF) as proxy

    # RSI (Relative Strength Index) - Overbought/Oversold indicator
    rsi_14 = models.FloatField(null=True, blank=True, help_text="RSI 14-period on 5-min chart (0-100)")

    # MACD (Moving Average Convergence Divergence) - Momentum indicator
    macd = models.FloatField(null=True, blank=True, help_text="MACD line")
    macd_signal = models.FloatField(null=True, blank=True, help_text="MACD signal line")
    macd_histogram = models.FloatField(null=True, blank=True, help_text="MACD histogram")

    # Bollinger Bands - Volatility indicator
    bb_upper = models.FloatField(null=True, blank=True, help_text="Bollinger Band upper band")
    bb_middle = models.FloatField(null=True, blank=True, help_text="Bollinger Band middle band (SMA)")
    bb_lower = models.FloatField(null=True, blank=True, help_text="Bollinger Band lower band")

    # Moving Averages - Trend indicators
    sma_20 = models.FloatField(null=True, blank=True, help_text="Simple Moving Average 20-period on 5-min")
    sma_50 = models.FloatField(null=True, blank=True, help_text="Simple Moving Average 50-period on 5-min")
    ema_9 = models.FloatField(null=True, blank=True, help_text="Exponential Moving Average 9-period on 5-min")
    ema_20 = models.FloatField(null=True, blank=True, help_text="Exponential Moving Average 20-period on 5-min")

    # Stochastic Oscillator - Momentum indicator
    stoch_k = models.FloatField(null=True, blank=True, help_text="Stochastic %K line")
    stoch_d = models.FloatField(null=True, blank=True, help_text="Stochastic %D line (signal)")

    # Williams %R - Overbought/Oversold indicator
    williams_r = models.FloatField(null=True, blank=True, help_text="Williams %R (-100 to 0)")

    # ATR (Average True Range) - Volatility indicator
    atr_14 = models.FloatField(null=True, blank=True, help_text="ATR 14-period on 5-min chart")

    # QQQ price for correlation analysis
    qqq_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="QQQ ETF price at analysis time")

    # REDDIT SENTIMENT (Social Media)
    reddit_sentiment = models.FloatField(null=True, blank=True, help_text="Reddit/social media sentiment score (-100 to 100)")
    reddit_posts_analyzed = models.IntegerField(default=0, help_text="Number of Reddit posts analyzed")
    reddit_comments_analyzed = models.IntegerField(default=0, help_text="Number of Reddit comments analyzed")

    # TECHNICAL INDICATORS COMPOSITE SCORE
    technical_composite_score = models.FloatField(null=True, blank=True, help_text="Technical indicators composite score (-100 to 100)")

    # ANALYST RECOMMENDATIONS (NASDAQ-wide aggregated)
    analyst_recommendations_score = models.FloatField(null=True, blank=True, help_text="Analyst recommendations composite score (-100 to 100)")
    analyst_recommendations_count = models.IntegerField(default=0, help_text="Total number of analyst recommendations analyzed")
    analyst_strong_buy = models.IntegerField(default=0, help_text="Total Strong Buy recommendations")
    analyst_buy = models.IntegerField(default=0, help_text="Total Buy recommendations")
    analyst_hold = models.IntegerField(default=0, help_text="Total Hold recommendations")
    analyst_sell = models.IntegerField(default=0, help_text="Total Sell recommendations")
    analyst_strong_sell = models.IntegerField(default=0, help_text="Total Strong Sell recommendations")

    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Analysis Run"
        verbose_name_plural = "Analysis Runs"
        indexes = [
            models.Index(fields=['ticker', '-timestamp']),
            models.Index(fields=['-timestamp']),
        ]
    
    def __str__(self):
        return f"{self.ticker.symbol} - Score: {self.composite_score:.2f} | Price: ${self.stock_price} @ {self.timestamp.strftime('%Y-%m-%d %H:%M')}"
    
    def save(self, *args, **kwargs):
        """Auto-calculate sentiment label based on composite score"""
        if self.composite_score > 50:
            self.sentiment_label = 'STRONGLY_BULLISH'
        elif self.composite_score > 20:
            self.sentiment_label = 'BULLISH'
        elif self.composite_score > -20:
            self.sentiment_label = 'NEUTRAL'
        elif self.composite_score > -50:
            self.sentiment_label = 'BEARISH'
        else:
            self.sentiment_label = 'STRONGLY_BEARISH'
        super().save(*args, **kwargs)


class NewsArticle(models.Model):
    """News article with sentiment analysis - linked to analysis run"""
    ticker = models.ForeignKey(Ticker, on_delete=models.CASCADE, related_name='news_articles')
    analysis_run = models.ForeignKey(AnalysisRun, on_delete=models.SET_NULL, null=True, blank=True, related_name='articles')
    
    # Article information
    headline = models.TextField()
    summary = models.TextField(blank=True)
    source = models.CharField(max_length=100)
    url = models.URLField(max_length=500, blank=True)
    published_at = models.DateTimeField(db_index=True)
    fetched_at = models.DateTimeField(auto_now_add=True)
    
    # Unique identifier to prevent duplicates
    article_hash = models.CharField(max_length=32, unique=True, db_index=True)
    
    # Article type: 'company' for ticker-specific, 'market' for general market news
    article_type = models.CharField(max_length=20, default='company', db_index=True)
    
    # Sentiment analysis results
    base_sentiment = models.FloatField(help_text="Base sentiment from -1 to 1")
    surprise_factor = models.FloatField(default=1.0)
    novelty_score = models.FloatField(default=1.0)
    source_credibility = models.FloatField(default=0.5)
    recency_weight = models.FloatField(default=1.0)
    article_score = models.FloatField(help_text="Calculated article score")
    weighted_contribution = models.FloatField(help_text="Contribution to composite score")
    
    # Status
    is_analyzed = models.BooleanField(default=False)
    sentiment_cached = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-published_at']
        verbose_name = "News Article"
        verbose_name_plural = "News Articles"
        indexes = [
            models.Index(fields=['ticker', '-published_at']),
            models.Index(fields=['article_hash']),
            models.Index(fields=['article_type']),
        ]
    
    def __str__(self):
        return f"{self.ticker.symbol} - {self.headline[:50]}... ({self.published_at.strftime('%Y-%m-%d')})"


class TickerContribution(models.Model):
    """Tracks individual ticker contributions to NASDAQ composite score"""
    analysis_run = models.ForeignKey(AnalysisRun, on_delete=models.CASCADE, related_name='ticker_contributions')
    ticker = models.ForeignKey(Ticker, on_delete=models.CASCADE)
    
    # Contribution metrics
    sentiment_score = models.FloatField(help_text="Individual ticker sentiment score")
    market_cap_weight = models.FloatField(help_text="Market cap weight used (0.0 to 1.0)")
    weighted_contribution = models.FloatField(help_text="Contribution to composite (score × weight)")
    
    # Article counts
    articles_analyzed = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Ticker Contribution"
        verbose_name_plural = "Ticker Contributions"
        indexes = [
            models.Index(fields=['analysis_run', 'ticker']),
        ]
    
    def __str__(self):
        return f"{self.ticker.symbol}: {self.sentiment_score:.2f} (weight: {self.market_cap_weight:.1%})"


class SentimentHistory(models.Model):
    """Aggregated historical sentiment data for charting/analysis"""
    ticker = models.ForeignKey(Ticker, on_delete=models.CASCADE, related_name='sentiment_history')
    date = models.DateField(db_index=True)
    
    # Daily aggregates
    avg_sentiment = models.FloatField(help_text="Average sentiment score for the day")
    min_sentiment = models.FloatField(help_text="Minimum sentiment score")
    max_sentiment = models.FloatField(help_text="Maximum sentiment score")
    total_analyses = models.IntegerField(default=0, help_text="Number of analysis runs")
    total_articles = models.IntegerField(default=0)
    
    # Stock price on that day
    closing_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    price_change_percent = models.FloatField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-date']
        verbose_name = "Sentiment History"
        verbose_name_plural = "Sentiment History"
        unique_together = ['ticker', 'date']
        indexes = [
            models.Index(fields=['ticker', '-date']),
        ]
    
    def __str__(self):
        return f"{self.ticker.symbol} - {self.date} (Avg: {self.avg_sentiment:.2f})"


# DEPRECATED - Keeping for migration compatibility, will be removed
class SentimentScore(models.Model):
    """DEPRECATED - Use AnalysisRun instead"""
    ticker = models.ForeignKey(Ticker, on_delete=models.CASCADE, related_name='old_sentiment_scores')
    score = models.FloatField(help_text="Sentiment score from -100 to 100")
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    articles_analyzed = models.IntegerField(default=0)
    cached_articles = models.IntegerField(default=0)
    new_articles = models.IntegerField(default=0)
    SENTIMENT_CHOICES = [
        ('STRONGLY_BULLISH', 'Strongly Bullish'),
        ('BULLISH', 'Bullish'),
        ('NEUTRAL', 'Neutral'),
        ('BEARISH', 'Bearish'),
        ('STRONGLY_BEARISH', 'Strongly Bearish'),
    ]
    sentiment_label = models.CharField(max_length=20, choices=SENTIMENT_CHOICES, blank=True)
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Old Sentiment Score"
        verbose_name_plural = "Old Sentiment Scores"


# ============================================================================
# REDDIT SENTIMENT MODELS
# ============================================================================

class RedditPost(models.Model):
    """Reddit post with sentiment analysis"""
    ticker = models.ForeignKey(Ticker, on_delete=models.CASCADE, related_name='reddit_posts', null=True, blank=True)
    analysis_run = models.ForeignKey(AnalysisRun, on_delete=models.SET_NULL, null=True, blank=True, related_name='reddit_posts')

    # Post information
    post_id = models.CharField(max_length=20, unique=True, db_index=True, help_text="Reddit post ID")
    subreddit = models.CharField(max_length=50, db_index=True)
    title = models.TextField()
    body = models.TextField(blank=True)
    author = models.CharField(max_length=50)
    url = models.URLField(max_length=500)

    # Post metrics
    score = models.IntegerField(help_text="Reddit upvotes - downvotes")
    upvote_ratio = models.FloatField(null=True, blank=True)
    num_comments = models.IntegerField(default=0)

    # Timestamps
    created_utc = models.DateTimeField(db_index=True, help_text="When post was created on Reddit")
    fetched_at = models.DateTimeField(auto_now_add=True, help_text="When we fetched it")

    # Content hash for deduplication
    content_hash = models.CharField(max_length=32, db_index=True)

    # Post classification
    is_relevant = models.BooleanField(default=False, help_text="Passed keyword filter")
    mentions_nasdaq = models.BooleanField(default=False)
    mentions_stock_tickers = models.TextField(blank=True, help_text="Comma-separated tickers mentioned")

    # Sentiment analysis results (same as NewsArticle for consistency)
    base_sentiment = models.FloatField(null=True, blank=True, help_text="Base sentiment from -1 to 1")
    surprise_factor = models.FloatField(default=1.0)
    novelty_score = models.FloatField(default=1.0)
    source_credibility = models.FloatField(default=0.5, help_text="Subreddit credibility")
    recency_weight = models.FloatField(default=1.0)
    post_score = models.FloatField(null=True, blank=True, help_text="Calculated post sentiment score")
    weighted_contribution = models.FloatField(null=True, blank=True)

    # Comments analyzed count
    comments_analyzed = models.IntegerField(default=0)

    # Status
    is_analyzed = models.BooleanField(default=False)
    sentiment_cached = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_utc']
        verbose_name = "Reddit Post"
        verbose_name_plural = "Reddit Posts"
        indexes = [
            models.Index(fields=['post_id']),
            models.Index(fields=['subreddit', '-created_utc']),
            models.Index(fields=['-created_utc']),
            models.Index(fields=['is_relevant', '-created_utc']),
        ]

    def __str__(self):
        return f"r/{self.subreddit} - {self.title[:50]}..."


class RedditComment(models.Model):
    """Reddit comment with sentiment analysis"""
    post = models.ForeignKey(RedditPost, on_delete=models.CASCADE, related_name='comments')
    ticker = models.ForeignKey(Ticker, on_delete=models.CASCADE, related_name='reddit_comments', null=True, blank=True)

    # Comment information
    comment_id = models.CharField(max_length=20, unique=True, db_index=True)
    parent_comment = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
    body = models.TextField()
    author = models.CharField(max_length=50)

    # Comment metrics
    score = models.IntegerField(help_text="Reddit comment score")
    is_submitter = models.BooleanField(default=False, help_text="Is comment by post author")
    depth = models.IntegerField(default=0, help_text="Comment depth (0=top-level, 1=reply, etc.)")

    # Timestamps
    created_utc = models.DateTimeField(db_index=True)
    fetched_at = models.DateTimeField(auto_now_add=True)

    # Content hash
    content_hash = models.CharField(max_length=32, db_index=True)

    # Sentiment analysis
    base_sentiment = models.FloatField(null=True, blank=True)
    comment_score_weighted = models.FloatField(null=True, blank=True, help_text="Sentiment weighted by comment upvotes")

    # Status
    is_analyzed = models.BooleanField(default=False)

    class Meta:
        ordering = ['-score', '-created_utc']
        verbose_name = "Reddit Comment"
        verbose_name_plural = "Reddit Comments"
        indexes = [
            models.Index(fields=['post', '-score']),
            models.Index(fields=['comment_id']),
        ]

    def __str__(self):
        return f"Comment by {self.author}: {self.body[:50]}..."


class RedditAnalysisRun(models.Model):
    """Tracks Reddit sentiment analysis runs - separate from news sentiment"""
    ticker = models.ForeignKey(Ticker, on_delete=models.CASCADE, related_name='reddit_analysis_runs')
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    # Reddit sentiment score
    reddit_composite_score = models.FloatField(help_text="Reddit sentiment from -100 to 100")
    reddit_sentiment_label = models.CharField(max_length=20, blank=True)

    # Component scores
    avg_base_sentiment = models.FloatField()
    avg_surprise_factor = models.FloatField(default=1.0)
    avg_novelty = models.FloatField(default=1.0)
    avg_source_credibility = models.FloatField(default=0.5)
    avg_recency_weight = models.FloatField(default=1.0)

    # Content analyzed
    posts_analyzed = models.IntegerField(default=0)
    comments_analyzed = models.IntegerField(default=0)
    cached_posts = models.IntegerField(default=0)
    new_posts = models.IntegerField(default=0)
    subreddits_checked = models.IntegerField(default=0)

    # Top mentioned tickers
    top_tickers_mentioned = models.TextField(blank=True, help_text="JSON list of most mentioned tickers")

    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Reddit Analysis Run"
        verbose_name_plural = "Reddit Analysis Runs"
        indexes = [
            models.Index(fields=['ticker', '-timestamp']),
        ]

    def __str__(self):
        return f"{self.ticker.symbol} - Reddit Score: {self.reddit_composite_score:.2f} @ {self.timestamp.strftime('%Y-%m-%d %H:%M')}"


class StockPrice(models.Model):
    """DEPRECATED - Use AnalysisRun instead"""
    ticker = models.ForeignKey(Ticker, on_delete=models.CASCADE, related_name='old_stock_prices')
    price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Current stock price")
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    open_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    high_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    low_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    volume = models.BigIntegerField(null=True, blank=True)
    change_percent = models.FloatField(null=True, blank=True, help_text="Percentage change")
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Old Stock Price"
        verbose_name_plural = "Old Stock Prices"


# Keep the example model for reference
class Example(models.Model):
    """Example model to demonstrate Django admin integration"""
    title = models.CharField(max_length=200, help_text="Title of the example")
    description = models.TextField(blank=True, help_text="Description of the example")
    created_by = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='examples',
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True, help_text="Is this example active?")
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Example"
        verbose_name_plural = "Examples"
    
    def __str__(self):
        return self.title
