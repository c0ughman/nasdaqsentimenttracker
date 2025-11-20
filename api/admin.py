from django.contrib import admin
from .models import (
    Ticker, AnalysisRun, NewsArticle, SentimentHistory, TickerContribution, Example,
    RedditPost, RedditComment, RedditAnalysisRun,
    OHLCVTick, SecondSnapshot, TickCandle100
)


@admin.register(Ticker)
class TickerAdmin(admin.ModelAdmin):
    """Admin configuration for Ticker model"""
    list_display = ['symbol', 'company_name', 'exchange', 'created_at']
    search_fields = ['symbol', 'company_name']
    list_filter = ['exchange', 'created_at']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(AnalysisRun)
class AnalysisRunAdmin(admin.ModelAdmin):
    """Admin configuration for AnalysisRun model - THE MAIN MODEL"""
    list_display = [
        'ticker',
        'timestamp',
        'composite_score',
        'sentiment_label',
        'news_driver',
        'social_driver',
        'technical_driver',
        'analyst_driver',
        'stock_price',
        'price_change_percent',
        'articles_analyzed',
        'reddit_posts_analyzed'
    ]
    list_filter = ['sentiment_label', 'timestamp', 'ticker']
    search_fields = ['ticker__symbol']
    readonly_fields = ['timestamp', 'sentiment_label', 'analyst_recommendations_score']
    date_hierarchy = 'timestamp'

    # Custom display methods for the 3 drivers
    def news_driver(self, obj):
        """Display news sentiment (avg_base_sentiment)"""
        if obj.avg_base_sentiment is not None:
            return f"{obj.avg_base_sentiment:+.2f}"
        return "-"
    news_driver.short_description = 'News (40%)'

    def social_driver(self, obj):
        """Display social media/Reddit sentiment"""
        if obj.reddit_sentiment is not None:
            return f"{obj.reddit_sentiment:+.2f}"
        return "-"
    social_driver.short_description = 'Social (30%)'

    def technical_driver(self, obj):
        """Display technical composite score"""
        if obj.technical_composite_score is not None:
            return f"{obj.technical_composite_score:+.2f}"
        return "-"
    technical_driver.short_description = 'Technical (30%)'

    def analyst_driver(self, obj):
        """Display analyst recommendations score"""
        if obj.analyst_recommendations_score is not None:
            return f"{obj.analyst_recommendations_score:+.2f}"
        return "-"
    analyst_driver.short_description = 'Analyst Recs'

    def analyst_recommendations_score_display(self, obj):
        """Display formatted analyst recommendations score for fieldsets"""
        if obj.analyst_recommendations_score is not None:
            return f"{obj.analyst_recommendations_score:+.2f}"
        return "-"
    analyst_recommendations_score_display.short_description = 'Analyst Recommendations Score'

    fieldsets = (
        ('Basic Information', {
            'fields': ('ticker', 'timestamp', 'composite_score', 'sentiment_label')
        }),
        ('4 Sentiment Drivers (News 40% + Social 30% + Technical 30% + Analyst Recs)', {
            'fields': (
                ('avg_base_sentiment', 'reddit_sentiment', 'technical_composite_score', 'analyst_recommendations_score_display'),
            ),
            'description': 'The 4 main sentiment drivers: News sentiment, Social media sentiment, Technical indicators, and Analyst recommendations'
        }),
        ('News Component Scores (The 5 factors - for reference)', {
            'fields': (
                'avg_surprise_factor',
                'avg_novelty',
                'avg_source_credibility',
                'avg_recency_weight'
            ),
            'description': 'Additional factors that contribute to the news sentiment (avg_base_sentiment above)',
            'classes': ('collapse',)
        }),
        ('Stock Price Data', {
            'fields': (
                'stock_price',
                'price_change_percent',
                'price_open',
                'price_high',
                'price_low',
                'volume'
            )
        }),
        ('Technical Indicators (Alpha Vantage)', {
            'fields': (
                ('rsi_14', 'macd', 'macd_signal', 'macd_histogram'),
                ('bb_upper', 'bb_middle', 'bb_lower'),
                ('sma_20', 'sma_50', 'ema_9', 'ema_20'),
                ('stoch_k', 'stoch_d', 'williams_r', 'atr_14'),
                ('qqq_price',)
            ),
            'description': 'Technical indicators fetched from Alpha Vantage API (5-minute intervals)',
            'classes': ('collapse',)
        }),
        ('Reddit Analysis Details (Social Media)', {
            'fields': (
                'reddit_posts_analyzed', 'reddit_comments_analyzed'
            ),
            'description': 'Reddit/social media analysis details (sentiment shown above in drivers)',
            'classes': ('collapse',)
        }),
        ('Analyst Recommendations Details (NASDAQ-wide)', {
            'fields': (
                'analyst_recommendations_count',
                ('analyst_strong_buy', 'analyst_buy', 'analyst_hold', 'analyst_sell', 'analyst_strong_sell')
            ),
            'description': 'Detailed analyst recommendations breakdown (score shown above in sentiment drivers)',
        }),
        ('Analysis Statistics', {
            'fields': ('articles_analyzed', 'cached_articles', 'new_articles'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        """Optimize query with select_related"""
        qs = super().get_queryset(request)
        return qs.select_related('ticker')


@admin.register(NewsArticle)
class NewsArticleAdmin(admin.ModelAdmin):
    """Admin configuration for NewsArticle model"""
    list_display = [
        'ticker', 
        'headline_short', 
        'source', 
        'base_sentiment', 
        'published_at', 
        'is_analyzed',
        'analysis_run_link'
    ]
    list_filter = ['ticker', 'source', 'is_analyzed', 'sentiment_cached', 'published_at']
    search_fields = ['headline', 'summary', 'ticker__symbol', 'source']
    readonly_fields = ['article_hash', 'fetched_at']
    date_hierarchy = 'published_at'
    
    fieldsets = (
        ('Article Information', {
            'fields': ('ticker', 'analysis_run', 'headline', 'summary', 'source', 'url', 'published_at', 'fetched_at')
        }),
        ('Identification', {
            'fields': ('article_hash',),
            'classes': ('collapse',)
        }),
        ('Sentiment Analysis Components', {
            'fields': (
                'base_sentiment', 
                'surprise_factor', 
                'novelty_score', 
                'source_credibility', 
                'recency_weight', 
                'article_score', 
                'weighted_contribution'
            )
        }),
        ('Status', {
            'fields': ('is_analyzed', 'sentiment_cached')
        }),
    )
    
    def headline_short(self, obj):
        """Return shortened headline for list display"""
        return obj.headline[:60] + '...' if len(obj.headline) > 60 else obj.headline
    headline_short.short_description = 'Headline'
    
    def analysis_run_link(self, obj):
        """Show link to the analysis run this article belongs to"""
        if obj.analysis_run:
            return f"Run #{obj.analysis_run.id}"
        return "-"
    analysis_run_link.short_description = 'Analysis Run'


@admin.register(TickerContribution)
class TickerContributionAdmin(admin.ModelAdmin):
    """Admin configuration for TickerContribution model"""
    list_display = [
        'analysis_run',
        'ticker',
        'sentiment_score',
        'market_cap_weight',
        'weighted_contribution',
        'articles_analyzed'
    ]
    list_filter = ['ticker', 'created_at']
    search_fields = ['ticker__symbol', 'analysis_run__id']
    readonly_fields = ['created_at']
    
    def get_queryset(self, request):
        """Optimize query with select_related"""
        qs = super().get_queryset(request)
        return qs.select_related('ticker', 'analysis_run')


@admin.register(SentimentHistory)
class SentimentHistoryAdmin(admin.ModelAdmin):
    """Admin configuration for SentimentHistory model"""
    list_display = [
        'ticker', 
        'date', 
        'avg_sentiment', 
        'total_analyses',
        'total_articles', 
        'closing_price', 
        'price_change_percent'
    ]
    list_filter = ['ticker', 'date']
    search_fields = ['ticker__symbol']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'date'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('ticker', 'date')
        }),
        ('Sentiment Metrics', {
            'fields': ('avg_sentiment', 'min_sentiment', 'max_sentiment', 'total_analyses', 'total_articles')
        }),
        ('Stock Price', {
            'fields': ('closing_price', 'price_change_percent')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Example)
class ExampleAdmin(admin.ModelAdmin):
    """Admin configuration for Example model"""
    list_display = ['title', 'created_by', 'is_active', 'created_at', 'updated_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['title', 'description']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'description', 'is_active')
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        """Automatically set created_by to current user if not set."""
        if not change and not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


# ============================================================================
# REDDIT MODELS ADMIN CONFIGURATION
# ============================================================================

@admin.register(RedditPost)
class RedditPostAdmin(admin.ModelAdmin):
    """Admin configuration for RedditPost model"""
    list_display = [
        'subreddit',
        'title_short',
        'author',
        'score',
        'num_comments',
        'base_sentiment',
        'post_score',
        'is_relevant',
        'created_utc',
        'is_analyzed'
    ]
    list_filter = [
        'subreddit', 
        'is_relevant', 
        'mentions_nasdaq', 
        'is_analyzed', 
        'sentiment_cached',
        'created_utc'
    ]
    search_fields = ['title', 'body', 'author', 'subreddit', 'mentions_stock_tickers']
    readonly_fields = ['post_id', 'content_hash', 'fetched_at']
    date_hierarchy = 'created_utc'
    
    fieldsets = (
        ('Post Information', {
            'fields': (
                'ticker', 'analysis_run', 'post_id', 'subreddit', 
                'title', 'body', 'author', 'url'
            )
        }),
        ('Reddit Metrics', {
            'fields': ('score', 'upvote_ratio', 'num_comments', 'created_utc', 'fetched_at')
        }),
        ('Content Analysis', {
            'fields': (
                'content_hash', 'is_relevant', 'mentions_nasdaq', 'mentions_stock_tickers'
            ),
            'classes': ('collapse',)
        }),
        ('Sentiment Analysis', {
            'fields': (
                'base_sentiment', 'surprise_factor', 'novelty_score', 
                'source_credibility', 'recency_weight', 'post_score', 'weighted_contribution'
            )
        }),
        ('Status', {
            'fields': ('is_analyzed', 'sentiment_cached', 'comments_analyzed'),
            'classes': ('collapse',)
        }),
    )
    
    def title_short(self, obj):
        """Return shortened title for list display"""
        return obj.title[:50] + '...' if len(obj.title) > 50 else obj.title
    title_short.short_description = 'Title'
    
    def get_queryset(self, request):
        """Optimize query with select_related"""
        qs = super().get_queryset(request)
        return qs.select_related('ticker', 'analysis_run')


@admin.register(RedditComment)
class RedditCommentAdmin(admin.ModelAdmin):
    """Admin configuration for RedditComment model"""
    list_display = [
        'post_link',
        'author',
        'score',
        'depth',
        'base_sentiment',
        'comment_score_weighted',
        'created_utc',
        'is_analyzed'
    ]
    list_filter = [
        'post__subreddit',
        'depth',
        'is_submitter',
        'is_analyzed',
        'created_utc'
    ]
    search_fields = ['body', 'author', 'post__title', 'post__subreddit']
    readonly_fields = ['comment_id', 'content_hash', 'fetched_at']
    date_hierarchy = 'created_utc'
    
    fieldsets = (
        ('Comment Information', {
            'fields': (
                'post', 'ticker', 'comment_id', 'parent_comment',
                'body', 'author', 'score', 'is_submitter', 'depth'
            )
        }),
        ('Timestamps', {
            'fields': ('created_utc', 'fetched_at'),
            'classes': ('collapse',)
        }),
        ('Content Hash', {
            'fields': ('content_hash',),
            'classes': ('collapse',)
        }),
        ('Sentiment Analysis', {
            'fields': ('base_sentiment', 'comment_score_weighted')
        }),
        ('Status', {
            'fields': ('is_analyzed',),
            'classes': ('collapse',)
        }),
    )
    
    def post_link(self, obj):
        """Show link to the parent post"""
        return f"r/{obj.post.subreddit} - {obj.post.title[:30]}..."
    post_link.short_description = 'Post'
    
    def get_queryset(self, request):
        """Optimize query with select_related"""
        qs = super().get_queryset(request)
        return qs.select_related('post', 'ticker', 'parent_comment')


@admin.register(RedditAnalysisRun)
class RedditAnalysisRunAdmin(admin.ModelAdmin):
    """Admin configuration for RedditAnalysisRun model"""
    list_display = [
        'ticker',
        'timestamp',
        'reddit_composite_score',
        'reddit_sentiment_label',
        'posts_analyzed',
        'comments_analyzed',
        'subreddits_checked'
    ]
    list_filter = ['ticker', 'timestamp', 'reddit_sentiment_label']
    search_fields = ['ticker__symbol', 'top_tickers_mentioned']
    readonly_fields = ['timestamp']
    date_hierarchy = 'timestamp'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('ticker', 'timestamp', 'reddit_composite_score', 'reddit_sentiment_label')
        }),
        ('Component Scores', {
            'fields': (
                'avg_base_sentiment', 'avg_surprise_factor', 'avg_novelty',
                'avg_source_credibility', 'avg_recency_weight'
            ),
            'classes': ('collapse',)
        }),
        ('Analysis Statistics', {
            'fields': (
                'posts_analyzed', 'comments_analyzed', 'cached_posts', 
                'new_posts', 'subreddits_checked'
            )
        }),
        ('Top Mentions', {
            'fields': ('top_tickers_mentioned',),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        """Optimize query with select_related"""
        qs = super().get_queryset(request)
        return qs.select_related('ticker')


# ============================================================================
# EODHD WEBSOCKET MODELS ADMIN CONFIGURATION
# ============================================================================

@admin.register(OHLCVTick)
class OHLCVTickAdmin(admin.ModelAdmin):
    """Admin configuration for OHLCVTick model - Raw second-by-second ticks"""
    list_display = [
        'ticker',
        'timestamp',
        'price',
        'volume',
        'source'
    ]
    list_filter = ['ticker', 'source', 'timestamp']
    search_fields = ['ticker__symbol']
    readonly_fields = ['created_at']
    date_hierarchy = 'timestamp'
    
    fieldsets = (
        ('Tick Information', {
            'fields': ('ticker', 'timestamp', 'price', 'volume', 'source')
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        """Optimize query with select_related"""
        qs = super().get_queryset(request)
        return qs.select_related('ticker')


@admin.register(SecondSnapshot)
class SecondSnapshotAdmin(admin.ModelAdmin):
    """Admin configuration for SecondSnapshot model - 1-second OHLCV candles"""
    list_display = [
        'ticker',
        'timestamp',
        'ohlc_1sec_open',
        'ohlc_1sec_high',
        'ohlc_1sec_low',
        'ohlc_1sec_close',
        'ohlc_1sec_volume',
        'ohlc_1sec_tick_count',
        'source'
    ]
    list_filter = ['ticker', 'source', 'timestamp']
    search_fields = ['ticker__symbol']
    readonly_fields = ['created_at']
    date_hierarchy = 'timestamp'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('ticker', 'timestamp', 'source')
        }),
        ('1-Second OHLCV Candle', {
            'fields': (
                ('ohlc_1sec_open', 'ohlc_1sec_high'),
                ('ohlc_1sec_low', 'ohlc_1sec_close'),
                ('ohlc_1sec_volume', 'ohlc_1sec_tick_count')
            )
        }),
        ('Real-Time Indicators (Future Phase 2)', {
            'fields': (
                'price_momentum_5sec',
                'price_change_1sec'
            ),
            'classes': ('collapse',)
        }),
        ('Composite Scores (Future Phase 2)', {
            'fields': (
                'composite_score',
                'news_score_cached',
                'technical_score_cached'
            ),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        """Optimize query with select_related"""
        qs = super().get_queryset(request)
        return qs.select_related('ticker')


@admin.register(TickCandle100)
class TickCandle100Admin(admin.ModelAdmin):
    """Admin configuration for TickCandle100 model - 100-tick volume-based candles"""
    list_display = [
        'ticker',
        'candle_number',
        'completed_at',
        'open',
        'high',
        'low',
        'close',
        'total_volume',
        'duration_seconds',
        'source'
    ]
    list_filter = ['ticker', 'source', 'completed_at']
    search_fields = ['ticker__symbol']
    readonly_fields = ['created_at']
    date_hierarchy = 'completed_at'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('ticker', 'candle_number', 'completed_at', 'source')
        }),
        ('100-Tick OHLCV Candle', {
            'fields': (
                ('open', 'high'),
                ('low', 'close'),
                'total_volume'
            )
        }),
        ('Timing Metadata', {
            'fields': (
                'first_tick_time',
                'last_tick_time',
                'duration_seconds'
            )
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        """Optimize query with select_related"""
        qs = super().get_queryset(request)
        return qs.select_related('ticker')
