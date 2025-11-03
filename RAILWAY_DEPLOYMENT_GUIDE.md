# Railway Deployment Guide - OpenAI Integration

## ✅ Ready to Deploy

Your OpenAI integration is **production-ready** and tested locally. Here's how to deploy to Railway.

## 🎯 Recommended Configuration

### Local Development (Current Setup)
```bash
SENTIMENT_PROVIDER=openai
OPENAI_API_KEY=sk-proj-...
```
**Benefits**: Faster, higher quality, better for testing

### Railway Production (Recommended)
```bash
SENTIMENT_PROVIDER=huggingface
HUGGINGFACE_API_KEY=hf_...
```
**Benefits**: Free tier, 24/7 operation, financial-specific model

## 📋 Deployment Steps

### Step 1: Update Railway Environment Variables

Go to Railway Dashboard → Your Project → Variables

**Add/Update these variables:**
```bash
# Required: Django Settings
DEBUG=False
SECRET_KEY=h!@u1p3o+eq3*5r5@_ln2jij&m7(htnt(5y+*ueoss8a)a+3+%
DATABASE_URL=${{Postgres.DATABASE_URL}}

# Required: Sentiment Provider (USE HUGGINGFACE FOR FREE TIER)
SENTIMENT_PROVIDER=huggingface

# Required: API Keys
HUGGINGFACE_API_KEY=hf_YOUR_HUGGINGFACE_KEY_HERE
FINNHUB_API_KEY=YOUR_FINNHUB_KEY_HERE

# Optional: OpenAI (for future switching)
OPENAI_API_KEY=sk-proj-YOUR_OPENAI_KEY_HERE

# Optional: Reddit API
REDDIT_CLIENT_ID=YOUR_REDDIT_CLIENT_ID
REDDIT_CLIENT_SECRET=YOUR_REDDIT_CLIENT_SECRET
REDDIT_USERNAME=YOUR_REDDIT_USERNAME
REDDIT_PASSWORD=YOUR_REDDIT_PASSWORD
REDDIT_USER_AGENT=NASDAQ_Sentiment_Tracker/1.0

# Optional: Market Hours
SKIP_MARKET_HOURS_CHECK=False

# Required: CORS
ALLOWED_HOSTS=nasdaqsentimenttracker-production.up.railway.app,.railway.app
FRONTEND_URLS=https://nasdaqsentimenttracker.netlify.app,https://*.netlify.app
```

### Step 2: Verify Requirements.txt

Ensure [requirements.txt](requirements.txt) includes:
```bash
openai==1.59.8  # ← This line must be present
```

**Current requirements.txt:**
```
Django==5.0.2
djangorestframework==3.14.0
django-cors-headers==4.3.1
python-dotenv==1.0.1
gunicorn==21.2.0
whitenoise==6.6.0
psycopg2-binary==2.9.9
dj-database-url==2.1.0
finnhub-python==2.4.19
requests==2.31.0
yfinance==0.2.66
praw==7.8.1
pandas==2.3.3
numpy==2.3.4
pytz==2025.2
ta==0.11.0
openai==1.59.8  # ← NEW
```

### Step 3: Push Changes to GitHub

The changes are already committed in your latest commit:
```
eb0afbf Add OpenAI sentiment analysis support with provider switching
```

If you need to push additional changes:

```bash
# Check current branch
git branch

# Push to main
git push origin main
```

### Step 4: Railway Auto-Deploy

Railway should automatically detect the push and redeploy:

1. ✅ Railway detects GitHub push
2. ✅ Installs dependencies (including `openai==1.59.8`)
3. ✅ Runs migrations
4. ✅ Starts the service

**Watch the deployment logs** in Railway dashboard.

### Step 5: Verify Deployment

Once deployed, check:

**1. Health Check:**
```bash
curl https://nasdaqsentimenttracker-production.up.railway.app/api/dashboard/
```

**2. Check Logs** in Railway Dashboard for:
```
✅ All tickers initialized
🔬 Analyzing X new articles with FinBERT (batched)...
✅ Analysis complete
```

**3. Verify Sentiment Provider:**
Look for log line showing **FinBERT** (not OpenAI):
```
🔬 Analyzing 146 new articles with FinBERT (single batch)...
```

## 🔄 Switching Providers in Production

### To Switch to OpenAI on Railway:

1. Go to Railway → Variables
2. Change: `SENTIMENT_PROVIDER=openai`
3. Redeploy (or let it auto-redeploy)
4. Monitor costs in OpenAI dashboard

**Cost estimate**:
- ~200 articles every 5 minutes during market hours
- ~57,600 articles/month
- **Cost: ~$2.88/month** with GPT-4o-mini

### To Switch Back to HuggingFace:

1. Change: `SENTIMENT_PROVIDER=huggingface`
2. Redeploy
3. Free tier resumes

## 🛡️ Safety Checks

### Before Deploying:

- ✅ `openai==1.59.8` in requirements.txt
- ✅ Factory functions with error handling
- ✅ Batch processing optimizations
- ✅ Tested locally successfully
- ✅ Environment variable switching works

### After Deploying:

- ✅ Check Railway logs for errors
- ✅ Verify sentiment analysis runs successfully
- ✅ Confirm Dashboard API returns data
- ✅ Monitor HuggingFace API quota (free tier: ~1,000 requests/day)

## 🔧 Troubleshooting

### Issue: "Package openai is not installed"
**Solution**: Verify `openai==1.59.8` is in requirements.txt and redeploy

### Issue: "HuggingFace API error: 503"
**Solution**: Model is loading, system will auto-retry after 20 seconds

### Issue: "HuggingFace rate limit exceeded"
**Solution**: Switch to OpenAI temporarily:
```bash
SENTIMENT_PROVIDER=openai
```

### Issue: No sentiment analysis running
**Solution**: Check Railway logs for errors, verify all environment variables are set

## 📊 Monitoring

**Track API Usage:**
- **HuggingFace**: https://huggingface.co/settings/tokens
- **OpenAI**: https://platform.openai.com/usage
- **Finnhub**: https://finnhub.io/dashboard

**Monitor Railway:**
- Deployment logs: Railway Dashboard → Deployments
- Environment variables: Railway Dashboard → Variables
- Metrics: Railway Dashboard → Metrics

## 🎯 Summary

**What's Being Deployed:**
1. ✅ OpenAI integration code (factory pattern)
2. ✅ HuggingFace integration (existing)
3. ✅ Environment variable switching
4. ✅ Batch processing optimizations
5. ✅ Dashboard API enhancements (reference_time fix)

**Recommended Production Config:**
```bash
SENTIMENT_PROVIDER=huggingface  # Free tier
DATABASE_URL=${{Postgres.DATABASE_URL}}
DEBUG=False
```

**Deployment is safe** because:
- Code has error handling for both providers
- Defaults to HuggingFace if provider not specified
- Tested successfully in local environment
- No breaking changes to existing functionality

## 🚀 Ready to Deploy!

Your OpenAI integration is production-ready. Follow the steps above to deploy safely to Railway with HuggingFace as the default provider.

You can switch to OpenAI anytime by changing one environment variable in Railway dashboard.
