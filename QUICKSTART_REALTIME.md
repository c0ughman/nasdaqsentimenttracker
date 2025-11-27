# Quick Start: Real-Time Sentiment (Second-by-Second)

## What Changed?

✅ **Sentiment now updates EVERY SECOND** (not every 5 minutes)  
✅ **News decays smoothly** (per second, not per minute)  
✅ **Micro momentum added** (1-second price velocity)  
✅ **All calculations < 1 second** (won't slow down WebSocket)

---

## Files Added/Modified

### **NEW FILES:**
1. `api/management/commands/sentiment_realtime.py` - Core sentiment module
2. `test_realtime_sentiment.py` - Comprehensive test suite
3. `REALTIME_SENTIMENT_GUIDE.md` - Full documentation
4. `QUICKSTART_REALTIME.md` - This file

### **MODIFIED FILES:**
1. `api/management/commands/run_websocket_collector_v2.py` - Added sentiment scoring
2. `api/views.py` - Added `/api/realtime-sentiment/` endpoint
3. `api/urls.py` - Registered new endpoint

---

## Quick Test (5 Minutes)

### 1. Run Tests
```bash
cd /Users/coughman/Desktop/Nasdaq-Sentiment-Tracker-Clean/backend

# Run comprehensive test suite
python test_realtime_sentiment.py
```

**Expected:** All tests pass, performance < 1 second ✅

---

### 2. Start WebSocket Collector

```bash
# In terminal 1
python manage.py run_websocket_collector_v2 --symbol QLD --verbose
```

**Look for these log messages:**
```
📊 1-sec candle #10: 14:30:45 | O:85.42 H:85.45 L:85.41 C:85.44 | 23 ticks
💚 Sentiment #10: Composite=+42.5 (News=+35.2, Macro=+48.3, Micro=+38.7)
```

If you see both messages, **sentiment is working!** ✅

---

### 3. Query the API

```bash
# In terminal 2 (while collector is running)
curl http://localhost:8000/api/realtime-sentiment/?seconds=10
```

**Expected response:**
```json
{
  "latest": {
    "composite_score": 42.5,
    "news_component": 35.2,
    "technical_component": 48.3,
    "timestamp": "2025-11-20T14:30:45Z",
    "price": 85.44
  },
  "data_points": [
    {"timestamp": "...", "composite_score": 42.3, ...},
    {"timestamp": "...", "composite_score": 42.4, ...},
    ...
  ],
  "count": 10
}
```

If you see scores, **API is working!** ✅

---

## Configuration (Optional)

Edit `api/management/commands/sentiment_realtime.py`:

```python
# Line 25-26: Decay rate
MINUTE_DECAY_RATE = 0.0383  # 3.83% per minute
# Try: 0.02 for slower decay, 0.05 for faster

# Line 28-30: Component weights
WEIGHT_NEWS = 0.40              # News (decaying)
WEIGHT_TECHNICAL_MACRO = 0.35   # 1-min indicators
WEIGHT_TECHNICAL_MICRO = 0.25   # 1-sec momentum
```

Restart WebSocket collector to apply changes.

---

## Troubleshooting

### ❌ "No sentiment data available"
**Fix:** Run main sentiment first to populate news:
```bash
python manage.py run_nasdaq_sentiment --once
```

### ❌ Sentiment scores are all zero
**Fix:** Wait 60 seconds for macro cache to populate, or check logs for errors.

### ❌ "Ticker QLD not found"
**Fix:** Create ticker:
```bash
python manage.py shell
>>> from api.models import Ticker
>>> Ticker.objects.create(symbol='QLD', company_name='ProShares Ultra QQQ')
```

---

## For Your Presentation Tomorrow

### Key Points to Highlight:

1. **Second-by-second updates** - No more waiting 5 minutes
2. **Smooth decay** - Score changes gradually, not in steps
3. **Multi-timeframe** - Combines 1-sec micro and 1-min macro indicators
4. **Fast & reliable** - All calculations < 10ms typically
5. **Simple architecture** - 3 components, easy to tune

### Demo Flow:

1. Start WebSocket collector (show live logs)
2. Open API endpoint in browser
3. Refresh every few seconds to show score updating
4. Point out the three components (news, macro, micro)
5. Show how score responds to price movements

### Visual:
```
Old system:  [====5min====][====5min====][====5min====]
             Score: 42 → 42 → 42 → 42 → 45 (jump!)

New system:  [=1s=][=1s=][=1s=][=1s=][=1s=]...
             Score: 42.0 → 42.1 → 42.3 → 42.5 → 42.8 (smooth!)
```

---

## Next Steps (After Presentation)

### Phase 2: Finnhub Integration
- Add rotating queries (1 per second)
- Detect breaking headlines
- Weight: 20-25%

### Phase 3: Frontend Real-Time Chart
- Chart.js with 1-second updates
- Show all 3 components separately
- Color-coded momentum indicators

### Phase 4: Machine Learning
- Train LSTM on sentiment→price
- Predict next 10-second momentum
- Blend with current micro score

---

## Architecture Diagram

```
Every Second:
┌──────────────────────────────────────┐
│ WebSocket receives tick data        │
└──────────────┬───────────────────────┘
               ↓
┌──────────────────────────────────────┐
│ Aggregate into 1-sec candle          │
│ (OHLCV from all ticks that second)   │
└──────────────┬───────────────────────┘
               ↓
┌──────────────────────────────────────┐
│ Calculate sentiment:                 │
│ ├─ News (decayed per second)         │
│ ├─ Macro (cached, recalc @ minute)   │
│ └─ Micro (calculated from last 60s)  │
└──────────────┬───────────────────────┘
               ↓
┌──────────────────────────────────────┐
│ Save SecondSnapshot with:            │
│ • composite_score                    │
│ • news_score_cached                  │
│ • technical_score_cached             │
└──────────────┬───────────────────────┘
               ↓
┌──────────────────────────────────────┐
│ API endpoint serves data:            │
│ GET /api/realtime-sentiment/         │
└──────────────────────────────────────┘
```

---

## Summary

✅ **Implementation complete**  
✅ **Tests passing**  
✅ **API working**  
✅ **Performance validated (< 1 second)**  
✅ **Documentation ready**  

**You're ready to present!** 🚀

For detailed explanation, see: `REALTIME_SENTIMENT_GUIDE.md`


