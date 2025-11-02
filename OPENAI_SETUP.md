# OpenAI Sentiment Analysis Setup

## Overview

The sentiment analysis system now supports **two providers**:
- **HuggingFace (FinBERT)** - Free tier, financial-specific model
- **OpenAI (GPT-4o-mini)** - Paid, high-quality general LLM

You can switch between them using a single environment variable.

## Environment Variables

Add these to your `.env` file:

```bash
# Sentiment Provider Selection (choose one)
SENTIMENT_PROVIDER=huggingface  # or "openai"

# API Keys (have both, only the selected one will be used)
HUGGINGFACE_API_KEY=hf_your_key_here
OPENAI_API_KEY=sk-your_key_here

# Other existing keys
FINNHUB_API_KEY=your_finnhub_key
# ... rest of your keys
```

## Configuration

### Local Development (OpenAI)
```bash
SENTIMENT_PROVIDER=openai
OPENAI_API_KEY=sk-proj-...
```

### Production/Railway (HuggingFace)
```bash
SENTIMENT_PROVIDER=huggingface
HUGGINGFACE_API_KEY=hf_...
```

## Installation

Install the OpenAI package:

```bash
pip install openai==1.59.8
```

Or install all requirements:

```bash
pip install -r requirements.txt
```

## How It Works

### Factory Functions

The system uses factory functions that automatically route to the correct API:

**News & General Sentiment:**
- `analyze_sentiment_api(text)` - Single text analysis
- `analyze_sentiment_batch(texts)` - Batch analysis

**Reddit Sentiment:**
- Same factory functions imported from `run_nasdaq_sentiment`

### What Gets Called

When `SENTIMENT_PROVIDER=openai`:
- ✓ Calls `analyze_sentiment_openai_api()` for single texts
- ✓ Calls `analyze_sentiment_openai_batch()` for batches

When `SENTIMENT_PROVIDER=huggingface` (default):
- ✓ Calls `analyze_sentiment_finbert_api()` for single texts
- ✓ Calls `analyze_sentiment_finbert_batch()` for batches

## Files Modified

1. **api/management/commands/run_nasdaq_sentiment.py**
   - Added `OPENAI_API_KEY` and `SENTIMENT_PROVIDER` config (lines 59-60)
   - Added `analyze_sentiment_openai_api()` (lines 181-218)
   - Added `analyze_sentiment_openai_batch()` (lines 221-269)
   - Added factory functions `analyze_sentiment_api()` and `analyze_sentiment_batch()` (lines 272-291)
   - Updated all sentiment calls to use factory functions (lines 513, 588, 1195)

2. **api/management/commands/reddit_sentiment_analyzer.py**
   - Added OpenAI config (lines 19-20)
   - Added `analyze_sentiment_openai_api()` (lines 57-87)
   - Added factory function `analyze_sentiment_api()` (lines 90-98)
   - Updated all sentiment calls to use factory function (lines 231, 272, 424, 427)

3. **requirements.txt**
   - Added `openai==1.59.8`

## Testing

### Test with HuggingFace (Default)
```bash
# In .env
SENTIMENT_PROVIDER=huggingface
HUGGINGFACE_API_KEY=hf_...

# Run analysis
python manage.py run_nasdaq_sentiment --once
```

### Test with OpenAI
```bash
# In .env
SENTIMENT_PROVIDER=openai
OPENAI_API_KEY=sk-...

# Run analysis
python manage.py run_nasdaq_sentiment --once
```

You should see in the logs:
- `🔬 Analyzing X new articles with OpenAI (batched)...` (if OpenAI)
- `🔬 Analyzing X new articles with FinBERT (batched)...` (if HuggingFace)

## Cost Comparison

### HuggingFace FinBERT
- **Free Tier**: ~1,000 requests/day
- **Cost**: $0 (free tier) or ~$0.06/1K requests

### OpenAI GPT-4o-mini
- **Model**: gpt-4o-mini
- **Input Cost**: ~$0.15/1M tokens
- **Typical Usage**: ~$0.01 per 200 articles
- **Monthly Estimate** (200 articles every 5 min during market hours):
  - ~57,600 articles/month
  - Cost: ~$2.88/month

### OpenAI Batch Processing
OpenAI doesn't have a native batch API like HuggingFace, so we use:
- **ThreadPoolExecutor** with max 10 concurrent workers
- This avoids rate limits while staying fast

## Deployment Strategy

### Recommended Setup

**Local Development:**
```bash
SENTIMENT_PROVIDER=openai
```
- Fast testing and development
- Higher quality for experimenting

**Railway Production:**
```bash
SENTIMENT_PROVIDER=huggingface
```
- Free tier
- 24/7 operation
- Financial-specific model

## Railway Environment Variables

In Railway dashboard, set:

```
SENTIMENT_PROVIDER=huggingface
HUGGINGFACE_API_KEY=hf_your_key_here
```

## Troubleshooting

### "Package `openai` is not installed"
```bash
pip install openai==1.59.8
```

### "OpenAI API key not found"
Make sure your `.env` has:
```bash
OPENAI_API_KEY=sk-proj-...
```

### "Failed to parse OpenAI response as float"
The OpenAI model returned non-numeric text. Check:
1. Model is set to `gpt-4o-mini` (line 190 in run_nasdaq_sentiment.py)
2. Temperature is `0` (deterministic)
3. System prompt is correct

### Sentiment scores seem wrong
Both APIs return scores from **-1 to +1**:
- `-1.0` = Very negative
- `0.0` = Neutral
- `+1.0` = Very positive

These are converted to `-100 to +100` scale later in the pipeline.

## Support

If you need help:
1. Check logs for which provider is being used
2. Verify API keys are set correctly
3. Test with `--once` flag first before continuous mode
4. Check API quotas/limits on provider dashboards
