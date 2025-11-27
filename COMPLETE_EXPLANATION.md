# Complete Explanation: Second-by-Second Sentiment System

## 🎯 What I Built - The Full Picture

### **TWO PARALLEL SCORING SYSTEMS**

You now have **TWO different composite scores** running simultaneously:

```
┌─────────────────────────────────────────────────────────────┐
│ SYSTEM 1: Minute-by-Minute (EXISTING)                      │
├─────────────────────────────────────────────────────────────┤
│ • Runs: Every 1 minute (Railway cron)                      │
│ • Command: run_nasdaq_sentiment.py                         │
│ • Stores in: AnalysisRun table                             │
│ • Fields:                                                   │
│   - composite_score (main score)                           │
│   - news_composite (news component)                        │
│   - technical_score (technical component)                  │
│   - reddit_score (social component)                        │
│   - analyst_score (analyst component)                      │
│ • This is your COMPREHENSIVE analysis                      │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ SYSTEM 2: Second-by-Second (NEW)                           │
├─────────────────────────────────────────────────────────────┤
│ • Runs: Every 1 second (WebSocket collector)               │
│ • Command: run_websocket_collector_v2.py                   │
│ • Stores in: SecondSnapshot table                          │
│ • Fields:                                                   │
│   - composite_score (real-time score)                      │
│   - news_score_cached (from System 1, decayed)            │
│   - technical_score_cached (macro + micro blend)          │
│ • This is your REAL-TIME analysis                         │
└─────────────────────────────────────────────────────────────┘
```

### **The Relationship:**

```
System 1 (Every minute):
├─ Fetch 200+ articles
├─ Full FinBERT analysis
├─ Reddit scraping
├─ Analyst recommendations
└─ Creates: AnalysisRun.composite_score = +42.5
                    ↓
            (System 2 reads this)
                    ↓
System 2 (Every second):
├─ Read: AnalysisRun.composite_score (+42.5)
├─ Apply: Per-second decay → +42.48
├─ Add: Macro technical (cached) → +55.2
├─ Add: Micro momentum (real-time) → +12.3
├─ Optional: Finnhub real-time news → +3.5
└─ Creates: SecondSnapshot.composite_score = +45.1
```

---

## 📊 Micro Momentum - Detailed Explanation

**What is it?** The velocity of price movement over the last 30 seconds.

### **Step-by-Step Calculation:**

```python
# Say we have these prices from the last 30 seconds:
second_0:  $85.42  ← 30 seconds ago
second_1:  $85.43
second_2:  $85.44
second_3:  $85.45
...
second_29: $85.50  ← right now

# Step 1: Calculate % change
pct_change = (85.50 - 85.42) / 85.42 * 100
           = 0.094%  (up 0.094% in 30 seconds)

# Step 2: Scale to sentiment range
# A 1% move in 30 seconds is SIGNIFICANT (that's 2% per minute!)
# So we amplify: multiply by 15
momentum_score = 0.094 * 15 = +1.4 points

# Step 3: Clip to -100/+100 range
final_score = clip(1.4, -100, 100) = +1.4
```

### **Real Examples:**

| Price Movement | % Change | Micro Score | Interpretation |
|----------------|----------|-------------|----------------|
| $85.00 → $85.00 | 0% | 0 | Flat market |
| $85.00 → $85.50 | +0.59% | +8.8 | Moderate bullish |
| $85.00 → $86.00 | +1.18% | +17.7 | Strong bullish |
| $85.00 → $84.50 | -0.59% | -8.8 | Moderate bearish |
| $85.00 → $80.00 | -5.88% | -88.2 | Crash (clipped to -100) |

### **Why It's Different from 1-Minute RSI:**

| Indicator | Window | What It Measures | Updates |
|-----------|--------|------------------|---------|
| **RSI (1-min)** | 14 minutes | Overbought/oversold relative to recent highs/lows | Every minute |
| **Micro Momentum** | 30 seconds | Raw price velocity (speed of movement) | Every second |

**They measure different things:**
- RSI might be 50 (neutral) while price is surging → Micro catches it
- RSI might be 70 (overbought) but price is flat → Micro shows 0

---

## 🔥 Finnhub Real-Time Implementation

### **How It Works:**

```
Second 1:  Query AAPL news → Found 1 new article → Score it → Add +2.3 points
Second 2:  Query MSFT news → No new articles → Add 0 points
Second 3:  Query GOOGL news → Found 1 new article → Score it → Add +1.5 points
Second 4:  Query AMZN news → No new articles → Add 0 points
...
Second 40: Query MELI news → Back to AAPL in next second
```

### **Article Processing Flow:**

```
1. Finnhub returns article:
   {
     "headline": "Apple beats Q4 earnings by 15%",
     "summary": "Strong iPhone sales drive record quarter...",
     "url": "https://...",
     "datetime": 1700000000
   }

2. Check if already seen:
   if article in cache:
       skip  # Already processed

3. Quick sentiment score (keyword-based):
   headline.lower() → contains "beats" → bullish
   sentiment = +0.8  (on -1 to +1 scale)

4. Calculate impact:
   AAPL weight = 14% of NASDAQ
   impact = +0.8 * 14 = +11.2 points

5. Add to running score:
   finnhub_news_score += 11.2
   
6. Update composite THIS SECOND:
   composite = (
       base_news_decayed * 0.35 +      # From AnalysisRun
       technical_macro * 0.25 +         # Cached 1-min
       technical_micro * 0.15 +         # Real-time velocity
       finnhub_realtime * 0.25          # NEW real-time news
   )
   
   SecondSnapshot.composite_score = composite
```

### **Two Options for Scoring:**

**Option A: Keyword-Based (FAST - no API call)**
```python
def quick_sentiment_score(headline):
    bullish = ['beat', 'surge', 'upgrade', 'profit']
    bearish = ['miss', 'drop', 'downgrade', 'loss']
    
    # Count keywords
    if 'beat' in headline: return +0.8
    if 'miss' in headline: return -0.8
    return 0.0
```
- ✅ Instant (< 1ms)
- ⚠️ Less accurate than FinBERT
- ✅ Good enough for real-time additions

**Option B: Cached FinBERT (ACCURATE - uses API)**
```python
def cached_finbert_score(headline):
    # Check if we've scored this exact headline before
    if headline in finbert_cache:
        return finbert_cache[headline]
    
    # New headline - call FinBERT API
    sentiment = finbert_api.analyze(headline)
    finbert_cache[headline] = sentiment
    return sentiment
```
- ✅ Very accurate
- ⚠️ Slower (API call)
- ✅ Caches results (only slow first time)

**My recommendation:** Start with Option A (keyword), add Option B later if needed.

---

## 🤔 Your Questions Answered

### **Q1: "Why not run news scoring every second for 40 seconds instead of every minute?"**

**Answer:** You COULD, but here's the tradeoff:

**Current Setup (Every minute):**
```
Minute 1: ├─ Fetch 200+ articles
          ├─ Batch FinBERT (30 API calls)
          ├─ Reddit scraping
          ├─ Analyst data
          └─ Takes ~15-20 seconds total

Wait 40 seconds...

Minute 2: Repeat
```

**Proposed (Every second for 40 seconds):**
```
Second 1:  Fetch 5 articles → Score → 0.5 sec
Second 2:  Fetch 5 articles → Score → 0.5 sec
...
Second 40: Fetch 5 articles → Score → 0.5 sec

Total: 200 articles processed over 40 seconds (same as before)
```

**The issue:**
- FinBERT API calls would spread out over 40 seconds (instead of batch)
- This is SLOWER and more complex
- Batching is more efficient (one HTTP request for 10 articles vs 10 requests)

**Better approach:** Keep minute-by-minute for comprehensive analysis, add Finnhub for real-time breaking news.

```
System 1 (Every minute): Deep analysis of 200+ articles
System 2 (Every second): Quick check for breaking news via Finnhub
```

### **Q2: "If Finnhub finds an article between minutes, how do we add it?"**

**Answer:** Exactly what I implemented in `finnhub_realtime.py`:

```
Minute 0:00 → System 1 runs → Base score = +40.0
Second 0:01 → No Finnhub news → Composite = +40.0
Second 0:02 → No Finnhub news → Composite = +39.99 (decay)
Second 0:15 → FINNHUB FINDS ARTICLE! → Score it → +5.0
              → Composite = +39.85 + 5.0 = +44.85  ← INSTANT UPDATE
Second 0:16 → No Finnhub news → Composite = +44.84 (decay)
...
Minute 1:00 → System 1 runs → New base score = +45.2
```

The article is **immediately added** to `SecondSnapshot.composite_score` without waiting for the next minute.

### **Q3: "Are we creating a new score or updating the existing composite?"**

**Critical clarification:** We're creating **SEPARATE scores** in **SEPARATE tables**.

```
┌─────────────────────────────────────────────────┐
│ AnalysisRun (Minute-by-Minute)                  │
├─────────────────────────────────────────────────┤
│ timestamp: 14:30:00                            │
│ composite_score: +42.5  ← System 1 creates this│
│ news_composite: +38.2                          │
│ technical_score: +55.1                         │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│ SecondSnapshot (Second-by-Second)               │
├─────────────────────────────────────────────────┤
│ timestamp: 14:30:01                            │
│ composite_score: +43.1  ← System 2 creates this│
│ news_score_cached: +38.1 (from AnalysisRun)   │
│ technical_score_cached: +48.7 (macro + micro) │
├─────────────────────────────────────────────────┤
│ timestamp: 14:30:02                            │
│ composite_score: +43.3  ← Different score!    │
│ news_score_cached: +38.0 (decayed)            │
│ technical_score_cached: +49.2                 │
└─────────────────────────────────────────────────┘
```

**They're independent:**
- `AnalysisRun.composite_score` = Comprehensive analysis (news + reddit + analyst + technical)
- `SecondSnapshot.composite_score` = Real-time analysis (news_cached + macro + micro + finnhub)

### **Q4: "Do news/technical/composite all have second-by-second components?"**

**Yes!** Here's the breakdown:

```python
# Every second in SecondSnapshot:

# 1. News Component (second-by-second via decay)
news_base = AnalysisRun.news_composite  # +38.2 (from minute analysis)
seconds_elapsed = 15
news_decayed = 38.2 * (0.99994 ** 15) = +38.18  ← Changes every second!

# 2. Technical Component (second-by-second via macro cache + micro calc)
technical_macro = get_macro_technical_score()  # +55.1 (cached for 60 sec)
technical_micro = calculate_micro_momentum()   # +12.3 (calculated now)
technical_combined = (55.1 * 0.58) + (12.3 * 0.42) = +37.1  ← Changes every second!

# 3. Finnhub Component (second-by-second via queries)
finnhub_score = get_finnhub_realtime_score()  # +3.5 (updates when articles found)

# 4. Final Composite (second-by-second)
composite = (
    news_decayed * 0.35 +          # +38.18 * 0.35 = +13.4
    technical_combined * 0.40 +    # +37.1 * 0.40 = +14.8
    finnhub_score * 0.25           # +3.5 * 0.25 = +0.9
)
composite = +29.1  ← This goes in SecondSnapshot.composite_score

# Save to database
SecondSnapshot.objects.create(
    timestamp=now,
    composite_score=+29.1,           # ← THE real-time score
    news_score_cached=+38.18,        # ← For debugging
    technical_score_cached=+37.1     # ← For debugging
)
```

**So yes:**
- News score updates every second (via decay + Finnhub additions)
- Technical score updates every second (macro cached, micro real-time)
- Composite score updates every second (combines all)

---

## 🔄 Complete Data Flow

### **Without Finnhub (Current Implementation):**

```
MINUTE BOUNDARY (e.g., 14:30:00):
├─ run_nasdaq_sentiment.py executes
├─ Analyzes 200+ articles with FinBERT
├─ Calculates comprehensive score
└─ Saves to AnalysisRun:
    • composite_score: +42.5
    • news_composite: +38.2
    • technical_score: +55.1

SECOND 1 (14:30:01):
├─ WebSocket creates 1-sec candle
├─ Calls calculate_realtime_composite():
│   ├─ get_news_sentiment_decayed() → +38.18 (1 sec decay)
│   ├─ get_macro_technical_score() → +55.1 (cached)
│   └─ calculate_micro_momentum() → +12.3 (real-time)
└─ Saves to SecondSnapshot:
    • composite_score: +43.1
    • news_score_cached: +38.18
    • technical_score_cached: +48.7

SECOND 2 (14:30:02):
├─ WebSocket creates 1-sec candle
├─ Calls calculate_realtime_composite():
│   ├─ get_news_sentiment_decayed() → +38.16 (2 sec decay)
│   ├─ get_macro_technical_score() → +55.1 (still cached)
│   └─ calculate_micro_momentum() → +13.8 (price moved up!)
└─ Saves to SecondSnapshot:
    • composite_score: +43.5
    • news_score_cached: +38.16
    • technical_score_cached: +49.2

... continues every second ...

SECOND 60 (14:31:00):
├─ WebSocket creates 1-sec candle
├─ Calls calculate_realtime_composite(force_macro_recalc=True):
│   ├─ get_news_sentiment_decayed() → +37.85 (60 sec decay)
│   ├─ get_macro_technical_score() → +52.3 (RECALCULATED!)
│   └─ calculate_micro_momentum() → +15.2
└─ Saves to SecondSnapshot:
    • composite_score: +42.8

ALSO AT SECOND 60:
└─ run_nasdaq_sentiment.py executes again
    └─ New AnalysisRun created with fresh base scores
```

### **With Finnhub (Proposed Enhancement):**

```
SECOND 1:
├─ WebSocket creates candle
├─ Query Finnhub (AAPL) → No new articles
├─ calculate_realtime_composite():
│   ├─ News: +38.18 (decayed)
│   ├─ Technical: +48.7
│   └─ Finnhub: +0.0 (no articles)
└─ Composite: +43.1

SECOND 15:
├─ WebSocket creates candle
├─ Query Finnhub (NVDA) → FOUND NEW ARTICLE!
│   ├─ Headline: "NVIDIA announces new AI chip"
│   ├─ Quick score: +0.9 (bullish)
│   ├─ Impact: +0.9 * 6% = +5.4 points
│   └─ Add to finnhub_score: +5.4
├─ calculate_realtime_composite():
│   ├─ News: +37.95 (decayed)
│   ├─ Technical: +49.1
│   └─ Finnhub: +5.4 (NEW!)
└─ Composite: +48.2  ← JUMPED UP from breaking news!

SECOND 16:
├─ WebSocket creates candle
├─ Query Finnhub (TSLA) → No new articles
├─ calculate_realtime_composite():
│   ├─ News: +37.94 (decayed)
│   ├─ Technical: +49.3
│   └─ Finnhub: +5.4 (still cached)
└─ Composite: +48.4
```

---

## 📈 Visual Comparison

### **Old System (5-minute updates):**
```
Score over time:
45 |     ●━━━━━━━━━━━━●━━━━━━━━━━━━●
40 |
35 |
   |_____|_____|_____|_____|_____|_____|
   0:00  0:05  0:10  0:15  0:20  0:25
   
Jumpy, stale between updates
```

### **Current System (1-minute updates):**
```
Score over time:
45 |  ●━━●━━●━━●━━●━━●━━●━━●━━●━━●
40 |
35 |
   |__|__|__|__|__|__|__|__|__|__|
   :00 :06 :12 :18 :24 :30 :36 :42
   
Better, but still steps
```

### **New System (1-second updates):**
```
Score over time:
45 |  ●-●-●-●-●-●-●-●-●-●-●-●-●-●
40 |
35 |
   |_|_|_|_|_|_|_|_|_|_|_|_|_|_
   :00:02:04:06:08:10:12:14:16
   
Smooth, continuous, responsive!
```

### **With Finnhub (breaking news spike):**
```
Score over time:
50 |                    ●─────●
45 |  ●─●─●─●─●─●─●─●─●↗      ↘●
40 |                              ●
   |_|_|_|_|_|_|_|_|_|_|_|_|_|_|_
   :00 :10 :20 :30 :40 :50 :00 :10
           ^
           Breaking news detected at :23
           (NVDA chip announcement)
```

---

## 🎯 Summary

### **What You Have Now:**

1. **System 1 (Comprehensive):** Minute-by-minute deep analysis
   - Uses FinBERT, Reddit, Analysts
   - Stores in `AnalysisRun`
   - Provides foundation

2. **System 2 (Real-Time):** Second-by-second responsive scoring
   - Uses System 1 as base (with decay)
   - Adds macro technical (1-min cached)
   - Adds micro momentum (1-sec real-time)
   - Stores in `SecondSnapshot`
   - Updates continuously

3. **System 3 (Optional - Finnhub):** Breaking news detection
   - Queries 1 symbol per second
   - Scores headlines instantly
   - Adds to composite immediately
   - Rotates through 40 stocks

### **Final Weights (With Finnhub):**

```python
composite_score = (
    base_news_decayed * 0.35 +      # From AnalysisRun
    technical_macro * 0.25 +         # 1-min RSI/MACD
    technical_micro * 0.15 +         # 1-sec momentum
    finnhub_realtime * 0.25          # Breaking headlines
)
```

### **Which Score Should Your Frontend Use?**

- **For dashboards:** Use `SecondSnapshot.composite_score` (real-time)
- **For analysis/reports:** Use `AnalysisRun.composite_score` (comprehensive)
- **For charts:** Use `SecondSnapshot` for 1-day view, `AnalysisRun` for historical

---

Does this clarify everything? Let me know which parts need more explanation!


