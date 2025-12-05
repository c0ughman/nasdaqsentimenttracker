# November 2025 AnalysisRun Data Export

**Export Date:** November 28, 2025
**Source:** Railway PostgreSQL Database
**Total Records:** 8,826 runs

---

## 📊 Files Exported

### 1. **analysis_runs_november_2025_complete.csv**
Complete November 2025 data with all available runs.

- **Records:** 8,826
- **Date Range:** Nov 2 - Nov 28, 2025
- **Dates with Data:** 22 days
- **Missing Dates:** 5 days (Nov 8, 15, 22, 23, 27)

### 2. **analysis_runs_nov3_to_14_complete_weeks.csv**
Two complete weeks of continuous data.

- **Records:** 4,920
- **Date Range:** Nov 3 - Nov 14, 2025
- **Includes:** Week 1 (Nov 3-7) + Week 2 (Nov 9-14)

### 3. **analysis_runs_nov16_onwards.csv**
Data from Nov 16 to present (after the two complete weeks).

- **Records:** 3,848
- **Date Range:** Nov 16 - Nov 28, 2025
- **Dates:** 10 days

### 4. **analysis_runs_nov16_onwards.json**
Same as #3 but in JSON format with key fields only.

---

## 📅 Data Coverage Summary

### Complete Weeks:
- **Week 1:** Nov 2-7 (6 days, 2,661 runs)
- **Week 2:** Nov 9-14 (6 days, 2,317 runs)
- **Week 3:** Nov 16-21 (6 days, 2,305 runs)

### Additional Days:
- Nov 24-26 (3 days)
- Nov 28 (today)

### Missing Days:
- Nov 8 (weekend gap)
- Nov 15 (missing)
- Nov 22-23 (weekend missing)
- Nov 27 (missing - yesterday)

---

## 🔢 Data Breakdown by Date

```
2025-11-02: 58 runs
2025-11-03: 809 runs
2025-11-04: 445 runs
2025-11-05: 450 runs
2025-11-06: 449 runs
2025-11-07: 450 runs
2025-11-08: MISSING
2025-11-09: 59 runs
2025-11-10: 748 runs
2025-11-11: 390 runs
2025-11-12: 374 runs
2025-11-13: 366 runs
2025-11-14: 380 runs
2025-11-15: MISSING
2025-11-16: 58 runs
2025-11-17: 749 runs
2025-11-18: 390 runs
2025-11-19: 390 runs
2025-11-20: 332 runs
2025-11-21: 386 runs
2025-11-22: MISSING
2025-11-23: MISSING
2025-11-24: 376 runs
2025-11-25: 389 runs
2025-11-26: 389 runs
2025-11-27: MISSING
2025-11-28: 389 runs
```

---

## 📋 CSV Columns (All Files)

1. **Timestamp & Identity:**
   - `timestamp` - ISO 8601 format with timezone

2. **Sentiment Scores:**
   - `composite_score` - Overall composite sentiment
   - `sentiment_label` - BULLISH/NEUTRAL/BEARISH
   - `avg_base_sentiment` - Base sentiment average
   - `avg_surprise_factor` - Surprise factor average
   - `avg_novelty` - Novelty score average
   - `avg_source_credibility` - Source credibility average
   - `avg_recency_weight` - Recency weight average

3. **Stock Price Data:**
   - `stock_price` - Current stock price (QLD)
   - `price_open` - Opening price
   - `price_high` - High price
   - `price_low` - Low price
   - `price_change_percent` - Price change percentage
   - `volume` - Trading volume
   - `qqq_price` - QQQ ETF price

4. **News Analysis:**
   - `articles_analyzed` - Total articles analyzed
   - `cached_articles` - Previously cached articles
   - `new_articles` - New articles in this run

5. **Technical Indicators:**
   - `rsi_14` - Relative Strength Index (14-period)
   - `macd` - MACD line
   - `macd_signal` - MACD signal line
   - `macd_histogram` - MACD histogram
   - `bb_upper` - Bollinger Band upper
   - `bb_middle` - Bollinger Band middle
   - `bb_lower` - Bollinger Band lower
   - `sma_20` - Simple Moving Average (20-period)
   - `sma_50` - Simple Moving Average (50-period)
   - `ema_9` - Exponential Moving Average (9-period)
   - `ema_20` - Exponential Moving Average (20-period)
   - `stoch_k` - Stochastic K
   - `stoch_d` - Stochastic D
   - `williams_r` - Williams %R
   - `atr_14` - Average True Range (14-period)
   - `vxn_index` - VXN Volatility Index
   - `technical_composite_score` - Technical composite score

6. **Reddit Sentiment:**
   - `reddit_sentiment` - Reddit sentiment score
   - `reddit_posts_analyzed` - Reddit posts analyzed
   - `reddit_comments_analyzed` - Reddit comments analyzed

7. **Analyst Recommendations:**
   - `analyst_recommendations_score` - Analyst recommendation score
   - `analyst_recommendations_count` - Total analyst recommendations
   - `analyst_strong_buy` - Strong buy count
   - `analyst_buy` - Buy count
   - `analyst_hold` - Hold count
   - `analyst_sell` - Sell count
   - `analyst_strong_sell` - Strong sell count

---

## 🎯 Recommended Usage

### For Complete Week Analysis:
Use `analysis_runs_nov3_to_14_complete_weeks.csv` - contains two complete, continuous weeks.

### For Recent Data Analysis:
Use `analysis_runs_nov16_onwards.csv` or `.json` - contains the most recent data from Nov 16 to present.

### For Full Month Analysis:
Use `analysis_runs_november_2025_complete.csv` - contains all available November data.

---

## ⚠️ Important Notes

1. **Missing Data**: The 5 missing dates (Nov 8, 15, 22, 23, 27) represent days when the analysis system was not running. This data cannot be retrieved retroactively.

2. **Run Frequency**: Run counts vary significantly:
   - High activity days: 700-800+ runs (likely every 1-2 minutes)
   - Moderate activity: 350-450 runs (every 3-4 minutes)
   - Low activity days: ~60 runs (startup/shutdown or partial day)

3. **Data Quality**:
   - Complete weeks (Nov 3-7, 9-14, 16-21) have consistent run frequencies
   - Partial days (Nov 2, 9, 16) likely represent system startup
   - Nov 28 data is ongoing (389 runs as of export time)

4. **Timezone**: All timestamps are in UTC.

---

## 🔄 To Refresh Data

To get updated data including the rest of today (Nov 28), re-run the export commands with:

```bash
export USE_SQLITE=False
export DATABASE_URL="postgresql://postgres:geMAFuUfpPSgoJNQbQTCRbGeAJOByIYk@interchange.proxy.rlwy.net:39925/railway"
python3 manage.py shell
# Then run the export script
```

---

**Generated:** November 28, 2025
**Database:** Railway PostgreSQL
**Ticker:** QLD (ProShares Ultra QQQ 2x Leveraged NASDAQ-100 ETF)
