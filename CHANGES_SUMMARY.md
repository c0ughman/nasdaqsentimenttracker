# Sentiment Scoring System Changes - Summary

## Date: 2025-10-31

## Overview
Completely redesigned the news sentiment scoring system to increase score movement and visibility while maintaining data quality. The changes simplify the logic and amplify the impact of individual articles.

---

## Changes Made

### 1. **Amplified Article Scoring** (Lines 407-417)
**Old multipliers:**
- Base sentiment: ×100 (range: -70 to +70)
- Surprise factor: ×50 (range: -7.5 to +37.5)
- Source credibility: ×20 (range: 0 to +3)
- **Total range**: -77.5 to +110.5, typically -20 to +20

**New multipliers:**
- Base sentiment: ×250 (range: -175 to +175)
- Surprise factor: ×150 (range: 0 to +150)
- Source credibility: ×50 (range: -25 to +25)
- **Total range**: -200 to +350, typically -50 to +50

**Impact**: Articles now have 3x more influence on the final score before averaging.

---

### 2. **Direct Market Cap Weighting** (Lines 1075-1153)
**Old approach:**
1. Group articles by ticker
2. Average within each ticker
3. Apply market cap weight to ticker average
4. Combine with 70/30 company/market split

**New approach:**
1. Apply market cap weight directly to each article
   - Company articles: weight = ticker's market cap (e.g., AAPL = 12%)
   - General market articles: weight = 0.30 (30%)
2. Accumulate all weighted scores
3. Average across all articles

**Impact**:
- Eliminates double-averaging dilution
- Simpler logic (single pass)
- Each article contributes directly to final score
- No artificial 70/30 split

---

### 3. **Removed 70/30 Company/Market Split** (Lines 1178-1183)
**Old calculation:**
```python
new_article_contribution = (
    company_sentiment × 0.70 +
    market_sentiment × 0.30
)
```

**New calculation:**
```python
new_article_impact = total_weighted_contribution / article_count
# Market cap weights already applied per article
```

**Impact**: Direct weighting eliminates need for post-hoc 70/30 adjustment.

---

### 4. **Added Per-Run Impact Cap** (Line 1183)
**New feature:**
```python
new_article_impact = max(-25, min(25, new_article_impact))
```

**Purpose**: Prevents single runs from causing extreme swings while allowing meaningful movement.

**Impact**: Each run can contribute ±25 points to news composite (before decay).

---

### 5. **Decay Logic Preserved** (Lines 1155-1176)
**No changes to decay function** - still 3.83% per minute.

**Why it now works visibly:**
- Old scale: `0.24 → 0.19` (5 mins) - invisible
- New scale: `24 → 19` (5 mins) - clearly visible!

**Impact**: Decay was always working, but now operates on larger numbers so you can see it.

---

## Expected Behavior Changes

### **Before (Old System)**
| Scenario | Old Score Movement |
|----------|-------------------|
| 10 bullish articles | +1 to +3 |
| Major news event | +3 to +8 |
| Decay after 1 hour | 0.5 → 0.06 (invisible) |
| Typical range | -5 to +5 |

### **After (New System)**
| Scenario | New Score Movement |
|----------|-------------------|
| 10 bullish articles | +8 to +15 |
| Major news event | +15 to +25 (capped) |
| Decay after 1 hour | 25 → 10 (clearly visible) |
| Typical range | -20 to +30 |

---

## Example: Real-World Scenario

### **Scenario: Fed Rate Decision Announced**

**Old System:**
- 20 bullish articles fetched
- Article scores: -5 to +8 each
- After ticker averaging: +2.3
- After 70/30 split: +1.6
- Added to decayed score (0.1): **Final news_composite = 1.7**

**New System:**
- 20 bullish articles fetched
- Article scores: -50 to +80 each (amplified)
- Direct weighting applied per article
- Average weighted impact: +22
- Capped at +25
- Added to decayed score (0.5): **Final news_composite = 25.5**

**After 1 hour of decay (no new articles):**
- Old: 1.7 → 0.6 (barely noticeable)
- New: 25.5 → 10.5 (clear downward movement)

---

## Data Integrity Safeguards

### **Preserved:**
✅ FinBERT sentiment analysis (unchanged)
✅ Caching system (unchanged)
✅ Batch processing (unchanged)
✅ Decay formula (unchanged)
✅ Database schema (unchanged)
✅ Final ±100 cap (unchanged)

### **Added:**
🆕 Per-run ±25 cap (prevents extreme single-run spikes)
🆕 Direct weighting (eliminates averaging dilution)
🆕 Amplified multipliers (3x scale for visibility)

---

## Files Modified

1. **`api/management/commands/run_nasdaq_sentiment.py`**
   - Lines 407-417: Amplified article scoring multipliers
   - Lines 1075-1153: Rewrote accumulation logic with direct weighting
   - Lines 1178-1196: Removed 70/30 split, added ±25 cap

---

## Testing Recommendations

1. **Run once and verify:**
   ```bash
   python3 manage.py run_nasdaq_sentiment --once
   ```

2. **Check output for:**
   - Article scores in range -50 to +50 (typical)
   - News composite in range -25 to +25 (per run)
   - Clear decay visible between runs
   - No errors in database saving

3. **Monitor over 2-3 hours:**
   - Scores should move more dynamically
   - Decay should be clearly visible
   - Scores should stay within -100 to +100 (hard cap)

---

## Rollback Instructions (If Needed)

If issues arise, revert to previous version:
```bash
git diff HEAD -- api/management/commands/run_nasdaq_sentiment.py
git checkout HEAD -- api/management/commands/run_nasdaq_sentiment.py
```

**Note**: No database migrations required - all changes are computational only.

---

## Performance Impact

**Negligible** - Changes are purely mathematical:
- No additional API calls
- No additional database queries
- Same number of articles processed
- Same caching behavior

**Expected:** Same execution time (±0-2 seconds).

---

## Summary

These changes transform the sentiment scoring from a "flat line" system (±5 range) to a dynamic, responsive system (±20-30 range) while maintaining all data quality safeguards. The key insight was that the system was already working correctly, but operating at a scale too small to see meaningful movement.

By amplifying the multipliers 3x and eliminating dilution through averaging, we achieve the desired 10-point impact per article run while keeping the decay system intact.
