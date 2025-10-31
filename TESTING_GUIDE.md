# Testing Guide for New Sentiment Scoring System

## Pre-Flight Checks ✅

All checks passed:
- ✅ Python syntax validation (no errors)
- ✅ Django system checks (passed)
- ✅ Import tests (all functions load correctly)
- ✅ Decay function tests (working at new scale)
- ✅ Surprise/credibility calculations (working)

---

## Quick Test (Recommended First)

Run a single analysis to see the new scoring in action:

```bash
python3 manage.py run_nasdaq_sentiment --once
```

### What to Look For:

1. **Article Processing Phase:**
   ```
   📈 PHASE 4: Processing articles with direct market cap weighting
   ```
   - Should show individual ticker scores (amplified range)
   - Check that scores are in the -50 to +50 range (typical)

2. **News Composite Calculation:**
   ```
   📰 News Composite Calculation (Simplified Direct Weighting):
      Decayed previous score: +X.XX
      New article impact (averaged): +X.XX
      Per-run cap applied: ±25
      Final news_composite: +X.XX
   ```
   - New article impact should be in ±25 range (capped)
   - Final news_composite should show meaningful values (not 0.02, 0.24)

3. **Final Composite Score:**
   ```
   🎯 FINAL NASDAQ COMPOSITE SENTIMENT SCORE: +X.XX
   ```
   - Should be more dynamic than before
   - News component should have visible contribution

---

## Full Test (Monitor Over Time)

Run continuously for 2-3 hours to see decay in action:

```bash
python3 manage.py run_nasdaq_sentiment --interval 300
```

### What to Monitor:

1. **First Run (New Articles):**
   - Note the `news_composite` value (e.g., +15.5)
   - Should be significantly higher than old system (0.5-3.0)

2. **Second Run (5 mins later):**
   - Check decay is visible:
     - Old: 0.5 → 0.4 (hard to see)
     - New: 15.5 → 12.7 (clearly visible)

3. **Third Run (30+ mins later):**
   - If no new articles: score should continue decaying
   - If new articles: should see impact of ±10-25 points

4. **Over 2 hours:**
   - Scores should decay toward zero without new articles
   - With periodic news: should see wave pattern (spike → decay → spike)

---

## Validation Checklist

- [ ] Article scores are amplified (check console output shows -50 to +50 range)
- [ ] Per-run cap working (new_article_impact never exceeds ±25)
- [ ] Decay is visible (scores decrease over time without new articles)
- [ ] No database errors (check for "✓ Saved X articles" message)
- [ ] Final composite stays within ±100 (hard cap working)
- [ ] Scores move more than before (-10 to +30 range expected vs old -5 to +5)

---

## Expected Differences

### Console Output Changes:

**Old output:**
```
📈 Company News Composite Sentiment: +1.23
📡 Market News Sentiment: +0.87
📰 News Composite Calculation:
   New articles contribution: +1.05
   Final news_composite: +1.05
```

**New output:**
```
📈 PHASE 4: Processing articles with direct market cap weighting
  AAPL (12.0%): +45.23 | Articles: 10
  MSFT (10.5%): +32.15 | Articles: 8
  ...
  MARKET (30.0%): +28.50 | Articles: 20
📊 Total articles processed: 220

📰 News Composite Calculation (Simplified Direct Weighting):
   New article impact (averaged): +18.42
   Per-run cap applied: ±25
   Final news_composite: +18.42
```

---

## Troubleshooting

### Issue: Scores still look small (0.5, 1.2, etc.)

**Possible causes:**
1. Database has old cached articles with old scoring
   - **Solution**: Run for 24 hours to let cache refresh with new scores

2. Very few articles fetched
   - **Solution**: Check API keys are valid, check market hours

### Issue: Scores too volatile (jumping ±50 per run)

**This should not happen** due to ±25 per-run cap.

**If it does:**
- Check console output for "Per-run cap applied: ±25"
- Verify final cap at ±100 is working
- Report as bug

### Issue: Decay not visible

**Check:**
- Time between runs (needs at least 5 minutes to see decay)
- Starting score magnitude (if score is 0.5, decay to 0.4 is hard to see)

---

## Database Check

After running once, verify the database saved correctly:

```bash
python3 manage.py shell -c "
from api.models import AnalysisRun
run = AnalysisRun.objects.filter(ticker__symbol='^IXIC').latest('timestamp')
print(f'Latest Run:')
print(f'  Timestamp: {run.timestamp}')
print(f'  News Composite: {run.avg_base_sentiment}')
print(f'  Final Composite: {run.composite_score}')
print(f'  Articles: {run.articles_analyzed} ({run.new_articles} new, {run.cached_articles} cached)')
"
```

**Expected:**
- `avg_base_sentiment` should be in ±25 range (not 0.02)
- `composite_score` should be in ±30 range (not ±5)

---

## Performance Check

The changes are computational only, so performance should be identical:

```bash
time python3 manage.py run_nasdaq_sentiment --once
```

**Expected:** Same execution time as before (±0-2 seconds difference).

---

## Rollback (If Needed)

If critical issues arise:

```bash
# View changes
git diff HEAD -- api/management/commands/run_nasdaq_sentiment.py

# Revert to previous version
git checkout HEAD -- api/management/commands/run_nasdaq_sentiment.py
```

**No database migration needed** - changes are computational only.

---

## Success Criteria

✅ System is working correctly if:
1. News composite scores are in ±20-30 range (typical)
2. Decay is clearly visible between runs
3. No database errors
4. Scores respond to news events (visible movement)
5. Per-run cap prevents extreme swings (±25 max per run)
6. Final composite stays within ±100

---

## Next Steps After Testing

If everything looks good:
1. Monitor for 24 hours to ensure stability
2. Check frontend displays scores correctly
3. Compare score movements to actual market events
4. Fine-tune if needed:
   - Adjust per-run cap (currently ±25)
   - Adjust decay rate (currently 3.83% per minute)
   - Adjust article multipliers (currently 250/150/50)

---

## Support

If issues arise, check:
1. [CHANGES_SUMMARY.md](CHANGES_SUMMARY.md) - Detailed explanation of changes
2. [sentiment_scoring_flow.md](sentiment_scoring_flow.md) - Mermaid flowchart
3. Console output for error messages
4. Database for correct score storage

All changes preserve data integrity and can be rolled back without data loss.
