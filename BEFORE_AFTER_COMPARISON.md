# Before/After Comparison - Sentiment Scoring Changes

## Visual Comparison

### Article Scoring

**BEFORE:**
```
Article: "Apple beats expectations with record iPhone sales"
├─ FinBERT sentiment: +0.6
├─ Surprise factor: 1.8 (beats expectations)
└─ Source credibility: 1.0 (Reuters)

Calculation:
  0.6 × 70% × 100 = 42
  + (1.8 - 1) × 15% × 50 = 6
  + 1.0 × 15% × 20 = 3
  = 51 points

Applied to AAPL (12% market cap):
  51 × 0.12 = 6.12 contribution
```

**AFTER:**
```
Article: "Apple beats expectations with record iPhone sales"
├─ FinBERT sentiment: +0.6
├─ Surprise factor: 1.8 (beats expectations)
└─ Source credibility: 1.0 (Reuters)

Calculation:
  0.6 × 70% × 250 = 105
  + (1.8 - 1) × 15% × 150 = 18
  + (1.0 - 0.5) × 15% × 50 = 3.75
  = 126.75 points

Applied to AAPL (12% market cap):
  126.75 × 0.12 = 15.21 contribution
```

**Impact:** 2.5x more contribution per article (6.12 → 15.21)

---

### Full Run Example

**Scenario:** 200 articles processed (180 company, 20 market)

#### BEFORE (Old System)

**Step 1: Score Articles**
```
AAPL articles (10): avg score = +45
MSFT articles (8): avg score = +32
NVDA articles (12): avg score = +52
... (17 more tickers)
Market articles (20): avg score = +38
```

**Step 2: Average by Ticker**
```
AAPL ticker average: 45
MSFT ticker average: 32
NVDA ticker average: 52
```

**Step 3: Apply Market Cap Weights**
```
AAPL: 45 × 0.12 = 5.4
MSFT: 32 × 0.105 = 3.36
NVDA: 52 × 0.085 = 4.42
... sum all = 85.2
```

**Step 4: Apply 70/30 Split**
```
Company sentiment: 85.2
Market sentiment: 38

Weighted combo:
  85.2 × 0.70 = 59.64
  38 × 0.30 = 11.4
  Total = 71.04

After averaging by 200 articles:
  71.04 / 200 = 0.355
```

**Step 5: Add to Decayed Score**
```
Previous: 0.24
Decayed (5 mins): 0.20
New contribution: 0.355
Final news_composite: 0.555
```

**Result: +0.56 points** (effectively a flat line)

---

#### AFTER (New System)

**Step 1: Score Articles (Amplified)**
```
AAPL articles (10): avg score = +112
MSFT articles (8): avg score = +80
NVDA articles (12): avg score = +130
... (17 more tickers)
Market articles (20): avg score = +95
```

**Step 2: Apply Weights DIRECTLY**
```
Each AAPL article: score × 0.12 weight
Each MSFT article: score × 0.105 weight
Each NVDA article: score × 0.085 weight
Each market article: score × 0.30 weight

Total weighted sum: 2,850
Article count: 200
```

**Step 3: Average Weighted Contributions**
```
New article impact: 2,850 / 200 = 14.25
Per-run cap: ±25 (not exceeded, no capping)
```

**Step 4: Add to Decayed Score**
```
Previous: 24 (scaled up from old 0.24)
Decayed (5 mins): 19.74
New contribution: 14.25
Final news_composite: 33.99
Cap at ±100: 33.99 (under cap)
```

**Result: +34 points** (clearly visible movement)

---

## Score Trajectory Over Time

**Scenario:** Major bullish news at 9:30 AM, then no new articles

### BEFORE (Old System)

| Time | New Articles | Previous | Decayed | New Impact | Final Score |
|------|--------------|----------|---------|------------|-------------|
| 9:30 AM | Yes (200) | 0.24 | 0.20 | +0.35 | **0.55** |
| 9:35 AM | No | 0.55 | 0.45 | 0 | **0.45** |
| 10:00 AM | No | 0.45 | 0.14 | 0 | **0.14** |
| 11:00 AM | No | 0.14 | 0.01 | 0 | **0.01** |

**Observation:** Movement barely visible (0.55 → 0.01)

---

### AFTER (New System)

| Time | New Articles | Previous | Decayed | New Impact | Final Score |
|------|--------------|----------|---------|------------|-------------|
| 9:30 AM | Yes (200) | 24 | 19.7 | +14.3 | **34.0** |
| 9:35 AM | No | 34.0 | 27.9 | 0 | **27.9** |
| 10:00 AM | No | 27.9 | 8.9 | 0 | **8.9** |
| 11:00 AM | No | 8.9 | 0.9 | 0 | **0.9** |

**Observation:** Clear movement and decay (34 → 0.9)

---

## Decay Visibility Comparison

**Starting score: +25**

| Minutes Elapsed | Old Scale (0.25) | New Scale (25) | Difference Visible? |
|-----------------|------------------|----------------|---------------------|
| 0 | 0.25 | 25.0 | - |
| 5 | 0.21 | 20.6 | ✅ YES (4.4 drop) |
| 10 | 0.17 | 16.9 | ✅ YES (3.7 drop) |
| 30 | 0.08 | 8.0 | ✅ YES (8.9 drop) |
| 60 | 0.02 | 2.4 | ✅ YES (5.6 drop) |
| 120 | 0.00 | 0.2 | ✅ YES (2.2 drop) |

**Old scale:** Changes of 0.04-0.08 are hard to notice
**New scale:** Changes of 2-9 points are clearly visible

---

## Impact on Final Composite Score

**4-Factor Model Weights:**
- News: 35%
- Reddit: 20%
- Technical: 25%
- Analyst: 20%

### BEFORE (Old System)

```
News:      0.55 × 35% = 0.19
Reddit:    -5.0 × 20% = -1.00
Technical: +8.0 × 25% = +2.00
Analyst:   +15  × 20% = +3.00

Final Composite: +4.19
```

**Observation:** News barely contributes (+0.19)

---

### AFTER (New System)

```
News:      34.0 × 35% = 11.90
Reddit:    -5.0 × 20% = -1.00
Technical: +8.0 × 25% = +2.00
Analyst:   +15  × 20% = +3.00

Final Composite: +15.90
```

**Observation:** News has meaningful contribution (+11.90)

---

## Code Complexity Comparison

### BEFORE (Old Approach)

```python
# Step 1: Group by ticker
for symbol in tickers:
    articles = get_articles_for_ticker(symbol)
    ticker_avg = sum(articles) / len(articles)
    ticker_averages[symbol] = ticker_avg

# Step 2: Apply weights
for symbol, avg in ticker_averages.items():
    weight = NASDAQ_TOP_20[symbol]
    weighted = avg × weight
    company_sentiment += weighted

# Step 3: Apply 70/30 split
new_contribution = (
    company_sentiment × 0.70 +
    market_sentiment × 0.30
)

# Step 4: Combine with decay
news_composite = decayed + new_contribution
```

**Lines of code:** ~60 lines
**Complexity:** O(n) + O(m) where n=articles, m=tickers

---

### AFTER (New Approach)

```python
# Step 1: Direct weighting
for article in all_articles:
    if article.type == 'market':
        weight = 0.30
    else:
        weight = NASDAQ_TOP_20[article.ticker]

    total_weighted += article.score × weight

# Step 2: Average
new_impact = total_weighted / len(all_articles)
new_impact = cap(new_impact, -25, 25)

# Step 3: Combine with decay
news_composite = decayed + new_impact
```

**Lines of code:** ~25 lines
**Complexity:** O(n) where n=articles

**Impact:** 60% less code, simpler logic, better performance

---

## Summary

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Article score range | -20 to +20 | -50 to +50 | 2.5x |
| Per-run impact | ±0.5 to ±3 | ±10 to ±25 | 8x |
| Decay visibility | Invisible | Clearly visible | ✅ |
| News composite range | -5 to +5 | -20 to +30 | 5x |
| Code complexity | 60 lines | 25 lines | -58% |
| Logic steps | 4 steps | 3 steps | -25% |
| Movement responsiveness | Flat line | Dynamic | ✅ |

---

## Why This Works Better

1. **Amplification:** 3x multipliers make individual articles matter
2. **Direct weighting:** Eliminates dilution from double averaging
3. **Simplified logic:** Fewer steps = fewer places to lose signal
4. **Proper scale:** System was designed for ±100 range, now uses it
5. **Visible decay:** Same decay rate, but operating on visible numbers

**Key insight:** The old system was mathematically correct but operating at 1/10th the scale it was designed for. By scaling up and simplifying, we achieve the intended behavior without changing the fundamental logic.
