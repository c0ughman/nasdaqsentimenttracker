# Directory Structure Issue - RESOLVED

## Problem Identified

The project had a **duplicate directory structure** that was causing configuration issues:

```
/backend/
├── .env                    ← Root .env (had placeholder values)
├── manage.py               ← Root Django project (UPDATED CODE)
├── requirements.txt        ← Updated with openai==1.59.8
├── api/                    ← Updated API code
│   ├── views.py           ← Dashboard API with reference_time fix
│   └── management/
│       └── commands/
│           ├── run_nasdaq_sentiment.py  ← OpenAI integration
│           └── reddit_sentiment_analyzer.py  ← OpenAI integration
├── config/
│   └── settings.py
│
└── backend/                ← NESTED Django project (OLD CODE)
    ├── .env               ← Had real API keys but missing OpenAI
    ├── manage.py
    ├── requirements.txt   ← Missing openai dependency
    ├── api/               ← Old code without OpenAI
    └── config/
        └── settings.py
```

## Root Cause

When running `python3 manage.py` from `/backend/`, it would sometimes load configuration from the nested `backend/backend/` directory, which:
1. Had an old `.env` file with Railway-specific config (`DATABASE_URL=${{Postgres.DATABASE_URL}}`)
2. Missing the OpenAI dependency in `requirements.txt`
3. Old code without our recent updates

## Solution Applied

**Updated the root `.env` file** with actual API keys from the nested version:
- ✅ Real Finnhub API key
- ✅ Real OpenAI API key
- ✅ Real HuggingFace API key
- ✅ Reddit credentials
- ✅ SQLite database URL (for local development)
- ✅ `SENTIMENT_PROVIDER=openai`
- ✅ `SKIP_MARKET_HOURS_CHECK=True`

## Current Working Configuration

**Active Directory**: `/Users/coughman/Desktop/Nasdaq-Sentiment-Tracker-Clean/backend/`

**Key Files** (all in root `/backend/`):
- [.env](.env) - Now has all real API keys
- [requirements.txt](requirements.txt) - Includes `openai==1.59.8`
- [manage.py](manage.py) - Django entry point
- [api/views.py](api/views.py) - Dashboard API with reference_time fix
- [api/management/commands/run_nasdaq_sentiment.py](api/management/commands/run_nasdaq_sentiment.py) - OpenAI integration
- [api/management/commands/reddit_sentiment_analyzer.py](api/management/commands/reddit_sentiment_analyzer.py) - OpenAI integration

## Verified Working

Successfully ran sentiment analysis with:
```bash
python3 manage.py run_nasdaq_sentiment --once
```

Results:
- ✅ Fetched 239 company news articles + 69 market articles
- ✅ Analyzed 146 articles using **OpenAI GPT-4o-mini** (batched)
- ✅ Analyzed 17 Reddit posts using **OpenAI** (batched)
- ✅ Fetched analyst recommendations for 20 stocks
- ✅ Final composite score: **+17.23/100** (NEUTRAL)

## Recommendation for Cleanup

The nested `backend/backend/` directory appears to be leftover Railway deployment config. Consider:
1. **Keep the nested directory** if it's actively used for Railway deployment
2. **Update the nested directory** with latest code and dependencies when deploying
3. **Always work from the root `/backend/` directory** for local development

## Environment Variable Reference

### Local Development (.env in root /backend/)
```bash
SENTIMENT_PROVIDER=openai
OPENAI_API_KEY=sk-proj-...
FINNHUB_API_KEY=d3qn321r01quv7kbk9q0d3qn321r01quv7kbk9qg
DATABASE_URL=sqlite:///db.sqlite3
SKIP_MARKET_HOURS_CHECK=True
```

### Railway Production (backend/backend/.env or Railway dashboard)
```bash
SENTIMENT_PROVIDER=huggingface
HUGGINGFACE_API_KEY=hf_...
FINNHUB_API_KEY=d3qn321r01quv7kbk9q0d3qn321r01quv7kbk9qg
DATABASE_URL=${{Postgres.DATABASE_URL}}
DEBUG=False
```

## Testing Commands

Run from `/backend/` directory:

```bash
# Run sentiment analysis once (for testing)
python3 manage.py run_nasdaq_sentiment --once

# Run migrations
python3 manage.py migrate

# Start dev server
python3 manage.py runserver

# Create superuser
python3 manage.py createsuperuser
```
