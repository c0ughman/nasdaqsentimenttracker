# 📊 Tiingo Integration - Logging Guide

**Last Updated:** November 28, 2025
**Commits:** dec4779, fef79e7, 008fbca, c285943

---

## 🐛 Issues Fixed

### Issue 1: Tiingo loop stopping when WebSocket disconnects (dec4779)
**Problem:** Tiingo loop was stopping and restarting repeatedly
**Root Cause:** The loop condition was checking `self.ws.sock.connected`, which caused it to stop when the WebSocket temporarily disconnected/reconnected
**Fix:** Changed loop condition from `while self.running and self.ws and self.ws.sock and self.ws.sock.connected` to `while self.running`
**Result:** Tiingo now runs independently of WebSocket state and won't stop unless the entire collector shuts down.

### Issue 2: Django logger not outputting to Railway logs (c285943)
**Problem:** ALL Tiingo logs were invisible in Railway despite code running
**Root Cause:** All logs used `logger.info()` and `logger.error()`, but Django's logger was not configured to output to Railway's stdout
**Fix:** Added `print()` statements alongside all `logger` calls to ensure messages appear in Railway console
**Result:** All Tiingo initialization, queries, results, and errors now visible in Railway logs!

---

## 📋 What You'll See in Railway Logs

### 1. **Initialization (on startup)**

```
🔧 Initializing Tiingo client with API key: your_api_k...
✅ Tiingo client initialized successfully
📰 Tiingo news loop started
Tiingo article scoring thread started
```

### 2. **Every 5 Seconds: Query Execution**

```
📰 TIINGO QUERY #1 START: Fetching news from 2025-11-28T10:00:00 to 2025-11-28T10:00:05
   Time window: 5.0 seconds
   → Querying 40 tickers: AAPL, MSFT, GOOGL, AMZN, NVDA... (limit=1000)
   ✓ Ticker query: 23 articles found, 15 new articles queued
      Sample: Apple announces new MacBook Pro with M4 chip and enhanced AI capabilities...
   → Querying QQQ market news (limit=50)
   ✓ Market query: 8 articles found, 3 new articles queued
      Sample: Tech stocks rally as Nasdaq hits new all-time high on AI optimism...
📰 TIINGO QUERY #1 COMPLETE: 31 total, 18 queued for scoring
```

### 3. **Article Queuing (for each new article)**

```
      📝 Queued: [AAPL] Apple announces new MacBook Pro with M4 chip and enhanced AI capab...
      📝 Queued: [MSFT] Microsoft cloud revenue beats expectations in Q4 earnings report...
      📝 Queued: [NVDA] NVIDIA stock surges 5% on new AI chip demand forecasts...
```

### 4. **Background Scoring (as articles are processed)**

```
   🤖 Scoring article: [AAPL] Apple announces new MacBook Pro with M4 chip and enhanced...
   ✅ SCORED: [AAPL] impact=+12.35 | Apple announces new MacBook Pro with M4 chip...
   🤖 Scoring article: [MSFT] Microsoft cloud revenue beats expectations in Q4...
   ✅ SCORED: [MSFT] impact=+8.42 | Microsoft cloud revenue beats expectations in Q4...
```

### 5. **Impact Application (when sentiment system consumes scores)**

```
   💰 Consuming 5 Tiingo impacts: Total=+42.18
Applied Tiingo article impact: +12.35
Applied Tiingo article impact: +8.42
Applied Tiingo article impact: +15.88
Applied Tiingo article impact: +3.17
Applied Tiingo article impact: +2.36
```

### 6. **Error Scenarios**

**No articles in time window:**
```
📰 TIINGO QUERY #3 START: Fetching news from 2025-11-28T10:00:10 to 2025-11-28T10:00:15
   Time window: 5.0 seconds
   → Querying 40 tickers: AAPL, MSFT, GOOGL, AMZN, NVDA... (limit=1000)
   ✓ Ticker query: No articles returned
   → Querying QQQ market news (limit=50)
   ✓ Market query: No articles returned
📰 TIINGO QUERY #3 COMPLETE: 0 total, 0 queued for scoring
```

**All articles are duplicates:**
```
📰 TIINGO QUERY #5 START: Fetching news from 2025-11-28T10:00:20 to 2025-11-28T10:00:25
   Time window: 5.0 seconds
   → Querying 40 tickers: AAPL, MSFT, GOOGL, AMZN, NVDA... (limit=1000)
   ✓ Ticker query: 42 articles found, 0 new articles queued
📰 TIINGO QUERY #5 COMPLETE: 42 total, 0 queued for scoring
```
*(All articles were already processed - duplicate detection working)*

**Queue full (system under load):**
```
      📝 Queued: [AAPL] Apple stock rises on earnings beat...
      📝 Queued: [MSFT] Microsoft announces Azure expansion...
      ⚠️  Queue FULL (100 items), skipping remaining articles
```

**API error:**
```
   → Querying 40 tickers: AAPL, MSFT, GOOGL, AMZN, NVDA... (limit=1000)
   ✗ Ticker query FAILED: 401 Unauthorized
```

---

## 🔍 How to Monitor Tiingo Performance

### Check if Tiingo is Working:

**Search Railway logs for:** `TIINGO QUERY`

**You should see:**
- Query logs every 5 seconds
- Articles being found and queued
- Scoring logs showing impact calculations
- Consumption logs showing impacts applied

### Check Article Volume:

**Search for:** `COMPLETE:`

**Example:**
```
📰 TIINGO QUERY #12 COMPLETE: 31 total, 18 queued for scoring
```

- **Total:** Articles returned by Tiingo API
- **Queued:** New articles (not duplicates)

### Check Scoring Progress:

**Search for:** `SCORED:`

**You should see:**
```
   ✅ SCORED: [AAPL] impact=+12.35 | Apple announces...
   ✅ SCORED: [MSFT] impact=+8.42 | Microsoft cloud...
```

### Check Impact Application:

**Search for:** `Consuming`

**You should see:**
```
   💰 Consuming 5 Tiingo impacts: Total=+42.18
```

---

## 📈 Expected Behavior

### During Market Hours (9:30 AM - 4:00 PM EST):

- **Queries:** Every 5 seconds
- **Articles found:** 10-50 per query (first query may have 100+ from 15-min lookback)
- **New articles queued:** 5-20 per query (70-80% are duplicates)
- **Scoring time:** 1-3 seconds per article
- **Impact range:** -25 to +25 per article

### After Market Hours:

- **Queries:** Every 5 seconds (still runs)
- **Articles found:** 0-10 per query (much less news)
- **New articles queued:** 0-5 per query

### First Query (on startup):

- **Time window:** Last 15 minutes (fallback)
- **Articles found:** 50-150 (backlog of recent news)
- **New articles queued:** 20-80 (all are new)
- **Scoring:** May take 1-2 minutes to process backlog

---

## 🚨 Troubleshooting

### Issue: No query logs appearing

**Check:**
1. `ENABLE_TIINGO_NEWS=True` in Railway variables
2. Look for `📰 Tiingo news loop started`
3. Look for error: `TIINGO_API_KEY not set`

### Issue: Articles found but none queued

**Likely cause:** All articles are duplicates (already processed)
**This is NORMAL** - means system is working correctly

### Issue: Articles queued but no scoring logs

**Check:**
1. Look for `Tiingo article scoring thread started`
2. Check for OpenAI API errors
3. Check Railway memory usage (may be throttling)

### Issue: Scored but no consumption logs

**Check:**
1. Sentiment calculation loop is running
2. Look for errors in `sentiment_realtime_v2.py`

### Issue: 401 Unauthorized errors

**Cause:** Invalid Tiingo API key
**Fix:** Check `TIINGO_API_KEY` in Railway variables

---

## 🎯 Success Indicators

**✅ Tiingo is working correctly when you see:**

1. Query logs every 5 seconds
2. Articles being found (at least during market hours)
3. New articles being queued (not all duplicates all the time)
4. Scoring completing with impact values
5. Impacts being consumed by sentiment system
6. No repeated errors

**Expected log flow:**
```
[Every 5 seconds]
📰 TIINGO QUERY START
   → Querying tickers
   ✓ X articles found
   → Querying market
   ✓ Y articles found
📰 COMPLETE: Z queued

[Background, as articles score]
   🤖 Scoring article
   ✅ SCORED: impact=+X.XX

[Every 1 second in sentiment loop]
   💰 Consuming N Tiingo impacts
Applied Tiingo article impact: +X.XX
```

---

## 📊 Performance Metrics

### Normal Operations:

- **API calls:** 12 per minute (2 per query × 12 queries)
- **CPU usage:** +2-5% (polling + scoring)
- **Memory usage:** +50-100MB (queues + caching)
- **Articles/minute:** 50-200 during market hours

### Queue Status:

- **article_to_score_queue:** Should stay under 20 items
- **scored_article_queue:** Should drain quickly (consumed every second)
- **Queue full warnings:** Occasional is OK, frequent means system overload

---

## 🔧 Quick Diagnostic Commands

### Check Tiingo Stats (if you can access Railway shell):

```bash
railway run python manage.py shell
```

```python
from api.management.commands.tiingo_realtime_news import get_stats
stats = get_stats()
print(stats)

# Expected output:
# {
#   'enabled': True,
#   'query_count': 150,
#   'last_query_time': '2025-11-28T10:12:35',
#   'queue_size': 3,
#   'scored_queue_size': 0,
#   'scoring_thread_alive': True
# }
```

---

## 📞 Summary

**With these enhanced logs, you can now:**

1. ✅ See exactly when Tiingo queries run
2. ✅ See what articles are being found
3. ✅ See which articles are new vs duplicates
4. ✅ See scoring progress in real-time
5. ✅ See impacts being applied to sentiment
6. ✅ Diagnose any issues immediately

**No more guessing if Tiingo is working!** 🚀

---

*Updated: November 28, 2025*
*Commits:*
*- dec4779: Fixed loop condition (independent of WebSocket)*
*- fef79e7: Enhanced logging detail*
*- 008fbca: Made error logs always visible*
*- c285943: Added print() statements for Railway visibility (CRITICAL FIX)*
