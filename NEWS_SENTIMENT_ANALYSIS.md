# 📰 News Sentiment Deep Dive Analysis

**Generated:** 2025-11-08 12:37:25

---

## 🎯 Analysis Goals

1. Compare news sentiment between Thursday/Friday vs earlier in the week
2. Identify if news sentiment has predictive power
3. Compare news vs technical vs composite indicators
4. Discover best news-based trading patterns

---

## 📊 Daily News Sentiment Comparison

| Day | Records | Avg News | Std | News UP Changes | News DOWN Changes |
|-----|---------|----------|-----|-----------------|-------------------|
| Monday | 809 | 20.41 | 23.74 | 31 | 345 |
| Tuesday | 445 | 36.18 | 22.15 | 25 | 355 |
| Wednesday | 450 | 39.61 | 15.15 | 29 | 412 |
| Thursday | 449 | 37.80 | 21.66 | 27 | 365 |
| Friday | 431 | 1.53 | 39.67 | 163 | 198 |


### Statistical Test: Mon-Wed vs Thu/Fri

- **Mon-Wed Avg News Sentiment**: 29.60
- **Thu/Fri Avg News Sentiment**: 20.04
- **Difference**: -9.56
- **t-statistic**: 8.1066
- **p-value**: 0.0000

✅ **Statistically Significant Difference!** Thu/Fri news sentiment is different from Mon-Wed.

---

## 🏆 Best News Sentiment Patterns

Top 10 news-based prediction patterns:

| Rank | Pattern | Time | Accuracy | Signals |
|------|---------|------|----------|---------|
| 1 | News UP Small | 10min | 87.0% ✅ | 23 |
| 2 | News UP Small | 25min | 87.0% ✅ | 23 |
| 3 | News UP Small | 15min | 82.6% ✅ | 23 |
| 4 | News UP Small | 5min | 60.9% ✅ | 23 |
| 5 | News DOWN Small | 25min | 57.3% ✅ | 143 |
| 6 | News UP Medium | 5min | 56.2% ✅ | 16 |
| 7 | News UP Medium | 10min | 56.2% ✅ | 16 |
| 8 | News UP Medium | 25min | 56.2% ✅ | 16 |
| 9 | News DOWN Small | 15min | 53.1% ⚠️ | 143 |
| 10 | News DOWN Small | 5min | 49.7% ❌ | 143 |


---

## 📊 News vs Technical vs Composite

Predictive power comparison at 15-minute horizon:

### Mon-Wed:

| Indicator | DOWN Accuracy | (n) | UP Accuracy | (n) |
|-----------|--------------|-----|------------|-----|
| News | 46.2% | 1112 | 40.0% | 85 |
| Technical | 50.3% | 185 | 44.2% | 190 |
| Composite | 49.4% | 265 | 39.8% | 171 |


### Thu/Fri:

| Indicator | DOWN Accuracy | (n) | UP Accuracy | (n) |
|-----------|--------------|-----|------------|-----|
| News | 49.2% | 563 | 59.4% | 175 |
| Technical | 57.6% | 132 | 46.8% | 126 |
| Composite | 50.9% | 161 | 50.0% | 134 |


---

## 💡 Key Insights

### 1. Best Indicator by Period:

- **Mon-Wed**: Technical is best for DOWN predictions (50.3% accuracy)
- **Thu/Fri**: Technical is best for DOWN predictions (57.6% accuracy)


### 2. News Sentiment Patterns:

- News sentiment changes (>0.5 points) occur in **75.5%** of records
- Most common news bucket: **Small** (664 signals)
- Best time horizon for news: **25 minutes** (57.6% avg accuracy)


### 3. News vs Overall Best Pattern:

- **Best News Pattern**: UP Small @ 10min
  - Accuracy: 87.0%
  - Sample size: 23

- **Best Overall Pattern (from previous analysis)**: DOWN Small @ 25min
  - Accuracy: 55.9%
  - Sample size: 367

✅ **News-based pattern BEATS overall best!**

### 4. Thursday/Friday vs Mon-Wed:

- Thu/Fri has **statistically significant lower** news sentiment than Mon-Wed
- This suggests end-of-week patterns may be different


---

## 📈 Visualizations

Generated charts in `news_sentiment_charts/`:

1. **1_daily_news_comparison.png** - Daily news sentiment patterns
2. **2_predictive_power_comparison.png** - News vs Technical vs Composite
3. **3_news_predictive_heatmap.png** - News accuracy across time horizons
4. **4_intraday_news_patterns.png** - Minute-by-minute news patterns each day
5. **5_news_summary.png** - Best news patterns summary

---

## 🚀 Trading Implications


### ❌ Composite Score is Better

Composite score (50.0%) outperforms news-only predictions (47.2%).

**Recommendation**: Continue using composite score, news alone is not sufficient.


---

## ⚠️ Important Notes

1. **Statistical Significance**: No news patterns are statistically proven (need 30+ days)
2. **Sample Sizes**: Many news patterns have <20 signals (unreliable)
3. **News Frequency**: News changes rarely (only 75.5% of records)
4. **News Lag**: News sentiment may be lagging indicator (processes past events)

---

*Generated: 2025-11-08 12:37:25*
