from rest_framework import serializers
from .models import Ticker, AnalysisRun, NewsArticle, TickerContribution
import math


class TickerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ticker
        fields = ['id', 'symbol', 'company_name']


class AnalysisRunSerializer(serializers.ModelSerializer):
    ticker = TickerSerializer(read_only=True)

    class Meta:
        model = AnalysisRun
        fields = [
            'id',
            'ticker',
            'timestamp',
            'composite_score',
            'sentiment_label',
            # Stock price data
            'stock_price',
            'price_change_percent',
            'price_open',
            'price_high',
            'price_low',
            'volume',
            # The 5 component scores
            'avg_base_sentiment',
            'avg_surprise_factor',
            'avg_novelty',
            'avg_source_credibility',
            'avg_recency_weight',
            # Metadata
            'articles_analyzed',
            'cached_articles',
            'new_articles',
            # Technical Indicators
            'rsi_14',
            'macd',
            'macd_signal',
            'macd_histogram',
            'bb_upper',
            'bb_middle',
            'bb_lower',
            'sma_20',
            'sma_50',
            'ema_9',
            'ema_20',
            'stoch_k',
            'stoch_d',
            'williams_r',
            'atr_14',
            'qqq_price',
            # VXN (NASDAQ-100 Volatility Index)
            'vxn_index',
            # Reddit sentiment
            'reddit_sentiment',
            'reddit_posts_analyzed',
            'reddit_comments_analyzed',
            # Technical composite score
            'technical_composite_score',
            # Analyst recommendations
            'analyst_recommendations_score',
            'analyst_recommendations_count',
            'analyst_strong_buy',
            'analyst_buy',
            'analyst_hold',
            'analyst_sell',
            'analyst_strong_sell',
        ]

    def to_representation(self, instance):
        """
        Convert NaN and None values to 0 or null to prevent JSON serialization errors.
        This ensures the API never returns NaN values which cause frontend issues.
        """
        data = super().to_representation(instance)

        # Fields that should be converted to 0 if NaN/None (numeric scores)
        numeric_fields = [
            'composite_score', 'price_change_percent', 'avg_base_sentiment',
            'avg_surprise_factor', 'avg_novelty', 'avg_source_credibility',
            'avg_recency_weight', 'rsi_14', 'macd', 'macd_signal', 'macd_histogram',
            'bb_upper', 'bb_middle', 'bb_lower', 'sma_20', 'sma_50', 'ema_9',
            'ema_20', 'stoch_k', 'stoch_d', 'williams_r', 'atr_14', 'vxn_index',
            'reddit_sentiment', 'technical_composite_score',
            'analyst_recommendations_score'
        ]

        # Fields that should be converted to None if NaN (price data - we want to preserve None)
        price_fields = ['stock_price', 'price_open', 'price_high', 'price_low', 'qqq_price']

        # Integer fields that should be converted to 0 if None
        count_fields = [
            'articles_analyzed', 'cached_articles', 'new_articles', 'volume',
            'reddit_posts_analyzed', 'reddit_comments_analyzed',
            'analyst_recommendations_count', 'analyst_strong_buy', 'analyst_buy',
            'analyst_hold', 'analyst_sell', 'analyst_strong_sell'
        ]

        for field in numeric_fields:
            if field in data:
                value = data[field]
                if value is None or (isinstance(value, float) and math.isnan(value)):
                    data[field] = 0.0
                elif isinstance(value, float) and math.isinf(value):
                    data[field] = 0.0

        for field in price_fields:
            if field in data:
                value = data[field]
                if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
                    data[field] = None

        for field in count_fields:
            if field in data:
                value = data[field]
                if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
                    data[field] = 0

        return data


class NewsArticleSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsArticle
        fields = [
            'id',
            'headline',
            'source',
            'published_at',
            'base_sentiment',
            'sentiment_cached',
        ]


class TickerContributionSerializer(serializers.ModelSerializer):
    ticker_symbol = serializers.CharField(source='ticker.symbol', read_only=True)
    ticker_name = serializers.CharField(source='ticker.company_name', read_only=True)
    
    class Meta:
        model = TickerContribution
        fields = [
            'id',
            'ticker_symbol',
            'ticker_name',
            'sentiment_score',
            'market_cap_weight',
            'weighted_contribution',
            'articles_analyzed',
        ]

