# News Sentiment Analysis - Commit Investigation

## Summary

**Current HEAD:** `db36aa9` (Update start.sh - Oct 28, 2025)  
**Result:** NO commits found after the current HEAD that were reverted.

All commits in the repository are accounted for, and there are no missing or reverted commits.

## News Sentiment Calculation Methods

### Current Implementation (run_nasdaq_sentiment.py)

The current news sentiment analysis uses **ARTICLE_WEIGHTS**:

```python
ARTICLE_WEIGHTS = {
    'base_sentiment': 0.40,      # 40%
    'surprise_factor': 0.25,     # 25%
    'novelty': 0.15,             # 15%
    'source_credibility': 0.10,  # 10%
    'recency': 0.10              # 10%
}
```

**Article Score Formula:**
```python
article_score = (
    base_sentiment * ARTICLE_WEIGHTS['base_sentiment'] * 100 +
    (surprise_factor - 1) * ARTICLE_WEIGHTS['surprise_factor'] * 50 +
    novelty_score * ARTICLE_WEIGHTS['novelty'] * 30 +
    source_credibility * ARTICLE_WEIGHTS['source_credibility'] * 20 +
    recency_weight * ARTICLE_WEIGHTS['recency'] * 20
)
```

**Location:** `backend/api/management/commands/run_nasdaq_sentiment.py`

### Older Implementation (run_sentiment_analysis.py)

The older script uses the same **WEIGHTS** but with a different calculation method:

```python
WEIGHTS = {
    'base_sentiment': 0.40,
    'surprise_factor': 0.25,
    'novelty': 0.15,
    'source_credibility': 0.10,
    'recency': 0.10
}
```

**Article Score Formula (different approach):**
```python
article_score = (base_sentiment * WEIGHTS['base_sentiment']) * surprise_multiplier
article_weight = (
    novelty * WEIGHTS['novelty'] +
    source_cred * WEIGHTS['source_credibility'] +
    recency * WEIGHTS['recency']
)
weighted_score = article_score * article_weight
```

**Location:** `backend/api/management/commands/run_sentiment_analysis.py`

## Key Differences

1. **run_nasdaq_sentiment.py** (currently used):
   - Uses additive formula with specific multipliers for each component
   - Multiplies base_sentiment by 100, surprise by 50, etc.
   - More explicit weight distribution

2. **run_sentiment_analysis.py** (older/alternative):
   - Uses multiplicative approach
   - Combines base_sentiment with surprise_factor first, then applies other weights
   - Different mathematical approach

## Commits Related to News Sentiment

From the commit history, **no commits specifically changed the news sentiment calculation formula**. The sentiment logic appears to have been established before the current commit history starts (commit 23a7247 - "Add files via upload" on Oct 22).

## Files That Handle News Sentiment

1. `backend/api/management/commands/run_nasdaq_sentiment.py` - **Currently Active**
   - Contains `analyze_article_sentiment()` function
   - Uses ARTICLE_WEIGHTS configuration
   - Handles batch processing of news articles

2. `backend/api/management/commands/run_sentiment_analysis.py` - **Older Script**
   - May have been replaced by run_nasdaq_sentiment.py
   - Uses similar WEIGHTS but different calculation method
   - Still exists in the codebase

3. `backend/api/models.py`
   - Contains NewsArticle model
   - Stores sentiment components (base_sentiment, surprise_factor, novelty_score, etc.)

## Conclusion

- **No commits after db36aa9** were found or reverted
- The news sentiment calculation appears stable throughout the commit history
- Two different calculation methods exist in the codebase:
  - `run_nasdaq_sentiment.py` (current, additive approach)
  - `run_sentiment_analysis.py` (older, multiplicative approach)

If you're looking for a specific change to news sentiment that you remember making, it's possible:
1. It was never committed
2. It was made in a different branch or repository
3. It was part of the initial commit (23a7247) which added all files

