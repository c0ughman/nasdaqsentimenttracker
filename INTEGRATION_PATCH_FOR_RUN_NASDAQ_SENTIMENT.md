# Integration Patch for run_nasdaq_sentiment.py

## 🎯 Purpose

Modify `run_nasdaq_sentiment.py` to intelligently detect if second-by-second system is running and adjust behavior:
- **If running**: Skip decay, skip Finnhub (already happening every second)
- **If not running**: Normal operation (backwards compatible)

---

## 📝 Changes to Make

### **1. Add Import at Top of File**

```python
# Near the top of run_nasdaq_sentiment.py, after other imports:

# Real-time integration (optional - backwards compatible)
try:
    from api.management.commands.sentiment_integration import (
        get_starting_scores_for_minute_analysis,
        is_second_by_second_active,
        save_minute_analysis_to_both_tables
    )
    REALTIME_INTEGRATION_AVAILABLE = True
    print("✅ Real-time integration available")
except ImportError:
    REALTIME_INTEGRATION_AVAILABLE = False
    print("ℹ️  Real-time integration not available (using standard mode)")
```

---

### **2. Modify News Score Calculation**

Find the section where news decay is applied (around line 1315-1320).

**REPLACE THIS:**
```python
# Calculate time elapsed since last update (in minutes)
time_elapsed = (timezone.now() - latest_run.timestamp).total_seconds() / 60
minutes_elapsed = max(1, int(time_elapsed))

# Apply decay to previous score (no new articles)
news_composite = apply_news_decay(previous_news_composite, minutes_elapsed)
```

**WITH THIS:**
```python
# Check if second-by-second system is running
if REALTIME_INTEGRATION_AVAILABLE and is_second_by_second_active(ticker_symbol):
    # Second-by-second is active - get latest SecondSnapshot
    print("🔄 Second-by-second system active - using latest SecondSnapshot")
    starting_scores = get_starting_scores_for_minute_analysis(ticker_symbol)
    
    if starting_scores and starting_scores['use_as_base']:
        # Use SecondSnapshot scores (decay already applied 60 times)
        news_composite = starting_scores['news']
        print(f"   ✓ News from SecondSnapshot: {news_composite:+.2f} (decay already applied)")
        print(f"   ✓ Age: {starting_scores['age_seconds']:.1f} seconds")
        
        # Also get other components
        previous_reddit = starting_scores['reddit']
        previous_technical = starting_scores['technical']
        previous_analyst = starting_scores['analyst']
        
        # Flag that we're using real-time mode
        using_realtime_base = True
    else:
        # SecondSnapshot too old, fall back to normal decay
        print("   ⚠️  SecondSnapshot too old, falling back to normal decay")
        time_elapsed = (timezone.now() - latest_run.timestamp).total_seconds() / 60
        minutes_elapsed = max(1, int(time_elapsed))
        news_composite = apply_news_decay(previous_news_composite, minutes_elapsed)
        using_realtime_base = False
else:
    # Normal mode - apply decay as usual
    print("📉 Standard mode - applying normal decay")
    time_elapsed = (timezone.now() - latest_run.timestamp).total_seconds() / 60
    minutes_elapsed = max(1, int(time_elapsed))
    news_composite = apply_news_decay(previous_news_composite, minutes_elapsed)
    using_realtime_base = False
```

---

### **3. Skip Finnhub if Second-by-Second Active**

If you're using Finnhub in `run_nasdaq_sentiment.py` (I don't see it in current version, but if you add it):

```python
# Before querying Finnhub:
if REALTIME_INTEGRATION_AVAILABLE and is_second_by_second_active(ticker_symbol):
    print("⏭️  Skipping Finnhub - already handled by second-by-second system")
    # Don't query Finnhub here
else:
    # Query Finnhub normally
    finnhub_articles = fetch_finnhub_articles()
```

---

### **4. Modify Save Logic**

Find where `AnalysisRun` is saved (around line 1267+).

**REPLACE THIS:**
```python
# Save to database
analysis_run = AnalysisRun.objects.create(
    ticker=ticker,
    composite_score=final_composite_score,
    # ... other fields
)
```

**WITH THIS:**
```python
# Save to database
if REALTIME_INTEGRATION_AVAILABLE and using_realtime_base:
    # Save to both AnalysisRun AND SecondSnapshot for continuity
    print("💾 Saving to both AnalysisRun and SecondSnapshot")
    
    analysis_run, second_snapshot = save_minute_analysis_to_both_tables(
        ticker=ticker,
        news_composite=news_composite,
        reddit_composite=reddit_sentiment,
        technical_composite=tech_composite,
        analyst_composite=analyst_sentiment,
        composite_score=final_composite_score,
        # Pass all other fields
        sentiment_label=sentiment_label,
        avg_base_sentiment=avg_base_sentiment,
        avg_surprise_factor=avg_surprise_factor,
        avg_novelty=avg_novelty,
        avg_source_credibility=avg_source_credibility,
        avg_recency_weight=avg_recency_weight,
        stock_price=stock_price,
        price_open=price_open,
        price_high=price_high,
        price_low=price_low,
        price_change_percent=price_change_percent,
        volume=volume,
        articles_analyzed=total_articles_analyzed,
        cached_articles=cached_count,
        new_articles=new_count,
        # ... all other fields
    )
    
    print(f"   ✓ Saved AnalysisRun: {analysis_run.id}")
    if second_snapshot:
        print(f"   ✓ Saved SecondSnapshot: {second_snapshot.timestamp}")
else:
    # Normal save (backwards compatible)
    print("💾 Saving to AnalysisRun only (standard mode)")
    
    analysis_run = AnalysisRun.objects.create(
        ticker=ticker,
        composite_score=final_composite_score,
        # ... all fields as before
    )
    
    print(f"   ✓ Saved AnalysisRun: {analysis_run.id}")
```

---

## 🔍 **What Gets Skipped When Second-by-Second is Active:**

### **1. Decay Calculation** ❌ Skip
```python
# DON'T DO THIS when second-by-second active:
minutes_elapsed = (now - previous).minutes
decayed_score = previous * (1 - 0.0383) ** minutes_elapsed

# INSTEAD: Use SecondSnapshot.news_score_cached directly
# (already has 60 seconds of decay applied)
```

### **2. Finnhub Queries** ❌ Skip
```python
# DON'T DO THIS when second-by-second active:
for symbol in WATCHLIST:
    articles = finnhub.company_news(symbol, ...)
    
# REASON: Already querying every second in finnhub_realtime_v2.py
# Querying again here would be duplicate work and waste API calls
```

### **3. Technical Micro Calculations** ❌ Skip (already in SecondSnapshot)
```python
# DON'T DO THIS when second-by-second active:
# Calculate ultra-short-term momentum from last 60 seconds

# REASON: Already calculated every second in sentiment_realtime_v2.py
# SecondSnapshot.technical_score_cached already includes micro blend
```

---

## ✅ **What Still Happens When Second-by-Second is Active:**

### **1. News Article Fetching** ✅ Still Do
```python
# STILL DO THIS:
company_articles = fetch_company_news(TICKERS)
market_articles = fetch_market_news()

# REASON: You might fetch from different sources than Finnhub
# Or fetch more comprehensive article sets
# Just use SecondSnapshot as base instead of applying decay
```

### **2. Reddit Analysis** ✅ Still Do
```python
# STILL DO THIS:
reddit_posts = fetch_reddit_posts()
reddit_sentiment = analyze_reddit_sentiment(reddit_posts)

# REASON: Not done in second-by-second (only at minute boundaries)
```

### **3. Analyst Recommendations** ✅ Still Do
```python
# STILL DO THIS:
analyst_data = fetch_analyst_recommendations()
analyst_sentiment = calculate_analyst_score(analyst_data)

# REASON: Not done in second-by-second (only at minute boundaries)
```

### **4. Technical Macro Indicators** ✅ Still Do
```python
# STILL DO THIS:
ohlcv = fetch_ohlcv_data()
rsi = calculate_rsi(ohlcv)
macd = calculate_macd(ohlcv)
tech_score = calculate_technical_composite(rsi, macd, ...)

# REASON: Macro technical (1-min RSI/MACD) needs full recalculation
# Second-by-second only blends, doesn't recalculate macro
```

---

## 🎯 **Summary of Changes:**

| Component | Normal Mode | Second-by-Second Active |
|-----------|-------------|-------------------------|
| **Decay** | ✅ Apply | ❌ Skip (already applied 60x) |
| **Finnhub** | ✅ Query | ❌ Skip (querying every second) |
| **News Fetch** | ✅ Do | ✅ Do (different sources) |
| **Reddit** | ✅ Do | ✅ Do (minute-only) |
| **Analyst** | ✅ Do | ✅ Do (minute-only) |
| **Technical Macro** | ✅ Do | ✅ Do (full recalc) |
| **Save Location** | AnalysisRun only | Both tables |

---

## 🔧 **Testing the Changes:**

### **Test 1: Second-by-Second Not Running**
```bash
# Don't start WebSocket collector
python manage.py run_nasdaq_sentiment --once

# Should see:
# "ℹ️  Real-time integration not available (using standard mode)"
# OR
# "📉 Standard mode - applying normal decay"
# Decay applied normally ✓
```

### **Test 2: Second-by-Second Running**
```bash
# Terminal 1: Start WebSocket collector
python manage.py run_websocket_collector_v2 --symbol QLD

# Terminal 2: Wait 1 minute, then run analysis
python manage.py run_nasdaq_sentiment --once

# Should see:
# "🔄 Second-by-second system active - using latest SecondSnapshot"
# "✓ News from SecondSnapshot: +39.5 (decay already applied)"
# "⏭️  Skipping Finnhub - already handled by second-by-second system"
# "💾 Saving to both AnalysisRun and SecondSnapshot"
```

---

## ⚠️ **Important Notes:**

1. **Backwards Compatible**: If integration module not available, works normally
2. **Automatic Detection**: Uses `is_second_by_second_active()` to check
3. **Age Check**: If SecondSnapshot > 70 seconds old, falls back to normal mode
4. **No Breaking Changes**: Existing functionality preserved

---

## 📋 **Quick Implementation Checklist:**

- [ ] Add import at top of file
- [ ] Modify news decay section
- [ ] Add Finnhub skip logic (if applicable)
- [ ] Modify save logic to use both tables
- [ ] Test with WebSocket off (should work normally)
- [ ] Test with WebSocket on (should use SecondSnapshot)
- [ ] Verify no decay applied when using SecondSnapshot
- [ ] Verify saves to both tables when active

---

**Would you like me to create the actual modified version of run_nasdaq_sentiment.py with these changes applied?**


